//! Primitive-to-SVG mark rendering built on the portable stroke and geometry domains.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

use crate::accepted_fills;
use crate::cloudform::{CloudformRequest, generate_cloudform_contour, sample_closed_catmull_rom};
use crate::determinism::{instruction_seed, needs_contour_variation, needs_path_variation};
use crate::fills::{is_noncomputer_solid_fill, render_interior_fill};
use crate::free_line::{
    FreeLinePath, FreeLineRequest, Obstacle, Sheet, free_line_path, free_line_seed,
};
use crate::geometry::{
    ArcGeometry, SEGMENT_TARGET_RATIO, STROKE_SAMPLE_TARGET_RATIO, arc_points,
    arc_points_with_variation, circle_points, closed_contour_with_variation,
    crescent_contour_points, edge_contour_with_anchors, ellipse_perimeter,
    open_line_with_variation, open_path_with_variation, point_to_pixels, polygon_points,
    size_to_pixels, stroke_sample_count,
};
use crate::mark_geometry::{ArcSpan, MarkGeometry};
use crate::mark_paths::{
    amplitude, cloudform_path, hand_contour, hand_line, points_attribute, polygon_path, rotate,
    uses_hand_stroke,
};
use crate::palette::resolve_color;
use crate::planning::instruction_anchor_on_canvas;
use crate::support::Support;
use crate::svg::{Element, format_number};
use crate::types::{
    CRESCENT_REFERENCE_CUBICS, CanvasSize, CarveDepth, Instruction, LineStyle, Point, Primitive,
    Seed, SurfaceIntensity, SurfaceTexture, SvgProfile, Thinness, Weight, crescent_transform_point,
};

pub(crate) const MIN_STROKE_WIDTH: f64 = 0.5;

fn rotated_instruction_point(
    instruction: &Instruction,
    context: MarkContext<'_>,
    point: Point,
) -> Point {
    instruction.rotation.map_or(point, |degrees| {
        let pivot = point_to_pixels(
            instruction_anchor_on_canvas(instruction, Some(context.canvas)),
            context.canvas,
        );
        let radians = degrees.to_radians();
        let dx = point.x - pivot.x;
        let dy = point.y - pivot.y;
        Point::new(
            pivot.x + dx * radians.cos() - dy * radians.sin(),
            pivot.y + dx * radians.sin() + dy * radians.cos(),
        )
    })
}

/// A mark whose primitive requires a field the instruction leaves out.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MarkError {
    pub primitive: Primitive,
    pub missing_field: &'static str,
}

impl fmt::Display for MarkError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{:?} requires '{}'",
            self.primitive, self.missing_field
        )
    }
}

impl std::error::Error for MarkError {}

#[derive(Clone, Copy)]
pub struct MarkContext<'a> {
    pub canvas: CanvasSize,
    pub color_map: &'a BTreeMap<String, String>,
    pub work_assignment: &'a BTreeMap<String, String>,
    pub render_seed: Option<Seed>,
    pub instruction_seed_override: Option<Seed>,
    pub instruction_index: usize,
    pub mark_index: usize,
    pub wild: bool,
    pub use_filters: bool,
    pub profile: SvgProfile,
    pub support: Support,
    pub geometry_transform: crate::affine::AffineTransform,
    /// Most loaded passes one oil-paint interior fill may lay down, shared out
    /// of a document-wide budget so many large oil fills stay bounded.
    pub oil_fill_pass_limit: usize,
    /// What the mark inherits from the arrangement that copied its instruction.
    pub effects: crate::effects::MarkEffects,
}

impl MarkContext<'_> {
    pub(crate) fn seed_for(self, instruction: &Instruction) -> Seed {
        self.instruction_seed_override
            .unwrap_or_else(|| instruction_seed(instruction, self.render_seed))
    }
}

/// How far past a stroke's centerline its ink may land, in pixels: the stroke's
/// own width and wobble, and the few pixels the texture and touch filters move.
fn ink_reach(width: f64, canvas: CanvasSize) -> f64 {
    width * 4.0 + canvas.unit() * 0.03
}

/// Whether a fill or surface stroke from `start` to `end`, `width` wide, can
/// put ink on the canvas.
///
/// The points are in the mark's own coordinates. On the identity path the
/// mark's rotation is still to come (an SVG `rotate`), so it is applied here
/// first. A stroke that cannot reach the canvas is left out of the SVG; the
/// caller still counts its index, so every other stroke keeps its seed.
pub(crate) fn reaches_canvas(
    instruction: &Instruction,
    context: MarkContext<'_>,
    start: Point,
    end: Point,
    width: f64,
) -> bool {
    let (start, end) = if context.geometry_transform.is_identity() {
        (
            rotated_instruction_point(instruction, context, start),
            rotated_instruction_point(instruction, context, end),
        )
    } else {
        (start, end)
    };
    let reach = ink_reach(width, context.canvas);
    start.x.max(end.x) + reach >= 0.0
        && start.x.min(end.x) - reach <= context.canvas.width
        && start.y.max(end.y) + reach >= 0.0
        && start.y.min(end.y) - reach <= context.canvas.height
}

/// Applies the instruction's own rotation before its containing Transform groups.
///
/// The identity path keeps its established SVG rotation representation. The general
/// affine path instead feeds transformed geometry into every mark and material
/// generator, so physical stroke and texture measurements remain in canvas pixels.
pub(crate) fn geometry_point(
    instruction: &Instruction,
    context: MarkContext<'_>,
    point: Point,
) -> Point {
    if context.geometry_transform.is_identity() {
        return point;
    }
    let rotated = rotated_instruction_point(instruction, context, point);
    context.geometry_transform.apply(rotated)
}

pub(crate) fn geometry_points(
    instruction: &Instruction,
    context: MarkContext<'_>,
    points: &[Point],
) -> Vec<Point> {
    points
        .iter()
        .copied()
        .map(|point| geometry_point(instruction, context, point))
        .collect()
}

#[derive(Clone)]
pub(crate) struct MarkStyle {
    pub(crate) color: String,
    pub(crate) width: f64,
    pub(crate) fill: bool,
    pub(crate) stroke_opacity: f64,
    pub(crate) fill_opacity: Option<f64>,
    linecap: &'static str,
    dash: Option<String>,
}

pub(crate) fn weight_width(weight: Weight) -> f64 {
    match weight {
        Weight::Silverpoint => 0.5,
        Weight::Pencil => 1.5,
        Weight::Pen | Weight::Computer => 2.0,
        Weight::Rotring => 1.0,
        Weight::Crayon => 4.0,
        Weight::Chalk | Weight::BrushThin => 3.0,
        Weight::BrushThick => 8.0,
        Weight::OilPaint => 12.0,
        Weight::Burin => 3.2,
        Weight::Drypoint => 2.6,
    }
}

pub(crate) fn thinness_scale(thinness: Option<Thinness>) -> f64 {
    match thinness {
        None | Some(Thinness::Thick | Thinness::ExtraThick) => 1.0,
        Some(Thinness::Fine) => 0.6,
        Some(Thinness::ExtraFine) => 0.35,
    }
}

/// The widest mark each tool makes, in the same units as `weight_width`.
///
/// With the canvas short side read as an A3 sheet (one unit about 0.3 mm), the
/// default widths of the fine tools already match the physical tools; this is
/// the broadest mark the physical tool makes on that scale.
pub(crate) fn extra_thick_width(weight: Weight) -> f64 {
    match weight {
        Weight::Silverpoint => 1.5,
        Weight::Pencil => 8.0,
        Weight::Pen | Weight::Computer => 6.0,
        Weight::Rotring => 6.7,
        Weight::Crayon => 20.0,
        Weight::Chalk => 25.0,
        Weight::BrushThin => 15.0,
        Weight::BrushThick => 50.0,
        Weight::OilPaint => 60.0,
        Weight::Burin => 7.0,
        Weight::Drypoint => 6.0,
    }
}

/// The step between each tool's default and its widest mark (their geometric
/// mean, rounded).
pub(crate) fn thick_width(weight: Weight) -> f64 {
    match weight {
        Weight::Silverpoint => 0.9,
        Weight::Pencil => 3.5,
        Weight::Pen | Weight::Computer => 3.5,
        Weight::Rotring => 2.6,
        Weight::Crayon | Weight::Chalk => 9.0,
        Weight::BrushThin => 6.7,
        Weight::BrushThick => 20.0,
        Weight::OilPaint => 27.0,
        Weight::Burin => 4.7,
        Weight::Drypoint => 3.9,
    }
}

/// A tool's width for a thinness: the thin side scales the default, while the
/// thick side reads each tool's own widths, since how wide a tool can go is a
/// property of the tool rather than a shared ratio.
pub(crate) fn thinned_width(weight: Weight, thinness: Option<Thinness>) -> f64 {
    match thinness {
        Some(Thinness::Thick) => thick_width(weight),
        Some(Thinness::ExtraThick) => extra_thick_width(weight),
        other => (weight_width(weight) * thinness_scale(other)).max(MIN_STROKE_WIDTH),
    }
}

pub(crate) fn is_closed(primitive: Primitive) -> bool {
    matches!(
        primitive,
        Primitive::Circle
            | Primitive::Point
            | Primitive::Ellipse
            | Primitive::Square
            | Primitive::Triangle
            | Primitive::Polygon
            | Primitive::Cloudform
    )
}

/// The opacity factor of a band a line or an arc draws for its surface word.
/// Wash is the pale band of the retired 薄墨. Sweep (刷き) is the same broad
/// band without paleness of its own, at the value the author chose on the
/// comparison sheet (2026-09-29): the handling word 薄い makes it pale.
const WASH_BAND_OPACITY: f64 = 0.35;
const SWEEP_BAND_OPACITY: f64 = 0.8;

fn band_opacity(instruction: &Instruction) -> Option<f64> {
    if is_closed(instruction.primitive) {
        return None;
    }
    match instruction.surface.as_ref()?.texture {
        SurfaceTexture::Wash => Some(WASH_BAND_OPACITY),
        SurfaceTexture::Sweep => Some(SWEEP_BAND_OPACITY),
        _ => None,
    }
}

/// How many times its tool's width the band of a line or an arc's sweep or wash is.
const BAND_WIDTH_SCALE: f64 = 3.0;

pub(crate) fn mark_width(instruction: &Instruction, canvas: CanvasSize) -> f64 {
    let width = thinned_width(instruction.weight, instruction.thinness) * canvas.unit() / 1000.0;
    width
        * if band_opacity(instruction).is_some() {
            BAND_WIDTH_SCALE
        } else {
            1.0
        }
}

/// The width of the band the mark's tool sweeps (刷き) as a line or an arc:
/// the size of its flat brush, the same for the mark's lines and its closed
/// shape's passes.
pub(crate) fn sweep_band_width(instruction: &Instruction, canvas: CanvasSize) -> f64 {
    thinned_width(instruction.weight, instruction.thinness) * canvas.unit() / 1000.0
        * BAND_WIDTH_SCALE
}

pub(crate) fn weight_opacity(weight: Weight) -> f64 {
    match weight {
        Weight::Silverpoint => 0.72,
        Weight::Pencil => 0.66,
        Weight::Pen | Weight::Computer => 1.0,
        Weight::Rotring => 0.95,
        Weight::Crayon => 0.78,
        Weight::Chalk => 0.70,
        Weight::BrushThin => 0.90,
        Weight::BrushThick => 0.86,
        Weight::OilPaint => 1.0,
        Weight::Burin => 0.96,
        Weight::Drypoint => 0.92,
    }
}

/// The factor a stated intensity gives the opacity of a stroke or a textured
/// surface. A flat fill keeps its own table per tool (`accepted_fills`).
pub(crate) const fn intensity_factor(intensity: SurfaceIntensity) -> f64 {
    match intensity {
        SurfaceIntensity::Normal => 1.0,
        SurfaceIntensity::Dense => 1.35,
        SurfaceIntensity::Faint => 0.55,
    }
}

/// An opacity scaled by an intensity factor, opaque at most, to six places.
fn scaled_opacity(opacity: f64, factor: f64) -> f64 {
    ((opacity * factor).min(1.0) * 1_000_000.0).round() / 1_000_000.0
}

pub(crate) fn weight_linecap(weight: Weight) -> &'static str {
    match weight {
        Weight::Silverpoint => "butt",
        Weight::Rotring => "square",
        _ => "round",
    }
}

pub(crate) fn style_dash(style: LineStyle, weight: Weight, scale: f64) -> Option<String> {
    let values: Option<&[f64]> = match style {
        LineStyle::Dashed => Some(&[12.0, 8.0]),
        LineStyle::Dotted => Some(&[2.0, 6.0]),
        LineStyle::DashDot => Some(&[12.0, 6.0, 2.0, 6.0]),
        LineStyle::Solid => match weight {
            Weight::Pencil => Some(&[1.0, 3.0]),
            Weight::Crayon => Some(&[10.0, 3.0, 2.0, 3.0]),
            Weight::Chalk => Some(&[7.0, 5.0, 1.0, 4.0]),
            _ => None,
        },
    };
    values.map(|values| {
        values
            .iter()
            .map(|value| format_number(*value * scale))
            .collect::<Vec<_>>()
            .join(",")
    })
}

/// Resolve the color, width, opacity, cap and dash of one mark.
///
/// The author's effect words in the color hint (haze and light, scent, buds,
/// the five senses, reflection, and older Scores' fade words) and the fade
/// the mark's arrangement gives it cap the tool's opacity; see `effects`.
/// Carve marks ignore the color and scrape to their depth's tone.
pub(crate) fn mark_style(instruction: &Instruction, context: MarkContext<'_>) -> MarkStyle {
    let fill = instruction.filled
        || instruction
            .surface
            .as_ref()
            .is_some_and(|surface| surface.texture == SurfaceTexture::Solid);
    let color = resolve_color(
        instruction.color,
        instruction.color_hint.as_deref(),
        context.color_map,
        context.work_assignment,
    );
    let (mut stroke_opacity, mut fill_opacity) = crate::effects::effect_opacity(
        crate::effects::HintWords::read(instruction.color_hint.as_deref()),
        context.effects,
        weight_opacity(instruction.weight),
        fill,
    );
    if let Some(band) = band_opacity(instruction) {
        stroke_opacity = (stroke_opacity * band * 1_000_000.0).round() / 1_000_000.0;
    }
    if instruction.surface_intensity != SurfaceIntensity::Normal
        && !instruction.is_closed_solid_fill()
    {
        let factor = intensity_factor(instruction.surface_intensity);
        stroke_opacity = scaled_opacity(stroke_opacity, factor);
        fill_opacity = fill_opacity.map(|opacity| scaled_opacity(opacity, factor));
    }
    if instruction.mode_ == crate::types::InstructionMode::Carve {
        let (carve_color, opacity) = match instruction.carve_depth.unwrap_or(CarveDepth::Half) {
            CarveDepth::Light => ("#8a8a8a", 0.58),
            CarveDepth::Half => ("#c7c7c7", 0.78),
            CarveDepth::Bright => ("#ffffff", 0.96),
        };
        return MarkStyle {
            color: carve_color.to_owned(),
            width: mark_width(instruction, context.canvas),
            fill,
            stroke_opacity: opacity,
            fill_opacity,
            linecap: weight_linecap(instruction.weight),
            dash: style_dash(
                instruction.style,
                instruction.weight,
                context.canvas.unit() / 1000.0,
            ),
        };
    }
    MarkStyle {
        color,
        width: mark_width(instruction, context.canvas),
        fill,
        stroke_opacity,
        fill_opacity,
        linecap: weight_linecap(instruction.weight),
        dash: style_dash(
            instruction.style,
            instruction.weight,
            context.canvas.unit() / 1000.0,
        ),
    }
}

pub(crate) fn apply_style(mut element: Element, style: &MarkStyle, allow_fill: bool) -> Element {
    element.set_attr("stroke", &style.color);
    element.set_attr("stroke-width", format_number(style.width));
    element.set_attr("stroke-linecap", style.linecap);
    element.set_attr("stroke-opacity", format_number(style.stroke_opacity));
    element.set_attr(
        "fill",
        if allow_fill && style.fill {
            &style.color
        } else {
            "none"
        },
    );
    if allow_fill
        && style.fill
        && let Some(opacity) = style.fill_opacity
    {
        element.set_attr("fill-opacity", format_number(opacity));
    }
    if let Some(dash) = &style.dash {
        element.set_attr("stroke-dasharray", dash);
    }
    element
}

/// Whether a closed mark draws its edge apart from its face (render engine 83).
///
/// A faint flat fill of a closed shape keeps its tool's density (the rotring's
/// opacity, the grain filter or the mask) on its face only, and its edge is
/// drawn after the face, outside that density, so the face is see-through
/// behind a clear edge. Points, oil paint and the computer keep their edge
/// inside the face.
fn faint_fill_edge(instruction: &Instruction) -> bool {
    instruction.surface_intensity == SurfaceIntensity::Faint
        && instruction.primitive != Primitive::Point
        && instruction.weight != Weight::Computer
        && accepted_fills::active(instruction)
}

/// The style of a closed mark's edge. An edge drawn apart from a faint fill
/// takes the tool's own opacity again, at the faint factor, as the edge of the
/// same tool's faint empty shape.
fn closed_edge_style(instruction: &Instruction, style: &MarkStyle) -> MarkStyle {
    let mut edge = style.clone();
    if faint_fill_edge(instruction) {
        edge.stroke_opacity = scaled_opacity(
            style.stroke_opacity * weight_opacity(instruction.weight),
            intensity_factor(SurfaceIntensity::Faint),
        );
    }
    edge
}

/// A closed mark. Its edge goes inside its face, the fill's density group,
/// except for a faint fill, whose face and edge sit side by side in a plain
/// group.
fn closed_mark_group(instruction: &Instruction, mut face: Element, edge: Element) -> Element {
    if faint_fill_edge(instruction) {
        let mut mark = Element::new("g");
        mark.push(face);
        mark.push(edge);
        mark
    } else {
        face.push(edge);
        face
    }
}

fn mechanical_closed_mark(
    instruction: &Instruction,
    contour: &[Point],
    geometry: Element,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    if !is_noncomputer_solid_fill(instruction) && !accepted_fills::active(instruction) {
        return apply_style(geometry, style, true);
    }
    let mut group = accepted_fills::group(instruction, context);
    if let Some(fill) = render_interior_fill(instruction, contour, style, context) {
        group.push(fill);
    }
    let edge = apply_style(geometry, &closed_edge_style(instruction, style), false);
    closed_mark_group(instruction, group, edge)
}

fn crescent_path(center: Point, size: Point) -> String {
    let segments = CRESCENT_REFERENCE_CUBICS
        .map(|cubic| cubic.map(|point| crescent_transform_point(point, center, size, 0.0)));
    let first = segments[0][0];
    let body = segments
        .iter()
        .map(|segment| {
            format!(
                "C {} {} {} {} {} {}",
                format_number(segment[1].x),
                format_number(segment[1].y),
                format_number(segment[2].x),
                format_number(segment[2].y),
                format_number(segment[3].x),
                format_number(segment[3].y),
            )
        })
        .collect::<Vec<_>>()
        .join(" ");
    format!(
        "M {} {} {body} Z",
        format_number(first.x),
        format_number(first.y)
    )
}

fn render_crescent(
    instruction: &Instruction,
    center: Point,
    size: Point,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let center = point_to_pixels(center, context.canvas);
    let size = size_to_pixels(size, context.canvas);
    let contour = crescent_contour_points(center, size, 25);
    let geometry = apply_style(
        Element::new("path").attr("d", crescent_path(center, size)),
        style,
        true,
    );
    if uses_hand_stroke(instruction.weight) {
        let mut group = accepted_fills::group(instruction, context);
        if let Some(fill) = render_interior_fill(instruction, &contour, style, context) {
            group.push(fill);
        }
        let edge = hand_contour(
            instruction,
            &contour,
            &BTreeSet::new(),
            &closed_edge_style(instruction, style),
            context,
            true,
        );
        group = closed_mark_group(instruction, group, edge);
        rotate(group, instruction, context.canvas)
    } else {
        rotate(
            mechanical_closed_mark(instruction, &contour, geometry, style, context),
            instruction,
            context.canvas,
        )
    }
}

fn open_path(points: &[Point]) -> String {
    crate::svg::open_polyline_path(points)
}

fn has_closed_area(points: &[Point]) -> bool {
    points.len() >= 3
        && points
            .iter()
            .zip(points.iter().cycle().skip(1))
            .take(points.len())
            .map(|(left, right)| left.x * right.y - left.y * right.x)
            .sum::<f64>()
            .abs()
            > 1.0e-9
}

fn contour_length(points: &[Point], closed: bool) -> f64 {
    let segments = points
        .windows(2)
        .map(|pair| (pair[1].x - pair[0].x).hypot(pair[1].y - pair[0].y));
    let closing = closed
        .then(|| points.first().zip(points.last()))
        .flatten()
        .map_or(0.0, |(first, last)| {
            (first.x - last.x).hypot(first.y - last.y)
        });
    segments.sum::<f64>() + closing
}

fn affine_curve_samples(
    instruction: &Instruction,
    context: MarkContext<'_>,
    provisional: &[Point],
    closed: bool,
    current: usize,
) -> usize {
    current.max(stroke_sample_count(
        contour_length(&geometry_points(instruction, context, provisional), closed),
        context.canvas,
    ))
}

fn render_affine_closed(
    instruction: &Instruction,
    contour: &[Point],
    anchors: &BTreeSet<usize>,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let contour = geometry_points(instruction, context, contour);
    let geometry = apply_style(
        Element::new("path").attr("d", polygon_path(&contour)),
        style,
        true,
    );
    if !has_closed_area(&contour) {
        return apply_style(
            Element::new("path").attr("d", polygon_path(&contour)),
            style,
            false,
        );
    }
    if uses_hand_stroke(instruction.weight) {
        let mut group = accepted_fills::group(instruction, context);
        if let Some(fill) = render_interior_fill(instruction, &contour, style, context) {
            group.push(fill);
        }
        let edge = hand_contour(
            instruction,
            &contour,
            anchors,
            &closed_edge_style(instruction, style),
            context,
            true,
        );
        group = closed_mark_group(instruction, group, edge);
        group
    } else {
        mechanical_closed_mark(instruction, &contour, geometry, style, context)
    }
}

fn arc_centerline_points(
    instruction: &Instruction,
    arc: ArcSpan,
    context: MarkContext<'_>,
    affine_sampling: bool,
) -> Vec<Point> {
    let center = point_to_pixels(arc.center, context.canvas);
    let radius = arc.radius * context.canvas.unit();
    let (start, end) = (arc.start, arc.end);
    let length = radius * (end - start).to_radians().abs();
    let points = if let Some(variation) = instruction
        .variation
        .as_ref()
        .filter(|variation| needs_contour_variation(variation))
    {
        arc_points_with_variation(
            ArcGeometry {
                center,
                radius,
                start_degrees: start,
                end_degrees: end,
            },
            variation,
            context.seed_for(instruction),
            amplitude(instruction, context.canvas),
            context.canvas,
        )
    } else {
        let current = stroke_sample_count(length, context.canvas);
        let samples = if affine_sampling {
            let provisional = arc_points(center, radius, start, end, current);
            affine_curve_samples(instruction, context, &provisional, false, current)
        } else {
            current
        };
        arc_points(center, radius, start, end, samples)
    };
    if context.geometry_transform.is_identity() {
        points
    } else {
        geometry_points(instruction, context, &points)
    }
}

fn performed_arc_centerline(
    instruction: &Instruction,
    arc: ArcSpan,
    context: MarkContext<'_>,
) -> Vec<Point> {
    let points = arc_centerline_points(
        instruction,
        arc,
        context,
        !context.geometry_transform.is_identity(),
    );
    if context.geometry_transform.is_identity() {
        points
            .into_iter()
            .map(|point| rotated_instruction_point(instruction, context, point))
            .collect()
    } else {
        points
    }
}

pub(crate) fn render_closed_arc_pair_fill(
    first: &Instruction,
    first_context: MarkContext<'_>,
    follower: &Instruction,
    follower_context: MarkContext<'_>,
) -> Result<Option<Element>, MarkError> {
    if first.primitive != Primitive::Arc
        || follower.primitive != Primitive::Arc
        || first.arc_form.is_some()
        || follower.arc_form.is_some()
        || !accepted_fills::solid_fill(follower)
    {
        return Ok(None);
    }
    let first_points = performed_arc_centerline(first, ArcSpan::of(first)?, first_context);
    let follower_points =
        performed_arc_centerline(follower, ArcSpan::of(follower)?, follower_context);
    if first_points.len() < 2 || follower_points.len() < 2 {
        return Ok(None);
    }
    let distance = |left: Point, right: Point| (right.x - left.x).hypot(right.y - left.y);
    let same_direction = distance(first_points[0], follower_points[0])
        + distance(
            *first_points.last().expect("non-empty Arc"),
            *follower_points.last().expect("non-empty Arc"),
        );
    let opposite_direction = distance(
        first_points[0],
        *follower_points.last().expect("non-empty Arc"),
    ) + distance(
        *first_points.last().expect("non-empty Arc"),
        follower_points[0],
    );
    let follower_boundary = if same_direction <= opposite_direction {
        follower_points.into_iter().rev().collect::<Vec<_>>()
    } else {
        follower_points
    };
    let mut contour = first_points;
    contour.extend(follower_boundary.into_iter().skip(1));
    let mut style = mark_style(follower, follower_context);
    accepted_fills::prepare_closed_contour_style(follower, &mut style);
    let fill = if follower.weight == Weight::OilPaint {
        render_interior_fill(follower, &contour, &style, follower_context)
    } else {
        accepted_fills::closed_contour_interior(follower, &contour, &style, follower_context)
    };
    let Some(fill) = fill else {
        return Ok(None);
    };
    let mut group = Element::new("g").attr("class", "closed-arc-pair-fill-v1");
    let mut material = accepted_fills::closed_contour_group(follower, follower_context);
    material.push(fill);
    group.push(material);
    Ok(Some(crate::ink_spread::wrap(
        group,
        follower,
        follower_context,
    )))
}

/// A round mark's radii in pixels. A circle keeps its own perimeter and SVG element.
#[derive(Clone, Copy)]
enum Radii {
    Circle(f64),
    Ellipse(f64, f64),
}

impl Radii {
    fn of_circle(radius: f64, canvas: CanvasSize) -> Self {
        Self::Circle(radius * canvas.unit())
    }

    fn of_ellipse(size: Point, canvas: CanvasSize) -> Self {
        let size = size_to_pixels(size, canvas);
        Self::Ellipse(size.x / 2.0, size.y / 2.0)
    }

    const fn xy(self) -> (f64, f64) {
        match self {
            Self::Circle(radius) => (radius, radius),
            Self::Ellipse(rx, ry) => (rx, ry),
        }
    }

    fn perimeter(self) -> f64 {
        match self {
            Self::Circle(radius) => std::f64::consts::TAU * radius,
            Self::Ellipse(rx, ry) => ellipse_perimeter(rx, ry),
        }
    }
}

/// A Square's corners in pixels, clockwise from its top left.
fn square_corners(position: Point, size: Point, canvas: CanvasSize) -> Vec<Point> {
    let position = point_to_pixels(position, canvas);
    let size = size_to_pixels(size, canvas);
    vec![
        position,
        Point::new(position.x + size.x, position.y),
        Point::new(position.x + size.x, position.y + size.y),
        Point::new(position.x, position.y + size.y),
    ]
}

/// A Triangle's corners in pixels: its apex, then its bottom left and bottom right.
fn triangle_corners(position: Point, size: Point, canvas: CanvasSize) -> Vec<Point> {
    let position = point_to_pixels(position, canvas);
    let size = size_to_pixels(size, canvas);
    vec![
        Point::new(position.x + size.x / 2.0, position.y),
        Point::new(position.x, position.y + size.y),
        Point::new(position.x + size.x, position.y + size.y),
    ]
}

fn polygon_corners(center: Point, radius: f64, sides: usize, canvas: CanvasSize) -> Vec<Point> {
    polygon_points(
        point_to_pixels(center, canvas),
        radius * canvas.unit(),
        sides,
        0.0,
    )
}

fn line_element(start: Point, end: Point) -> Element {
    Element::new("line")
        .attr("x1", format_number(start.x))
        .attr("y1", format_number(start.y))
        .attr("x2", format_number(end.x))
        .attr("y2", format_number(end.y))
}

/// A connected centerline, stored in short-side units, in pixels.
fn centerline_in_pixels(centerline: &[Point], canvas: CanvasSize) -> Vec<Point> {
    centerline
        .iter()
        .map(|point| Point::new(point.x * canvas.unit(), point.y * canvas.unit()))
        .collect()
}

/// A rotring Line, which has no hand stroke (render engine 83).
///
/// A variation that moves its path draws it as a `<polyline>` along the
/// centerline a hand line of the same seed and variation follows, or along
/// the centerline a path connection fixed, which already carries the
/// rotation; without one the line stays a straight `<line>`. `start` and
/// `end` are in pixels, already transformed when the context carries a
/// group transform.
fn rotring_line(
    instruction: &Instruction,
    start: Point,
    end: Point,
    connected_centerline: Option<&[Point]>,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let canvas = context.canvas;
    if let Some(centerline) = connected_centerline {
        return apply_style(
            Element::new("polyline").attr(
                "points",
                points_attribute(&centerline_in_pixels(centerline, canvas)),
            ),
            style,
            false,
        );
    }
    let element = instruction
        .variation
        .as_ref()
        .filter(|variation| needs_path_variation(variation))
        .map_or_else(
            || line_element(start, end),
            |variation| {
                let centerline = open_line_with_variation(
                    start,
                    end,
                    variation,
                    context.seed_for(instruction),
                    amplitude(instruction, canvas),
                    canvas,
                );
                Element::new("polyline").attr("points", points_attribute(&centerline))
            },
        );
    let element = apply_style(element, style, false);
    if context.geometry_transform.is_identity() {
        rotate(element, instruction, canvas)
    } else {
        element
    }
}

fn render_affine_round(
    instruction: &Instruction,
    center: Point,
    radii: Radii,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let center = point_to_pixels(center, context.canvas);
    let (rx, ry) = radii.xy();
    let current = stroke_sample_count(radii.perimeter(), context.canvas);
    let provisional = circle_points(center, rx, ry, current);
    let samples = affine_curve_samples(instruction, context, &provisional, true, current);
    let mut contour = if samples == current {
        provisional
    } else {
        circle_points(center, rx, ry, samples)
    };
    if let Some(variation) = instruction
        .variation
        .as_ref()
        .filter(|variation| needs_contour_variation(variation))
    {
        contour = closed_contour_with_variation(
            &contour,
            center,
            variation,
            context.seed_for(instruction),
            amplitude(instruction, context.canvas),
        );
    }
    render_affine_closed(instruction, &contour, &BTreeSet::new(), style, context)
}

fn render_affine_corners(
    instruction: &Instruction,
    corners: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let contour = edge_contour_with_anchors(
        corners,
        instruction
            .variation
            .as_ref()
            .filter(|variation| needs_contour_variation(variation)),
        context.seed_for(instruction),
        amplitude(instruction, context.canvas),
        context.canvas,
    );
    render_affine_closed(
        instruction,
        &contour.points,
        &contour.anchors,
        style,
        context,
    )
}

fn render_affine_instruction(
    instruction: &Instruction,
    geometry: MarkGeometry,
    style: &MarkStyle,
    context: MarkContext<'_>,
    connected_centerline: Option<&[Point]>,
    obstacles: &[Obstacle],
) -> Element {
    debug_assert!(!context.geometry_transform.is_identity());
    let canvas = context.canvas;
    match geometry {
        MarkGeometry::Line { from, to } => {
            let start = geometry_point(instruction, context, point_to_pixels(from, canvas));
            let end = geometry_point(instruction, context, point_to_pixels(to, canvas));
            if uses_hand_stroke(instruction.weight) {
                if (end.x - start.x).hypot(end.y - start.y) <= 1.0e-9 {
                    apply_style(line_element(start, end), style, false)
                } else {
                    hand_line(
                        instruction,
                        start,
                        end,
                        connected_centerline,
                        style,
                        context,
                    )
                }
            } else {
                rotring_line(
                    instruction,
                    start,
                    end,
                    connected_centerline,
                    style,
                    context,
                )
            }
        }
        MarkGeometry::Circle { center, radius } => render_affine_round(
            instruction,
            center,
            Radii::of_circle(radius, canvas),
            style,
            context,
        ),
        MarkGeometry::Ellipse { center, size } => render_affine_round(
            instruction,
            center,
            Radii::of_ellipse(size, canvas),
            style,
            context,
        ),
        MarkGeometry::Square { position, size } => render_affine_corners(
            instruction,
            &square_corners(position, size, canvas),
            style,
            context,
        ),
        MarkGeometry::Triangle { position, size } => render_affine_corners(
            instruction,
            &triangle_corners(position, size, canvas),
            style,
            context,
        ),
        MarkGeometry::Polygon {
            center,
            radius,
            sides,
        } => render_affine_corners(
            instruction,
            &polygon_corners(center, radius, sides, canvas),
            style,
            context,
        ),
        MarkGeometry::Crescent { center, size } => {
            let center = point_to_pixels(center, canvas);
            let size = size_to_pixels(size, canvas);
            let provisional = crescent_contour_points(center, size, 25);
            let total_samples =
                affine_curve_samples(instruction, context, &provisional, true, provisional.len());
            let samples_per_cubic = total_samples.div_ceil(4);
            let contour = if samples_per_cubic == 25 {
                provisional
            } else {
                crescent_contour_points(center, size, samples_per_cubic)
            };
            render_affine_closed(instruction, &contour, &BTreeSet::new(), style, context)
        }
        MarkGeometry::Arc(arc) => {
            let centerline = connected_centerline.map_or_else(
                || arc_centerline_points(instruction, arc, context, true),
                |points| centerline_in_pixels(points, canvas),
            );
            if uses_hand_stroke(instruction.weight)
                && centerline
                    .windows(2)
                    .any(|pair| (pair[1].x - pair[0].x).hypot(pair[1].y - pair[0].y) > 1.0e-9)
            {
                hand_contour(
                    instruction,
                    &centerline,
                    &BTreeSet::new(),
                    style,
                    context,
                    false,
                )
            } else {
                apply_style(
                    Element::new("path").attr("d", open_path(&centerline)),
                    style,
                    false,
                )
            }
        }
        MarkGeometry::Cloudform { center, size } => {
            let controls = generate_cloudform_contour(CloudformRequest {
                center: point_to_pixels(center, canvas),
                size: size_to_pixels(size, canvas),
                performance_seed: Some(context.seed_for(instruction)),
                instruction_index: context.instruction_index,
                mark_index: context.mark_index,
                variation: instruction.variation.as_ref(),
                weight: instruction.weight,
                point_count: 49,
            });
            let sampled = sample_closed_catmull_rom(&controls, 5);
            render_affine_closed(instruction, &sampled, &BTreeSet::new(), style, context)
        }
        MarkGeometry::FreeLine { from, to } => {
            render_free_line(instruction, from, to, style, context, obstacles)
        }
    }
}

/// Render one expanded, performed instruction into an SVG-specific element tree.
pub fn render_instruction(
    instruction: &Instruction,
    context: MarkContext<'_>,
) -> Result<Element, MarkError> {
    let geometry = MarkGeometry::of(instruction)?;
    Ok(render_instruction_with_line_centerline(
        instruction,
        geometry,
        context,
        None,
        &[],
    ))
}

fn render_round(
    instruction: &Instruction,
    center: Point,
    radii: Radii,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let center = point_to_pixels(center, context.canvas);
    let (rx, ry) = radii.xy();
    let mut contour = circle_points(
        center,
        rx,
        ry,
        stroke_sample_count(radii.perimeter(), context.canvas),
    );
    if let Some(variation) = instruction
        .variation
        .as_ref()
        .filter(|variation| needs_contour_variation(variation))
    {
        contour = closed_contour_with_variation(
            &contour,
            center,
            variation,
            context.seed_for(instruction),
            amplitude(instruction, context.canvas),
        );
    }
    let geometry = match radii {
        Radii::Circle(radius) => Element::new("circle")
            .attr("cx", format_number(center.x))
            .attr("cy", format_number(center.y))
            .attr("r", format_number(radius)),
        Radii::Ellipse(rx, ry) => Element::new("ellipse")
            .attr("cx", format_number(center.x))
            .attr("cy", format_number(center.y))
            .attr("rx", format_number(rx))
            .attr("ry", format_number(ry)),
    };
    if uses_hand_stroke(instruction.weight) {
        let mut group = accepted_fills::group(instruction, context);
        if let Some(fill) = render_interior_fill(instruction, &contour, style, context) {
            group.push(fill);
        }
        let edge = hand_contour(
            instruction,
            &contour,
            &BTreeSet::new(),
            &closed_edge_style(instruction, style),
            context,
            true,
        );
        group = closed_mark_group(instruction, group, edge);
        rotate(group, instruction, context.canvas)
    } else {
        rotate(
            mechanical_closed_mark(instruction, &contour, geometry, style, context),
            instruction,
            context.canvas,
        )
    }
}

fn render_arc(
    instruction: &Instruction,
    arc: ArcSpan,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    if uses_hand_stroke(instruction.weight) {
        let centerline = arc_centerline_points(instruction, arc, context, false);
        return rotate(
            hand_contour(
                instruction,
                &centerline,
                &BTreeSet::new(),
                style,
                context,
                false,
            ),
            instruction,
            context.canvas,
        );
    }
    let center = point_to_pixels(arc.center, context.canvas);
    let radius = arc.radius * context.canvas.unit();
    let (start, end) = (arc.start, arc.end);
    let start_radians = start.to_radians();
    let end_radians = end.to_radians();
    let start_point = Point::new(
        center.x + radius * start_radians.cos(),
        center.y - radius * start_radians.sin(),
    );
    let end_point = Point::new(
        center.x + radius * end_radians.cos(),
        center.y - radius * end_radians.sin(),
    );
    let large = usize::from((end - start).abs() > 180.0);
    let sweep = usize::from(end - start <= 0.0);
    let path = format!(
        "M {} {} A {} {} 0 {large} {sweep} {} {}",
        format_number(start_point.x),
        format_number(start_point.y),
        format_number(radius),
        format_number(radius),
        format_number(end_point.x),
        format_number(end_point.y)
    );
    rotate(
        apply_style(Element::new("path").attr("d", path), style, false),
        instruction,
        context.canvas,
    )
}

fn render_cloudform(
    instruction: &Instruction,
    center: Point,
    size: Point,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let controls = generate_cloudform_contour(CloudformRequest {
        center: point_to_pixels(center, context.canvas),
        size: size_to_pixels(size, context.canvas),
        performance_seed: Some(context.seed_for(instruction)),
        instruction_index: context.instruction_index,
        mark_index: context.mark_index,
        variation: instruction.variation.as_ref(),
        weight: instruction.weight,
        point_count: 49,
    });
    let sampled = sample_closed_catmull_rom(&controls, 5);
    let geometry = apply_style(
        Element::new("path")
            .attr("d", cloudform_path(&controls))
            .attr("class", "cloudform contour-v1"),
        style,
        true,
    );
    if uses_hand_stroke(instruction.weight) {
        let mut group = accepted_fills::group(instruction, context);
        if let Some(fill) = render_interior_fill(instruction, &sampled, style, context) {
            group.push(fill);
        }
        let edge = hand_contour(
            instruction,
            &sampled,
            &BTreeSet::new(),
            &closed_edge_style(instruction, style),
            context,
            true,
        );
        group = closed_mark_group(instruction, group, edge);
        rotate(group, instruction, context.canvas)
    } else {
        rotate(
            mechanical_closed_mark(instruction, &sampled, geometry, style, context),
            instruction,
            context.canvas,
        )
    }
}

/// Draw one mark of `geometry`, which [`MarkGeometry::of`] read from `instruction`.
///
/// A Line or an open Arc that a path connection targets follows the
/// `connected_centerline` fixed during execution, in short-side units. A free
/// line turns away from `obstacles`, the pixel boxes of the marks drawn before
/// it that are not lines.
pub(crate) fn render_instruction_with_line_centerline(
    instruction: &Instruction,
    geometry: MarkGeometry,
    context: MarkContext<'_>,
    connected_centerline: Option<&[Point]>,
    obstacles: &[Obstacle],
) -> Element {
    let mut style = mark_style(instruction, context);
    accepted_fills::prepare_style(instruction, &mut style);
    if !context.geometry_transform.is_identity() {
        return render_affine_instruction(
            instruction,
            geometry,
            &style,
            context,
            connected_centerline,
            obstacles,
        );
    }
    let canvas = context.canvas;
    match geometry {
        MarkGeometry::Line { from, to } => {
            let start = point_to_pixels(from, canvas);
            let end = point_to_pixels(to, canvas);
            if uses_hand_stroke(instruction.weight) {
                hand_line(
                    instruction,
                    start,
                    end,
                    connected_centerline,
                    &style,
                    context,
                )
            } else {
                rotring_line(
                    instruction,
                    start,
                    end,
                    connected_centerline,
                    &style,
                    context,
                )
            }
        }
        MarkGeometry::Circle { center, radius } => render_round(
            instruction,
            center,
            Radii::of_circle(radius, canvas),
            &style,
            context,
        ),
        MarkGeometry::Ellipse { center, size } => render_round(
            instruction,
            center,
            Radii::of_ellipse(size, canvas),
            &style,
            context,
        ),
        MarkGeometry::Square { position, size } => render_corner_shape(
            instruction,
            &square_corners(position, size, canvas),
            &style,
            context,
        ),
        MarkGeometry::Triangle { position, size } => render_corner_shape(
            instruction,
            &triangle_corners(position, size, canvas),
            &style,
            context,
        ),
        MarkGeometry::Polygon {
            center,
            radius,
            sides,
        } => render_corner_shape(
            instruction,
            &polygon_corners(center, radius, sides, canvas),
            &style,
            context,
        ),
        MarkGeometry::Crescent { center, size } => {
            render_crescent(instruction, center, size, &style, context)
        }
        MarkGeometry::Arc(arc) => match connected_centerline {
            Some(centerline) => {
                let centerline = centerline_in_pixels(centerline, canvas);
                if uses_hand_stroke(instruction.weight) {
                    hand_contour(
                        instruction,
                        &centerline,
                        &BTreeSet::new(),
                        &style,
                        context,
                        false,
                    )
                } else {
                    apply_style(
                        Element::new("path").attr("d", open_path(&centerline)),
                        &style,
                        false,
                    )
                }
            }
            None => render_arc(instruction, arc, &style, context),
        },
        MarkGeometry::Cloudform { center, size } => {
            render_cloudform(instruction, center, size, &style, context)
        }
        MarkGeometry::FreeLine { from, to } => {
            render_free_line(instruction, from, to, &style, context, obstacles)
        }
    }
}

/// A free line's centerline in pixels and its corners (I-715).
///
/// The ends take the instruction's rotation and the group transform first, so
/// the path is built where it is drawn and turns away from the paper's edges
/// and `obstacles` there. The path is built once, for this mark, and a
/// variation then moves it about its own course with the ends kept.
pub(crate) fn free_line_centerline(
    instruction: &Instruction,
    from: Point,
    to: Point,
    context: MarkContext<'_>,
    obstacles: &[Obstacle],
) -> (Vec<Point>, BTreeSet<usize>) {
    let canvas = context.canvas;
    let place = |point: Point| {
        let point = point_to_pixels(point, canvas);
        if context.geometry_transform.is_identity() {
            rotated_instruction_point(instruction, context, point)
        } else {
            geometry_point(instruction, context, point)
        }
    };
    let variation = instruction
        .variation
        .as_ref()
        .filter(|variation| needs_path_variation(variation));
    // A varied path is sampled as finely as a varied line, a plain one as a
    // stroke.
    let spacing = canvas.unit()
        * if variation.is_some() {
            SEGMENT_TARGET_RATIO
        } else {
            STROKE_SAMPLE_TARGET_RATIO
        };
    let FreeLinePath { points, corners } = free_line_path(FreeLineRequest {
        weight: instruction.weight,
        seed: free_line_seed(
            context.seed_for(instruction),
            context.instruction_index,
            context.mark_index,
        ),
        start: place(from),
        end: place(to),
        sheet: Sheet {
            width: canvas.width,
            height: canvas.height,
        },
        obstacles,
        spacing,
    });
    let points = match variation {
        Some(variation) => open_path_with_variation(
            &points,
            variation,
            context.seed_for(instruction),
            amplitude(instruction, canvas),
        ),
        None => points,
    };
    (points, corners)
}

/// The pixel box a drawn mark leaves for the free lines drawn after it, or
/// none for a Line or a free line, which a free line does not avoid (I-715).
///
/// The box holds the mark's geometry after its rotation and the group
/// `transform` (in short-side units, as performance keeps it), before any
/// clipping. A cloudform's is the contour this very mark drew, since each
/// copy draws its own.
pub(crate) fn free_line_obstacle(
    instruction: &Instruction,
    geometry: MarkGeometry,
    context: MarkContext<'_>,
    transform: crate::affine::AffineTransform,
) -> Option<Obstacle> {
    let canvas = context.canvas;
    match geometry {
        MarkGeometry::Line { .. } | MarkGeometry::FreeLine { .. } => None,
        MarkGeometry::Cloudform { center, size } => {
            let controls = generate_cloudform_contour(CloudformRequest {
                center: point_to_pixels(center, canvas),
                size: size_to_pixels(size, canvas),
                performance_seed: Some(context.seed_for(instruction)),
                instruction_index: context.instruction_index,
                mark_index: context.mark_index,
                variation: instruction.variation.as_ref(),
                weight: instruction.weight,
                point_count: 49,
            });
            let mut obstacle = [
                f64::INFINITY,
                f64::INFINITY,
                f64::NEG_INFINITY,
                f64::NEG_INFINITY,
            ];
            for point in controls {
                let point = if context.geometry_transform.is_identity() {
                    rotated_instruction_point(instruction, context, point)
                } else {
                    geometry_point(instruction, context, point)
                };
                obstacle = [
                    obstacle[0].min(point.x),
                    obstacle[1].min(point.y),
                    obstacle[2].max(point.x),
                    obstacle[3].max(point.y),
                ];
            }
            obstacle
                .iter()
                .all(|value| value.is_finite())
                .then_some(obstacle)
        }
        _ => {
            let bounds = crate::affine_geometry::bounds(
                instruction,
                context.render_seed,
                context.instruction_index,
                Some(canvas),
                context.instruction_seed_override,
                transform,
            )?;
            let unit = canvas.unit();
            let obstacle = [
                bounds.min.x * unit,
                bounds.min.y * unit,
                bounds.max.x * unit,
                bounds.max.y * unit,
            ];
            obstacle
                .iter()
                .all(|value| value.is_finite())
                .then_some(obstacle)
        }
    }
}

/// Draw a free line along [`free_line_centerline`]: a hand tool's open stroke,
/// tapered at both ends and anchored at the corners, or the rotring's path. A
/// broken style lays the thin broken line along it, as on a hand-drawn Line.
fn render_free_line(
    instruction: &Instruction,
    from: Point,
    to: Point,
    style: &MarkStyle,
    context: MarkContext<'_>,
    obstacles: &[Obstacle],
) -> Element {
    let (points, corners) = free_line_centerline(instruction, from, to, context, obstacles);
    let drawn = points
        .windows(2)
        .any(|pair| (pair[1].x - pair[0].x).hypot(pair[1].y - pair[0].y) > 1.0e-9);
    if !drawn || !uses_hand_stroke(instruction.weight) {
        return apply_style(
            Element::new("path").attr("d", open_path(&points)),
            style,
            false,
        );
    }
    let stroke = hand_contour(instruction, &points, &corners, style, context, false);
    if instruction.style == LineStyle::Solid {
        return stroke;
    }
    let mut line_style = style.clone();
    line_style.width = (context.canvas.unit() / 1000.0 * 0.45).max(style.width * 0.42);
    let mut group = Element::new("g");
    group.push(stroke);
    group.push(apply_style(
        Element::new("path").attr("d", open_path(&points)),
        &line_style,
        false,
    ));
    group
}

fn render_corner_shape(
    instruction: &Instruction,
    corners: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let varied = instruction
        .variation
        .as_ref()
        .is_some_and(needs_contour_variation);
    let variation = if varied {
        instruction.variation.as_ref()
    } else {
        None
    };
    let contour = edge_contour_with_anchors(
        corners,
        variation,
        context.seed_for(instruction),
        amplitude(instruction, context.canvas),
        context.canvas,
    );
    let points = if varied { &contour.points } else { corners };
    let geometry = apply_style(
        Element::new("polygon").attr("points", points_attribute(points)),
        style,
        true,
    );
    if uses_hand_stroke(instruction.weight) {
        let mut group = accepted_fills::group(instruction, context);
        if let Some(fill) = render_interior_fill(instruction, &contour.points, style, context) {
            group.push(fill);
        }
        let edge = hand_contour(
            instruction,
            &contour.points,
            &contour.anchors,
            &closed_edge_style(instruction, style),
            context,
            true,
        );
        group = closed_mark_group(instruction, group, edge);
        rotate(group, instruction, context.canvas)
    } else {
        rotate(
            mechanical_closed_mark(instruction, &contour.points, geometry, style, context),
            instruction,
            context.canvas,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_stroke_brought_onto_the_canvas_by_the_mark_rotation_is_kept() {
        // Fill strokes are laid before the mark's SVG `rotate`, so a stroke
        // off the canvas in the mark's own coordinates may land on it.
        let colors = BTreeMap::new();
        let context = MarkContext {
            canvas: CanvasSize::new(1000.0, 1000.0),
            color_map: &colors,
            work_assignment: &colors,
            render_seed: Some(1),
            instruction_seed_override: None,
            instruction_index: 0,
            mark_index: 0,
            wild: false,
            use_filters: false,
            profile: SvgProfile::Display,
            support: crate::support::DEFAULT_SUPPORT,
            geometry_transform: crate::affine::AffineTransform::identity(),
            oil_fill_pass_limit: crate::fills::MAX_OIL_FILL_PASSES,
            effects: crate::effects::MarkEffects::default(),
        };
        let circle = |rotation: &str| {
            serde_json::from_str::<Instruction>(&format!(
                r#"{{"primitive":"circle","center":[0.1,0.5],"radius":0.4{rotation}}}"#
            ))
            .unwrap()
        };
        let off = Point::new(-400.0, 500.0);
        assert!(!reaches_canvas(&circle(""), context, off, off, 1.0));
        // Turned 90 degrees about (100, 500), the point lands at (100, 0).
        assert!(reaches_canvas(
            &circle(r#","rotation":90"#),
            context,
            off,
            off,
            1.0
        ));
    }

    #[test]
    fn a_free_line_path_runs_between_its_rotated_ends_and_its_variation_keeps_them() {
        let colors = BTreeMap::new();
        let context = MarkContext {
            canvas: CanvasSize::new(1000.0, 1000.0),
            color_map: &colors,
            work_assignment: &colors,
            render_seed: Some(7),
            instruction_seed_override: None,
            instruction_index: 1,
            mark_index: 0,
            wild: false,
            use_filters: false,
            profile: SvgProfile::Display,
            support: crate::support::DEFAULT_SUPPORT,
            geometry_transform: crate::affine::AffineTransform::identity(),
            oil_fill_pass_limit: crate::fills::MAX_OIL_FILL_PASSES,
            effects: crate::effects::MarkEffects::default(),
        };
        let free_line = |extra: &str| {
            serde_json::from_str::<Instruction>(&format!(
                r#"{{"primitive":"free_line","from":[0.225,0.5],"to":[0.775,0.5],"rotation":-23,"weight":"brush_thin"{extra}}}"#
            ))
            .unwrap()
        };
        // -23 degrees about the chord's midpoint (500, 500).
        let (sin, cos) = (-23.0_f64).to_radians().sin_cos();
        let turned = |x: f64| Point::new(500.0 + (x - 500.0) * cos, 500.0 + (x - 500.0) * sin);
        let (start, end) = (turned(225.0), turned(775.0));
        for extra in [
            "",
            r#","variation":{"quality":"wave","frequency":"high","amplitude":"broad","dimensions":["position_x","position_y"]}"#,
        ] {
            let instruction = free_line(extra);
            let (points, _) = free_line_centerline(
                &instruction,
                Point::new(0.225, 0.5),
                Point::new(0.775, 0.5),
                context,
                &[],
            );
            for (point, expected) in [(points[0], start), (points[points.len() - 1], end)] {
                assert!(
                    (point.x - expected.x).abs() <= 1.0e-6
                        && (point.y - expected.y).abs() <= 1.0e-6,
                    "{extra}: {point:?} {expected:?}"
                );
            }
            assert!(points.len() > 2, "{extra}");
        }
        let plain = free_line_centerline(
            &free_line(""),
            Point::new(0.225, 0.5),
            Point::new(0.775, 0.5),
            context,
            &[],
        );
        let varied = free_line_centerline(
            &free_line(
                r#","variation":{"quality":"wave","frequency":"high","amplitude":"broad","dimensions":["position_x","position_y"]}"#,
            ),
            Point::new(0.225, 0.5),
            Point::new(0.775, 0.5),
            context,
            &[],
        );
        assert_ne!(plain.0, varied.0, "a variation moves the path");
    }

    #[test]
    fn silverpoint_thinness_stops_at_the_shared_minimum_width() {
        let instruction = |thinness| {
            serde_json::from_str::<Instruction>(&format!(
                r#"{{"primitive":"line","weight":"silverpoint","thinness":"{thinness}"}}"#
            ))
            .unwrap()
        };
        let canvas = CanvasSize::new(1000.0, 1000.0);
        let fine = mark_width(&instruction("fine"), canvas);
        let extra_fine = mark_width(&instruction("extra_fine"), canvas);

        assert_eq!(fine, MIN_STROKE_WIDTH);
        assert_eq!(extra_fine, MIN_STROKE_WIDTH);
    }

    #[test]
    fn a_sweep_line_is_the_wash_band_without_its_paleness() {
        let colors = BTreeMap::new();
        let context = MarkContext {
            canvas: CanvasSize::new(1000.0, 1000.0),
            color_map: &colors,
            work_assignment: &colors,
            render_seed: Some(1),
            instruction_seed_override: None,
            instruction_index: 0,
            mark_index: 0,
            wild: false,
            use_filters: false,
            profile: SvgProfile::Display,
            support: crate::support::DEFAULT_SUPPORT,
            geometry_transform: crate::affine::AffineTransform::identity(),
            oil_fill_pass_limit: crate::fills::MAX_OIL_FILL_PASSES,
            effects: crate::effects::MarkEffects::default(),
        };
        let line = |surface: &str, intensity: &str| {
            serde_json::from_str::<Instruction>(&format!(
                r#"{{"primitive":"line","weight":"pen","surface_intensity":"{intensity}"{surface}}}"#
            ))
            .unwrap()
        };
        let plain = mark_style(&line("", "normal"), context);
        let wash = mark_style(&line(r#","surface":{"texture":"wash"}"#, "normal"), context);
        let sweep = mark_style(
            &line(r#","surface":{"texture":"sweep"}"#, "normal"),
            context,
        );
        let faint_sweep = mark_style(&line(r#","surface":{"texture":"sweep"}"#, "faint"), context);

        assert_eq!(wash.width, plain.width * 3.0);
        assert_eq!(sweep.width, wash.width);
        assert_eq!(plain.stroke_opacity, 1.0);
        assert_eq!(wash.stroke_opacity, 0.35);
        assert_eq!(sweep.stroke_opacity, 0.8);
        // 薄いを添えた刷き reads a little darker than the retired 薄墨 band, so a
        // migrated work (薄墨 -> 薄い刷き) darkens slightly (the author's choice).
        assert_eq!(faint_sweep.stroke_opacity, 0.44);
        assert!(faint_sweep.stroke_opacity > wash.stroke_opacity);
        // A closed shape draws its sweep as a surface, not as a band.
        let circle = serde_json::from_str::<Instruction>(
            r#"{"primitive":"circle","weight":"pen","surface":{"texture":"sweep"}}"#,
        )
        .unwrap();
        assert_eq!(mark_style(&circle, context).width, plain.width);
    }

    #[test]
    fn a_rotring_line_follows_its_varied_path_or_stays_straight() {
        let colors = BTreeMap::new();
        let context = MarkContext {
            canvas: CanvasSize::new(1000.0, 1000.0),
            color_map: &colors,
            work_assignment: &colors,
            render_seed: Some(7),
            instruction_seed_override: None,
            instruction_index: 0,
            mark_index: 0,
            wild: false,
            use_filters: false,
            profile: SvgProfile::Display,
            support: crate::support::DEFAULT_SUPPORT,
            geometry_transform: crate::affine::AffineTransform::identity(),
            oil_fill_pass_limit: crate::fills::MAX_OIL_FILL_PASSES,
            effects: crate::effects::MarkEffects::default(),
        };
        let line = |variation: &str| {
            serde_json::from_str::<Instruction>(&format!(
                r#"{{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"rotring"{variation}}}"#
            ))
            .unwrap()
        };
        let draw = |instruction: &Instruction, centerline: Option<&[Point]>| {
            render_instruction_with_line_centerline(
                instruction,
                MarkGeometry::of(instruction).unwrap(),
                context,
                centerline,
                &[],
            )
        };
        let points = |element: &Element| {
            element
                .attribute("points")
                .unwrap()
                .split(' ')
                .map(|pair| {
                    let (x, y) = pair.split_once(',').unwrap();
                    Point::new(x.parse().unwrap(), y.parse().unwrap())
                })
                .collect::<Vec<_>>()
        };
        let plain = draw(&line(""), None);
        assert_eq!(plain.name(), "line");
        let varied = line(
            r#","variation":{"quality":"wave","frequency":"slow","amplitude":"medium","dimensions":["position_x","position_y"]}"#,
        );
        let waved = draw(&varied, None);
        assert_eq!(waved.name(), "polyline");
        let path = points(&waved);
        assert_eq!(path[0], Point::new(100.0, 500.0));
        assert_eq!(path[path.len() - 1], Point::new(900.0, 500.0));
        assert!(path.iter().any(|point| (point.y - 500.0).abs() > 1.0));
        for name in [
            "stroke",
            "stroke-width",
            "stroke-linecap",
            "stroke-opacity",
            "fill",
        ] {
            assert_eq!(waved.attribute(name), plain.attribute(name), "{name}");
        }
        // A path connection fixes the same centerline, and the line follows it.
        let centerline = crate::mark_paths::connected_line_centerline(
            &varied,
            context.seed_for(&varied),
            context.canvas,
            crate::affine::AffineTransform::identity(),
        )
        .unwrap();
        let connected = points(&draw(&varied, Some(&centerline)));
        assert_eq!(connected.len(), path.len());
        for (point, expected) in connected.iter().zip(&path) {
            assert!(
                (point.x - expected.x).abs() <= 1.0e-5 && (point.y - expected.y).abs() <= 1.0e-5,
                "{point:?} {expected:?}"
            );
        }
    }
}
