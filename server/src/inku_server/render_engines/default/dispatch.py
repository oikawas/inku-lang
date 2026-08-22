"""Explicit primitive instruction dispatch for the default render engine."""

from __future__ import annotations

import math

import svgwrite

from ...cloudform import generate_cloudform_contour, sample_closed_catmull_rom
from ...plugins import CanvasSize, canvas_size_for_aspect
from ...schema import Instruction
from ...stroke_engine import Support
from . import marks as _marks
from . import palette as _palette
from . import surfaces as _surfaces
from .determinism import _needs_contour_variation, _seed_for_instruction


COLOR_MAP = _palette.COLOR_MAP
_work_color_assignment = _palette._work_color_assignment

_MARK_SURFACE_OPS = _marks.MarkSurfaceOps(
    fills_interior=_surfaces._fills_interior,
    scatter=_surfaces._surface_scatter,
)

_add_material_arc_outline = _marks._add_material_arc_outline
_add_material_circle_outline = _marks._add_material_circle_outline
_add_material_ellipse_outline = _marks._add_material_ellipse_outline
_add_material_performed_outline = _marks._add_material_performed_outline
_add_material_rect_outline = _marks._add_material_rect_outline
_amplitude_px = _marks._amplitude_px
_apply_rotation = _marks._apply_rotation
_arc_path_d = _marks._arc_path_d
_arc_points_with_variation = _marks._arc_points_with_variation
_body_attrs_for_contour_stroke = _marks._body_attrs_for_contour_stroke
_circle_points = _marks._circle_points
_closed_contour_with_variation = _marks._closed_contour_with_variation
_closed_path_length = _marks._closed_path_length
_copy_attrs = _marks._copy_attrs
_edge_contour_with_anchors = _marks._edge_contour_with_anchors
_ellipse_perimeter = _marks._ellipse_perimeter
_instruction_support = _marks._instruction_support
_interior_fill = _marks._interior_fill
_points_center = _marks._points_center
_polygon_points = _marks._polygon_points
_px = _marks._px
_render_arc_hand_stroke = _marks._render_arc_hand_stroke
_render_contour_hand_stroke = _marks._render_contour_hand_stroke
_render_corner_shape = _marks._render_corner_shape
_render_hand_stroke = _marks._render_hand_stroke
_segment_count = _marks._segment_count
_size_px = _marks._size_px
_stroke_attrs = _marks._stroke_attrs
_stroke_sample_count = _marks._stroke_sample_count
_uses_hand_stroke = _marks._uses_hand_stroke
_uses_material_outline = _marks._uses_material_outline


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
