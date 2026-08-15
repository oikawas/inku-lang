"""Endpoints for the render group, moved out of api.py unchanged."""

from __future__ import annotations

import itertools
import json
import os
import re
import secrets
import sys
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from ...autonomous_refine import ALLOWED_KINDS as AUTONOMOUS_REFINE_KINDS, vision_refine_advice
from ...color_catalogs import color_catalog_ids
from ...color_selector import select_catalog_id
from ...description_labels import pipeline_description
from ...coerce import (
    coerce_score,
    count_hint_from_ddl,
    enforce_hard_ceiling,
    ensure_renderable_score,
)
from ...composer import _finalize_score, canvas_retry_line, compose
from ...interpreter import _sanitize_placement_words, interpret_detail
from ...languages import expand_intermediate_for_lang
from ...limits import DEFAULT_LIMITS, Limits, limits_as_dict, using_limits
from ...plugins import DOCUMENT_PLUGIN_MANAGER
from ...carriage import carriage_warnings as _carriage_warnings
from ...schema import Score
from ...sketch import (
    DEFAULT_SKETCH_GRAIN,
    SketchDetail,
    build_system_prompt as _sketch_system_prompt,
    normalize_sketch_grain,
    prompt_digest as _sketch_prompt_digest,
    sketch_from_life,
    sketch_state_of,
)
from ... import db as _db
from ..common import _is_qualified_model_id, _normalize_instruction_lang, _normalize_ui_lang, _resolve_instruction_lang, _resolved_vision_model, _unexpected_http_error
from ..deps import _current_user, _logger
from ..rendering import COLOR_CATALOG_ID_HEADER, COLOR_SOURCE_HEADER, _color_render_metadata, _effective_limits, _add_history_item, _output_prefix, _render_hash_metadata, _render_metadata, _render_score_svg, _render_seed_from_text, _render_with_metadata, _resolved_catalog_id, _score_canvas_aspect_value, _score_with_canvas, _submit_history_artifact_save, _validated_canvas_aspect, _validated_canvas_aspect_override, _validated_variation_amplitude, _work_for_color_snapshot
from ..state import _increment_stage_stat, _stage_executor, _stage_slots


router = APIRouter(dependencies=[Depends(_current_user)])


def _provider_failure_detail(operation: str, exc: BaseException | None) -> dict | None:
    """LLM プロバイダ由来の失敗を種別に分けて返す (v1.98)。

    種別が分かるものだけを構造化する。判別できない失敗は None を返し、
    従来どおり `<operation> failed` として扱う。原文メッセージは常に添える。
    """
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        status = getattr(exc, "status_code", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        if isinstance(status, int):
            if status == 410:
                code = "model_gone"
            elif status in (401, 403):
                code = "provider_auth"
            elif status == 429:
                code = "provider_rate_limit"
            else:
                code = "provider_error"
            return {
                "code": code,
                "stage": operation,
                "provider_status": status,
                "message": str(exc),
            }
        exc = exc.__cause__ or exc.__context__
    return None


# A description that is nothing but the author's numbering and bracketed
# comments leaves the drawing nothing to read: the cut in description_labels
# empties it, and every layer below -- Stage 0.5 included -- would then invent
# its subject from an empty string.  A stable sentinel, not a sentence: the web
# turns it into the localized message the way it does for "render capacity is
# full", so the wording stays authored in ja.ts.
_LABEL_ONLY_DESCRIPTION = "description is only labels"


def _stage_http_error(operation: str, status_code: int) -> HTTPException:
    """種別が分かるプロバイダ失敗は構造化し、それ以外は従来の扱いに落とす。"""
    _, exc_value, _ = sys.exc_info()
    detail = _provider_failure_detail(operation, exc_value)
    if detail is not None:
        _logger.warning("%s failed: %s %s", operation, detail["provider_status"], detail["message"])
        return HTTPException(status_code=status_code, detail=detail)
    return _unexpected_http_error(operation, status_code)


def _resolved_stage_model(model: str | None, actor: dict | None, *, stage: str) -> str:
    settings = (actor or {}).get("model_settings") or {}
    provider_key = "stage1_provider" if stage == "stage1" else "stage2_provider"
    model_key = "stage1_model" if stage == "stage1" else "stage2_model"
    default_model = "google/gemma-4-31b-it"
    provider = str(settings.get(provider_key, "nvidia") or "nvidia")
    model_id = str(settings.get(model_key, default_model) or default_model)
    if model:
        requested = str(model).strip()
        if _is_qualified_model_id(requested):
            return requested
        if requested == model_id:
            return f"{provider}:{requested}"
        return requested
    return model_id if _is_qualified_model_id(model_id) else f"{provider}:{model_id}"


def _resolved_stage1_model(model: str | None, actor: dict | None = None) -> str:
    return _resolved_stage_model(model, actor, stage="stage1")


def _resolved_stage2_model(model: str | None, actor: dict | None = None) -> str:
    return _resolved_stage_model(model, actor, stage="stage2")


def _score_with_plugin_instructions(
    score: Score,
    instructions: list[dict],
    *,
    limits: Limits = DEFAULT_LIMITS,
    notes: list[str] | None = None,
) -> Score:
    """展開層の決定的転写 instruction を coerce 後の Score へ合流させる (v1.94 輪1)。

    機械生成の instruction は構築時に確定済みのため coerce の対象にしない。
    自由文由来の instruction 群の後ろへ、展開順のまま連結する。
    """
    if not instructions:
        return score
    data = score.model_dump(by_alias=True)
    data["instructions"] = list(data["instructions"]) + [dict(i) for i in instructions]
    # The ceiling holds here too, and what it drops is recorded: the limits are
    # settings, so no caller can predict the drop, and a drop nobody records is
    # a mark that left the work with no account of where it went.
    return enforce_hard_ceiling(Score.model_validate(data), limits, notes)


def _resolved_paint_catalog_id(catalog_id: str | None, *, mode: str, source_text: str) -> str:
    resolved = _resolved_catalog_id(catalog_id)
    if mode == "auto":
        return select_catalog_id(source_text, fallback_id=resolved)
    if mode == "random":
        # Refinement keeps the draw: "another catalog" exists to see the same
        # description in a different colour, and reading the description would
        # settle on the same catalog every time.
        candidates = [candidate for candidate in color_catalog_ids() if candidate != resolved]
        return secrets.choice(candidates) if candidates else resolved
    return resolved


def _score_relation_count(score: Score | None) -> int:
    if score is None:
        return 0
    return sum(1 for instruction in score.instructions if instruction.relation is not None)


def _coerce_relation_report(before: Score | None, after: Score | None) -> dict[str, object]:
    input_count = _score_relation_count(before)
    output_count = _score_relation_count(after)
    dropped_count = max(0, input_count - output_count)
    warnings = ["relation dropped during coerce validation"] if dropped_count else []
    return {
        "coerce_relation_input_count": input_count,
        "coerce_relation_output_count": output_count,
        "coerce_relation_dropped_count": dropped_count,
        "coerce_relation_drop_rate": round(dropped_count / input_count, 6) if input_count else None,
        "coerce_warnings": warnings,
    }


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
    auto_repair: bool = Field(default=True, description="Stage 2 Score の自動補正を適用するか")
    variation_amplitude: str | None = Field(default=None, description="変奏 (v2.0): 展開層をずらす強度 small / medium / large。variation_seed と揃って初めて有効")
    variation_seed: int | None = Field(default=None, description="変奏 (v2.0): どの軸がどう動くかを決める seed。variation_amplitude と揃って初めて有効")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    composition_seed: int | None = Field(default=None, description="Composition seed: it re-salts the intermediate expansion (Stage 1.5) and, from render engine 23, decides where the renderer places the marks; omitted means the placement follows the performance seed")
    interpretation_seed: str | None = Field(default=None, description="Opaque identifier for an explicit Stage 1 re-interpretation")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")
    fires_on: str | None = Field(
        default=None,
        max_length=200,
        description="展開層の発火だけに使う散文。DDL 直筆の作品に記述を与えないまま、プラグイン語の展開を引き出す",
    )
    include_trace: bool = Field(default=False, description="各層の RAW 中間生成物を trace として返すか (観測のみ)")
    # Stage 0.5: this endpoint starts at Stage 2, so it never runs 0.5 itself.
    # A caller that already has a sketch text (a candidate, a replay) passes it
    # here and it stands in for the description everywhere the description went.
    sketch_text: str | None = Field(default=None, max_length=100_000, description="写生層 (Stage 0.5) の出力。与えられたら記述の代わりに後段へ渡る")
    sketch_grain: str | None = Field(default=None, pattern="^(fine|coarse)$", description="写生の区切り fine / coarse (記録・再現用。この経路では 0.5 を呼ばない)")


class ComposeResponse(BaseModel):
    ddl: str
    # 入力側 DDL (展開前)。ddl は Stage 2 に渡った展開後。
    source_ddl: str | None = None
    plugin_provenance: list[dict[str, str]] = Field(default_factory=list)
    plugin_warnings: list[str] = Field(default_factory=list)
    carriage_warnings: list[str] | None = None  # v1.94 B: 搬送契約の鏡（検査のみ）
    score: Score
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
    expand_intermediate: bool = Field(default=False, description="Stage 1.5 の中間DDL拡張を適用するか")

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
    auto_repair: bool = Field(default=True, description="Stage 2 Score の自動補正を適用するか")
    variation_amplitude: str | None = Field(default=None, description="変奏 (v2.0): 展開層をずらす強度 small / medium / large。variation_seed と揃って初めて有効")
    variation_seed: int | None = Field(default=None, description="変奏 (v2.0): どの軸がどう動くかを決める seed。variation_amplitude と揃って初めて有効")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    composition_seed: int | None = Field(default=None, description="Composition seed: it re-salts the intermediate expansion (Stage 1.5) and, from render engine 23, decides where the renderer places the marks; omitted means the placement follows the performance seed")
    interpretation_seed: str | None = Field(default=None, description="Opaque identifier for an explicit Stage 1 re-interpretation")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")
    include_trace: bool = Field(default=False, description="各層の RAW 中間生成物を trace として返すか (観測のみ)")
    # Stage 0.5 (v2.10). Carried per request, the way render_seed is: it is an
    # option of one drawing, not a setting of the user.
    sketch: bool = Field(default=False, description="写生層 (Stage 0.5) を通すか")
    sketch_text: str | None = Field(default=None, max_length=100_000, description="既にある写生文 (作者が直した / 保存済み作品の再演)。与えられたら 0.5 を呼び直さない")
    sketch_grain: str | None = Field(default=None, pattern="^(fine|coarse)$", description="写生の区切り fine (既定・細かく区切る) / coarse (大きく区切る)")


class PaintResponse(BaseModel):
    description: str
    ddl: str
    # 入力側 DDL (展開前)。ddl は Stage 2 に渡った展開後。
    source_ddl: str | None = None
    plugin_provenance: list[dict[str, str]] = Field(default_factory=list)
    plugin_warnings: list[str] = Field(default_factory=list)
    carriage_warnings: list[str] | None = None  # v1.94 B: 搬送契約の鏡（検査のみ）
    thinking: str | None = None
    score: Score
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


class RenderSvgRequest(BaseModel):
    score: dict
    # The work being redrawn. Its own recorded colors decide this render, so a
    # definition that has since changed, been renamed, or been retired does not
    # silently repaint it. Absent means "a new drawing": catalog_id decides.
    work_id: str | None = Field(default=None, description="Id of the work being redrawn; its recorded colors decide this render")
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
    catalog_id: str | None = None
    canvas_aspect: str | None = None
    svg_profile: str = Field(default="display", description="SVG output profile: display / editable / compat")
    render_seed: int | None = None
    wild: bool = False
    composition_seed: int | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None


class RenderScoreResponse(BaseModel):
    score: Score
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
    # What the hard ceiling did, when it fired. The first half applied it with
    # nowhere to say so; a work silently reduced from 900 marks to 400 looked
    # like a work that asked for 400.
    render_limit_notes: list[str] | None = None
    render_hash_short: str


@dataclass
class InterpretDetail:
    ddl: str
    thinking: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    fallback_used: bool = False
    fallback_reasons: list[str] = field(default_factory=list)
    raw: str | None = None  # trace: サニタイズ前の Stage 1 生 DDL (include_trace 時のみ)
    stage1_prompt_digest: str | None = None
    stage1_prompt_base_digest: str | None = None


@dataclass
class ComposeDetail:
    score: Score
    # ddl は Stage 2 に渡った展開後 DDL。source_ddl は展開前の入力側 (Stage 1 出力
    # またはユーザーが書いた DDL)。v1.98 で trace 限定から常時保持へ昇格。
    ddl: str
    source_ddl: str = ""
    plugin_provenance: list[dict[str, str]] = field(default_factory=list)
    plugin_warnings: list[str] = field(default_factory=list)
    # v1.94 輪1: 展開層が決定的に転写した instruction（coerce を迂回して後段合流）
    plugin_instructions: list[dict] = field(default_factory=list)
    tokens_in: int | None = None
    tokens_out: int | None = None
    retry_count: int = 0
    retry_reasons: list[str] = field(default_factory=list)
    fallback_used: bool = False
    # trace (include_trace 時のみ; ddl は stage15 と同一)
    stage1_ddl_in: str | None = None
    plugin_expanded_ddl: str | None = None
    stage15_ddl: str | None = None
    stage2_raw_attempts: list[dict] | None = None
    # 変奏 (v2.0): 展開層が実際に振った結果。resolved_focus は history.focus の供給源。
    variation_moved_axes: list[dict[str, str]] = field(default_factory=list)
    resolved_focus: str | None = None
    stage2_prompt_digest: str | None = None


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


def _fallback_score_from_ddl(ddl: str, *, lang: str) -> Score:
    """Build a visible deterministic score when Stage 2 returns empty twice."""
    lower = ddl.lower()

    if ("背景を黒" in ddl) or ("fill background with black" in lower):
        background = "black"
        color = "white"
    elif ("背景を赤" in ddl) or ("fill background with red" in lower):
        background = "red"
        color = "black"
    elif ("背景を青" in ddl) or ("fill background with blue" in lower):
        background = "blue"
        color = "white"
    elif ("背景を緑" in ddl) or ("fill background with green" in lower):
        background = "green"
        color = "black"
    else:
        background = "white"
        color = "black"

    if (("白" in ddl) or ("white" in lower)) and background != "white":
        color = "white"
    elif (("青" in ddl) or ("blue" in lower)) and background != "blue":
        color = "blue"
    elif (("赤" in ddl) or ("red" in lower)) and background != "red":
        color = "red"
    elif (("緑" in ddl) or ("green" in lower)) and background != "green":
        color = "green"
    elif (("灰" in ddl) or ("gray" in lower) or ("grey" in lower)) and background != "gray":
        color = "gray"

    if color == background:
        color = "white" if background in {"black", "blue"} else "black"

    weight = "pen"
    if ("ビュラン" in ddl) or ("burin" in lower):
        weight = "burin"
    elif ("ドライポイント" in ddl) or ("drypoint" in lower):
        weight = "drypoint"
    elif ("コンピュータ" in ddl) or ("computer" in lower):
        weight = "computer"
    elif ("ロットリング" in ddl) or ("rotring" in lower):
        weight = "rotring"
    elif ("鉛筆" in ddl) or ("pencil" in lower):
        weight = "pencil"
    elif ("クレヨン" in ddl) or ("crayon" in lower):
        weight = "crayon"
    elif ("チョーク" in ddl) or ("chalk" in lower):
        weight = "chalk"
    elif ("太筆" in ddl) or ("thick-brush" in lower) or ("thick brush" in lower) or ("厚塗り" in ddl):
        weight = "brush_thick"
    elif ("細筆" in ddl) or ("水墨" in ddl) or ("墨" in ddl) or ("fine-brush" in lower) or ("ink" in lower):
        weight = "brush_thin"

    if any(marker in ddl for marker in ("色とりどり", "多色", "赤・青", "赤、青")) or any(
        marker in lower for marker in ("colorful", "multi-color", "multicolor", "red, blue")
    ):
        color_cycle = ["red", "blue", "green", "gray"]
    elif any(marker in ddl for marker in ("春", "花", "蕾", "桜", "温", "陽光")) or any(
        marker in lower for marker in ("spring", "flower", "bud", "warm", "sunlight")
    ):
        color_cycle = ["red", "green", "white"]
        if color == "black":
            color = "red"
    elif any(marker in ddl for marker in ("夜", "月", "水", "雨", "霧", "冷")) or any(
        marker in lower for marker in ("night", "moon", "water", "rain", "mist", "cold")
    ):
        color_cycle = ["blue", "white", "gray"]
        if color == "black":
            color = "blue"
    else:
        color_cycle = []

    if ("雲形" in ddl) or ("cloudform" in lower):
        instruction = {
            "primitive": "cloudform",
            "center": [0.62, 0.36],
            "size": [0.34, 0.22],
            "color": color,
            "weight": weight,
            "note": "fallback from explicit DDL cloudform",
        }
    elif ("三角" in ddl) or ("triangle" in lower) or ("山" in ddl) or ("mountain" in lower):
        instruction = {
            "primitive": "triangle",
            "position": [0.54, 0.22],
            "size": [0.20, 0.18],
            "rotation": -8,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    elif ("弧" in ddl) or ("arc" in lower) or ("crescent" in lower):
        instruction = {
            "primitive": "arc",
            "center": [0.72, 0.32],
            "radius": 0.16,
            "angle_start": 210,
            "angle_end": 330,
            "color": color,
            "weight": weight,
            "note": "fallback from DDL",
        }
    elif ("四角" in ddl) or ("square" in lower) or ("rectangle" in lower) or ("紙片" in ddl) or ("patch" in lower):
        instruction = {
            "primitive": "square",
            "position": [0.62, 0.28],
            "size": [0.18, 0.12],
            "rotation": -12,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    elif ("多角形" in ddl) or ("五角" in ddl) or ("六角" in ddl) or ("polygon" in lower):
        instruction = {
            "primitive": "polygon",
            "center": [0.62, 0.30],
            "radius": 0.13,
            "sides": 6 if ("六角" in ddl or "hexagon" in lower) else 5,
            "rotation": -12,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    elif ("楕円" in ddl) or ("oval" in lower) or ("ellipse" in lower) or ("蕾" in ddl) or ("花びら" in ddl) or ("petal" in lower) or ("bud" in lower):
        instruction = {
            "primitive": "ellipse",
            "center": [0.72, 0.32],
            "size": [0.18, 0.11],
            "rotation": -18,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    elif ("円" in ddl) or ("circle" in lower) or ("moon" in lower) or ("月" in ddl):
        instruction = {
            "primitive": "circle",
            "center": [0.72, 0.32],
            "radius": 0.09,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    else:
        instruction = {
            "primitive": "line",
            "from": [0.16, 0.78],
            "to": [0.84, 0.28],
            "rotation": -8,
            "color": color,
            "weight": weight,
            "note": "fallback from DDL",
        }

    arrangement: dict[str, object] | None = None
    # This builder is handed the language; the reader is told it too, or the
    # fallback for an English description reads counts by the Japanese rules.
    explicit_count = count_hint_from_ddl(ddl, lang=lang)
    if ("散らす" in ddl) or ("点々" in ddl) or ("scatter" in lower) or ("dotted" in lower):
        arrangement = {"count": explicit_count or 11, "layout": "scatter", "margin": 0.18}
    elif ("並べる" in ddl) or ("line up" in lower):
        arrangement = {"count": explicit_count or 3, "layout": "horizontal", "margin": 0.1}
    elif explicit_count and explicit_count > 1:
        arrangement = {"count": explicit_count, "layout": "scatter", "margin": 0.18}

    ma_fallback = _fallback_needs_negative_space_support(ddl)
    if arrangement is not None:
        if ("波打つ軌跡" in ddl) or ("undulating trace" in lower):
            arrangement["path"] = "wave"
        elif ("斜めの帯" in ddl) or ("diagonal band" in lower):
            arrangement["path"] = "diagonal"
        elif ("右半分" in ddl) or ("right half" in lower):
            arrangement["path"] = "right_half"
        elif ("上から下" in ddl) or ("top to bottom" in lower):
            arrangement["layout"] = "vertical"
            arrangement["path"] = "top_to_bottom"
        elif ("左から右" in ddl) or ("left to right" in lower):
            arrangement["layout"] = "horizontal"
            arrangement["path"] = "left_to_right"
        count = int(arrangement.get("count") or 1)
        if count > 120:
            arrangement["count"] = min(count, 120)
            arrangement["density"] = "high" if count >= 300 else "medium"
            arrangement["cluster_count"] = 9 if count >= 300 else 5
            arrangement["fade"] = "directional" if arrangement.get("path") not in (None, "none") else "outward"
            arrangement["preserve_space"] = True
        elif count >= 40:
            arrangement["density"] = "medium"
            arrangement["cluster_count"] = 4
            arrangement["fade"] = "directional" if arrangement.get("path") not in (None, "none") else "outward"
            arrangement["preserve_space"] = True
        if color_cycle:
            arrangement["color_cycle"] = color_cycle
        instruction["arrangement"] = arrangement
    elif ma_fallback:
        instruction["arrangement"] = {
            "count": 3,
            "layout": "scatter",
            "margin": 0.26,
            "density": "low",
            "fade": "outward",
            "preserve_space": True,
        }
    elif color_cycle:
        instruction["note"] = f"{instruction['note']}; palette {'/'.join(color_cycle)}"

    instructions = [instruction]
    if ma_fallback:
        support_color = _fallback_support_color(background, color)
        instructions.append(
            {
                "primitive": "arc",
                "center": [0.28, 0.72],
                "radius": 0.075,
                "angle_start": 25,
                "angle_end": 205,
                "rotation": -18,
                "color": support_color,
                "weight": "silverpoint",
                "note": "fallback negative space support",
                "arrangement": {
                    "count": 3,
                    "layout": "radial",
                    "margin": 0.26,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                },
            }
        )

    return _finalize_score(
        Score.model_validate({"background": background, "instructions": instructions}),
        ddl,
    )


def _fallback_needs_negative_space_support(ddl: str) -> bool:
    lower = ddl.lower()
    return any(
        marker in ddl or marker in lower
        for marker in (
            "余白",
            "間",
            "気配",
            "記憶",
            "忘れ",
            "手紙",
            "新聞紙",
            "紙片",
            "窓",
            "鏡",
            "膜",
            "透明",
            "消え",
            "迷う",
            "漂う",
            "薄い",
            "negative space",
            "presence",
            "memory",
            "forgotten",
            "letter",
            "newspaper",
            "paper",
            "window",
            "mirror",
            "membrane",
            "transparent",
            "fade",
            "fading",
            "wander",
            "drift",
            "thin",
        )
    )


def _fallback_support_color(background: str, main_color: str) -> str:
    for color in ("gray", "blue", "red", "black", "white"):
        if color != background and color != main_color:
            return color
    return "white" if background in {"black", "blue"} else "black"


def _compose_retry_reason(score: Score, *, tokens_out: int | None, elapsed_ms: int) -> str:
    if not score.instructions:
        return "empty_instructions"
    return "none"


def _should_retry_compose_result(score: Score, *, tokens_out: int | None, elapsed_ms: int) -> bool:
    return _compose_retry_reason(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms) != "none"


def _compose_retry_prompt(*, reason: str, lang: str, canvas_aspect: str | None = None) -> str:
    canvas_line = canvas_retry_line(canvas_aspect, lang)
    if lang == "en":
        return (
            "# Compact Stage 2 retry\n"
            f"The previous Stage 2 result was invalid or inefficient: {reason}.\n"
            f"{canvas_line}"
            "Submit a valid Score through the submit_score tool.\n"
            "Required: instructions must contain 1-5 drawable items.\n"
            "Allowed primitives: line, circle, ellipse, triangle, square, polygon, arc, cloudform.\n"
            "Allowed colors: white, black, blue, red, green, gray.\n"
            "For repeated marks in the same placement, use one instruction with arrangement instead of many instructions. Groups with different counts or placements may use separate instructions.\n"
            "Do not draw humans, faces, or animals as objects; convert them to abstract presence, weight, spacing, symmetry, or gaze pressure.\n"
            "Do not add unspecified helper lines or helper shapes. Apply adjectives and motion words to the requested primitive.\n"
            "Keep the result compact and do not restate the DDL."
        )
    return (
        "# 空描画リトライ / コンパクト描画リトライ\n"
        f"直前の Stage 2 出力は無効または非効率: {reason}。\n"
        f"{canvas_line}"
        "submit_score tool で有効な Score を提出する。\n"
        "必須: instructions には描画可能な命令を1〜5個入れる。空配列は禁止。\n"
        "使用できる primitive: line, circle, ellipse, triangle, square, polygon, arc, cloudform。\n"
        "使用できる color: white, black, blue, red, green, gray。\n"
        "同一配置の繰り返し図形は複数 instruction にせず、1 instruction + arrangement で表す。個数や配置が異なる群は別 instruction でよい。\n"
        "人・顔・動物を対象物として描かず、存在感、重心、余白、対称性、視線圧として抽象化する。\n"
        "未指定の補助線・補助図形を追加しない。形容・動作語は指定された primitive へ適用する。\n"
        "DDLを説明し直さず、JSONを短く保つ。"
    )


def _call_compose_detail(
    ddl: str,
    *,
    model: str | None = None,
    original_description: str | None = None,
    plugin_seed_text: str | None = None,
    # v2.14: prose that decides only WHETHER a plugin fires. A work authored
    # straight in DDL has no description and must not be given one to make a
    # plugin expand -- the description is the work's origin, not a switch.
    plugin_fires_on: str | None = None,
    system_prompt: str | None = None,
    lang: str = "ja",
    composition_seed: int | None = None,
    include_trace: bool = False,
    focus: str | None = None,
    variation_amplitude: str | None = None,
    variation_seed: int | None = None,
    limits: Limits = DEFAULT_LIMITS,
    # The support this work will be drawn on, already settled. The raw request
    # field is not accepted here: `None` there means "square", and a second
    # place deciding that default is a second place to get it wrong.
    canvas_aspect: str | None = None,
) -> ComposeDetail:
    stage1_ddl_in = ddl  # trace: Stage 1 output before plugin expansion
    # Two arguments of one call with different jobs: `source_text` is the prose
    # and decides WHETHER a plugin fires; `seed_text` is never read as language
    # and is only hashed, so it has to be the description -- the one string that
    # is stable across repetitions and bound to the identity of the work.
    plugin_expansion = DOCUMENT_PLUGIN_MANAGER.expand(
        ddl,
        source_text=plugin_fires_on or original_description,
        lang=lang,
        seed_text=plugin_seed_text or ddl,
    )
    plugin_expanded_ddl = plugin_expansion.ddl  # trace: after plugin expansion
    variation_report: dict = {}
    ddl = expand_intermediate_for_lang(
        plugin_expansion.ddl,
        lang=lang,
        context_text=original_description,
        composition_seed=composition_seed,
        plugin_instructions_present=bool(plugin_expansion.instructions),
        focus=focus,
        variation_amplitude=variation_amplitude,
        variation_seed=variation_seed,
        variation_report=variation_report,
    )
    stage15_ddl = ddl  # trace: Stage 1.5 output = Stage 2 input (== ComposeDetail.ddl)
    plugin_provenance = list(plugin_expansion.provenance)
    plugin_warnings = list(plugin_expansion.warnings)
    plugin_instructions = list(
        getattr(plugin_expansion, "score_instructions", plugin_expansion.instructions)
    )
    retry_count = 0
    retry_reasons: list[str] = []
    fallback_used = False
    attempts: list[dict] = [] if include_trace else []
    prompt_metadata: dict[str, str] = {}

    def _detail_fields() -> dict:
        fields: dict = {
            "source_ddl": stage1_ddl_in,
            "variation_moved_axes": list(variation_report.get("moved_axes") or []),
            "resolved_focus": variation_report.get("resolved_focus"),
            "stage2_prompt_digest": prompt_metadata.get("stage2_prompt_digest"),
        }
        if include_trace:
            fields.update(
                {
                    "plugin_expanded_ddl": plugin_expanded_ddl,
                    "stage15_ddl": stage15_ddl,
                    "stage2_raw_attempts": attempts,
                    "stage1_ddl_in": stage1_ddl_in,
                }
            )
        return fields

    def _record_fallback_attempt() -> None:
        if include_trace:
            attempts.append(
                {"attempt": len(attempts) + 1, "raw_text": None, "parse_ok": None, "fallback": True}
            )

    def invoke(prompt: str | None) -> tuple[Score, int | None, int | None, int]:
        started = time.perf_counter()
        sink: list[dict] | None = [] if include_trace else None

        def run_compose():
            kwargs: dict = {
                "model": model,
                "system_prompt": prompt,
                "lang": lang,
                "prompt_metadata": prompt_metadata,
                # The prompt states these numbers, so it is built from the same
                # limits coerce will apply to the answer.
                "limits": limits,
                # ... and the same support the renderer will draw the answer on.
                "canvas_aspect": canvas_aspect,
            }
            if sink is not None:  # only when tracing: keep the no-trace call byte-identical
                kwargs["trace_sink"] = sink
            try:
                return compose(ddl, **kwargs)
            except TypeError as e:
                if "unexpected keyword argument" not in str(e):
                    raise
                kwargs.pop("prompt_metadata", None)
                try:
                    return compose(ddl, **kwargs)
                except TypeError as retry_error:
                    if "unexpected keyword argument" not in str(retry_error):
                        raise
                return compose(ddl, model=model)

        value = _run_with_hard_timeout(
            "stage2",
            _hard_timeout_seconds("INKU_STAGE2_HARD_TIMEOUT_SECONDS"),
            run_compose,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if include_trace:
            raw = sink[-1] if sink else {"raw_text": None, "parse_ok": None}
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "raw_text": raw.get("raw_text"),
                    "parse_ok": raw.get("parse_ok"),
                    "fallback": False,
                }
            )
        if isinstance(value, tuple):
            return value[0], value[1], value[2], elapsed_ms
        return value, None, None, elapsed_ms

    try:
        score, tokens_in, tokens_out, elapsed_ms = invoke(system_prompt)
    except StageHardTimeoutError:
        _record_fallback_attempt()
        return ComposeDetail(
            score=_fallback_score_from_ddl(ddl, lang=lang),
            ddl=ddl,
            retry_reasons=["stage2_hard_timeout"],
            fallback_used=True,
            plugin_provenance=plugin_provenance,
            plugin_instructions=plugin_instructions,
            plugin_warnings=plugin_warnings,
            **_detail_fields(),
        )
    if score.instructions and not _should_retry_compose_result(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms):
        return ComposeDetail(
            score=score,
            ddl=ddl,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            plugin_provenance=plugin_provenance,
            plugin_instructions=plugin_instructions,
            plugin_warnings=plugin_warnings,
            **_detail_fields(),
        )

    reason = _compose_retry_reason(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms)
    retry_count += 1
    retry_reasons.append(reason)
    try:
        retry_score, retry_tokens_in, retry_tokens_out, _retry_elapsed_ms = invoke(
            _compose_retry_prompt(reason=reason, lang=lang, canvas_aspect=canvas_aspect)
        )
    except StageHardTimeoutError:
        fallback_used = True
        retry_reasons.append("stage2_retry_hard_timeout")
        retry_score = _fallback_score_from_ddl(ddl, lang=lang)
        retry_tokens_in = None
        retry_tokens_out = None
        _record_fallback_attempt()
    if retry_tokens_in is not None:
        tokens_in = (tokens_in or 0) + retry_tokens_in
    if retry_tokens_out is not None:
        tokens_out = (tokens_out or 0) + retry_tokens_out
    if not retry_score.instructions:
        fallback_used = True
        retry_reasons.append("fallback_after_empty_retry")
        retry_score = _fallback_score_from_ddl(ddl, lang=lang)
        if include_trace and attempts:
            attempts[-1]["fallback"] = True
    return ComposeDetail(
        score=retry_score,
        ddl=ddl,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        retry_count=retry_count,
        retry_reasons=retry_reasons,
        fallback_used=fallback_used,
        plugin_provenance=plugin_provenance,
            plugin_instructions=plugin_instructions,
        plugin_warnings=plugin_warnings,
        **_detail_fields(),
    )


def _call_interpret_detail(
    text: str,
    *,
    model: str | None = None,
    include_thinking: bool = False,
    system_prompt_prefix: str | None = None,
    lang: str = "ja",
    include_trace: bool = False,
    limits: Limits = DEFAULT_LIMITS,
) -> InterpretDetail:
    trace_sink: list[str] | None = [] if include_trace else None
    prompt_metadata: dict[str, str] = {}

    def run_interpret():
        kwargs: dict = {
            "model": model,
            "include_thinking": include_thinking,
            "system_prompt_prefix": system_prompt_prefix,
            "lang": lang,
            "prompt_metadata": prompt_metadata,
            # Stage 1 names the same ceilings; same reason as Stage 2.
            "limits": limits,
        }
        if trace_sink is not None:  # only when tracing: keep the no-trace call byte-identical
            kwargs["trace_sink"] = trace_sink
        try:
            return interpret_detail(text, **kwargs)
        except TypeError as e:
            if "unexpected keyword argument" not in str(e):
                raise
            kwargs.pop("prompt_metadata", None)
            try:
                return interpret_detail(text, **kwargs)
            except TypeError as retry_error:
                if "unexpected keyword argument" not in str(retry_error):
                    raise
            return interpret_detail(text, model=model, include_thinking=include_thinking)

    try:
        value = _run_with_hard_timeout(
            "stage1",
            _hard_timeout_seconds("INKU_STAGE1_HARD_TIMEOUT_SECONDS"),
            run_interpret,
        )
    except StageHardTimeoutError:
        return InterpretDetail(
            ddl=_fallback_ddl_from_text(text, lang=lang),
            fallback_used=True,
            fallback_reasons=["stage1_hard_timeout"],
        )
    raw = trace_sink[-1] if trace_sink else None
    if len(value) == 4:
        ddl, thinking, tokens_in, tokens_out = value
    else:
        ddl, thinking = value
        tokens_in = None
        tokens_out = None
    if not (ddl or "").strip():
        # v1.98: 空の Stage 1 出力はハードタイムアウトと同じ失敗として扱う。
        # 素通しすると展開層が空を返し、記述を持たない作品が描かれて保存される
        # （2026-05-05 以降 11 件確認）。
        return InterpretDetail(
            ddl=_fallback_ddl_from_text(text, lang=lang),
            thinking=thinking,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            fallback_used=True,
            fallback_reasons=["stage1_empty_output"],
            raw=raw,
            stage1_prompt_digest=prompt_metadata.get("stage1_prompt_digest"),
            stage1_prompt_base_digest=prompt_metadata.get("stage1_prompt_base_digest"),
        )
    return InterpretDetail(
        ddl=_sanitize_placement_words(ddl),
        thinking=thinking,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        raw=raw,
        stage1_prompt_digest=prompt_metadata.get("stage1_prompt_digest"),
        stage1_prompt_base_digest=prompt_metadata.get("stage1_prompt_base_digest"),
    )


def _clean_sketch_text(raw: str) -> str:
    """Trim what the model wrapped around the prose.

    Some providers fence prose the same way they fence code; Stage 1 does the
    same trimming for the DDL (see _interpret_openai_detail).
    """
    return re.sub(r"^```(?:\w+)?\s*\n?|\n?```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()


def _call_sketch_detail(
    text: str,
    *,
    model: str | None = None,
    lang: str = "ja",
    grain: str = DEFAULT_SKETCH_GRAIN,
    include_trace: bool = False,
) -> SketchDetail:
    """Run Stage 0.5. A failure here never stops a painting.

    Provider error, hard timeout or empty output all mean the same thing: the
    description itself travels on to Stage 1, so the picture still gets made.
    This is the rule Stage 1 already follows for its own failures.
    """
    grain = normalize_sketch_grain(grain)
    digest = _sketch_prompt_digest(_sketch_system_prompt(lang=lang, grain=grain))
    try:
        raw, tokens_in, tokens_out = _run_with_hard_timeout(
            "sketch",
            _hard_timeout_seconds("INKU_SKETCH_HARD_TIMEOUT_SECONDS"),
            lambda: sketch_from_life(text, model=model, lang=lang, grain=grain),
        )
    except StageHardTimeoutError:
        return SketchDetail(
            text=text,
            grain=grain,
            fallback_used=True,
            fallback_reasons=["sketch_hard_timeout"],
            prompt_digest=digest,
        )
    except Exception as exc:  # noqa: BLE001 — 0.5 must never break generation
        _logger.warning("stage 0.5 failed, painting from the description: %s", exc)
        return SketchDetail(
            text=text,
            grain=grain,
            fallback_used=True,
            fallback_reasons=["sketch_failed"],
            prompt_digest=digest,
        )
    rendered = _clean_sketch_text(raw)
    if not rendered:
        return SketchDetail(
            text=text,
            grain=grain,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            fallback_used=True,
            fallback_reasons=["sketch_empty_output"],
            raw=raw if include_trace else None,
            prompt_digest=digest,
        )
    return SketchDetail(
        text=rendered,
        grain=grain,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        raw=raw if include_trace else None,
        prompt_digest=digest,
    )


def _resolved_sketch(
    req_sketch: bool,
    req_sketch_text: str | None,
    req_sketch_grain: str | None,
    *,
    description: str,
    model: str | None,
    lang: str,
    include_trace: bool = False,
) -> SketchDetail | None:
    """Decide what Stage 0.5 contributes to this request.

    Three cases, in order:
      - a sketch text came with the request (the author edited it, or a saved
        work is being redrawn): use it verbatim and DO NOT call the model;
      - 0.5 is on: call the model at the requested grain;
      - otherwise: None, and the description travels as it always did.
    """
    stored = (req_sketch_text or "").strip()
    if stored:
        return SketchDetail(text=stored, grain=normalize_sketch_grain(req_sketch_grain))
    if not req_sketch:
        return None
    return _call_sketch_detail(
        description,
        model=model,
        lang=lang,
        grain=normalize_sketch_grain(req_sketch_grain),
        include_trace=include_trace,
    )


def _assemble_trace(
    include_trace: bool,
    *,
    interpret_result: InterpretDetail | None = None,
    sketch_result: SketchDetail | None = None,
    compose_detail: ComposeDetail,
    score_pre_coerce_dump: dict | None,
    coerce_report: dict,
) -> dict | None:
    """Assemble the RAW trace bundle (observation only). Never fails generation:
    a collection error is reported as a warning inside the trace instead."""
    if not include_trace:
        return None
    try:
        trace: dict = {}
        if sketch_result is not None:
            trace["sketch_raw"] = sketch_result.raw
            trace["sketch_text"] = sketch_result.text
            trace["sketch_grain"] = sketch_result.grain
            trace["sketch_prompt_digest"] = sketch_result.prompt_digest
            trace["sketch_fallback_used"] = sketch_result.fallback_used
        if interpret_result is not None:
            trace["stage1_raw"] = interpret_result.raw
            trace["stage1_thinking"] = interpret_result.thinking
            trace["stage1_ddl"] = interpret_result.ddl
        trace.update(
            {
                "plugin_expanded_ddl": compose_detail.plugin_expanded_ddl,
                "stage15_ddl": compose_detail.stage15_ddl,
                "stage2_raw_attempts": compose_detail.stage2_raw_attempts,
                "score_pre_coerce": score_pre_coerce_dump,
                "coerce_branch_counts": coerce_report.get("coerce_branch_counts", {}),
                "coerce_relation_input_count": coerce_report.get("coerce_relation_input_count", 0),
                "coerce_relation_output_count": coerce_report.get("coerce_relation_output_count", 0),
                "coerce_relation_dropped_count": coerce_report.get("coerce_relation_dropped_count", 0),
                "plugin_provenance": compose_detail.plugin_provenance,
                "plugin_warnings": compose_detail.plugin_warnings,
            }
        )
        return trace
    except Exception as exc:  # noqa: BLE001 — trace must never break generation
        return {"warning": f"trace collection failed: {exc}"}


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


@router.post("/api/compose", response_model=ComposeResponse, response_model_exclude_none=True)
def api_compose(req: ComposeRequest, actor: dict = Depends(_current_user)) -> ComposeResponse:
    # The author's leading numbers and bracketed comments are their document,
    # not their description: they are cut once, here, so that no layer -- Stage
    # 0.5 included -- and no client can read them.  req.description stays whole
    # for saving and display (see description_labels).
    description = pipeline_description(req.description)
    render_seed, seed_text = _render_seed_from_text(req.seed_text, req.render_seed)
    t0 = time.perf_counter()
    instruction_lang_requested = _normalize_instruction_lang(req.instruction_lang)
    ui_lang = _normalize_ui_lang(req.ui_lang)
    instruction_lang_resolved = _resolve_instruction_lang(
        description or req.ddl,
        instruction_lang_requested,
        ui_lang=ui_lang,
    )
    resolved_stage2_model = _resolved_stage2_model(req.model, actor)
    # This endpoint begins at Stage 2, so Stage 0.5 never runs here. When the
    # caller carries a sketch text (a candidate, a redraw of a saved work) it
    # stands in for the description for the plugin expansion, Stage 1.5,
    # Stage 2 and coerce -- the same four places it stands in during a paint.
    sketch_grain = normalize_sketch_grain(req.sketch_grain) if req.sketch_text else None
    source_text = (req.sketch_text or "").strip() or description
    # The same shape _resolved_sketch builds for a carried prose, so this route
    # names its state through the one derivation function instead of its own
    # rules. No description at all is a work authored straight in DDL.
    sketch_detail = (
        SketchDetail(text=(req.sketch_text or "").strip(), grain=sketch_grain)
        if (req.sketch_text or "").strip()
        else None
    )
    sketch_state = sketch_state_of(
        sketch_detail,
        requested=False,
        has_description=bool((description or "").strip()),
    )
    resolved_variation_amplitude = _validated_variation_amplitude(req.variation_amplitude)
    resolved_variation_seed = (
        req.variation_seed if resolved_variation_amplitude is not None else None
    )
    # Read once for this request and handed to every layer that states or
    # applies a limit: the prompt, coerce, and the count clamp inside
    # Score.model_validate (which reaches it through using_limits).
    limits = _effective_limits()
    # Settled before Stage 2 rather than after it: the composition is told which
    # paper it composes for, and it cannot be told a value that has not been
    # decided yet. The 422 for an unsupported id therefore now answers before
    # Stage 2 runs instead of after it.
    canvas_aspect = _validated_canvas_aspect(req.canvas_aspect)
    try:
        with using_limits(limits):
            compose_detail = _call_compose_detail(
                req.ddl,
                model=resolved_stage2_model,
                original_description=source_text,
                plugin_seed_text=description,
                plugin_fires_on=(req.fires_on or "").strip() or None,
                system_prompt=None,
                lang=instruction_lang_resolved,
                composition_seed=req.composition_seed,
                include_trace=req.include_trace,
                variation_amplitude=resolved_variation_amplitude,
                variation_seed=resolved_variation_seed,
                limits=limits,
                canvas_aspect=canvas_aspect,
            )
    except Exception as e:  # noqa: BLE001
        raise _stage_http_error("compose", 502) from e

    score_pre_coerce_dump = (
        compose_detail.score.model_dump(mode="json", by_alias=True)
        if req.include_trace
        else None
    )
    coerce_report: dict[str, object] = _coerce_relation_report(None, None)
    limit_notes: list[str] = []
    try:
        score = compose_detail.score
        ensure_renderable_score(score)
        if req.auto_repair:
            before_coerce = score
            branch_counts: dict[str, int] = {}
            # Site 3 of 5.
            with using_limits(limits):
                score = coerce_score(
                    score,
                    branch_report=branch_counts,
                    limit_notes=limit_notes,
                    # The DDL alone. Handing the prose along too let coerce's 30
                    # branches author instructions from words the DDL never carried.
                    ddl=compose_detail.ddl,
                    limits=limits,
                    lang=instruction_lang_resolved,
                )
            coerce_report = {**_coerce_relation_report(before_coerce, score), "coerce_branch_counts": branch_counts}
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("compose", 502) from e

    score = _score_with_plugin_instructions(
        score, compose_detail.plugin_instructions, limits=limits, notes=limit_notes
    )

    normalized_compose_ddl = compose_detail.ddl.lower()
    if "雲形" in compose_detail.ddl or "cloudform" in normalized_compose_ddl:
        score = _finalize_score(score, compose_detail.ddl)
        coerce_report["coerce_relation_output_count"] = _score_relation_count(score)

    # The Score keeps whatever support Stage 2 declared, including a declaration
    # that disagrees with the request: it is the record of which paper the
    # composition was built for. The paper actually performed on rides in
    # render_canvas_aspect* and reaches the renderer from there.
    render_metadata = {
        **_render_metadata(req.catalog_id, canvas_aspect=canvas_aspect),
        "stage2_prompt_digest": compose_detail.stage2_prompt_digest,
        "instruction_lang_requested": instruction_lang_requested,
        "instruction_lang_resolved": instruction_lang_resolved,
        "ui_lang": ui_lang,
        "render_seed": render_seed,
        "render_wild": req.wild,
        "composition_seed": req.composition_seed,
        "focus": compose_detail.resolved_focus,
        "variation_amplitude": resolved_variation_amplitude,
        "variation_seed": resolved_variation_seed,
        "seed_text": seed_text,
        "interpretation_seed": req.interpretation_seed,
        "render_limits": limits_as_dict(limits),
    }
    try:
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("render", 500) from e
    render_metadata = {
        **render_metadata,
        **_render_hash_metadata(
            input_text=description or req.ddl,
            ddl=compose_detail.ddl,
            score=score,
            svg=svg,
            catalog_id=req.catalog_id,
            render_metadata=render_metadata,
        ),
    }

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    _carriage = _carriage_warnings(compose_detail.ddl, score) or None
    return ComposeResponse(
        ddl=compose_detail.ddl,
        source_ddl=compose_detail.source_ddl or None,
        plugin_provenance=compose_detail.plugin_provenance,
        plugin_warnings=compose_detail.plugin_warnings,
        carriage_warnings=_carriage,
        score=score,
        svg=svg,
        stage2_model=resolved_stage2_model,
        variation_moved_axes=compose_detail.variation_moved_axes,
        **render_metadata,
        elapsed_ms=elapsed_ms,
        tokens_in=compose_detail.tokens_in,
        tokens_out=compose_detail.tokens_out,
        retry_count=compose_detail.retry_count,
        retry_reasons=compose_detail.retry_reasons,
        fallback_used=compose_detail.fallback_used,
        sketch_text=req.sketch_text or None,
        sketch_grain=sketch_grain,
        sketch_state=sketch_state,
        render_limit_notes=limit_notes or None,
        **coerce_report,
        trace=_assemble_trace(
            req.include_trace,
            compose_detail=compose_detail,
            score_pre_coerce_dump=score_pre_coerce_dump,
            coerce_report=coerce_report,
        ),
    )


@router.post("/api/interpret")
def api_interpret(req: InterpretRequest, actor: dict = Depends(_current_user)) -> dict:
    # The author's leading numbers and bracketed comments are their document,
    # not their description: they are cut once, here, so that no layer -- Stage
    # 0.5 included -- and no client can read them.  req.description stays whole
    # for saving and display (see description_labels).
    description = pipeline_description(req.description)
    # Two conditions, never one.  An empty req.description is already refused by
    # min_length=1, and judging the cut alone would answer "only labels" to a
    # text that carried no label at all.
    if req.description.strip() and not description:
        raise HTTPException(status_code=400, detail=_LABEL_ONLY_DESCRIPTION)
    instruction_lang_requested = _normalize_instruction_lang(req.instruction_lang)
    ui_lang = _normalize_ui_lang(req.ui_lang)
    # Settled on the author's own words: Stage 0.5 writes in the language it is
    # told to, so reading its output back would be circular.
    instruction_lang_resolved = _resolve_instruction_lang(
        description, instruction_lang_requested, ui_lang=ui_lang
    )
    sketch_result = _resolved_sketch(
        req.sketch,
        req.sketch_text,
        req.sketch_grain,
        description=description,
        model=_resolved_stage1_model(req.model, actor),
        lang=instruction_lang_resolved,
    )
    # Stage 0.5 stands in for the description for Stage 1 and for the expansion
    # below, the same two places it stands in during a paint.
    source_text = sketch_result.text if sketch_result is not None else description
    # Stage 1 が読むのは、記述に文脈を注入したあとの文字列。注入しない client は
    # stage1_input を送ってこないので、そのときは記述そのものを読む。
    stage1_text = (
        sketch_result.text
        if sketch_result is not None
        else (pipeline_description(req.stage1_input) if req.stage1_input else description)
    )
    try:
        # Pure-invocation bypass: an input made of nothing but qualified
        # plugin terms is transcribed rather than interpreted. This is about
        # transcription fidelity, not staffage, so it no longer asks a level:
        # sending the term through Stage 1 risks the model rewriting it.
        if DOCUMENT_PLUGIN_MANAGER.is_pure_invocation(stage1_text):
            detail = InterpretDetail(ddl=stage1_text.strip(), thinking=None, raw=None)
        else:
            detail = _call_interpret_detail(
                stage1_text,
                model=_resolved_stage1_model(req.model, actor),
                include_thinking=req.include_thinking,
                system_prompt_prefix=None,
                lang=instruction_lang_resolved,
                # Stage 1 states the ceilings in its prompt even though this
                # route never reaches coerce.
                limits=_effective_limits(),
            )
    except Exception as e:  # noqa: BLE001
        raise _stage_http_error("interpret", 502) from e
    plugin_provenance: list[dict[str, str]] = []
    plugin_warnings: list[str] = []
    if req.expand_intermediate:
        plugin_expansion = DOCUMENT_PLUGIN_MANAGER.expand(
            detail.ddl,
            source_text=source_text,
            lang=instruction_lang_resolved,
            # The hash source, not language: the description, so that two runs
            # of the same work resolve the same counts and rotations.
            seed_text=description,
        )
        detail.ddl = expand_intermediate_for_lang(
            plugin_expansion.ddl,
            lang=instruction_lang_resolved,
            context_text=source_text,
            plugin_instructions_present=bool(plugin_expansion.instructions),
        )
        plugin_provenance = list(plugin_expansion.provenance)
        plugin_warnings = list(plugin_expansion.warnings)
    data: dict = {
        "ddl": detail.ddl,
        "thinking": detail.thinking,
        "instruction_lang_requested": instruction_lang_requested,
        "instruction_lang_resolved": instruction_lang_resolved,
        "ui_lang": ui_lang,
    }
    if sketch_result is not None:
        data["sketch_text"] = sketch_result.text
        data["sketch_grain"] = sketch_result.grain
    if detail.stage1_prompt_digest is not None:
        data["stage1_prompt_digest"] = detail.stage1_prompt_digest
    if detail.stage1_prompt_base_digest is not None:
        data["stage1_prompt_base_digest"] = detail.stage1_prompt_base_digest
    if plugin_provenance:
        data["plugin_provenance"] = plugin_provenance
    if plugin_warnings:
        data["plugin_warnings"] = plugin_warnings
    if detail.tokens_in is not None:
        data["tokens_in"] = detail.tokens_in
    if detail.tokens_out is not None:
        data["tokens_out"] = detail.tokens_out
    if detail.fallback_used:
        data["fallback_used"] = detail.fallback_used
        data["fallback_reasons"] = detail.fallback_reasons
    return data


class StageHardTimeoutError(TimeoutError):
    pass


def _hard_timeout_seconds(env_name: str, default: str = "120") -> float:
    return max(0.1, float(os.getenv(env_name, default)))


def _run_with_hard_timeout(label: str, timeout_seconds: float, operation):
    stage_slots = _stage_slots
    if not stage_slots.acquire(timeout=timeout_seconds):
        _increment_stage_stat("rejected")
        raise StageHardTimeoutError(f"{label} could not start within {timeout_seconds:g}s stage capacity timeout")
    try:
        future = _stage_executor.submit(operation)
    except Exception:
        stage_slots.release()
        raise
    _increment_stage_stat("submitted")
    future.add_done_callback(lambda _future, slots=stage_slots: slots.release())
    try:
        result = future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        _increment_stage_stat("timed_out")
        future.cancel()
        raise StageHardTimeoutError(f"{label} exceeded {timeout_seconds:g}s hard timeout") from exc
    except Exception:
        _increment_stage_stat("failed")
        raise
    _increment_stage_stat("completed")
    return result


def _fallback_background_from_text(text: str, *, lang: str) -> tuple[str, str]:
    lower = text.lower()
    if lang == "en":
        has_dawn = "dawn" in lower or "daybreak" in lower or "sunrise" in lower
        is_dark = not has_dawn and any(marker in lower for marker in ("night", "dark", "black"))
        background = "black" if is_dark else "white"
        foreground = "white" if background == "black" else "black"
        return background, foreground
    has_dawn = any(marker in text for marker in ("夜明け", "明け方", "朝焼け"))
    is_dark = not has_dawn and any(marker in text for marker in ("夜", "黒", "暗"))
    background = "黒" if is_dark else "白"
    foreground = "白" if background == "黒" else "黒"
    return background, foreground


def _fallback_ddl_from_text(text: str, *, lang: str) -> str:
    if lang == "en":
        background, foreground = _fallback_background_from_text(text, lang=lang)
        return (
            f"Fill background with {background}. "
            f"Draw three thin {foreground} diagonal lines. "
            "Scatter twelve small gray dots across the whole canvas."
        )
    background, foreground = _fallback_background_from_text(text, lang=lang)
    accent = "青" if foreground == "黒" and ("白" in text or "雪" in text) else "灰色"
    return (
        f"背景を{background}で埋める。"
        f"{foreground}い細い斜めの線を三本並べる。"
        f"{accent}の小さな点を十二個、画面全体に点々と散らす。"
    )


@router.post("/api/render-score", response_model=RenderScoreResponse, response_model_exclude_none=True)
def api_render_score(req: RenderScoreRequest, actor: dict = Depends(_current_user)) -> RenderScoreResponse:
    render_seed, seed_text = _render_seed_from_text(req.seed_text, req.render_seed)
    # Outside the try: a 404 for an unknown work is the answer, not a render
    # failure to be relabelled 422 by the handler below.
    work = _work_for_color_snapshot(actor, req.work_id) if req.work_id else None
    try:
        # Site 4 of 5.
        limits = _effective_limits()
        limit_notes: list[str] = []
        with using_limits(limits):
            score = coerce_score(
                Score.model_validate(req.score),
                # The DDL alone -- see the note at the /api/compose call site.
                ddl=req.ddl,
                limits=limits,
                limit_notes=limit_notes,
                # This route begins at Stage 2 and carries no language field, so
                # the language is settled the same way the paint route settles
                # it -- off the author's own words, through the one resolver.
                lang=_resolve_instruction_lang(req.ddl or req.input, "auto"),
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
        render_limit_notes=limit_notes or None,
        **render_metadata,
    )


@router.post("/api/render-svg")
def api_render_svg(req: RenderSvgRequest, actor: dict = Depends(_current_user)) -> Response:
    render_seed, _ = _render_seed_from_text(req.seed_text, req.render_seed)
    work = _work_for_color_snapshot(actor, req.work_id) if req.work_id else None
    try:
        svg, resolved_catalog_id, color_source = _render_score_svg(
            req.score,
            catalog_id=req.catalog_id,
            canvas_aspect=req.canvas_aspect,
            svg_profile=req.svg_profile,
            render_seed=render_seed,
            composition_seed=req.composition_seed,
            wild=req.wild,
            work=work,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("svg render", 422) from e
    # The body of this endpoint is the SVG itself, so the one thing a caller
    # cannot read off it -- whether it got the work's own colors -- rides here.
    return Response(
        content=svg,
        media_type="image/svg+xml; charset=utf-8",
        headers={
            COLOR_SOURCE_HEADER: color_source,
            COLOR_CATALOG_ID_HEADER: resolved_catalog_id,
        },
    )


def _paint_events(
    req: PaintRequest,
    idempotency_key: str | None,
    actor: dict,
) -> Iterator[dict[str, object]]:
    """Run a paint and yield its stage boundaries.

    Both /api/paint and /api/paint/stream consume this generator, so the two
    endpoints cannot drift apart. Events are ``stage1`` (interpretation is
    finished, its DDL and token counts are known) followed by ``done`` (the
    complete PaintResponse).
    """
    # The author's leading numbers and bracketed comments are their document,
    # not their description: they are cut once, here, so that no layer -- Stage
    # 0.5 included -- and no client can read them.  req.description stays whole
    # for saving and display (see description_labels).
    description = pipeline_description(req.description)
    # Two conditions, never one.  An empty req.description is already refused by
    # min_length=1, and judging the cut alone would answer "only labels" to a
    # text that carried no label at all.  This is the last gate for a client
    # that has no editor of its own: the CLI, Android, anything written later.
    if req.description.strip() and not description:
        raise HTTPException(status_code=400, detail=_LABEL_ONLY_DESCRIPTION)
    t0 = time.perf_counter()
    instruction_lang_requested = _normalize_instruction_lang(req.instruction_lang)
    ui_lang = _normalize_ui_lang(req.ui_lang)
    # The language is settled on the author's own words: Stage 0.5 writes in the
    # language it is told to, so reading it back would be circular.
    instruction_lang_resolved = _resolve_instruction_lang(
        description, instruction_lang_requested, ui_lang=ui_lang
    )
    resolved_stage1_model = _resolved_stage1_model(req.stage1_model, actor)
    sketch_result = _resolved_sketch(
        req.sketch,
        req.sketch_text,
        req.sketch_grain,
        description=description,
        model=resolved_stage1_model,
        lang=instruction_lang_resolved,
        include_trace=req.include_trace,
    )
    # Stage 0.5 stands in for the description everywhere the description went:
    # Stage 1, the plugin expansion, Stage 1.5, Stage 2 and coerce. Wiring it
    # into stage1_input alone would leave the other four reading the raw
    # description, and the range the layer exists to open would not appear
    # (contract section 0.2). req.description is kept for saving and display.
    source_text = sketch_result.text if sketch_result is not None else description
    stage1_text = (
        sketch_result.text
        if sketch_result is not None
        else (pipeline_description(req.stage1_input) if req.stage1_input else description)
    )
    catalog_id = _resolved_paint_catalog_id(
        req.catalog_id, mode=req.catalog_mode, source_text=source_text
    )
    resolved_stage2_model = _resolved_stage2_model(req.stage2_model, actor)
    render_seed, seed_text = _render_seed_from_text(req.seed_text, req.render_seed)
    resolved_variation_amplitude = _validated_variation_amplitude(req.variation_amplitude)
    resolved_variation_seed = (
        req.variation_seed if resolved_variation_amplitude is not None else None
    )
    # Read once for the whole paint: Stage 1, Stage 2 and coerce all state or
    # apply these numbers, and they have to be the same numbers.
    limits = _effective_limits()
    try:
        # Pure-invocation bypass: an input made of nothing but qualified
        # plugin terms is transcribed rather than interpreted. This is about
        # transcription fidelity, not staffage, so it no longer asks a level:
        # sending the term through Stage 1 risks the model rewriting it.
        if DOCUMENT_PLUGIN_MANAGER.is_pure_invocation(stage1_text):
            interpret_detail_result = InterpretDetail(
                ddl=stage1_text.strip(), raw=stage1_text.strip() if req.include_trace else None
            )
        else:
            interpret_detail_result = _call_interpret_detail(
                stage1_text,
                model=resolved_stage1_model,
                include_thinking=req.include_thinking,
                lang=instruction_lang_resolved,
                include_trace=req.include_trace,
                limits=limits,
            )
    except Exception as e:  # noqa: BLE001
        raise _stage_http_error("interpret", 502) from e
    ddl = interpret_detail_result.ddl
    t1 = time.perf_counter()
    stage1_event = {
        "event": "stage1",
        # 入力側 DDL (展開前)。done イベントの ddl は展開後なので別物。
        "ddl": ddl,
        "thinking": interpret_detail_result.thinking,
        "stage1_model": resolved_stage1_model,
        "stage2_model": resolved_stage2_model,
        "tokens_in": interpret_detail_result.tokens_in,
        "tokens_out": interpret_detail_result.tokens_out,
        "elapsed_ms": int((t1 - t0) * 1000),
        "interpret_fallback_used": interpret_detail_result.fallback_used,
    }
    if interpret_detail_result.stage1_prompt_digest is not None:
        stage1_event["stage1_prompt_digest"] = interpret_detail_result.stage1_prompt_digest
    if interpret_detail_result.stage1_prompt_base_digest is not None:
        stage1_event["stage1_prompt_base_digest"] = (
            interpret_detail_result.stage1_prompt_base_digest
        )
    yield stage1_event
    # Settled before Stage 2, for the reason given at the /api/compose call
    # site: the composition is told which paper it composes for.
    canvas_aspect = _validated_canvas_aspect(req.canvas_aspect)
    try:
        with using_limits(limits):
            compose_detail = _call_compose_detail(
                ddl,
                model=resolved_stage2_model,
                original_description=source_text,
                plugin_seed_text=description,
                lang=instruction_lang_resolved,
                include_trace=req.include_trace,
                variation_amplitude=resolved_variation_amplitude,
                variation_seed=resolved_variation_seed,
                limits=limits,
                canvas_aspect=canvas_aspect,
            )
    except Exception as e:  # noqa: BLE001
        raise _stage_http_error("compose", 502) from e

    ddl = compose_detail.ddl
    # trace: capture the pre-coerce Score before any coerce/ensure mutation.
    score_pre_coerce_dump = (
        compose_detail.score.model_dump(mode="json", by_alias=True)
        if req.include_trace
        else None
    )
    coerce_report: dict[str, object] = _coerce_relation_report(None, None)
    limit_notes: list[str] = []
    try:
        score = compose_detail.score
        ensure_renderable_score(score)
        if req.auto_repair:
            before_coerce = score
            branch_counts: dict[str, int] = {}
            # Site 5 of 5.
            with using_limits(limits):
                score = coerce_score(
                    score,
                    branch_report=branch_counts,
                    limit_notes=limit_notes,
                    # The DDL alone -- see the note at the /api/compose call site.
                    ddl=ddl,
                    limits=limits,
                    lang=instruction_lang_resolved,
                )
            coerce_report = {**_coerce_relation_report(before_coerce, score), "coerce_branch_counts": branch_counts}
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("compose", 502) from e

    score = _score_with_plugin_instructions(
        score, compose_detail.plugin_instructions, limits=limits, notes=limit_notes
    )

    normalized_compose_ddl = compose_detail.ddl.lower()
    if "雲形" in compose_detail.ddl or "cloudform" in normalized_compose_ddl:
        score = _finalize_score(score, compose_detail.ddl)
        coerce_report["coerce_relation_output_count"] = _score_relation_count(score)

    # The Score keeps Stage 2's declaration -- see the note at the /api/compose
    # call site.
    render_metadata = {
        **_render_metadata(catalog_id, canvas_aspect=canvas_aspect),
        "stage1_prompt_digest": interpret_detail_result.stage1_prompt_digest,
        "stage1_prompt_base_digest": interpret_detail_result.stage1_prompt_base_digest,
        "stage2_prompt_digest": compose_detail.stage2_prompt_digest,
        "instruction_lang_requested": instruction_lang_requested,
        "instruction_lang_resolved": instruction_lang_resolved,
        "ui_lang": ui_lang,
        "render_seed": render_seed,
        "render_wild": req.wild,
        "composition_seed": req.composition_seed,
        "focus": compose_detail.resolved_focus,
        "variation_amplitude": resolved_variation_amplitude,
        "variation_seed": resolved_variation_seed,
        "seed_text": seed_text,
        "interpretation_seed": req.interpretation_seed,
        "render_limits": limits_as_dict(limits),
    }
    if compose_detail.plugin_provenance:
        render_metadata["plugin_provenance"] = compose_detail.plugin_provenance
    if compose_detail.plugin_warnings:
        render_metadata["plugin_warnings"] = compose_detail.plugin_warnings
    t2 = time.perf_counter()
    try:
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("render", 500) from e
    # Saving and display keep the author's words: source_text is what the
    # pipeline read, which is the sketch prose when Stage 0.5 ran.
    artifact_input = req.history_input or req.description
    artifact_catalog_id = None if catalog_id == "default" else catalog_id
    render_metadata = {
        **render_metadata,
        **_render_hash_metadata(
            input_text=artifact_input,
            ddl=ddl,
            score=score,
            svg=svg,
            catalog_id=artifact_catalog_id,
            render_metadata=render_metadata,
        ),
    }
    sketch_recorded = sketch_result is not None and not sketch_result.fallback_used
    stored_sketch_text = sketch_result.text if sketch_recorded else None
    stored_sketch_grain = sketch_result.grain if sketch_recorded else None
    # Three of the four events above used to be one NULL sketch_text. The state
    # is derived once here and used by both the row and the response, so the
    # record and what the author is shown cannot disagree.
    sketch_state = sketch_state_of(
        sketch_result,
        requested=req.sketch,
        has_description=bool((description or "").strip()),
    )
    elapsed_stage1_ms = int((t1 - t0) * 1000)
    elapsed_stage2_ms = int((t2 - t1) * 1000)
    elapsed_total_ms = int((time.perf_counter() - t0) * 1000)
    history_id = None
    history_at = None
    saved_identity: dict[str, object] = {}
    idempotent_replay = False
    save_artifacts = req.save_artifacts if req.save_artifacts is not None else req.save_history
    if req.save_history:
        history_at = req.history_at or int(time.time() * 1000)
        item = _add_history_item(
            actor=actor,
            input_text=req.history_input or req.description,
            ddl=compose_detail.source_ddl or ddl,
            expanded_ddl=ddl,
            interpret_fallback=(
                (interpret_detail_result.fallback_reasons or ["stage1_fallback"])[0]
                if interpret_detail_result.fallback_used
                else None
            ),
            score=score,
            svg=svg,
            at=history_at,
            elapsed_ms=elapsed_total_ms,
            stage1_model=resolved_stage1_model,
            stage2_model=resolved_stage2_model,
            tokens_in=(interpret_detail_result.tokens_in or 0) + (compose_detail.tokens_in or 0) or None,
            tokens_out=(interpret_detail_result.tokens_out or 0) + (compose_detail.tokens_out or 0) or None,
            catalog_id=artifact_catalog_id,
            # The request's own word, not the resolved id: `auto` picks a
            # different catalog for every description, so the id alone cannot
            # say the author let the server read the words.
            catalog_mode=req.catalog_mode,
            save_artifacts=save_artifacts,
            render_metadata=render_metadata,
            source_text=req.history_source_text or req.description,
            display_label=req.history_display_label,
            batch_line_number=req.batch_line_number,
            batch_run_id=req.batch_run_id,
            history_visibility=req.history_visibility,
            lineage_parent_node_id=req.lineage_parent_node_id,
            derivation_kind=req.derivation_kind,
            derivation_metadata={
                **req.derivation_metadata,
                "plugin_provenance": compose_detail.plugin_provenance,
                "plugin_warnings": compose_detail.plugin_warnings,
            },
            idempotency_key=idempotency_key,
            # A work whose 0.5 failed was painted from the description, and is
            # recorded that way: storing the fallback text would make it look
            # like prose the layer wrote, and which works went through the layer
            # is the thing these two columns exist to answer.
            sketch_text=stored_sketch_text,
            sketch_grain=stored_sketch_grain,
            sketch_state=sketch_state,
        )
        history_id = item["id"]
        idempotent_replay = bool(item.get("_idempotent_replay"))
        saved_identity = {
            "description_hash": item.get("description_hash"),
            "lineage_node_id": item.get("lineage_node_id"),
            "lineage_parent_node_id": item.get("lineage_parent_node_id"),
            "derivation_kind": item.get("derivation_kind"),
        }
    elif save_artifacts:
        history_at = req.history_at or int(time.time() * 1000)
        item_id = str(uuid.uuid4())
        score_dict = score.model_dump(by_alias=True)
        _submit_history_artifact_save({
            "id": item_id,
            "user_id": actor["id"],
            "output_path": str(_output_prefix(actor["id"], item_id, history_at)),
            "input": req.history_input or req.description,
            "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
            "score": score_dict,
            "svg": svg,
            "at": history_at,
            "stage1_model": resolved_stage1_model,
            "stage2_model": resolved_stage2_model,
            "render_metadata": render_metadata,
        })
    user_generation_count = None
    if req.count_generation and not idempotent_replay:
        user_generation_count = _db.increment_user_generation_count(actor["id"])
        if user_generation_count is None:
            raise HTTPException(status_code=404, detail="user not found")
    paint_trace = _assemble_trace(
        req.include_trace,
        sketch_result=sketch_result,
        interpret_result=interpret_detail_result,
        compose_detail=compose_detail,
        score_pre_coerce_dump=score_pre_coerce_dump,
        coerce_report=coerce_report,
    )
    _carriage = _carriage_warnings(compose_detail.ddl, score) or None
    response = PaintResponse(
        description=req.description,
        ddl=ddl,
        source_ddl=compose_detail.source_ddl or None,
        thinking=interpret_detail_result.thinking,
        carriage_warnings=_carriage,
        score=score,
        svg=svg,
        stage1_model=resolved_stage1_model,
        stage2_model=resolved_stage2_model,
        variation_moved_axes=compose_detail.variation_moved_axes,
        **render_metadata,
        history_id=history_id,
        history_at=history_at,
        **saved_identity,
        elapsed_stage1_ms=elapsed_stage1_ms,
        elapsed_stage2_ms=elapsed_stage2_ms,
        elapsed_total_ms=elapsed_total_ms,
        tokens_in_stage1=interpret_detail_result.tokens_in,
        tokens_out_stage1=interpret_detail_result.tokens_out,
        tokens_in_stage2=compose_detail.tokens_in,
        tokens_out_stage2=compose_detail.tokens_out,
        interpret_fallback_used=interpret_detail_result.fallback_used,
        interpret_fallback_reasons=interpret_detail_result.fallback_reasons,
        compose_retry_count=compose_detail.retry_count,
        compose_retry_reasons=compose_detail.retry_reasons,
        compose_fallback_used=compose_detail.fallback_used,
        user_generation_count=user_generation_count,
        catalog_id=catalog_id,
        sketch_text=sketch_result.text if sketch_result is not None else None,
        sketch_grain=sketch_result.grain if sketch_result is not None else None,
        sketch_fallback_used=sketch_result.fallback_used if sketch_result is not None else False,
        sketch_state=sketch_state,
        render_limit_notes=limit_notes or None,
        **coerce_report,
        trace=paint_trace,
    )
    yield {"event": "done", "response": response}


@router.post("/api/paint", response_model=PaintResponse, response_model_exclude_none=True)
def api_paint(
    req: PaintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> PaintResponse:
    for event in _paint_events(req, idempotency_key, actor):
        if event["event"] == "done":
            return event["response"]  # type: ignore[return-value]
    raise _unexpected_http_error("paint", 500)


@router.post("/api/paint/stream")
def api_paint_stream(
    req: PaintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> StreamingResponse:
    """Newline-delimited JSON variant of /api/paint.

    The response is already committed once the first event is written, so a
    failure after that point is reported as an in-band ``error`` event instead
    of an HTTP status.  Before that point nothing is committed, so the first
    event is pulled here and a refusal reaches the client as the status it is
    -- the guard on a label-only description raises before any event, and this
    route answers 400 like the other two rather than 200 carrying an error.
    """
    events = _paint_events(req, idempotency_key, actor)
    try:
        first = next(events)
    except StopIteration:
        raise _unexpected_http_error("paint", 500) from None

    def lines() -> Iterator[str]:
        try:
            for event in itertools.chain([first], events):
                if event["event"] == "done":
                    response = event["response"]
                    payload = {
                        "event": "done",
                        **response.model_dump(mode="json", by_alias=True, exclude_none=True),
                    }
                else:
                    payload = event
                yield json.dumps(payload, ensure_ascii=False) + "\n"
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
