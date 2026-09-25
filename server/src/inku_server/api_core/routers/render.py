"""Current render routes and compatibility request/response contracts."""

from __future__ import annotations

import itertools
import json
import logging
import secrets
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ... import db as _db
from ... import pipeline_compat as _pipeline_compat
from ...autonomous_refine import ALLOWED_KINDS as AUTONOMOUS_REFINE_KINDS, vision_refine_advice
from ...limits import limits_as_dict
from ...saved_score_compat import coerce_saved_score
from ...schema import Score
from ..common import _resolve_instruction_lang, _resolved_vision_model, _unexpected_http_error
from ..deps import _current_user
from ..rendering import (
    COLOR_CATALOG_ID_HEADER,
    COLOR_SOURCE_HEADER,
    LIMITS_SOURCE_HEADER,
    _color_render_metadata,
    _limits_for_render,
    _render_hash_metadata,
    _render_score_svg,
    _render_seed_from_text,
    _render_with_metadata,
    _score_canvas_aspect_value,
    _score_with_canvas,
    _validated_canvas_aspect_override,
    _validated_variation_amplitude,
    _work_for_color_snapshot,
)


_logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(_current_user)])

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
    variation_amplitude: str | None = Field(default=None, description="変奏強度 small / medium / large。variation_seed と揃って初めて有効")
    variation_seed: int | None = Field(default=None, description="変奏 (v2.0): どの軸がどう動くかを決める seed。variation_amplitude と揃って初めて有効")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    composition_seed: int | None = Field(default=None, description="Composition seed for shared-pipeline layout; omitted means the placement follows the performance seed")
    interpretation_seed: str | None = Field(default=None, description="Opaque identifier for an explicit Stage 1 re-interpretation")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")
    fires_on: str | None = Field(
        default=None,
        max_length=200,
        description="Deprecated compatibility field; ignored",
    )
    include_trace: bool = Field(default=False, description="各層の RAW 中間生成物を trace として返すか (観測のみ)")
    # Stage 0.5: this endpoint starts at Stage 2, so it never runs 0.5 itself.
    # A caller that already has a sketch text (a candidate, a replay) passes it
    # here and it stands in for the description everywhere the description went.
    sketch_text: str | None = Field(default=None, max_length=100_000, description="写生層 (Stage 0.5) の出力。与えられたら記述の代わりに後段へ渡る")
    sketch_grain: str | None = Field(default=None, pattern="^(fine|coarse)$", description="写生の区切り fine / coarse (記録・再現用。この経路では 0.5 を呼ばない)")
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    derivation_metadata: dict[str, object] = Field(default_factory=dict)


class ComposeResponse(BaseModel):
    ddl: str
    # 入力側 DDL (展開前)。ddl は Stage 2 に渡った展開後。
    source_ddl: str | None = None
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
    render_seed: int | None = None
    render_wild: bool | None = None
    composition_seed: int | None = None
    focus: str | None = None
    variation_amplitude: str | None = None
    variation_seed: int | None = None
    variation_moved_axes: list[dict[str, str]] = Field(default_factory=list)
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
    trace: dict | None = None
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
    variation_amplitude: str | None = Field(default=None, description="変奏強度 small / medium / large。variation_seed と揃って初めて有効")
    variation_seed: int | None = Field(default=None, description="変奏 (v2.0): どの軸がどう動くかを決める seed。variation_amplitude と揃って初めて有効")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    composition_seed: int | None = Field(default=None, description="Composition seed: it re-salts the intermediate expansion (Stage 1.5) and, from render engine 23, decides where the renderer places the marks; omitted means the placement follows the performance seed")
    interpretation_seed: str | None = Field(default=None, description="Opaque identifier for an explicit Stage 1 re-interpretation")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")
    include_trace: bool = Field(default=False, description="各層の RAW 中間生成物を trace として返すか (観測のみ)")
    # The sketch. Carried per request, the way render_seed is: it is an
    # option of one drawing, not a setting of the user.
    sketch: bool = Field(default=False, description="写生を通すか（場所の広がりと季節・時刻の光を記述の横に補う）。既定は通さない")
    sketch_text: str | None = Field(default=None, max_length=100_000, description="既にある写生文 (作者が直した / 保存済み作品の再演)。与えられたら写生を呼び直さない")
    sketch_grain: str | None = Field(default=None, pattern="^(fine|coarse)$", description="旧写生層の区切り（保存互換のみ。新しい写生では使わない）")
    limits: dict[str, int] | None = Field(default=None, description=_LIMITS_FIELD_DESCRIPTION)


class PaintResponse(BaseModel):
    description: str
    ddl: str
    # 入力側 DDL (展開前)。ddl は Stage 2 に渡った展開後。
    source_ddl: str | None = None
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
    render_seed: int | None = None
    render_wild: bool | None = None
    composition_seed: int | None = None
    focus: str | None = None
    variation_amplitude: str | None = None
    variation_seed: int | None = None
    variation_moved_axes: list[dict[str, str]] = Field(default_factory=list)
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
    trace: dict | None = None
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
    svg_profile: str = Field(default="display", description="SVG output profile: display / editable / compat")
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
    limits: dict[str, int] | None = Field(default=None, description=_LIMITS_FIELD_DESCRIPTION)
    catalog_id: str | None = None
    canvas_aspect: str | None = None
    svg_profile: str = Field(default="display", description="SVG output profile: display / editable / compat")
    render_seed: int | None = None
    wild: bool = False
    composition_seed: int | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None


class RenderScoreResponse(BaseModel):
    score: Score | dict
    render_diagnostics: dict | None = None
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
    render_seed: int
    composition_seed: int | None = None
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


class VisionRefineAdviceBody(BaseModel):
    history_id: str = Field(..., min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    instruction: str = Field(..., min_length=1, max_length=100_000)
    direction: str = Field(default="", max_length=2000)
    enabled_kinds: list[str] = Field(..., min_length=1, max_length=5)
    language: str = Field(default="ja", pattern="^(ja|en)$")


class VisionRefineAdviceResponse(BaseModel):
    observation: str
    next_direction: str
    suggested_kind: str
    model: str

class VariationSeedsRequest(BaseModel):
    amplitude: str = Field(..., description="変奏の強度 small / medium / large")
    count: int = Field(default=4, ge=1, le=8, description="採番する候補数")


class VariationSeedsResponse(BaseModel):
    amplitude: str
    seeds: list[int]


@router.post("/api/variation/seeds", response_model=VariationSeedsResponse)
def api_variation_seeds(
    req: VariationSeedsRequest
) -> VariationSeedsResponse:
    """変奏候補の seed を採番する。

    採番をサーバー側に置くのは、seed 空間の管理と重複回避を UI に持ち込まない
    ため（契約 §3.4）。展開は決定的なので、返した seed をそのまま /api/compose
    へ渡せば候補が再現できる。
    """
    amplitude = _validated_variation_amplitude(req.amplitude)
    if amplitude is None:
        raise HTTPException(status_code=422, detail="unknown variation amplitude")
    seeds: list[int] = []
    while len(seeds) < req.count:
        candidate = secrets.randbelow(2**31 - 1) + 1
        if candidate not in seeds:
            seeds.append(candidate)
    return VariationSeedsResponse(amplitude=amplitude, seeds=seeds)

@router.post("/api/render-score", response_model=RenderScoreResponse, response_model_exclude_none=True)
def api_render_score(req: RenderScoreRequest, actor: dict = Depends(_current_user)) -> RenderScoreResponse:
    if req.score.get("version") in {"0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"}:
        from ...pipeline_runtime import get_service
        work = _work_for_color_snapshot(actor, req.work_id) if req.work_id else None
        return RenderScoreResponse(**get_service().replay_for(actor["id"], req.model_dump(), work))
    render_seed, seed_text = _render_seed_from_text(req.seed_text, req.render_seed)
    # Outside the try: a 404 for an unknown work is the answer, not a render
    # failure to be relabelled 422 by the handler below.
    work = _work_for_color_snapshot(actor, req.work_id) if req.work_id else None
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
            score, render_metadata, svg_profile=req.svg_profile
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
    if req.score.get("version") in {"0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"}:
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


@router.post("/api/compose", response_model=ComposeResponse, response_model_exclude_none=True)
def api_compose(req: ComposeRequest, actor: dict = Depends(_current_user)) -> dict:
    """Run the old Stage-2 URL through the shared authority pipeline."""
    return _pipeline_compat.compose(actor["id"], req.model_dump(mode="json"))


@router.post("/api/interpret")
def api_interpret(req: InterpretRequest, actor: dict = Depends(_current_user)) -> dict:
    """Project the shared pipeline's committed document for old callers."""
    return _pipeline_compat.interpret(actor["id"], req.model_dump(mode="json"))


@router.post("/api/paint", response_model=PaintResponse, response_model_exclude_none=True)
def api_paint(
    req: PaintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> dict:
    return _pipeline_compat.paint(
        actor["id"], req.model_dump(mode="json"), idempotency_key
    )


@router.post("/api/paint/stream")
def api_paint_stream(
    req: PaintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> StreamingResponse:
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

    return StreamingResponse(
        lines(),
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
    try:
        advice = vision_refine_advice(
            svg=svg,
            instruction=body.instruction,
            direction=body.direction,
            enabled_kinds=body.enabled_kinds,
            model=_resolved_vision_model(body.model, actor),
            language=body.language,
            settings=_db.get_model_settings(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise _unexpected_http_error("Vision refinement advice", 502) from exc
    return VisionRefineAdviceResponse(**advice)
