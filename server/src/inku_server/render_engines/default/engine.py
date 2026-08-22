"""Canonical orchestration for the default render engine."""

from __future__ import annotations

from ...master_grid import fmt
from ...plugins import CanvasSize, canvas_size_for_aspect
from ...schema import Score
from ...svg_compat import validate_compat_svg
from ..base import RenderEngineResult
from . import determinism, dispatch, document, layers, marks, palette, planning, surfaces

ENGINE_ID = "default"
ENGINE_VERSION = "40"
_BACKGROUND = "#ffffff"

_SURFACE_MARK_STYLE = surfaces.SurfaceMarkStyle(
    mark_width_px=marks._mark_width_px,
    weight_style=marks.WEIGHT_STYLE,
    texture_filter_weights=marks.TEXTURE_FILTER_WEIGHTS,
)


def _inject_blur_filters(
    svg: str,
    blur_needed: dict[str, float],
    blur_elems: list[tuple[str, str]],
) -> str:
    """Inject Gaussian blur definitions and attach them to performed marks."""
    # Map keys include the amplitude name and resolved standard deviation because
    # shapes with the same amplitude can need different deviations due to size.
    filter_xml = "".join(
        f'<filter id="{filter_id}" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="{fmt(std)}"/>'
        f"</filter>"
        for filter_id, std in sorted(blur_needed.items())
    )
    # svgwrite serializes an empty definitions element as `<defs />`, with a space.
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
        marks._texture_filter_xml(weight, canvas) for weight in sorted(filters)
    )
    if "<defs />" in svg:
        return svg.replace("<defs />", f"<defs>{filter_xml}</defs>", 1)
    if "<defs/>" in svg:
        return svg.replace("<defs/>", f"<defs>{filter_xml}</defs>", 1)
    return svg.replace("<defs>", f"<defs>{filter_xml}", 1)


def render_result(
    score: Score,
    color_map: dict[str, str] | None = None,
    *,
    catalog_id: str | None = None,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
    render_seed: int | None = None,
    composition_seed: int | None = None,
    wild: bool = False,
) -> RenderEngineResult:
    source_score = score
    profile = document._normalize_svg_profile(svg_profile)
    # Build the canvas before resolving the score because `_resolve_at_region`
    # needs it. Resolution replaces only instructions and preserves this canvas.
    canvas = canvas_size_for_aspect(
        canvas_aspect or document._score_canvas_aspect(score)
    )
    score = planning._resolve_performance_score(
        score, render_seed, canvas, composition_seed=composition_seed
    )
    structured = profile != "display"
    use_filters = profile == "display"
    cmap = {**palette.COLOR_MAP, **(color_map or {})}
    work_assignment = palette._work_color_assignment(cmap, render_seed, catalog_id)
    dwg = document._new_svg_drawing(canvas)
    bg = work_assignment.get(
        score.background, cmap.get(score.background, _BACKGROUND)
    )
    ground_layer, ground_defs_xml = layers._render_canvas_ground(
        dwg, score, canvas, bg, profile=profile, render_seed=render_seed
    )
    surface_filter_xml: list[str] = []
    solid_mottle_filter_xml: list[str] = []
    performance_filter_xml: str | None = None
    artboard, content, presence_content = document._build_root_groups(
        dwg, canvas, bg, ground_layer, structured=structured
    )

    if use_filters and render_seed is not None:
        performance_filter_id, performance_filter_xml = (
            marks._performance_touch_filter(render_seed, canvas)
        )
        content["filter"] = f"url(#{performance_filter_id})"

    blur_needed: dict[str, float] = {}
    texture_filters = marks._texture_filter_weights(score) if use_filters else set()
    blur_elems: list[tuple[str, str]] = []
    elem_idx = 0
    # Resolve support once and pass it down explicitly. Keeping it out of module
    # globals makes every rendering handoff visible and prevents missed context.
    sheet = layers._score_support(score)
    ordered_instructions = sorted(
        enumerate(score.instructions), key=lambda pair: pair[1].mode == "carve"
    )
    # Placement belongs to the composition seed; touch belongs to the performance
    # seed. Use `is None` so zero remains valid, and fall back to the performance
    # seed when older works have no composition seed so their replay stays stable.
    placement_seed = composition_seed if composition_seed is not None else render_seed
    for ins_idx, ins in ordered_instructions:
        expanded = (
            planning._expand_arrangement(
                ins, placement_seed, canvas, performance_seed=render_seed
            )
            if ins.arrangement
            else [ins]
        )
        instruction_group = (
            dwg.g(id=document._instruction_svg_id(ins, ins_idx))
            if structured
            else content
        )
        for mark_idx, single in enumerate(expanded):
            solid_mottle_id: str | None = None
            if (
                profile != "compat"
                and marks._is_noncomputer_solid_fill(
                    single, surface_ops=dispatch._MARK_SURFACE_OPS
                )
            ):
                solid_mottle_id, solid_mottle_seed = marks._solid_mottle_filter_id(
                    single, render_seed, ins_idx, mark_idx
                )
                solid_mottle_filter_xml.append(
                    marks._solid_mottle_filter_xml(
                        solid_mottle_id, solid_mottle_seed
                    )
                )
            element = dispatch._render_instruction(
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
                    element["id"] = document._mark_svg_id(single, ins_idx, mark_idx)
                elif determinism._needs_blur(single.variation):
                    variation = single.variation
                    assert variation is not None
                    std = marks._blur_std_px(variation, single, canvas)
                    # Blur is dimension-dependent, so its ID includes the resolved
                    # standard deviation instead of naming only the amplitude.
                    filter_id = (
                        f"blur-{variation.amplitude}-{int(round(std * 10))}"
                    )
                    blur_needed[filter_id] = std
                    eid = f"e{elem_idx}"
                    element["id"] = eid
                    blur_elems.append((eid, filter_id))
                instruction_group.add(element)
            surface_group, surface_filter = surfaces._render_surface_texture(
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

    ground = document._score_canvas_ground(score)
    is_print = (
        ground is not None
        and ground.material == "mezzotint"
        or any(ins.weight in {"burin", "drypoint"} for ins in score.instructions)
    )
    if is_print and render_seed is not None:
        plate_opacity = (
            0.02 + determinism._hash01(0, int(render_seed), "plate-tone") * 0.04
        )
        plate = dwg.rect(
            insert=(0, 0),
            size=(canvas.width, canvas.height),
            fill="#111111",
            opacity=plate_opacity,
            id="layer_15_plate_tone",
        )
        content.add(plate)

    presence_layer = layers._render_presence_layer(
        dwg, score, cmap, canvas, work_assignment=work_assignment
    )
    if presence_layer is not None:
        presence_content.add(presence_layer)

    document._attach_root_groups(dwg, artboard, content, structured=structured)
    svg = dwg.tostring()
    svg = document._inject_extra_defs(
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
        svg = document._inject_svg_document_metadata(svg, profile=profile)
    svg = marks._apply_master_grid(svg)
    if profile == "compat":
        validate_compat_svg(svg)

    return RenderEngineResult(
        svg=svg,
        metadata={
            "render_engine_id": ENGINE_ID,
            "render_engine_version": ENGINE_VERSION,
            **document.build_texture_metadata(
                source_score, svg_profile=svg_profile
            ),
        },
    )
