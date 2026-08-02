"""Pydantic models used by more than one router group."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class HistoryPostBody(BaseModel):
    input: str
    ddl: str | None = None
    expanded_ddl: str | None = None
    focus: str | None = None
    variation_amplitude: str | None = None
    variation_seed: int | None = None
    interpret_fallback: str | None = None
    score: dict
    svg: str = ""
    at: int
    elapsed_ms: int = 0
    stage1_model: str | None = None
    stage2_model: str | None = None
    stage1_prompt_digest: str | None = None
    stage1_prompt_base_digest: str | None = None
    stage2_prompt_digest: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    catalog_id: str | None = None
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
    tenkei: str | None = Field(default=None, pattern="^(none|sparse|auto)$")
    interpretation_seed: str | None = None
    seed_text: str | None = None
    source_text: str | None = None
    display_label: str | None = None
    batch_line_number: int | None = None
    batch_run_id: str | None = None
    history_visibility: str = "normal"
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    derivation_metadata: dict[str, object] = Field(default_factory=dict)
    instruction_lang_requested: str | None = None
    instruction_lang_resolved: str | None = None
    ui_lang: str | None = None
    save_artifacts: bool = True
    count_generation: bool = Field(default=False, exclude=True)
    color_map: dict[str, str] | None = Field(default=None, exclude=True, description="Deprecated: ignored; catalog_id is resolved server-side")
    canvas_aspect: str | None = Field(default=None, exclude=True)


class HistoryItem(HistoryPostBody):
    id: str
    output_path: str | None = None
    render_hash: str | None = None
    render_hash_short: str | None = None
    trashed: bool = False
    starred: bool = False
    # The revision mark, independent of starred.
    for_revision: bool = False
    note: str | None = None
    description_hash: str | None = None
    lineage_node_id: str | None = None
    lineage_root_node_id: str | None = None
    lineage_generation: int | None = Field(default=None, ge=1)
    lineage_state: Literal["active", "lineage_only", "tombstone"] | None = None
    data_warnings: list[str] = Field(default_factory=list)


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int
    offset: int
    limit: int


class UserAccountItem(BaseModel):
    id: str
    username: str
    email: str
    role: str
    role_label: str
    group_id: str | None = None
    group_name: str | None = None
    ui_theme: str = "dark"
    ui_mode: str = "simple"
    ui_custom: dict[str, bool] = Field(default_factory=dict)
    tooltips_enabled: bool = True
    settings_tab: str = "db"
    model_settings: dict = Field(default_factory=dict)
    image_generation_count: int = 0
    at: int


class ModelSettingsResponse(BaseModel):
    catalog: list[dict] = Field(default_factory=list)
    llm_catalog: list[dict] = Field(default_factory=list)
    vision_catalog: list[dict] = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)
