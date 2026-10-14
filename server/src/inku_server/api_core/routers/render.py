"""Current render routes and compatibility request/response contracts."""

from __future__ import annotations

import itertools
import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from hashlib import sha256
from typing import Literal

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, computed_field, field_validator

from ... import db as _db
from ... import pipeline_compat as _pipeline_compat
from ...autonomous_refine import ALLOWED_KINDS as AUTONOMOUS_REFINE_KINDS, vision_refine_advice
from ...limits import limits_as_dict
from ...color_arrangements import ColorArrangements
from ... import ground_variants as _ground
from ...color_catalogs import get_color_catalog, render_color_map_for_catalog
from ...saved_score_compat import coerce_saved_score
from ...schema import Score
from ..common import DESCRIPTION_LOCKED_DETAIL, _resolve_instruction_lang, _resolved_vision_model, _unexpected_http_error
from ..vision import chatgpt_vision_error, prepare_vision_settings
from ...chatgpt_store import ChatGPTError
from ..deps import _current_user
from ..models import CompositionRanges, JsonSeed, RecompositionResult
from ..rendering import (
    COLOR_CATALOG_ID_HEADER,
    COLOR_SOURCE_HEADER,
    LIMITS_SOURCE_HEADER,
    _COMPACT_SCORE_VERSIONS,
    _color_render_metadata,
    _limits_for_render,
    _render_hash_metadata,
    _render_score_svg,
    _render_seed_from_text,
    _render_with_metadata,
    _score_canvas_aspect_value,
    _score_with_canvas,
    _validated_canvas_aspect_override,
    _work_for_color_snapshot,
)


_logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(_current_user)])


@router.get("/api/composition/ranges", response_model=CompositionRanges)
def composition_ranges() -> CompositionRanges:
    return _pipeline_compat.composition_ranges()


_LIMITS_FIELD_DESCRIPTION = (
    "Draw under these limits instead of the installation's settings. Missing keys "
    "keep their default, and each value is capped at today's setting -- a request "
    "can only lower a limit, never raise one. Omitted means the work's own "
    "recorded limits (when a work_id is given) or today's settings."
)

class ComposeRequest(BaseModel):
    ddl: str = Field(..., min_length=1, max_length=100_000, description="正規化DDL テキスト")
    model: str | None = Field(
        default=None, description="Stage 2 モデル名 (未指定時は利用者の Stage 2 既定)"
    )
    description: str | None = Field(default=None, max_length=100_000, description="作者が書いた記述 (省略可)")
    instruction_lang: str = Field(default="auto", description="指示文言語 (auto / ja / en)")
    ui_lang: str | None = Field(default=None, description="UI表示言語")
    color_map: dict[str, str] | None = Field(default=None, description="Deprecated: ignored; catalog_id is resolved server-side")
    catalog_id: str | None = Field(default=None, description="使用するサーバー側色カタログID")
    canvas_aspect: str | None = Field(default=None, description="Canvas aspect plugin selection")
    auto_repair: bool = Field(default=True, description="Deprecated compatibility field; ignored")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    composition_seed: int | None = Field(default=None, description="Composition seed for shared-pipeline layout; omitted means the placement follows the performance seed")
    recompose_mode: Literal["principled", "chance"] | None = Field(
        default=None,
        description="Choose the saved DDL's numeric ranges again; omission keeps the existing rebuild",
    )
    interpretation_seed: str | None = Field(default=None, description="Opaque identifier for an explicit Stage 1 re-interpretation")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")
    fires_on: str | None = Field(
        default=None,
        max_length=200,
        description="Deprecated compatibility field; ignored",
    )
    imported_plugins: list[dict] | None = Field(
        default=None,
        max_length=64,
        description="DDL書き出し(inku.ddl-export.v1)が運ぶプラグイン定義。この新しい作品だけで使う",
    )
    # Stage 0.5: this endpoint starts at Stage 2, so it never runs 0.5 itself.
    # A caller that already has a sketch text (a candidate, a replay) passes it
    # here and it stands in for the description everywhere the description went.
    sketch_text: str | None = Field(default=None, max_length=100_000, description="写生層 (Stage 0.5) の出力。与えられたら記述の代わりに後段へ渡る")
    sketch_grain: str | None = Field(default=None, pattern="^(fine|coarse)$", description="写生の区切り fine / coarse (記録・再現用。この経路では 0.5 を呼ばない)")
    work_id: str | None = Field(
        default=None,
        description="Id of the saved work being drawn again; the run forks from it with its saved settings and seeds",
    )
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    derivation_metadata: dict[str, object] = Field(default_factory=dict)


class ComposeResponse(BaseModel):
    ddl: str
    recomposition: RecompositionResult | None = None
    # The committed pipeline document, also used when this work is saved.
    plugin_provenance: list[dict[str, str]] = Field(default_factory=list)
    plugin_warnings: list[str] = Field(default_factory=list)
    carriage_warnings: list[str] | None = None  # v1.94 B: 搬送契約の鏡（検査のみ）
    # Score 0.10 is the shared core's opaque delivery document. Compatibility
    # routes must not expand or coerce it through the retired Python model.
    score: dict
    svg: str
    stage2_model: str | None = None
    stage2_prompt_digest: str | None = None
    ddl_version: str | None = None
    ddl_engine_version: str | None = None
    render_build_number: str | None = None
    render_color_profile: dict[str, str] | None = None
    render_engine_id: str | None = None
    render_engine_version: str | None = None
    # The limits that governed this work. Present only when the row recorded
    # them; absent means "drawn before they were recorded", not "the defaults".
    render_limits: dict[str, int] | None = None
    # Which of the four sources those numbers came from. `render_limits` says
    # what was used, not whether a redraw replayed the work's own ceiling or ran
    # at today's setting -- and the two are different pictures (ledger I-154).
    render_limits_source: str | None = None
    # What the hard ceiling did, when it fired. The first half applied it with
    # nowhere to say so; a work silently reduced from 900 marks to 400 looked
    # like a work that asked for 400.
    render_limit_notes: list[str] | None = None
    render_hash: str | None = None
    render_hash_short: str | None = None
    render_color_catalog_id: str | None = None
    render_color_catalog_name: str | None = None
    render_color_catalog_sub: str | None = None
    render_color_map: dict[str, str] | None = None
    render_canvas_aspect: str | None = None
    render_canvas_aspect_id: str | None = None
    render_canvas_aspect_ratio: float | None = None
    render_seed: JsonSeed | None = None
    render_wild: bool | None = None
    composition_seed: JsonSeed | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None
    instruction_lang_requested: str | None = None
    instruction_lang_resolved: str | None = None
    ui_lang: str | None = None
    elapsed_ms: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    retry_count: int = 0
    retry_reasons: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    coerce_relation_input_count: int = 0
    coerce_relation_output_count: int = 0
    coerce_relation_dropped_count: int = 0
    coerce_relation_drop_rate: float | None = None
    coerce_warnings: list[str] = Field(default_factory=list)
    coerce_branch_counts: dict[str, int] = Field(default_factory=dict)
    sketch_text: str | None = None
    sketch_grain: str | None = None
    # This route saves nothing itself: the client saves what it drew through
    # POST /api/history, so the state has to travel back with the drawing or
    # the row it writes has no record of the layer at all.
    sketch_state: str | None = None
    pipeline_variation_id: str | None = None
    pipeline_execution_id: str | None = None
    pipeline_revision: str | None = None
    compiler_outcome: str | None = None
    pipeline_diagnostics: dict[str, object] | None = None


class InterpretRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=100_000, description="作者が書いた記述")
    stage1_input: str | None = Field(default=None, max_length=100_000, description="Stage 1 が実際に読む文字列 (記述に文脈を注入したもの)。省略時は description")
    sketch: bool = Field(default=False, description="写生層 (Stage 0.5) を通すか")
    sketch_text: str | None = Field(default=None, max_length=100_000, description="既にある写生文。与えられたら 0.5 を呼び直さずこれを使う")
    sketch_grain: str | None = Field(default=None, pattern="^(fine|coarse)$", description="写生の区切り fine (既定・細かく区切る) / coarse (大きく区切る)")
    model: str | None = Field(
        default=None, description="Stage 1 モデル名 (未指定時は利用者の Stage 1 既定)"
    )
    include_thinking: bool = Field(
        default=False, description="qwen3 の <think> 内容を別フィールドで返すか"
    )
    instruction_lang: str = Field(default="auto", description="指示文言語 (auto / ja / en)")
    ui_lang: str | None = Field(default=None, description="UI表示言語")
    expand_intermediate: bool = Field(default=False, description="Deprecated compatibility field; ignored")

    @field_validator("description")
    @classmethod
    def _validate_description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description cannot be blank")
        return v


class PaintRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=100_000, description="作者が書いた記述")

    @field_validator("description")
    @classmethod
    def _validate_description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description cannot be blank")
        return v
    stage1_input: str | None = Field(default=None, max_length=100_000, description="Stage 1 が実際に読む文字列 (記述に文脈を注入したもの)。省略時は description")
    stage1_model: str | None = Field(default=None, description="Stage 1 モデル名")
    stage2_model: str | None = Field(default=None, description="Stage 2 モデル名")
    include_thinking: bool = Field(default=False, description="Stage 1 の思考を返すか")
    instruction_lang: str = Field(default="auto", description="指示文言語 (auto / ja / en)")
    ui_lang: str | None = Field(default=None, description="UI表示言語")
    color_map: dict[str, str] | None = Field(default=None, description="Deprecated: ignored; catalog_id is resolved server-side")
    canvas_aspect: str | None = Field(default=None, description="Canvas aspect plugin selection")
    save_history: bool = Field(default=False, description="描画結果を履歴に保存するか")
    save_artifacts: bool | None = Field(default=None, description="SVG/JSON/PNG などの副産物ファイルを保存するか")
    count_generation: bool = Field(default=True, description="完了した描画をユーザーの累積生成数に加算するか")
    history_input: str | None = Field(default=None, description="履歴に表示するユーザー記述")
    history_at: int | None = Field(default=None, description="履歴保存時刻")
    history_source_text: str | None = Field(default=None, description="作者が書いたラベルなしの履歴本文")
    history_display_label: str | None = Field(default=None, description="バッチ番号やdemoなどの表示ラベル")
    batch_line_number: int | None = None
    batch_run_id: str | None = None
    history_visibility: str = "normal"
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    derivation_metadata: dict[str, object] = Field(default_factory=dict)
    catalog_id: str | None = Field(default=None, description="使用する色カタログID。auto では失敗時の落とし先、random では除外する直前ID")
    catalog_mode: Literal["fixed", "auto", "random"] = Field(default="fixed", description="色カタログの決め方。fixed=catalog_id をそのまま使う / auto=記述を読んでサーバーが選ぶ / random=catalog_id 以外から抽選 (推敲専用)")
    auto_repair: bool = Field(default=True, description="Deprecated compatibility field; ignored")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    composition_seed: int | None = Field(default=None, description="Composition seed: it re-salts the intermediate expansion (Stage 1.5) and, from render engine 23, decides where the renderer places the marks; omitted means the placement follows the performance seed")
    interpretation_seed: str | None = Field(default=None, description="Opaque identifier for an explicit Stage 1 re-interpretation")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")
    # The sketch. Carried per request, the way render_seed is: it is an
    # option of one drawing, not a setting of the user.
    sketch: bool = Field(default=False, description="写生を通すか（場所の広がりと季節・時刻の光を記述の横に補う）。既定は通さない")
    sketch_text: str | None = Field(default=None, max_length=100_000, description="既にある写生文 (作者が直した / 保存済み作品の再演)。与えられたら写生を呼び直さない")
    sketch_grain: str | None = Field(default=None, pattern="^(fine|coarse)$", description="旧写生層の区切り（保存互換のみ。新しい写生では使わない）")
    limits: dict[str, int] | None = Field(default=None, description=_LIMITS_FIELD_DESCRIPTION)


class PaintResponse(BaseModel):
    description: str
    ddl: str
    # The committed pipeline document, also used when this work is saved.
    plugin_provenance: list[dict[str, str]] = Field(default_factory=list)
    plugin_warnings: list[str] = Field(default_factory=list)
    carriage_warnings: list[str] | None = None  # v1.94 B: 搬送契約の鏡（検査のみ）
    thinking: str | None = None
    score: dict
    svg: str
    stage1_model: str | None = None
    stage2_model: str | None = None
    stage1_prompt_digest: str | None = None
    stage1_prompt_base_digest: str | None = None
    stage2_prompt_digest: str | None = None
    ddl_version: str | None = None
    ddl_engine_version: str | None = None
    render_build_number: str | None = None
    render_color_profile: dict[str, str] | None = None
    render_engine_id: str | None = None
    render_engine_version: str | None = None
    render_color_catalog_id: str | None = None
    render_color_catalog_name: str | None = None
    render_color_catalog_sub: str | None = None
    render_color_map: dict[str, str] | None = None
    render_canvas_aspect: str | None = None
    render_canvas_aspect_id: str | None = None
    render_canvas_aspect_ratio: float | None = None
    render_seed: JsonSeed | None = None
    render_wild: bool | None = None
    composition_seed: JsonSeed | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None
    instruction_lang_requested: str | None = None
    instruction_lang_resolved: str | None = None
    ui_lang: str | None = None
    # The limits that governed this work. Present only when the row recorded
    # them; absent means "drawn before they were recorded", not "the defaults".
    render_limits: dict[str, int] | None = None
    # Which of the four sources those numbers came from -- see RenderScoreResponse.
    render_limits_source: str | None = None
    # What the hard ceiling did, when it fired. The first half applied it with
    # nowhere to say so; a work silently reduced from 900 marks to 400 looked
    # like a work that asked for 400.
    render_limit_notes: list[str] | None = None
    render_hash: str | None = None
    render_hash_short: str | None = None
    history_id: str | None = None
    history_at: int | None = None
    description_hash: str | None = None
    lineage_node_id: str | None = None
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    elapsed_stage1_ms: int = 0
    elapsed_stage2_ms: int = 0
    elapsed_total_ms: int = 0
    tokens_in_stage1: int | None = None
    tokens_out_stage1: int | None = None
    tokens_in_stage2: int | None = None
    tokens_out_stage2: int | None = None
    interpret_fallback_used: bool = False
    interpret_fallback_reasons: list[str] = Field(default_factory=list)
    compose_retry_count: int = 0
    compose_retry_reasons: list[str] = Field(default_factory=list)
    compose_fallback_used: bool = False
    user_generation_count: int | None = None
    catalog_id: str | None = None
    coerce_relation_input_count: int = 0
    coerce_relation_output_count: int = 0
    coerce_relation_dropped_count: int = 0
    coerce_relation_drop_rate: float | None = None
    coerce_warnings: list[str] = Field(default_factory=list)
    coerce_branch_counts: dict[str, int] = Field(default_factory=dict)
    sketch_text: str | None = None
    sketch_grain: str | None = None
    sketch_fallback_used: bool = False
    # What was written into the history row for this drawing (section 2.3 of the
    # contract). sketch_fallback_used stays: the flag and the column have
    # different readers, and the flag says nothing about the other four states.
    sketch_state: str | None = None
    pipeline_variation_id: str | None = None
    pipeline_execution_id: str | None = None
    pipeline_revision: str | None = None
    compiler_outcome: str | None = None
    pipeline_diagnostics: dict[str, object] | None = None


class RenderSvgRequest(BaseModel):
    score: dict
    # The work being redrawn. Its own recorded colors decide this render, so a
    # definition that has since changed, been renamed, or been retired does not
    # silently repaint it. Absent means "a new drawing": catalog_id decides.
    work_id: str | None = Field(default=None, description="Id of the work being redrawn; its recorded colors decide this render")
    limits: dict[str, int] | None = Field(default=None, description=_LIMITS_FIELD_DESCRIPTION)
    catalog_id: str | None = None
    canvas_aspect: str | None = None
    svg_profile: str = Field(default="display", description="SVG output profile: display / editable / compat / live")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    composition_seed: int | None = Field(default=None, description="Placement seed for arrangements; omitted means the placement follows the performance seed")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")


class RenderScoreRequest(BaseModel):
    score: dict
    input: str = ""
    ddl: str | None = None
    # Same key, same rule as RenderSvgRequest.
    work_id: str | None = Field(default=None, description="Id of the work being redrawn; its recorded colors decide this render")
    replay_saved_work: bool = Field(default=False, description="Replay the referenced saved work's Score and recorded conditions instead of client conditions")
    limits: dict[str, int] | None = Field(default=None, description=_LIMITS_FIELD_DESCRIPTION)
    catalog_id: str | None = None
    canvas_aspect: str | None = None
    svg_profile: str = Field(default="display", description="SVG output profile: display / editable / compat / live")
    render_seed: int | None = None
    wild: bool = False
    composition_seed: int | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None


class RenderScoreResponse(BaseModel):
    score: Score | dict
    @computed_field
    @property
    def svg_sha256(self) -> str:
        """Bind a save to the exact preview without changing render identity."""
        return sha256(self.svg.encode("utf-8")).hexdigest()

    render_diagnostics: dict | None = None
    # What the core drew around without stopping (an unusable host color); absent when nothing.
    render_warnings: list[dict] | None = None
    resource_execution: dict | None = None
    svg: str
    catalog_id: str
    ddl_version: str
    ddl_engine_version: str
    render_build_number: str
    render_color_profile: dict[str, str]
    render_engine_id: str
    render_engine_version: str
    render_color_catalog_id: str
    render_color_catalog_name: str
    render_color_catalog_sub: str
    render_color_map: dict[str, str]
    render_canvas_aspect: str
    render_canvas_aspect_id: str
    render_canvas_aspect_ratio: float
    render_seed: JsonSeed
    render_wild: bool = False
    composition_seed: JsonSeed | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None
    render_hash: str
    # Which source decided the colors: the work's own snapshot, or today's
    # catalog. A work that predates the snapshot still draws, but not in the
    # colors it was drawn in, and only this field says so.
    render_color_source: str
    # The limits that governed this work. Present only when the row recorded
    # them; absent means "drawn before they were recorded", not "the defaults".
    render_limits: dict[str, int] | None = None
    # Which of the four sources those numbers came from -- see the note above
    # `render_limits` and ledger I-154.
    render_limits_source: str | None = None
    # What the hard ceiling did, when it fired. The first half applied it with
    # nowhere to say so; a work silently reduced from 900 marks to 400 looked
    # like a work that asked for 400.
    render_limit_notes: list[str] | None = None
    render_hash_short: str
    derivation_metadata: dict[str, object] | None = None


class ColorArrangementPlanRequest(BaseModel):
    work_id: str = Field(min_length=1, max_length=200)
    cursor: int = Field(default=0, ge=0, strict=True)


class ColorArrangementRenderRequest(BaseModel):
    work_id: str = Field(min_length=1, max_length=200)
    index: int = Field(ge=0, strict=True)


def _saved_color_arrangements(work: dict) -> tuple[ColorArrangements, dict[str, str], str]:
    catalog_id = work.get("render_color_catalog_id") or work.get("catalog_id")
    color_map = work.get("render_color_map")
    if not isinstance(color_map, dict) or not color_map:
        # Unlike ordinary replay, this action cannot guess a default palette.
        catalog = get_color_catalog(catalog_id) if catalog_id else None
        if catalog is None:
            raise HTTPException(status_code=422, detail="saved color catalog is unknown and has no snapshot")
        catalog_id = catalog["id"]
        color_map = render_color_map_for_catalog(catalog_id)
    if not catalog_id:
        raise HTTPException(status_code=422, detail="saved color catalog is unknown")
    try:
        return ColorArrangements.from_saved(work.get("svg") or "", color_map), color_map, str(catalog_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/api/color-arrangements/plan")
def api_color_arrangement_plan(req: ColorArrangementPlanRequest, actor: dict = Depends(_current_user)) -> dict:
    work = _work_for_color_snapshot(actor, req.work_id)
    arrangements, _, _ = _saved_color_arrangements(work)
    return arrangements.page(req.cursor)


def _render_color_arrangement_for_work(actor: dict, work: dict, index: int) -> RenderScoreResponse:
    arrangements, color_map, catalog_id = _saved_color_arrangements(work)
    try:
        recolored = arrangements.color_map(color_map, index)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    snapshot = {**work, "render_color_map": recolored, "render_color_catalog_id": catalog_id}
    if work.get("render_seed") is None and not work.get("seed_text"):
        raise HTTPException(status_code=422, detail="saved work has no performance seed to preserve its drawing")
    result = _render_authorized_score(RenderScoreRequest(
        score=work["score"], input=work.get("input") or "", ddl=work.get("ddl"),
        catalog_id=catalog_id, canvas_aspect=work.get("render_canvas_aspect_id") or work.get("render_canvas_aspect"),
        render_seed=work.get("render_seed"), composition_seed=work.get("composition_seed"),
        interpretation_seed=work.get("interpretation_seed"), seed_text=work.get("seed_text"),
        wild=bool(work.get("render_wild")),
    ), actor, snapshot)
    result.render_color_source = "color_arrangement"
    result.interpretation_seed = work.get("interpretation_seed")
    result.derivation_metadata = {"color_arrangement_index": index}
    return result


@router.post("/api/render-color-arrangement", response_model=RenderScoreResponse, response_model_exclude_none=True)
def api_render_color_arrangement(req: ColorArrangementRenderRequest, actor: dict = Depends(_current_user)) -> RenderScoreResponse:
    return _render_color_arrangement_for_work(actor, _work_for_color_snapshot(actor, req.work_id), req.index)


class GroundVariantPlanRequest(BaseModel):
    work_id: str = Field(min_length=1, max_length=200)


class GroundVariantRenderRequest(BaseModel):
    work_id: str = Field(min_length=1, max_length=200)
    material: str = Field(min_length=1, max_length=40)


class GroundVariantResponse(RenderScoreResponse):
    # The child's instructions with the new ground sentence.
    ddl: str


@router.post("/api/ground-variants/plan")
def api_ground_variant_plan(req: GroundVariantPlanRequest, actor: dict = Depends(_current_user)) -> dict:
    """Every named support the work is not on, in the saijiki's order."""
    work = _work_for_color_snapshot(actor, req.work_id)
    score = work.get("score") if isinstance(work.get("score"), dict) else {}
    current = _ground.current_material(score)

    def labels(material: str, key: str) -> dict:
        named = material in _ground.GROUND_MATERIALS
        return {f"{key}_ja": _ground.ground_label(material, "ja") if named else None,
                f"{key}_en": _ground.ground_label(material, "en") if named else None}

    return {"current": current, **labels(current, "current_label"),
            "entries": [{"material": material, **labels(material, "label")} for material in _ground.unused_materials(score)]}


def _render_ground_variant_for_work(actor: dict, work: dict, material: str) -> GroundVariantResponse:
    score = work.get("score")
    if not isinstance(score, dict):
        raise HTTPException(status_code=422, detail="saved work has no Score to redraw")
    if material not in _ground.unused_materials(score):
        raise HTTPException(status_code=422, detail="ground must be a named support the work is not on")
    if work.get("render_seed") is None and not work.get("seed_text"):
        raise HTTPException(status_code=422, detail="saved work has no performance seed to preserve its drawing")
    ddl = _ground.ddl_with_ground(work.get("ddl") or "", material, work.get("instruction_lang_resolved"))
    result = _render_authorized_score(RenderScoreRequest(
        score=_ground.score_with_ground(score, material), input=work.get("input") or "", ddl=ddl,
        catalog_id=work.get("render_color_catalog_id") or work.get("catalog_id"),
        canvas_aspect=work.get("render_canvas_aspect_id") or work.get("render_canvas_aspect"),
        render_seed=work.get("render_seed"), composition_seed=work.get("composition_seed"),
        interpretation_seed=work.get("interpretation_seed"), seed_text=work.get("seed_text"),
        wild=bool(work.get("render_wild")),
    ), actor, work)
    result.interpretation_seed = work.get("interpretation_seed")
    result.derivation_metadata = {"ground_material": material, "parent_ground_material": _ground.current_material(score)}
    return GroundVariantResponse(**result.model_dump(), ddl=ddl)


@router.post("/api/render-ground-variant", response_model=GroundVariantResponse, response_model_exclude_none=True)
def api_render_ground_variant(req: GroundVariantRenderRequest, actor: dict = Depends(_current_user)) -> GroundVariantResponse:
    return _render_ground_variant_for_work(actor, _work_for_color_snapshot(actor, req.work_id), req.material)


class VisionRefineAdviceBody(BaseModel):
    history_id: str = Field(..., min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    instruction: str = Field(..., min_length=1, max_length=100_000)
    direction: str = Field(default="", max_length=2000)
    enabled_kinds: list[str] = Field(..., min_length=1, max_length=4)
    language: str = Field(default="ja", pattern="^(ja|en)$")


class VisionRefineAdviceResponse(BaseModel):
    observation: str
    next_direction: str
    suggested_kind: str
    model: str

@router.post("/api/render-score", response_model=RenderScoreResponse, response_model_exclude_none=True)
def api_render_score(req: RenderScoreRequest, actor: dict = Depends(_current_user)) -> RenderScoreResponse:
    # Authorization stays outside the render handler: an unknown work is 404.
    if req.replay_saved_work and not req.work_id:
        raise HTTPException(status_code=422, detail="saved-work replay requires a work id")
    work = _work_for_color_snapshot(actor, req.work_id) if req.work_id else None
    if req.replay_saved_work:
        req = _saved_work_replay_request(work)
    return _render_authorized_score(req, actor, work)


def _saved_work_replay_request(work: dict) -> RenderScoreRequest:
    """Use one server-owned request for a saved replay's preview and child."""
    seed_text = work.get("seed_text")
    if seed_text is not None and not seed_text.strip():
        seed_text = None
    seed = work.get("render_seed")
    return RenderScoreRequest(
        work_id=work["id"], score=work["score"], input=work.get("input") or "", ddl=work.get("ddl"),
        catalog_id=work.get("catalog_id"),
        canvas_aspect=work.get("render_canvas_aspect_id") or work.get("render_canvas_aspect"),
        render_seed=0 if seed is None and seed_text is None else seed,
        seed_text=seed_text, composition_seed=work.get("composition_seed"),
        interpretation_seed=work.get("interpretation_seed"), wild=bool(work.get("render_wild")),
    )


def _render_authorized_score(req: RenderScoreRequest, actor: dict, work: dict | None) -> RenderScoreResponse:
    if req.score.get("version") in _COMPACT_SCORE_VERSIONS:
        from ...pipeline_runtime import get_service
        return RenderScoreResponse(**get_service().replay_for(actor["id"], req.model_dump(), work))
    render_seed, seed_text = _render_seed_from_text(req.seed_text, req.render_seed)
    try:
        # Site 4 of 5. The work is resolved above for its colors; its row also
        # records the limits it was drawn under, and this is the route a redraw
        # comes through (ledger I-154).
        limits, limits_source = _limits_for_render(work, req.limits)
        limit_notes: list[str] = []
        score = coerce_saved_score(
            req.score,
            limits=limits,
            limit_notes=limit_notes,
            lang=_resolve_instruction_lang(req.input, "auto"),
        )
        canvas_aspect = _validated_canvas_aspect_override(req.canvas_aspect)
        if canvas_aspect is not None:
            score = _score_with_canvas(score, canvas_aspect)
        color_metadata, catalog_id, color_source = _color_render_metadata(
            work=work,
            catalog_id=req.catalog_id,
            canvas_aspect=_score_canvas_aspect_value(score),
        )
        render_metadata = {
            **color_metadata,
            "render_seed": render_seed,
            "render_wild": req.wild,
            "composition_seed": req.composition_seed,
            "interpretation_seed": req.interpretation_seed,
            "seed_text": seed_text,
            "render_limits": limits_as_dict(limits),
        }
        svg, render_metadata = _render_with_metadata(
            score, render_metadata, svg_profile=req.svg_profile, owner=actor["id"]
        )
        render_metadata = {
            **render_metadata,
            **_render_hash_metadata(
                input_text=req.input,
                ddl=req.ddl,
                score=score,
                svg=svg,
                catalog_id=catalog_id,
                render_metadata=render_metadata,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("score render", 422) from e
    return RenderScoreResponse(
        score=score,
        svg=svg,
        catalog_id=catalog_id,
        render_color_source=color_source,
        render_limits_source=limits_source,
        render_limit_notes=limit_notes or None,
        **render_metadata,
    )


@router.post("/api/render-svg")
def api_render_svg(req: RenderSvgRequest, actor: dict = Depends(_current_user)) -> Response:
    if req.score.get("version") in _COMPACT_SCORE_VERSIONS:
        from ...pipeline_runtime import get_service
        work = _work_for_color_snapshot(actor, req.work_id) if req.work_id else None
        result = get_service().replay_for(actor["id"], req.model_dump(), work)
        return Response(content=result["svg"], media_type="image/svg+xml; charset=utf-8", headers={
            COLOR_SOURCE_HEADER: result["render_color_source"],
            COLOR_CATALOG_ID_HEADER: result["render_color_catalog_id"],
            LIMITS_SOURCE_HEADER: result["render_limits_source"],
        })
    render_seed, _ = _render_seed_from_text(req.seed_text, req.render_seed)
    work = _work_for_color_snapshot(actor, req.work_id) if req.work_id else None
    try:
        svg, resolved_catalog_id, color_source, limits_source = _render_score_svg(
            req.score,
            catalog_id=req.catalog_id,
            canvas_aspect=req.canvas_aspect,
            svg_profile=req.svg_profile,
            render_seed=render_seed,
            composition_seed=req.composition_seed,
            wild=req.wild,
            work=work,
            requested_limits=req.limits,
            owner=actor["id"],
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("svg render", 422) from e
    # The body of this endpoint is the SVG itself, so the things a caller cannot
    # read off it -- whether it got the work's own colors, and whether it got the
    # work's own limits -- ride here.
    return Response(
        content=svg,
        media_type="image/svg+xml; charset=utf-8",
        headers={
            COLOR_SOURCE_HEADER: color_source,
            COLOR_CATALOG_ID_HEADER: resolved_catalog_id,
            LIMITS_SOURCE_HEADER: limits_source,
        },
    )


def _reader_left(request: Request) -> Callable[[], bool]:
    """Whether the client of a sync route has gone, asked from its worker thread."""
    return lambda: anyio.from_thread.run(request.is_disconnected)


@router.post("/api/compose", response_model=ComposeResponse, response_model_exclude_none=True)
def api_compose(req: ComposeRequest, request: Request, actor: dict = Depends(_current_user)) -> dict:
    """Run the old Stage-2 URL through the shared authority pipeline."""
    return _pipeline_compat.compose(actor["id"], req.model_dump(mode="json"), _reader_left(request))


@router.post("/api/interpret")
def api_interpret(req: InterpretRequest, request: Request, actor: dict = Depends(_current_user)) -> dict:
    """Project the shared pipeline's committed document for old callers."""
    return _pipeline_compat.interpret(actor["id"], req.model_dump(mode="json"), _reader_left(request))


def _refuse_a_description_redraw_of_a_locked_parent(req: "PaintRequest") -> None:
    """These routes draw from the description. A child of a work its DDL holds
    would throw the edited DDL away, so it is refused; the pipeline's fork from
    the description is the way back to the words."""
    if req.lineage_parent_node_id and _db.lineage_node_description_locked(req.lineage_parent_node_id):
        raise HTTPException(status_code=409, detail=DESCRIPTION_LOCKED_DETAIL)


@router.post("/api/paint", response_model=PaintResponse, response_model_exclude_none=True)
def api_paint(
    req: PaintRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> dict:
    _refuse_a_description_redraw_of_a_locked_parent(req)
    return _pipeline_compat.paint(
        actor["id"], req.model_dump(mode="json"), idempotency_key, _reader_left(request)
    )


def _next_or_none(iterator: Iterator[str]) -> str | None:
    return next(iterator, None)


async def _closing_in_threadpool(iterator: Iterator[str]) -> AsyncIterator[str]:
    """Read a blocking generator off the event loop and close it however the
    read ends.

    Starlette's own threadpool reader, on a client disconnect, drops the
    generator and leaves its closing to garbage collection, so the run of a
    reader that had left was cancelled late or never.
    """
    try:
        while (chunk := await anyio.to_thread.run_sync(_next_or_none, iterator)) is not None:
            yield chunk
    finally:
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(iterator.close)


@router.post("/api/paint/stream")
def api_paint_stream(
    req: PaintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> StreamingResponse:
    _refuse_a_description_redraw_of_a_locked_parent(req)
    # The response is committed once the first event is written. Pulling it
    # here lets a refusal before any layer settles (a label-only description,
    # a full pool, a failed Stage 1) reach the client as its HTTP status; a
    # failure after that point arrives as an in-band ``error`` event.
    events = _pipeline_compat.paint_events(
        actor["id"], req.model_dump(mode="json"), idempotency_key
    )
    try:
        first = next(events)
    except StopIteration:
        raise _unexpected_http_error("paint", 500) from None

    def lines() -> Iterator[str]:
        try:
            for event in itertools.chain([first], events):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except HTTPException as e:
            yield json.dumps(
                {"event": "error", "status": e.status_code, "detail": e.detail},
                ensure_ascii=False,
            ) + "\n"
        except Exception as e:  # noqa: BLE001
            _logger.exception("paint stream failed: %s", e)
            yield json.dumps(
                {"event": "error", "status": 500, "detail": "unexpected error"},
                ensure_ascii=False,
            ) + "\n"
        finally:
            # Closing the events cancels a run still going (SPEC §12.10).
            events.close()

    return StreamingResponse(
        _closing_in_threadpool(lines()),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/api/refine/vision-advice", response_model=VisionRefineAdviceResponse)
def api_vision_refine_advice(
    body: VisionRefineAdviceBody,
    actor: dict = Depends(_current_user),
) -> VisionRefineAdviceResponse:
    invalid_kinds = [kind for kind in body.enabled_kinds if kind not in AUTONOMOUS_REFINE_KINDS]
    if invalid_kinds:
        raise HTTPException(status_code=422, detail=f"unsupported refinement kind: {invalid_kinds[0]}")
    items = _db.get_items(actor["id"], [body.history_id])
    if not items:
        raise HTTPException(status_code=404, detail="refinement source not found")
    svg = str(items[0].get("svg") or "")
    if not svg:
        raise HTTPException(status_code=422, detail="refinement source has no image")
    model = _resolved_vision_model(body.model, actor)
    settings = prepare_vision_settings(actor, model, _db.get_model_settings())
    try:
        advice = vision_refine_advice(
            svg=svg,
            instruction=body.instruction,
            direction=body.direction,
            enabled_kinds=body.enabled_kinds,
            model=model,
            language=body.language,
            settings=settings,
        )
    except ChatGPTError as exc:
        raise chatgpt_vision_error(exc) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise _unexpected_http_error("Vision refinement advice", 502) from exc
    return VisionRefineAdviceResponse(**advice)
