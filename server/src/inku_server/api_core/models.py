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
    # How the catalog was asked for (fixed / auto / random), kept beside the
    # resolved id so a work can say whether the author chose one.
    catalog_mode: str | None = None
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
    interpretation_seed: str | None = None
    seed_text: str | None = None
    # Stage 0.5 (v2.10). Carried with the work so a redraw replays the same
    # prose instead of asking a non-deterministic layer for it again.
    sketch_text: str | None = None
    sketch_grain: str | None = None
    # What Stage 0.5 did. A client knows its own path, so it may say; an unknown
    # value is a 422 rather than a quiet not_applicable, and an absent one is
    # derived server-side. Only a row older than the column may end up NULL.
    sketch_state: str | None = Field(
        default=None, pattern="^(fine|coarse|fallback|off|not_applicable)$"
    )
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
    # The work's own weight in UTF-8 bytes, sent whether or not the picture is.
    # The listing that draws the strip asks for `include_svg=false`, so a client
    # cannot count this for itself: what arrives in `svg` is then an empty
    # string, and measuring it would report every work as nothing.
    #
    # It belongs here and not on HistoryPostBody, which this inherits from: the
    # weight is something the server reports about a stored work, never
    # something a caller states when saving one.
    svg_bytes: int = 0
    output_path: str | None = None
    # True when this work is somebody else's, reached through a group scope or an
    # explicit grant. Absent (not false) for one's own, so the ordinary listing
    # is unchanged on the wire; a client that never learned the field sees what
    # it always saw.
    shared: bool | None = None
    # The staffage level a work was drawn at. The axis was folded away in
    # v2.11.0 and nothing writes this any more, so it is declared on the
    # RESPONSE model and not on the post body: a work saved before the removal
    # still reports the conditions it was drawn under, and no client can set it.
    tenkei: str | None = None
    # The limits that governed this work. Present only when the row recorded
    # them; absent means "drawn before they were recorded", not "the defaults".
    render_limits: dict[str, int] | None = None
    render_hash: str | None = None
    render_hash_short: str | None = None
    trashed: bool = False
    starred: bool = False
    # The revision mark, independent of starred.
    for_revision: bool = False
    # The share bit and where it points. Unlike `shared`, which says this work
    # reached the caller from somebody else, these two are what the OWNER set:
    # the bit is a permission and the group is its destination, and a reader who
    # saw only the bit would not know who else is looking.
    for_share: bool = False
    share_group_id: str | None = None
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
    permission_groups: list[str]
    permission_group_labels: list[str]
    group_id: str | None = None
    group_name: str | None = None
    ui_theme: str = "dark"
    ui_mode: str = "simple"
    ui_custom: dict[str, bool] = Field(default_factory=dict)
    # What the history strip prints under each thumbnail. The default matches
    # what it printed before it could be asked; an empty list means the reader
    # asked for nothing, and is not the same as the field being absent.
    history_strip_fields: list[str] = Field(default_factory=lambda: ["generation", "model"])
    tooltips_enabled: bool = True
    download_folder_enabled: bool = False
    download_folder_name: str | None = None
    settings_tab: str = "db"
    model_settings: dict = Field(default_factory=dict)
    image_generation_count: int = 0
    at: int


class ModelSettingsResponse(BaseModel):
    catalog: list[dict] = Field(default_factory=list)
    llm_catalog: list[dict] = Field(default_factory=list)
    vision_catalog: list[dict] = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)
