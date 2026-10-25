"""Pydantic models used by more than one router group."""

from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, Field, PlainSerializer, model_validator

from ..persistence.ddl_source import select_ddl

# A seed can pass 2**53 (one drawn from seed text has 64 bits), beyond what a
# JavaScript number holds exactly, and a client that sends back a rounded seed
# draws another picture. So a JSON answer carries it as a decimal string; a
# request may send a number or a decimal string.
JsonSeed = Annotated[int, PlainSerializer(str, return_type=str, when_used="json")]


def json_seeds(item: dict | None) -> dict | None:
    """A work or result dict with its seeds as JsonSeed sends them.

    For the answers that leave as plain dicts rather than through a model.
    """
    if not item:
        return item
    return {**item, **{key: str(item[key]) for key in ("render_seed", "composition_seed")
                       if item.get(key) is not None}}


RangeNumerator = Annotated[int, Field(ge=0, strict=True)]
RangeDenominator = Annotated[int, Field(gt=0, strict=True)]
RangeFraction = tuple[RangeNumerator, RangeDenominator]


class CompositionRangeWords(BaseModel):
    """The display words of one composition range, in Japanese and English."""

    ja: str = Field(min_length=1, strict=True, description="The Japanese display name of the range.")
    en: str = Field(min_length=1, strict=True, description="The English display name of the range.")


class CompositionRange(BaseModel):
    """One range of allowed positions for a layer, with its display words."""

    key: str = Field(min_length=1, strict=True, description="The identifier of the range.")
    words: CompositionRangeWords = Field(description="The Japanese and English display names of the range.")
    # Keep the core's exact rational numbers, rather than rounding to floats.
    bounds: tuple[RangeFraction, RangeFraction, RangeFraction, RangeFraction] = Field(
        description=(
            "The four corners of the range as exact fractions, each a [numerator, denominator] pair "
            "with a numerator of 0 or more and a denominator above 0."
        ),
    )
    corner: bool = Field(strict=True, description="True when the range is a corner of the canvas.")


class CompositionRanges(BaseModel):
    """The composition ranges the server offers for a work."""

    schema_id: Literal["inku.composition-ranges.v1"] = Field(
        alias="schema", description="The schema identifier of this payload. Always inku.composition-ranges.v1.",
    )
    ranges: list[CompositionRange] = Field(description="The composition ranges, in the order the server lists them.")


class CompositionMove(BaseModel):
    """One move of a sentence from one composition range to another."""

    layer: int = Field(ge=0, strict=True, description="The zero-based index of the layer that moves.")
    from_key: str | None = Field(
        default=None, description="The key of the range the layer moves from, or null when not given.",
    )
    from_: str = Field(
        alias="from", min_length=1, description="The display words of the range the layer moves from.",
    )
    to_key: str = Field(min_length=1, description="The key of the range the layer moves to.")
    to: str = Field(min_length=1, description="The display words of the range the layer moves to.")


class RecompositionResult(BaseModel):
    """The answer to a request to recompose a work's layers."""

    mode: Literal["principled", "chance"] = Field(
        description=(
            "How the new composition was chosen: principled (by the rules of the instructions) "
            "or chance (by a seeded random choice among the allowed positions)."
        ),
    )
    outcome: Literal["recomposed", "unchanged"] = Field(
        description="recomposed when the layers were moved, unchanged when they were not.",
    )
    moves: list[CompositionMove] = Field(
        default_factory=list, description="The layer moves made. Empty when the outcome is unchanged.",
    )
    reason: Literal[
        "nothing_to_move", "laws_placed", "not_canonical", "unsupported_sentence", "unplaced_sentence",
        "author_range", "no_other_answer", "same_ranges", "unsolved", "not_canonical_after",
        "binding_unavailable", "invalid_request", "internal_invariant", "internal",
        "invalid_response", "recompose_failed",
    ] | None = Field(
        default=None,
        description=(
            "Why nothing was moved. Required when the outcome is unchanged; null when it is recomposed. "
            "Each value names one reason, such as nothing_to_move or no_other_answer."
        ),
    )
    answer: Literal["near", "next", "chance"] | None = Field(
        default=None,
        description=(
            "Which kind of composition was chosen: near (close to the current one), next (the following "
            "allowed composition) or chance. Required when the outcome is recomposed; null otherwise."
        ),
    )

    @model_validator(mode="after")
    def consistent_outcome(self):
        if self.outcome == "recomposed":
            if not self.moves or self.answer is None or self.reason is not None:
                raise ValueError("a recomposed answer must name its moves and choice")
        elif self.reason is None or self.moves or self.answer is not None:
            raise ValueError("an unchanged answer must give only its reason")
        return self


class HistoryPostBody(BaseModel):
    """The fields a client sends to save a work to history, and the saved fields of a work."""

    input: str = Field(description="The description shown for the work in history: the client's history text when sent, otherwise the description the work was drawn from. The author's own words are in source_text.")
    image_provenance: str | None = Field(
        default=None,
        description=(
            "The Source note of the input image: its source or memo text. "
            "It is shown with the work and is never read as a description. Empty text or null when there is none."
        ),
    )
    image_ddl: dict | None = Field(
        default=None,
        description=(
            "The metadata of the image-derived DDL: the core's JSON record for the image. "
            "It holds metadata only, never image bytes. Null when the work was not made from an image."
        ),
    )
    ddl: str | None = Field(
        default=None,
        description="The saved DDL instructions document of the work. Null when none was saved.",
    )
    ddl_source_origin: Literal["legacy_expanded"] | None = Field(
        default=None,
        description=(
            "Where the saved DDL came from when it was migrated from an older expanded-DDL record: "
            "legacy_expanded. Null for every other work."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def import_legacy_ddl(cls, value):
        """Read old JSON once, without exposing a second text in the API."""
        if isinstance(value, dict) and "expanded_ddl" in value:
            value = dict(value)
            if any(value.get(key) is not None and not isinstance(value[key], str)
                   for key in ("ddl", "expanded_ddl")):
                raise ValueError("legacy DDL texts must be strings or null")
            ddl, origin = select_ddl(value.get("ddl"), value.pop("expanded_ddl"))
            value["ddl"] = ddl
            if origin is not None:
                value["ddl_source_origin"] = origin
        return value

    interpret_fallback: str | None = Field(
        default=None,
        description=(
            "Why the Interpretation fallback was used, when Stage 1 (interpretation) failed and the work "
            "was drawn from fallback instructions. Null when the interpretation held."
        ),
    )
    # Stage 2's counterpart. Three readings, not two: a reason means compose
    # fell over, "none" means a sender said it did not, and NULL means the row
    # predates the column. Stage 1's field cannot say the middle one, which is
    # why only this one is asked to.
    compose_fallback: str | None = Field(
        default=None,
        description=(
            "Why the Score fallback was used, when Stage 2 (score composition) failed. "
            "none means the sender reported that the stage did not fall back. Absent or null on a work "
            "saved before this was recorded."
        ),
    )
    score: dict = Field(description="The JSON Score of the work: the performable instructions that were drawn.")
    svg: str = Field(
        default="",
        description=(
            "The SVG picture of the work. Empty when the picture is not included in the response "
            "or was not saved."
        ),
    )
    at: int = Field(description="When the work was saved, in epoch milliseconds.")
    elapsed_ms: int = Field(
        default=0, description="The total time it took to make the work, in milliseconds. 0 when not recorded.",
    )
    stage1_model: str | None = Field(
        default=None, description="The identifier of the model used for Stage 1 (interpretation). Null if not recorded.",
    )
    stage2_model: str | None = Field(
        default=None,
        description="The identifier of the model used for Stage 2 (score composition). Null if not recorded.",
    )
    tokens_in: int | None = Field(
        default=None, description="The number of input tokens the model reported for the work. Null when not recorded, including for works saved through the pipeline, which do not record token counts.",
    )
    tokens_out: int | None = Field(
        default=None, description="The number of output tokens the model reported for the work. Null when not recorded, including for works saved through the pipeline, which do not record token counts.",
    )
    catalog_id: str | None = Field(
        default=None,
        description="The identifier of the color catalog the work was drawn with, after it was resolved. Null when not recorded, or when the default catalog was used on the direct save route.",
    )
    # How the catalog was asked for (fixed / auto / random), kept beside the
    # resolved id so a work can say whether the author chose one.
    catalog_mode: str | None = Field(
        default=None,
        description=(
            "How the color catalog was requested: fixed, auto or random, as the pipeline writes them. "
            "The value is stored as sent. Null for works saved before this was recorded."
        ),
    )
    ddl_version: str | None = Field(default=None, description="The version of the DDL format the work was saved in.")
    ddl_engine_version: str | None = Field(
        default=None, description="The version of the DDL engine that read the work's instructions.",
    )
    render_build_number: str | None = Field(
        default=None, description="The build number recorded when the work was drawn.",
    )
    render_color_profile: dict[str, str] | None = Field(
        default=None, description="The color profile the work was drawn with, as a map of names to values.",
    )
    render_engine_id: str | None = Field(default=None, description="The identifier of the render engine that drew the work.")
    render_engine_version: str | None = Field(default=None, description="The version of the render engine that drew the work.")
    render_color_catalog_id: str | None = Field(
        default=None, description="The identifier of the color catalog the work was drawn with.",
    )
    render_color_catalog_name: str | None = Field(
        default=None, description="The display name of the color catalog the work was drawn with.",
    )
    render_color_catalog_sub: str | None = Field(
        default=None, description="The secondary (subtitle) label of the color catalog the work was drawn with.",
    )
    render_color_map: dict[str, str] | None = Field(
        default=None,
        description="The color assignments the work was drawn with, as a map from color role to color value.",
    )
    render_canvas_aspect: str | None = Field(
        default=None, description="The canvas aspect the work was drawn on, as recorded.",
    )
    render_canvas_aspect_id: str | None = Field(
        default=None, description="The identifier of the canvas aspect the work was drawn on, normalized.",
    )
    render_canvas_aspect_ratio: float | None = Field(
        default=None, description="The width-to-height ratio of the canvas the work was drawn on.",
    )
    render_seed: JsonSeed | None = Field(
        default=None,
        description=(
            "The seed the work was drawn with. Requests may send a number or a decimal string; "
            "responses send a decimal string. Null when not recorded."
        ),
    )
    render_wild: bool | None = Field(
        default=None,
        description=(
            "Whether the Wild setting was on when the work was drawn. "
            "Null when the work was drawn before the setting was recorded."
        ),
    )
    composition_seed: JsonSeed | None = Field(
        default=None,
        description=(
            "The seed that chose the composition of the work. Requests may send a number or a decimal "
            "string; responses send a decimal string. Null when not recorded."
        ),
    )
    # Stage 0.5 (v2.10). Carried with the work so a redraw replays the same
    # prose instead of asking a non-deterministic layer for it again.
    sketch_text: str | None = Field(
        default=None,
        description="The Sketch from life prose written for the work, reused when the work is redrawn. Null when none.",
    )
    sketch_grain: str | None = Field(
        default=None,
        description="The grain of the Sketch from life step: fine or coarse, in lowercase, as the server writes them. The value is stored as sent. Null when the step did not record one.",
    )
    # What Stage 0.5 did. A client knows its own path, so it may say; an unknown
    # value is a 422 rather than a quiet not_applicable, and an absent one is
    # derived server-side. Only a row older than the column may end up NULL.
    sketch_state: str | None = Field(
        default=None,
        pattern="^(fine|coarse|fallback|off|not_applicable|not_needed|supplemented)$",
        description=(
            "What the Sketch from life step did for the work: fine, coarse, fallback, off, not_applicable, "
            "not_needed or supplemented. A request may send it; when it is omitted the server derives it. "
            "Null only for works saved before this was recorded."
        ),
    )
    source_text: str | None = Field(
        default=None,
        description=(
            "The description text as the author wrote it. Responses fall back to input when it is not stored."
        ),
    )
    display_label: str | None = Field(
        default=None, description="A short label shown for the work in place of its description. Null when none.",
    )
    batch_line_number: int | None = Field(
        default=None, description="The line number of the work within its batch run. Null when it was not a batch work.",
    )
    batch_run_id: str | None = Field(
        default=None, description="The identifier of the batch run the work belongs to. Null when it was not a batch work.",
    )
    history_visibility: str = Field(
        default="normal",
        description=(
            "Where the work is listed: normal (in the history) or lineage_only (kept in the lineage "
            "without being listed in the history). Omitting it means normal."
        ),
    )
    lineage_parent_node_id: str | None = Field(
        default=None,
        description="The identifier of the lineage node of the work this one was derived from. Null for an origin work.",
    )
    # Request-only: save the current performance of an authorized saved work.
    replay_work_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        exclude=True,
        description=(
            "Request only, not returned. The identifier of a saved work whose current performance is "
            "replayed to save a new copy. Only the owner or an authorized reader can name a work."
        ),
    )
    replay_render_hash: str | None = Field(
        default=None,
        pattern="^rh3:[0-9a-f]{64}$",
        exclude=True,
        description=(
            "Request only, not returned. The render hash (rh3: followed by 64 lowercase hex digits) "
            "that the replayed performance must match."
        ),
    )
    replay_svg_sha256: str | None = Field(
        default=None,
        pattern="^[0-9a-f]{64}$",
        exclude=True,
        description=(
            "Request only, not returned. The SHA-256 of the SVG (64 lowercase hex digits) that the "
            "replayed performance must match."
        ),
    )
    derivation_kind: str | None = Field(
        default=None,
        description=(
            "How the work was derived from its parent, such as ddl_edit or description_edit. "
            "Null for an origin work."
        ),
    )
    derivation_metadata: dict[str, object] = Field(
        default_factory=dict,
        description="Extra details of the derivation from the parent work. An empty object when there are none.",
    )
    instruction_lang_requested: str | None = Field(
        default=None, description="The instruction language the client asked for. Null when none was asked for.",
    )
    instruction_lang_resolved: str | None = Field(
        default=None, description="The instruction language the server actually used. Null when not recorded.",
    )
    ui_lang: str | None = Field(
        default=None, description="The language of the user interface when the work was saved. Null when not recorded.",
    )
    save_artifacts: bool = Field(
        default=True,
        description="Request only in practice: whether the server writes the work's output files to storage when it is saved. True by default. Responses always show true; they do not report whether files were written.",
    )
    count_generation: bool = Field(
        default=False,
        exclude=True,
        description=(
            "Request only, not returned. True to count this save toward the user's image generation count. "
            "Defaults to False."
        ),
    )
    color_map: dict[str, str] | None = Field(default=None, exclude=True, description="Deprecated: ignored; catalog_id is resolved server-side")
    canvas_aspect: str | None = Field(
        default=None,
        exclude=True,
        description=(
            "Request only, not returned. The canvas aspect to draw the work on. It replaces the Score's "
            "canvas for this save. Omit it to use the Score's own canvas."
        ),
    )


class HistoryItem(HistoryPostBody):
    """A saved work as the history listing and the work endpoints return it."""

    id: str = Field(description="The identifier of the work, a UUID.")
    # Read-only: the Python Stage 1/2 recorded these until the shared core took
    # over (2026-09-14). The core's prompt digest lives in the execution record.
    stage1_prompt_digest: str | None = Field(
        default=None,
        description="Read-only. A digest of the Stage 1 prompt recorded for an older work. Not written for new works. Null when absent.",
    )
    stage1_prompt_base_digest: str | None = Field(
        default=None,
        description="Read-only. A digest of the base Stage 1 prompt recorded for an older work. Not written for new works. Null when absent.",
    )
    stage2_prompt_digest: str | None = Field(
        default=None,
        description="Read-only. A digest of the Stage 2 prompt recorded for an older work. Not written for new works. Null when absent.",
    )
    # Read-only historical metadata: new authoring no longer records variation.
    focus: str | None = Field(
        default=None,
        description="Read-only. The focus recorded for an older work. Not written for new works. Null when absent.",
    )
    variation_amplitude: str | None = Field(
        default=None,
        description="Read-only. The variation amplitude recorded for an older work. Not written for new works.",
    )
    variation_seed: int | None = Field(
        default=None,
        description="Read-only. The variation seed recorded for an older work. Not written for new works.",
    )
    # The words a touch was refined by, and the identifier of an explicit
    # reading, on works refined that way before both were removed (2026-10-14).
    # A save no longer carries them.
    seed_text: str | None = Field(
        default=None,
        description="Read-only. The words a touch was refined by, for older works refined that way. Not written for new works.",
    )
    interpretation_seed: str | None = Field(
        default=None,
        description="Read-only. The identifier of an explicit reading, for older works that recorded one. Not written for new works, except that a replay save carries it over from its parent work.",
    )
    pipeline_variation_id: str | None = Field(
        default=None,
        description="The identifier of the authoring record (variation) this work was saved from. Null when there is none.",
    )
    # True when the work is held by its DDL (edited, or derived from an edited
    # work without reading the description again): it is not redrawn from its
    # description; a new variation from the description is the way back.
    description_locked: bool = Field(
        default=False,
        description=(
            "True when the work is held by its DDL: it was edited, derived from an edited work, drawn from DDL "
            "authority, or written from an image. Such a work is not redrawn from its description. "
            "Computed in listings; a save response reports false."
        ),
    )
    pipeline_revision: str | None = Field(
        default=None,
        description="The revision of the authoring record this work was saved from, as a decimal string. Null when there is none.",
    )
    # Raw core and renderer diagnostics frozen with this exact saved performance.
    # None means the work predates this record; empty arrays mean the recorded
    # performance had no diagnostics in that channel.
    pipeline_diagnostics: dict[str, object] | None = Field(
        default=None,
        description=(
            "The core and renderer diagnostics saved with this exact performance. Null when the work "
            "predates this record. Empty arrays mean there were no diagnostics."
        ),
    )
    # The work's own weight in UTF-8 bytes, sent whether or not the picture is.
    # The listing that draws the strip asks for `include_svg=false`, so a client
    # cannot count this for itself: what arrives in `svg` is then an empty
    # string, and measuring it would report every work as nothing.
    #
    # It belongs here and not on HistoryPostBody, which this inherits from: the
    # weight is something the server reports about a stored work, never
    # something a caller states when saving one.
    svg_bytes: int = Field(
        default=0,
        description="The size of the work's SVG in UTF-8 bytes, computed by the listing endpoints even when the svg field is left out. A save response reports 0.",
    )
    output_path: str | None = Field(
        default=None,
        description="The storage path prefix where the work's output files are written. Set for every new work, even when no files were written (for example, when output saving is off). Null for older works without one.",
    )
    # True when this work is somebody else's, reached through a group scope or an
    # explicit grant. Absent (not false) for one's own, so the ordinary listing
    # is unchanged on the wire; a client that never learned the field sees what
    # it always saw.
    shared: bool | None = Field(
        default=None,
        description=(
            "True when the work belongs to another user and reached the caller through a group or a grant. "
            "Absent for the caller's own works."
        ),
    )
    # Whether this owner has granted access to anyone through this work's ACL.
    # Omitted for works owned by somebody else; their guest list is private.
    has_acl_shares: bool | None = Field(
        default=None,
        description=(
            "True when the owner has granted access to this work to at least one person. "
            "Absent for works owned by somebody else."
        ),
    )
    # The staffage level a work was drawn at. The axis was folded away in
    # v2.11.0 and nothing writes this any more, so it is declared on the
    # RESPONSE model and not on the post body: a work saved before the removal
    # still reports the conditions it was drawn under, and no client can set it.
    tenkei: str | None = Field(
        default=None,
        description="Read-only. The staffage level a work was drawn at, for works saved before that axis was removed.",
    )
    # The limits that governed this work. Present only when the row recorded
    # them; absent means "drawn before they were recorded", not "the defaults".
    render_limits: dict[str, int] | None = Field(
        default=None,
        description=(
            "The drawing limits that governed the work, as a map from limit name to integer. "
            "Absent when the work was drawn before the limits were recorded."
        ),
    )
    render_hash: str | None = Field(
        default=None,
        description="The render hash that identifies the drawing (rh3: followed by 64 lowercase hex digits).",
    )
    render_hash_short: str | None = Field(
        default=None,
        description="The last four characters of render_hash, in uppercase. Null when render_hash is null.",
    )
    trashed: bool = Field(default=False, description="True when the work is in the trash.")
    starred: bool = Field(default=False, description="True when the owner has starred the work.")
    # The revision mark, independent of starred.
    for_revision: bool = Field(
        default=False,
        description="True when the work is marked for revision. This mark is independent of starred.",
    )
    # The share bit and where it points. Unlike `shared`, which says this work
    # reached the caller from somebody else, these two are what the OWNER set:
    # the bit is a permission and the group is its destination, and a reader who
    # saw only the bit would not know who else is looking.
    for_share: bool = Field(
        default=False,
        description="True when the owner has opened the work to its share group. False when it is not shared.",
    )
    share_group_id: str | None = Field(
        default=None,
        description="The identifier of the user group the work is shared with. Null when it is not shared.",
    )
    note: str | None = Field(default=None, description="The owner's free-text note on the work. Null when there is none.")
    description_hash: str | None = Field(
        default=None, description="A hash of the description the work was made from, used to find works with the same description.",
    )
    lineage_node_id: str | None = Field(
        default=None, description="The identifier of the lineage node that records this work. Null when there is none.",
    )
    lineage_root_node_id: str | None = Field(
        default=None, description="The identifier of the root node of the work's lineage. Null when there is none. Not included in a save response.",
    )
    lineage_generation: int | None = Field(
        default=None,
        ge=1,
        description="The generation of the work in its lineage, counted from the root as 1. Null when there is no lineage. Not included in a save response.",
    )
    lineage_state: Literal["active", "lineage_only", "tombstone"] | None = Field(
        default=None,
        description=(
            "The state of the work's lineage node: active (the work is listed), lineage_only (kept in the "
            "lineage but not listed) or tombstone (the work was deleted and only its node remains). "
            "Not included in a save response."
        ),
    )
    data_warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Warnings about stored data that could not be read in full, such as score_json_invalid. "
            "An empty list when there are none."
        ),
    )


class HistoryListResponse(BaseModel):
    """One page of the history listing."""

    items: list[HistoryItem] = Field(description="The works on this page, in listing order.")
    total: int = Field(description="The total number of works that match the listing, across all pages.")
    offset: int = Field(description="The number of works skipped before this page.")
    limit: int = Field(description="The maximum number of works requested for this page.")


class UserAccountItem(BaseModel):
    """A user account as the account endpoints return it, with its settings."""

    id: str = Field(description="The identifier of the user account.")
    username: str = Field(description="The user's sign-in name.")
    email: str = Field(description="The user's email address.")
    permission_groups: list[str] = Field(
        description="The permission groups the user belongs to, by identifier: admins, leaders or users.",
    )
    permission_group_labels: list[str] = Field(
        description="The display names of the user's permission groups, in the same order as permission_groups.",
    )
    group_id: str | None = Field(default=None, description="The identifier of the user group the user belongs to. Null when none.")
    group_name: str | None = Field(default=None, description="The name of the user group the user belongs to. Null when none.")
    ui_theme: str = Field(default="dark", description="The color theme of the interface: light or dark.")
    ui_mode: str = Field(
        default="simple",
        description="The interface preset: simple, full or custom. Custom uses the ui_custom flags.",
    )
    ui_custom: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "For the custom interface mode, a map from each interface section name to whether it is shown. "
            "The names are input_modes, drawing_settings, ddl_tools, detail_status, work_tools, history and auxiliary."
        ),
    )
    # What the history strip prints under each thumbnail. The default matches
    # what it printed before it could be asked; an empty list means the reader
    # asked for nothing, and is not the same as the field being absent.
    history_strip_fields: list[str] = Field(
        default_factory=lambda: ["generation", "model"],
        description=(
            "The facts printed under each history thumbnail, in display order: generation, model, "
            "engine_version and bytes, at most three. An empty list means nothing is printed."
        ),
    )
    tooltips_enabled: bool = Field(default=True, description="Whether the interface shows tooltips.")
    download_folder_enabled: bool = Field(default=False, description="Whether downloads go to a named folder.")
    download_folder_name: str | None = Field(
        default=None, description="The name of the folder downloads go to when download_folder_enabled is true.",
    )
    settings_tab: str = Field(
        default="db",
        description=(
            "The settings tab the interface opens first: chatgpt, models, db, plugins, users, export, demo, "
            "misc, server_misc, logs or limits."
        ),
    )
    model_settings: dict = Field(
        default_factory=dict, description="The user's own model choices, as a free-form object. Empty when none are set.",
    )
    image_generation_count: int = Field(
        default=0, description="The number of images the user has generated and counted so far.",
    )
    at: int = Field(description="The time of the account record, in epoch milliseconds.")


def _model_label_table() -> list[dict]:
    from ..model_catalog import MODEL_LABELS
    return [dict(label) for label in MODEL_LABELS]


class ModelSettingsResponse(BaseModel):
    """The model catalog and the model settings the interface needs."""

    # The label table of the model catalog (model_catalog.json), in fold order: what each label
    # of a model is called and whether it lets the model be published. Every model in the lists
    # carries its `labels` and the `fold` it is filed in.
    model_labels: list[dict] = Field(
        default_factory=_model_label_table,
        description=(
            "The label table of the model catalog, in fold order. Each entry says what a label is called "
            "and whether it lets the model be published."
        ),
    )
    catalog: list[dict] = Field(
        default_factory=list,
        description="The model providers and their models, as the model settings page lists them.",
    )
    llm_catalog: list[dict] = Field(
        default_factory=list, description="The model providers and their models for drawing instructions (LLM purpose).",
    )
    vision_catalog: list[dict] = Field(
        default_factory=list, description="The model providers and their models for reading images (vision purpose).",
    )
    drawing_catalog: list[dict] = Field(
        default_factory=list, description="The model providers and their models for drawing (LLM purpose).",
    )
    chatgpt_profile_id: str | None = Field(
        default=None, description="The identifier of the caller's ChatGPT plan profile. Null when there is none.",
    )
    chatgpt_generation: int | None = Field(
        default=None, description="The generation number of the ChatGPT plan profile. Null when there is none.",
    )
    chatgpt_plan_available: bool = Field(
        default=False, description="True when the caller can use a ChatGPT plan for models.",
    )
    settings: dict = Field(
        default_factory=dict, description="The model settings, as a free-form object. Empty when none are set.",
    )
