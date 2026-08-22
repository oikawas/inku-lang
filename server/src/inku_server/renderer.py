"""JSON Score → SVG renderer.

楽譜(Score)を演奏(SVG)に変換する。揺らぎ(variation)の実現は Renderer 層で行う
(SPEC §13.8)。Phase 1 は静的描画のみ、perlin/wave は段階追加。
"""

from __future__ import annotations

import logging
import math

import svgwrite

from .cloudform import generate_cloudform_contour, sample_closed_catmull_rom
from .color_catalogs import DEFAULT_COLOR_CATALOG_ID as DEFAULT_COLOR_CATALOG_ID
from .master_grid import fmt
from .plugins import CanvasSize, canvas_size_for_aspect
from .schema import (
    Instruction,
    Score,
)
from .render_engines.default.determinism import (
    _SEED_ARRANGEMENT_FIELDS as _SEED_ARRANGEMENT_FIELDS,
    _SEED_INSTRUCTION_FIELDS as _SEED_INSTRUCTION_FIELDS,
    _VARIATION_SEED_FIELDS_ALL as _VARIATION_SEED_FIELDS_ALL,
    _WORK_COLOR_SEED_FIELDS as _WORK_COLOR_SEED_FIELDS,
    _hash01,
    _needs_blur,
    _needs_contour_variation,
    _seed_for_instruction,
    _variation_seed_fields as _variation_seed_fields,
    new_render_seed as new_render_seed,
)
from .render_engines.default import planning as _planning
from .render_engines.default import document as _document
from .render_engines.default import palette as _palette
from .render_engines.default import layers as _layers
from .render_engines.default import surfaces as _surfaces
from .render_engines.default import marks as _marks
from .svg_compat import validate_compat_svg
from .stroke_engine import (
    Support,
)

logger = logging.getLogger(__name__)

CANVAS_PX = _marks.CANVAS_PX
WEIGHT_TO_STROKE_WIDTH = _marks.WEIGHT_TO_STROKE_WIDTH
THINNESS_TO_WIDTH_SCALE = _marks.THINNESS_TO_WIDTH_SCALE
MIN_STROKE_WIDTH = _marks.MIN_STROKE_WIDTH
STYLE_TO_DASH = _marks.STYLE_TO_DASH
WEIGHT_STYLE = _marks.WEIGHT_STYLE
AMPLITUDE_WIDTHS = _marks.AMPLITUDE_WIDTHS
MATERIAL_OUTLINE_MAX_WIDTH_RATIO = _marks.MATERIAL_OUTLINE_MAX_WIDTH_RATIO
FREQUENCY_CYCLES = _marks.FREQUENCY_CYCLES
BLUR_RATIO = _marks.BLUR_RATIO
BLUR_MIN_RATIO = _marks.BLUR_MIN_RATIO
REPRESENTATIVE_MIN_RATIO = _marks.REPRESENTATIVE_MIN_RATIO
AMPLITUDE_CLAMP_RATIO = _marks.AMPLITUDE_CLAMP_RATIO
PRIMITIVE_AMP_GAIN = _marks.PRIMITIVE_AMP_GAIN
SEGMENT_TARGET_RATIO = _marks.SEGMENT_TARGET_RATIO
SEGMENT_COUNT_MIN = _marks.SEGMENT_COUNT_MIN
SEGMENT_COUNT_MAX = _marks.SEGMENT_COUNT_MAX
STROKE_SAMPLE_TARGET_RATIO = _marks.STROKE_SAMPLE_TARGET_RATIO
STROKE_SAMPLE_MIN = _marks.STROKE_SAMPLE_MIN
STROKE_SAMPLE_MAX = _marks.STROKE_SAMPLE_MAX
MATERIAL_INTENSITY = _marks.MATERIAL_INTENSITY
MATERIAL_INTENSITY_LEVEL = _marks.MATERIAL_INTENSITY_LEVEL
SPECK_ANCHOR_PERIMETER_RATIO = _marks.SPECK_ANCHOR_PERIMETER_RATIO
SPECK_COUNT_MIN = _marks.SPECK_COUNT_MIN
SPECK_COUNT_MAX_GAIN = _marks.SPECK_COUNT_MAX_GAIN
TEXTURE_SPECS = _marks.TEXTURE_SPECS
TEXTURE_FILTER_WEIGHTS = _marks.TEXTURE_FILTER_WEIGHTS
_material_gain = _marks._material_gain
_outline_wander_px = _marks._outline_wander_px
_outline_offset_px = _marks._outline_offset_px
_outline_opacity = _marks._outline_opacity
_unit_scale = _marks._unit_scale
_stroke_width_px = _marks._stroke_width_px
WASH_MARK_WIDTH_GAIN = _marks.WASH_MARK_WIDTH_GAIN
WASH_MARK_OPACITY_GAIN = _marks.WASH_MARK_OPACITY_GAIN
_is_wash_mark = _marks._is_wash_mark
_mark_width_gain = _marks._mark_width_gain
_mark_width_px = _marks._mark_width_px
_nominal_mark_width_px = _marks._nominal_mark_width_px
_grid_step_px = _marks._grid_step_px
_speck_count = _marks._speck_count
_speck_opacity = _marks._speck_opacity
_GRID_ATTR_RE = _marks._GRID_ATTR_RE
_GRID_NUM_RE = _marks._GRID_NUM_RE
_UNGRIDDED_ATTRS = _marks._UNGRIDDED_ATTRS
_apply_master_grid = _marks._apply_master_grid
_scale_dash = _marks._scale_dash
_texture_filter_xml = _marks._texture_filter_xml
SOLID_MOTTLE_BASE_FREQUENCY = _marks.SOLID_MOTTLE_BASE_FREQUENCY
SOLID_MOTTLE_NUM_OCTAVES = _marks.SOLID_MOTTLE_NUM_OCTAVES
SOLID_MOTTLE_ALPHA_FLOOR = _marks.SOLID_MOTTLE_ALPHA_FLOOR
SOLID_MOTTLE_OVERLAY_OPACITY = _marks.SOLID_MOTTLE_OVERLAY_OPACITY
_solid_mottle_filter_id = _marks._solid_mottle_filter_id
_solid_mottle_filter_xml = _marks._solid_mottle_filter_xml
_performance_touch_filter = _marks._performance_touch_filter
_ellipse_perimeter = _marks._ellipse_perimeter
_representative_size_px = _marks._representative_size_px
_clamped_representative_px = _marks._clamped_representative_px
_amplitude_px = _marks._amplitude_px
_blur_std_px = _marks._blur_std_px
_segment_count = _marks._segment_count
_stroke_sample_count = _marks._stroke_sample_count
_sample_offset = _marks._sample_offset
_line_with_variation = _marks._line_with_variation
_sample_offset_periodic = _marks._sample_offset_periodic
_offset_contour_point = _marks._offset_contour_point
_closed_contour_with_variation = _marks._closed_contour_with_variation
_edge_contour_with_anchors = _marks._edge_contour_with_anchors
_edge_contour_with_variation = _marks._edge_contour_with_variation
_arc_points_with_variation = _marks._arc_points_with_variation
_instruction_support = _marks._instruction_support
_CLOSED_SHAPES = _marks._CLOSED_SHAPES
_texture_filter_weights = _marks._texture_filter_weights
_stroke_attrs = _marks._stroke_attrs
_copy_attrs = _marks._copy_attrs
_line_direction = _marks._line_direction
_offset_polyline = _marks._offset_polyline
_dash_spec_stats = _marks._dash_spec_stats
_contact_field = _marks._contact_field
CONTACT_LENGTH_QUANTUM = _marks.CONTACT_LENGTH_QUANTUM
_quantise_contact_length = _marks._quantise_contact_length
_resample_by_length = _marks._resample_by_length
_contact_fragments = _marks._contact_fragments
_polyline_sample = _marks._polyline_sample
_add_powder_specks = _marks._add_powder_specks
_add_specks_at_points = _marks._add_specks_at_points
_circle_points = _marks._circle_points
_rect_points = _marks._rect_points
_arc_points = _marks._arc_points
_polygon_points = _marks._polygon_points
_outline_attrs = _marks._outline_attrs
_MATERIAL_OUTLINE_SPECS = _marks._MATERIAL_OUTLINE_SPECS
_SPECK_SPECS = _marks._SPECK_SPECS
_material_outline_profile = _marks._material_outline_profile
_speck_profile = _marks._speck_profile
_uses_material_outline = _marks._uses_material_outline
_add_material_circle_outline = _marks._add_material_circle_outline
_add_material_ellipse_outline = _marks._add_material_ellipse_outline
_add_material_rect_outline = _marks._add_material_rect_outline
_add_material_arc_outline = _marks._add_material_arc_outline
_resample_points = _marks._resample_points
_offset_performed_path = _marks._offset_performed_path
_closed_path_length = _marks._closed_path_length
_points_center = _marks._points_center
_add_material_performed_outline = _marks._add_material_performed_outline
RASTER_BLEED_OPACITY = _marks.RASTER_BLEED_OPACITY
_add_raster_bleed = _marks._add_raster_bleed
_material_line_group = _marks._material_line_group
_px = _marks._px
_size_px = _marks._size_px
_apply_rotation = _marks._apply_rotation
_arc_path_d = _marks._arc_path_d
_render_hand_stroke = _marks._render_hand_stroke
_uses_hand_stroke = _marks._uses_hand_stroke
_body_attrs_for_contour_stroke = _marks._body_attrs_for_contour_stroke
FILL_SPACING_WIDTH_GAIN = _marks.FILL_SPACING_WIDTH_GAIN
FILL_SPACING_UNIT_RATIO = _marks.FILL_SPACING_UNIT_RATIO
FILL_SPACING_JITTER = _marks.FILL_SPACING_JITTER
FILL_MIN_SCANLINES = _marks.FILL_MIN_SCANLINES
FILL_MIN_STROKE_WIDTHS = _marks.FILL_MIN_STROKE_WIDTHS
FILL_COVERAGE_BRANCH = _marks.FILL_COVERAGE_BRANCH
FILL_COVERAGE_TARGET = _marks.FILL_COVERAGE_TARGET
FILL_UNDERLAY_OPACITY_RATIO = _marks.FILL_UNDERLAY_OPACITY_RATIO
FILL_ANGLE_MIN_DEG = _marks.FILL_ANGLE_MIN_DEG
FILL_ANGLE_SPAN_DEG = _marks.FILL_ANGLE_SPAN_DEG
FILL_PITCH_CV_MIN = _marks.FILL_PITCH_CV_MIN
FILL_PITCH_CV_SPAN = _marks.FILL_PITCH_CV_SPAN
FILL_REACH_WIDTHS_MIN = _marks.FILL_REACH_WIDTHS_MIN
FILL_REACH_WIDTHS_SPAN = _marks.FILL_REACH_WIDTHS_SPAN
FILL_TEXTURE_DENSITY = _marks.FILL_TEXTURE_DENSITY
FILL_TEXTURE_CONTRAST = _marks.FILL_TEXTURE_CONTRAST
FILL_TEXTURE_TONE_SPREAD = _marks.FILL_TEXTURE_TONE_SPREAD
FILL_FIELD_TONE_DROP = _marks.FILL_FIELD_TONE_DROP
FILL_FIELD_TONE_LAYERS = _marks.FILL_FIELD_TONE_LAYERS
FILL_FIELD_TONE_RINGS = _marks.FILL_FIELD_TONE_RINGS
FILL_FIELD_TONE_RING_STEP = _marks.FILL_FIELD_TONE_RING_STEP
FILL_FIELD_TONE_COUNT_MIN = _marks.FILL_FIELD_TONE_COUNT_MIN
FILL_FIELD_TONE_COUNT_SPAN = _marks.FILL_FIELD_TONE_COUNT_SPAN
FILL_FIELD_TONE_RADIUS_MIN = _marks.FILL_FIELD_TONE_RADIUS_MIN
FILL_FIELD_TONE_RADIUS_SPAN = _marks.FILL_FIELD_TONE_RADIUS_SPAN
FILL_FIELD_TONE_INSET = _marks.FILL_FIELD_TONE_INSET
FILL_FIELD_TONE_WOBBLE = _marks.FILL_FIELD_TONE_WOBBLE
FILL_FIELD_TONE_ROUGHNESS = _marks.FILL_FIELD_TONE_ROUGHNESS
FILL_FIELD_TONE_SEGMENTS = _marks.FILL_FIELD_TONE_SEGMENTS
FILL_SCAN_CONTRAST = _marks.FILL_SCAN_CONTRAST
FILL_RASTER_HALO_WIDTHS = _marks.FILL_RASTER_HALO_WIDTHS
FILL_RASTER_HALO_STEP = _marks.FILL_RASTER_HALO_STEP
FILL_RASTER_CORE_WIDTHS = _marks.FILL_RASTER_CORE_WIDTHS
_fill_scan_angle = _marks._fill_scan_angle
_fill_scan_spacing = _marks._fill_scan_spacing
_fill_coverage = _marks._fill_coverage
_fill_takes_scan_branch = _marks._fill_takes_scan_branch
_fill_hand = _marks._fill_hand
_fill_contrast = _marks._fill_contrast
_fill_angle_amplitude = _marks._fill_angle_amplitude
_fill_is_scannable = _marks._fill_is_scannable
_polygon_area = _marks._polygon_area
_field_tone_patches = _marks._field_tone_patches
_field_tones = _marks._field_tones
_wobbly_blob = _marks._wobbly_blob
_clamp_inside = _marks._clamp_inside
_fill_underlay = _marks._fill_underlay
_is_noncomputer_solid_fill = _marks._is_noncomputer_solid_fill
_render_solid_mottle_fill = _marks._render_solid_mottle_fill
_fill_stroke_seed = _marks._fill_stroke_seed
_scanline_segments = _marks._scanline_segments
_line_spans = _marks._line_spans
_raster_band = _marks._raster_band
_render_fill_strokes = _marks._render_fill_strokes
_render_fill_texture = _marks._render_fill_texture
FILL_DAB_SAMPLES = _marks.FILL_DAB_SAMPLES
FILL_DAB_MIN_TRAVEL = _marks.FILL_DAB_MIN_TRAVEL
_render_fill_dab = _marks._render_fill_dab
_interior_fill = _marks._interior_fill
_render_contour_hand_stroke = _marks._render_contour_hand_stroke
_render_arc_hand_stroke = _marks._render_arc_hand_stroke
_render_corner_shape = _marks._render_corner_shape

COLOR_MAP = _palette.COLOR_MAP
SVG_PROFILES = _document.SVG_PROFILES
HUE_HINTS = _palette.HUE_HINTS

BACKGROUND = "#ffffff"

FRAME_LO = _planning.FRAME_LO
FRAME_HI = _planning.FRAME_HI
_scatter_pos = _planning._scatter_pos
_rhythm_t = _planning._rhythm_t
_PATH_WAVE_AMPLITUDE = _planning._PATH_WAVE_AMPLITUDE
_PATH_JITTER = _planning._PATH_JITTER
_PATH_SPREAD = _planning._PATH_SPREAD
_path_pos = _planning._path_pos
_density_radius = _planning._density_radius
_clustered_pos = _planning._clustered_pos
_clamp01 = _planning._clamp01
_ensure_line_coords = _planning._ensure_line_coords
_anchor = _planning._anchor
_shift = _planning._shift
_apply_color_cycle = _planning._apply_color_cycle
_strip_performance_fields = _planning._strip_performance_fields
_move_anchor_to = _planning._move_anchor_to
_short_side_scales = _planning._short_side_scales
_region_in_short_side_units = _planning._region_in_short_side_units
_resolve_at_region = _planning._resolve_at_region
_bbox_for_instruction = _planning._bbox_for_instruction
_bbox_center = _planning._bbox_center
_bbox_radius = _planning._bbox_radius
_relation_gap = _planning._relation_gap
_rotate_screen_point = _planning._rotate_screen_point
_rotate_screen_vector = _planning._rotate_screen_vector
_canvas_endpoint_geometry = _planning._canvas_endpoint_geometry
_performed_arc_sagitta = _planning._performed_arc_sagitta
_dropped_relation = _planning._dropped_relation
_resolve_touching_relation = _planning._resolve_touching_relation
_resolve_relation = _planning._resolve_relation
_instruction_extent = _planning._instruction_extent
_scale_instruction = _planning._scale_instruction
_composite_member_copy = _planning._composite_member_copy
_expand_composite_groups = _planning._expand_composite_groups
_resolve_performance_score = _planning._resolve_performance_score
_render_effect_hint = _palette._render_effect_hint
_FADE_NEAR_FAR = _planning._FADE_NEAR_FAR
_FADE_FILL_RATIO = _planning._FADE_FILL_RATIO
_FADE_SPAN_EPS = _planning._FADE_SPAN_EPS
_FADE_LEVEL_RE = _planning._FADE_LEVEL_RE
_FADE_LEVEL_TAG_RE = _planning._FADE_LEVEL_TAG_RE
_fade_levels = _planning._fade_levels
_apply_fade_levels = _planning._apply_fade_levels
_scale_member = _planning._scale_member
_turn_member = _planning._turn_member
_apply_member_sizes = _planning._apply_member_sizes
_apply_member_rotations = _planning._apply_member_rotations
_finish_expanded_group = _planning._finish_expanded_group
_fade_level_from_hint = _planning._fade_level_from_hint
_strip_fade_level = _planning._strip_fade_level
_expand_arrangement_layout = _planning._expand_arrangement_layout
_fit_axis_scales = _planning._fit_axis_scales
_fit_group_to_anchor = _planning._fit_group_to_anchor
ARRANGEMENT_QUANTUM = _planning.ARRANGEMENT_QUANTUM
_quantise = _planning._quantise
_quantise_instructions = _planning._quantise_instructions
_expand_arrangement = _planning._expand_arrangement
_norm_label = _palette._norm_label
_line_perp_offsets = _planning._line_perp_offsets
_point_on_line = _planning._point_on_line


def _inject_blur_filters(
    svg: str,
    blur_needed: dict[str, float],
    blur_elems: list[tuple[str, str]],
) -> str:
    """feGaussianBlur フィルター定義を defs に注入し、対象要素に filter 属性を付与する。

    blur_needed の key は filter id (振幅名 + std 値)。滲みは図形寸法比なので
    同じ振幅語でも図形ごとに std が変わる。
    """
    filter_xml = "".join(
        f'<filter id="{filter_id}" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="{fmt(std)}"/>'
        f"</filter>"
        for filter_id, std in sorted(blur_needed.items())
    )
    # svgwrite は "<defs />" を出力する (スペースあり)
    if "<defs />" in svg:
        svg = svg.replace("<defs />", f"<defs>{filter_xml}</defs>", 1)
    elif "<defs/>" in svg:
        svg = svg.replace("<defs/>", f"<defs>{filter_xml}</defs>", 1)
    else:
        svg = svg.replace("<defs>", f"<defs>{filter_xml}", 1)

    for eid, filter_id in blur_elems:
        id_start = svg.find(f'id="{eid}"')
        if id_start < 0:
            continue
        tag_start = svg.rfind("<", 0, id_start)
        tag_end = svg.find(">", id_start)
        if tag_start < 0 or tag_end < 0:
            continue
        if ' filter="' in svg[tag_start:tag_end]:
            continue
        svg = svg.replace(
            f'id="{eid}"', f'id="{eid}" filter="url(#{filter_id})"', 1
        )
    return svg


def _inject_texture_filters(
    svg: str, filters: set[str], canvas: CanvasSize
) -> str:
    if not filters:
        return svg
    filter_xml = "".join(
        _texture_filter_xml(weight, canvas) for weight in sorted(filters)
    )
    if "<defs />" in svg:
        return svg.replace("<defs />", f"<defs>{filter_xml}</defs>", 1)
    if "<defs/>" in svg:
        return svg.replace("<defs/>", f"<defs>{filter_xml}</defs>", 1)
    return svg.replace("<defs>", f"<defs>{filter_xml}", 1)


_score_canvas_aspect = _document._score_canvas_aspect
_score_canvas_ground = _document._score_canvas_ground


_score_support = _layers._score_support


_texture_seed = _layers._texture_seed
_ground_tone_color = _layers._ground_tone_color
_GROUND_MM = _layers._GROUND_MM
_GROUND_GRAIN_RADIUS = _layers._GROUND_GRAIN_RADIUS
_GROUND_OPACITY_DEFAULT = _layers._GROUND_OPACITY_DEFAULT
_GROUND_DENSITY_DEFAULT = _layers._GROUND_DENSITY_DEFAULT
GROUND_BYTE_BUDGET = _layers.GROUND_BYTE_BUDGET
_MEZZOTINT_PLATE = _layers._MEZZOTINT_PLATE
_ground_mm = _layers._ground_mm
_GroundRandom = _layers._GroundRandom
_ground_wrapped = _layers._ground_wrapped
_paper_ground_layers = _layers._paper_ground_layers
_washi_ground_layers = _layers._washi_ground_layers
_ink_wash_ground_layers = _layers._ink_wash_ground_layers
_charcoal_ground_layers = _layers._charcoal_ground_layers
_canvas_ground_layers = _layers._canvas_ground_layers
_drawing_paper_ground_layers = _layers._drawing_paper_ground_layers
_mezzotint_ground_layers = _layers._mezzotint_ground_layers
_PAPER_COARSE_TILES = _layers._PAPER_COARSE_TILES
_PAPER_COARSE_RADIUS = _layers._PAPER_COARSE_RADIUS
_GROUND_LAYER_BUILDERS = _layers._GROUND_LAYER_BUILDERS
_render_canvas_ground = _layers._render_canvas_ground


SurfaceMarkStyle = _surfaces.SurfaceMarkStyle
_SURFACE_MARK_STYLE = SurfaceMarkStyle(
    mark_width_px=_mark_width_px,
    weight_style=WEIGHT_STYLE,
    texture_filter_weights=TEXTURE_FILTER_WEIGHTS,
)
MarkSurfaceOps = _marks.MarkSurfaceOps
_MARK_SURFACE_OPS = MarkSurfaceOps(
    fills_interior=_surfaces._fills_interior,
    scatter=_surfaces._surface_scatter,
)
SURFACE_MARK_MAX = _surfaces.SURFACE_MARK_MAX
HATCH_SPAN_SEED_STRIDE = _surfaces.HATCH_SPAN_SEED_STRIDE
SURFACE_DAB_SAMPLES = _surfaces.SURFACE_DAB_SAMPLES
SURFACE_WASH_LAYERS = _surfaces.SURFACE_WASH_LAYERS
SURFACE_WASH_WIDTH_BASE = _surfaces.SURFACE_WASH_WIDTH_BASE
SURFACE_WASH_WIDTH_SPAN = _surfaces.SURFACE_WASH_WIDTH_SPAN
SURFACE_WASH_OPACITY = _surfaces.SURFACE_WASH_OPACITY
SURFACE_BLEED_RINGS = _surfaces.SURFACE_BLEED_RINGS
_surface_seed = _surfaces._surface_seed
_surface_grain_seed = _surfaces._surface_grain_seed
_shape_bbox = _surfaces._shape_bbox
_surface_contour = _surfaces._surface_contour
_point_in_polygon = _surfaces._point_in_polygon
_surface_color = _surfaces._surface_color
_surface_line_angle = _surfaces._surface_line_angle
_surface_stroke_seed = _surfaces._surface_stroke_seed
_surface_scatter = _surfaces._surface_scatter
_surface_dab = _surfaces._surface_dab
_surface_grain_pattern_id = _surfaces._surface_grain_pattern_id
_surface_grain_logical_mark_count = _surfaces._surface_grain_logical_mark_count
_surface_grain_carrier_path = _surfaces._surface_grain_carrier_path
_surface_grain_wrap_offsets = _surfaces._surface_grain_wrap_offsets
_render_surface_grain_pattern = _surfaces._render_surface_grain_pattern
_surface_sweep = _surfaces._surface_sweep
_render_surface_vectors = _surfaces._render_surface_vectors
_render_surface_texture = _surfaces._render_surface_texture



build_texture_metadata = _document.build_texture_metadata
_normalize_svg_profile = _document._normalize_svg_profile
_safe_svg_id = _document._safe_svg_id
_instruction_svg_id = _document._instruction_svg_id
_mark_svg_id = _document._mark_svg_id
_inject_svg_document_metadata = _document._inject_svg_document_metadata
_new_svg_drawing = _document._new_svg_drawing
_build_root_groups = _document._build_root_groups
_attach_root_groups = _document._attach_root_groups
_inject_extra_defs = _document._inject_extra_defs


def render(
    score: Score,
    color_map: dict[str, str] | None = None,
    *,
    catalog_id: str | None = None,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
    render_seed: int | None = None,
    composition_seed: int | None = None,
    wild: bool = False,
) -> str:
    profile = _normalize_svg_profile(svg_profile)
    # Built before the score is resolved because `_resolve_at_region` needs it.
    # Resolution only replaces `instructions` and passes `canvas` through, so
    # the aspect read here is the same one the old order read after it.
    canvas = canvas_size_for_aspect(canvas_aspect or _score_canvas_aspect(score))
    score = _resolve_performance_score(
        score, render_seed, canvas, composition_seed=composition_seed
    )
    structured = profile != "display"
    use_filters = profile == "display"
    cmap = {**COLOR_MAP, **(color_map or {})}
    work_assignment = _work_color_assignment(cmap, render_seed, catalog_id)
    dwg = _new_svg_drawing(canvas)
    bg = work_assignment.get(score.background, cmap.get(score.background, BACKGROUND))
    ground_layer, ground_defs_xml = _render_canvas_ground(
        dwg, score, canvas, bg, profile=profile, render_seed=render_seed
    )
    surface_filter_xml: list[str] = []
    solid_mottle_filter_xml: list[str] = []
    performance_filter_xml: str | None = None
    artboard, content, presence_content = _build_root_groups(
        dwg, canvas, bg, ground_layer, structured=structured
    )

    if use_filters and render_seed is not None:
        performance_filter_id, performance_filter_xml = _performance_touch_filter(
            render_seed, canvas
        )
        content["filter"] = f"url(#{performance_filter_id})"

    blur_needed: dict[str, float] = {}
    texture_filters = _texture_filter_weights(score) if use_filters else set()
    blur_elems: list[tuple[str, str]] = []
    elem_idx = 0

    # The sheet this work is worked on. Resolved once from the ground the work
    # names, then handed down by argument -- never held in a module variable,
    # because the more places read it the quieter a missed hand-over gets.
    sheet = _score_support(score)
    ordered_instructions = sorted(
        enumerate(score.instructions), key=lambda pair: pair[1].mode == "carve"
    )
    # Placement is the composition seed's, the touch stays the performance
    # seed's. Read with `is None` and never with `or`: 0 is a seed a caller can
    # legitimately state, and it is how the rest of the server reads this field
    # (db.py:1911). Without a composition seed the placement falls back to the
    # performance seed, so every drawing made before this split replays.
    placement_seed = composition_seed if composition_seed is not None else render_seed
    for ins_idx, ins in ordered_instructions:
        expanded = (
            _expand_arrangement(
                ins, placement_seed, canvas, performance_seed=render_seed
            )
            if ins.arrangement
            else [ins]
        )
        instruction_group = (
            dwg.g(id=_instruction_svg_id(ins, ins_idx)) if structured else content
        )
        for mark_idx, single in enumerate(expanded):
            solid_mottle_id: str | None = None
            if (
                profile != "compat"
                and _is_noncomputer_solid_fill(
                    single, surface_ops=_MARK_SURFACE_OPS
                )
            ):
                solid_mottle_id, solid_mottle_seed = _solid_mottle_filter_id(
                    single, render_seed, ins_idx, mark_idx
                )
                solid_mottle_filter_xml.append(
                    _solid_mottle_filter_xml(solid_mottle_id, solid_mottle_seed)
                )
            element = _render_instruction(
                dwg,
                single,
                cmap,
                canvas,
                work_assignment=work_assignment,
                use_filters=use_filters,
                solid_mottle_filter_id=solid_mottle_id,
                render_seed=render_seed,
                ins_idx=ins_idx,
                mark_idx=mark_idx,
                wild=wild,
                support=sheet,
            )
            if element is not None:
                if structured:
                    element["id"] = _mark_svg_id(single, ins_idx, mark_idx)
                elif _needs_blur(single.variation):
                    v = single.variation
                    assert v is not None
                    # 滲みは図形寸法比なので、filter は振幅名ではなく値で識別する
                    std = _blur_std_px(v, single, canvas)
                    filter_id = f"blur-{v.amplitude}-{int(round(std * 10))}"
                    blur_needed[filter_id] = std
                    eid = f"e{elem_idx}"
                    element["id"] = eid
                    blur_elems.append((eid, filter_id))
                instruction_group.add(element)
            surface_group, surface_filter = _render_surface_texture(
                dwg,
                single,
                cmap,
                work_assignment,
                canvas,
                profile=profile,
                render_seed=render_seed,
                ins_idx=ins_idx,
                mark_idx=mark_idx,
                wild=wild,
                use_filters=use_filters,
                support=sheet,
                mark_style=_SURFACE_MARK_STYLE,
            )
            if surface_group is not None:
                instruction_group.add(surface_group)
            if surface_filter is not None:
                surface_filter_xml.append(surface_filter)
            elem_idx += 1
        if structured:
            content.add(instruction_group)

    is_print = (
        _score_canvas_ground(score) is not None
        and _score_canvas_ground(score).material == "mezzotint"
        or any(ins.weight in {"burin", "drypoint"} for ins in score.instructions)
    )
    if is_print and render_seed is not None:
        plate_opacity = 0.02 + _hash01(0, int(render_seed), "plate-tone") * 0.04
        plate = dwg.rect(
            insert=(0, 0),
            size=(canvas.width, canvas.height),
            fill="#111111",
            opacity=plate_opacity,
            id="layer_15_plate_tone",
        )
        content.add(plate)

    presence_layer = _render_presence_layer(
        dwg, score, cmap, canvas, work_assignment=work_assignment
    )
    if presence_layer is not None:
        presence_content.add(presence_layer)

    _attach_root_groups(dwg, artboard, content, structured=structured)
    svg = dwg.tostring()
    svg = _inject_extra_defs(
        svg,
        [
            ground_defs_xml or "",
            *surface_filter_xml,
            *solid_mottle_filter_xml,
            performance_filter_xml or "",
        ],
    )
    svg = _inject_texture_filters(svg, texture_filters, canvas)
    if blur_elems:
        svg = _inject_blur_filters(svg, blur_needed, blur_elems)
    if structured:
        svg = _inject_svg_document_metadata(svg, profile=profile)
    svg = _apply_master_grid(svg)
    if profile == "compat":
        validate_compat_svg(svg)
    return svg


_score_visual_load = _layers._score_visual_load
_presence_center_px = _layers._presence_center_px
_presence_seed = _layers._presence_seed
_render_presence_layer = _layers._render_presence_layer


_hex_to_rgb = _palette._hex_to_rgb
_hue_from_hex = _palette._hue_from_hex
_ASCII_HINT_TOKEN_RE = _palette._ASCII_HINT_TOKEN_RE
_ASCII_HINT_WORD_RE = _palette._ASCII_HINT_WORD_RE
_ACHROMATIC_COLORS = _palette._ACHROMATIC_COLORS
_CHROMATIC_COLORS = _palette._CHROMATIC_COLORS
_CHROMATIC_BANDS = _palette._CHROMATIC_BANDS
_CHROMATIC_BAND_CENTERS = _palette._CHROMATIC_BAND_CENTERS
_OKLCH_CHROMA_FLOOR = _palette._OKLCH_CHROMA_FLOOR
_HINT_HUE_PRIORITY = _palette._HINT_HUE_PRIORITY
_oklch_from_hex = _palette._oklch_from_hex
_chromatic_band = _palette._chromatic_band
_circular_hue_distance = _palette._circular_hue_distance
_work_color_choice = _palette._work_color_choice
_work_color_assignment = _palette._work_color_assignment
_hint_hues = _palette._hint_hues
_resolve_color = _palette._resolve_color


_has_surface_texture = _surfaces._has_surface_texture
_fills_interior = _surfaces._fills_interior


def _render_instruction(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    cmap: dict[str, str] = COLOR_MAP,
    canvas: CanvasSize | None = None,
    *,
    work_assignment: dict[str, str] | None = None,
    use_filters: bool = True,
    solid_mottle_filter_id: str | None = None,
    support: Support,
    render_seed: int | None = None,
    ins_idx: int = 0,
    mark_idx: int = 0,
    wild: bool = False,
):
    canvas = canvas or canvas_size_for_aspect(None)
    # Once, here: every mark of this instruction meets the same sheet, and a
    # word about how the mark runs belongs to this instruction alone.
    support = _instruction_support(ins, support)
    assignment = work_assignment or _work_color_assignment(cmap, render_seed, None)
    attrs = _stroke_attrs(
        ins,
        cmap,
        canvas,
        work_assignment=assignment,
        surface_ops=_MARK_SURFACE_OPS,
        use_filters=use_filters,
    )
    if ins.mode == "carve":
        depth = ins.carve_depth or "half"
        attrs["stroke"] = {"light": "#8a8a8a", "half": "#c7c7c7", "bright": "#ffffff"}[
            depth
        ]
        attrs["fill"] = attrs["stroke"] if attrs.get("fill") != "none" else "none"
        attrs["stroke_opacity"] = {"light": 0.58, "half": 0.78, "bright": 0.96}[depth]

    if ins.primitive == "line":
        start = _px(ins.from_ if ins.from_ is not None else (0.5, 0.0), canvas)
        end = _px(ins.to if ins.to is not None else (0.5, 1.0), canvas)
        if ins.weight != "rotring":
            return _render_hand_stroke(
                dwg,
                ins,
                start,
                end,
                attrs,
                canvas,
                render_seed,
                use_filters=use_filters,
                wild=wild,
                support=support,
            )
        return _apply_rotation(dwg.line(start=start, end=end, **attrs), ins, canvas)

    if ins.primitive == "circle":
        if ins.center is None or ins.radius is None:
            raise ValueError("circle requires 'center' and 'radius'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        hand = _uses_hand_stroke(ins.weight)
        varied = _needs_contour_variation(ins.variation)
        if varied:
            assert ins.variation is not None
            contour = _closed_contour_with_variation(
                _circle_points(
                    cx, cy, r, r, _segment_count(2 * math.pi * r, canvas)
                ),
                (cx, cy),
                ins.variation,
                _seed_for_instruction(ins, render_seed),
                _amplitude_px(ins.variation, ins, canvas),
            )
        else:
            contour = _circle_points(
                cx, cy, r, r, _stroke_sample_count(2 * math.pi * r, canvas)
            )
        fill_group, region_fill = _interior_fill(
            dwg,
            ins,
            contour,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            surface_ops=_MARK_SURFACE_OPS,
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else (
                _body_attrs_for_contour_stroke(attrs, ins, region_fill=True)
                if fill_group is not None
                else attrs
            )
        )
        if varied:
            element = dwg.polygon(points=contour, **body_attrs)
        else:
            element = dwg.circle(center=(cx, cy), r=r, **body_attrs)
        if hand or fill_group is not None or _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(element)
            if fill_group is not None:
                group.add(fill_group)
            performed: list[tuple[float, float]] | None = None
            if hand:
                contour_group, performed = _render_contour_hand_stroke(
                    dwg,
                    ins,
                    contour,
                    attrs,
                    canvas,
                    render_seed,
                    use_filters=use_filters,
                    wild=wild,
                    support=support,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if performed is not None:
                    _add_material_performed_outline(
                        dwg,
                        group,
                        ins,
                        attrs,
                        performed,
                        canvas,
                        render_seed,
                        closed=True,
                        path_len_px=2 * math.pi * r,
                        center=(cx, cy),
                    )
                else:
                    _add_material_circle_outline(
                        dwg, group, ins, attrs, cx, cy, r, canvas, render_seed
                    )
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(element, ins, canvas)

    if ins.primitive == "ellipse":
        if ins.center is None or ins.size is None:
            raise ValueError("ellipse requires 'center' and 'size'")
        cx, cy = _px(ins.center, canvas)
        size_w, size_h = _size_px(ins.size, canvas)
        rx, ry = size_w / 2, size_h / 2
        hand = _uses_hand_stroke(ins.weight)
        varied = _needs_contour_variation(ins.variation)
        if varied:
            assert ins.variation is not None
            contour = _closed_contour_with_variation(
                _circle_points(
                    cx,
                    cy,
                    rx,
                    ry,
                    _segment_count(_ellipse_perimeter(rx, ry), canvas),
                ),
                (cx, cy),
                ins.variation,
                _seed_for_instruction(ins, render_seed),
                _amplitude_px(ins.variation, ins, canvas),
            )
        else:
            contour = _circle_points(
                cx,
                cy,
                rx,
                ry,
                _stroke_sample_count(_ellipse_perimeter(rx, ry), canvas),
            )
        fill_group, region_fill = _interior_fill(
            dwg,
            ins,
            contour,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            surface_ops=_MARK_SURFACE_OPS,
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else (
                _body_attrs_for_contour_stroke(attrs, ins, region_fill=True)
                if fill_group is not None
                else attrs
            )
        )
        if varied:
            element = dwg.polygon(points=contour, **body_attrs)
        else:
            element = dwg.ellipse(center=(cx, cy), r=(rx, ry), **body_attrs)
        if hand or fill_group is not None or _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(element)
            if fill_group is not None:
                group.add(fill_group)
            performed: list[tuple[float, float]] | None = None
            if hand:
                contour_group, performed = _render_contour_hand_stroke(
                    dwg,
                    ins,
                    contour,
                    attrs,
                    canvas,
                    render_seed,
                    use_filters=use_filters,
                    wild=wild,
                    support=support,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if performed is not None:
                    _add_material_performed_outline(
                        dwg,
                        group,
                        ins,
                        attrs,
                        performed,
                        canvas,
                        render_seed,
                        closed=True,
                        path_len_px=_ellipse_perimeter(rx, ry),
                        center=(cx, cy),
                    )
                else:
                    _add_material_ellipse_outline(
                        dwg, group, ins, attrs, cx, cy, rx, ry, canvas, render_seed
                    )
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(element, ins, canvas)

    if ins.primitive == "cloudform":
        if ins.center is None or ins.size is None:
            raise ValueError("cloudform requires center and size")
        cx, cy = _px(ins.center, canvas)
        contour = generate_cloudform_contour(
            (cx, cy),
            _size_px(ins.size, canvas),
            performance_seed=_seed_for_instruction(ins, render_seed),
            instruction_index=ins_idx,
            mark_index=mark_idx,
            variation=ins.variation,
            weight=ins.weight,
        )
        # 塗りは描かれた曲線に沿わせたいので、制御点ではなく Catmull-Rom を
        # 標本化した密なポリゴンを走査する。凹みも交点対のまま扱える。
        sampled = list(sample_closed_catmull_rom(contour.points))
        fill_group, region_fill = _interior_fill(
            dwg,
            ins,
            sampled,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            surface_ops=_MARK_SURFACE_OPS,
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )
        # engine 15: 同じ密なポリラインを閉輪郭の共通経路へ渡す。square / circle /
        # polygon と同じ道を通るので、材質層の 3 機構 (材質輪郭・raster-bleed・
        # burr) と wild がまとめて届く。輪郭生成そのものは engine 14 のまま。
        hand = _uses_hand_stroke(ins.weight)
        if hand:
            body_attrs = _body_attrs_for_contour_stroke(
                attrs, ins, region_fill=region_fill
            )
        elif fill_group is not None:
            body_attrs = _copy_attrs(attrs)
            body_attrs["fill"] = "none"
            body_attrs.pop("fill_opacity", None)
        else:
            body_attrs = attrs
        path = dwg.path(d=contour.path_d, **body_attrs)
        # class は事実だけを名乗る。rotring は幾何のままなので触れていない。
        path["class"] = "cloudform contour-v1" + (
            " stroke-engine-touch" if hand else ""
        )
        if fill_group is None and not hand:
            return _apply_rotation(path, ins, canvas)
        group = dwg.g()
        group.add(path)
        if fill_group is not None:
            group.add(fill_group)
        if hand:
            contour_group, performed = _render_contour_hand_stroke(
                dwg,
                ins,
                sampled,
                attrs,
                canvas,
                render_seed,
                use_filters=use_filters,
                closed=True,
                wild=wild,
                support=support,
            )
            group.add(contour_group)
            if _uses_material_outline(ins.weight):
                _add_material_performed_outline(
                    dwg,
                    group,
                    ins,
                    attrs,
                    performed,
                    canvas,
                    render_seed,
                    closed=True,
                    path_len_px=_closed_path_length(performed),
                    center=_points_center(sampled),
                )
        return _apply_rotation(group, ins, canvas)

    if ins.primitive == "square":
        if ins.position is None or ins.size is None:
            raise ValueError("square requires 'position' and 'size'")
        x, y = _px(ins.position, canvas)
        w, h = _size_px(ins.size, canvas)
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        hand = _uses_hand_stroke(ins.weight)
        varied = _needs_contour_variation(ins.variation)
        contour, anchors = _edge_contour_with_anchors(
            corners,
            ins.variation if varied else None,
            _seed_for_instruction(ins, render_seed),
            _amplitude_px(ins.variation, ins, canvas) if ins.variation else 0.0,
            canvas,
        )
        fill_group, region_fill = _interior_fill(
            dwg,
            ins,
            contour if varied else corners,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            surface_ops=_MARK_SURFACE_OPS,
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else (
                _body_attrs_for_contour_stroke(attrs, ins, region_fill=True)
                if fill_group is not None
                else attrs
            )
        )
        if varied:
            element = dwg.polygon(points=contour, **body_attrs)
        else:
            element = dwg.rect(insert=(x, y), size=(w, h), **body_attrs)
        if hand or fill_group is not None or _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(element)
            if fill_group is not None:
                group.add(fill_group)
            performed = None
            if hand:
                contour_group, performed = _render_contour_hand_stroke(
                    dwg,
                    ins,
                    contour,
                    attrs,
                    canvas,
                    render_seed,
                    use_filters=use_filters,
                    anchors=anchors,
                    wild=wild,
                    support=support,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if performed is not None:
                    _add_material_performed_outline(
                        dwg,
                        group,
                        ins,
                        attrs,
                        performed,
                        canvas,
                        render_seed,
                        closed=True,
                        path_len_px=2 * (w + h),
                        center=(x + w / 2, y + h / 2),
                    )
                else:
                    _add_material_rect_outline(
                        dwg, group, ins, attrs, x, y, w, h, canvas, render_seed
                    )
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(element, ins, canvas)

    if ins.primitive == "triangle":
        if ins.position is None or ins.size is None:
            raise ValueError("triangle requires 'position' and 'size'")
        x, y = _px(ins.position, canvas)
        w, h = _size_px(ins.size, canvas)
        corners = [
            (x + w / 2, y),
            (x, y + h),
            (x + w, y + h),
        ]
        return _render_corner_shape(
            dwg,
            ins,
            corners,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            surface_ops=_MARK_SURFACE_OPS,
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )

    if ins.primitive == "polygon":
        if ins.center is None or ins.radius is None:
            raise ValueError("polygon requires 'center' and 'radius'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        return _render_corner_shape(
            dwg,
            ins,
            _polygon_points(cx, cy, r, ins.sides or 5),
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            surface_ops=_MARK_SURFACE_OPS,
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )

    if ins.primitive == "arc":
        if ins.center is None or ins.radius is None:
            raise ValueError("arc requires 'center' and 'radius'")
        if ins.angle_start is None or ins.angle_end is None:
            raise ValueError("arc requires 'angle_start' and 'angle_end'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        if _uses_hand_stroke(ins.weight):
            return _render_arc_hand_stroke(
                dwg,
                ins,
                cx,
                cy,
                r,
                attrs,
                canvas,
                render_seed,
                use_filters=use_filters,
                wild=wild,
                support=support,
            )
        if _needs_contour_variation(ins.variation):
            assert ins.variation is not None
            contour = _arc_points_with_variation(
                cx,
                cy,
                r,
                ins.angle_start,
                ins.angle_end,
                ins.variation,
                _seed_for_instruction(ins, render_seed),
                _amplitude_px(ins.variation, ins, canvas),
                canvas,
            )
            element = dwg.polyline(points=contour, **attrs)
        else:
            path_d = _arc_path_d(cx, cy, r, ins.angle_start, ins.angle_end)
            element = dwg.path(d=path_d, **attrs)
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(element)
            _add_material_arc_outline(
                dwg,
                group,
                ins,
                attrs,
                cx,
                cy,
                r,
                ins.angle_start,
                ins.angle_end,
                canvas,
                render_seed,
            )
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(element, ins, canvas)

    raise NotImplementedError(f"primitive '{ins.primitive}' not yet supported")
