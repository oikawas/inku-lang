//! SVG path construction and performed stroke emission for primitive marks.

use std::collections::BTreeSet;

use crate::determinism::{needs_contour_variation, needs_path_variation};
use crate::geometry::{
    ArcGeometry, arc_points, arc_points_with_variation, line_with_variation, point_to_pixels,
    size_to_pixels, stroke_sample_count,
};
use crate::marks::{MarkContext, MarkStyle, apply_style, is_closed, mark_width};
use crate::materials::{OilPaintStyle, oil_paint_stroke, with_texture_filter};
use crate::planning::instruction_anchor_on_canvas;
use crate::stroke::{
    ContourStrokeRequest, ContourStrokeResult, StrokeRequest, StrokeTerminal,
    outline_for_centerline, synthesize_contour, synthesize_stroke,
};
use crate::support::{Support, support_with_mark_word};
use crate::svg::{Element, format_number};
use crate::types::{Amplitude, CanvasSize, Instruction, LineStyle, Point, Primitive, Weight};

pub(crate) fn rotate(
    mut element: Element,
    instruction: &Instruction,
    canvas: CanvasSize,
) -> Element {
    let Some(rotation) = instruction
        .rotation
        .filter(|rotation| rotation.abs() >= 1.0e-9)
    else {
        return element;
    };
    let center = point_to_pixels(
        instruction_anchor_on_canvas(instruction, Some(canvas)),
        canvas,
    );
    element.set_attr(
        "transform",
        format!(
            "rotate({} {} {})",
            format_number(rotation),
            format_number(center.x),
            format_number(center.y)
        ),
    );
    element
}

fn closed_subpath(points: &[Point]) -> String {
    if points.is_empty() {
        return String::new();
    }
    let body = points
        .iter()
        .map(|point| format!("{} {}", format_number(point.x), format_number(point.y)))
        .collect::<Vec<_>>()
        .join(" L ");
    format!("M {body} Z")
}

fn split_at_breaks(points: &[Point], minimum: usize) -> Vec<Vec<Point>> {
    let mut runs = Vec::new();
    let mut current = Vec::new();
    for point in points {
        if !point.x.is_finite() || !point.y.is_finite() {
            if current.len() >= minimum {
                runs.push(std::mem::take(&mut current));
            }
        } else {
            current.push(*point);
        }
    }
    if current.len() >= minimum {
        runs.push(current);
    }
    runs
}

pub(crate) fn polygon_path(points: &[Point]) -> String {
    if points
        .iter()
        .any(|point| !point.x.is_finite() || !point.y.is_finite())
    {
        split_at_breaks(points, 3)
            .iter()
            .map(|run| closed_subpath(run))
            .collect::<Vec<_>>()
            .join(" ")
    } else {
        closed_subpath(points)
    }
}

pub(crate) fn contour_stroke_path(stroke: &ContourStrokeResult) -> String {
    if stroke.closed {
        return format!(
            "{} {}",
            polygon_path(&stroke.left),
            polygon_path(&stroke.right)
        );
    }
    if stroke
        .left
        .iter()
        .all(|point| point.x.is_finite() && point.y.is_finite())
    {
        let points = stroke
            .left
            .iter()
            .copied()
            .chain(stroke.right.iter().rev().copied())
            .collect::<Vec<_>>();
        return polygon_path(&points);
    }
    split_at_breaks(&stroke.left, 2)
        .into_iter()
        .zip(split_at_breaks(&stroke.right, 2))
        .map(|(left, right)| {
            let points = left
                .into_iter()
                .chain(right.into_iter().rev())
                .collect::<Vec<_>>();
            closed_subpath(&points)
        })
        .collect::<Vec<_>>()
        .join(" ")
}

pub(crate) fn points_attribute(points: &[Point]) -> String {
    points
        .iter()
        .map(|point| format!("{},{}", format_number(point.x), format_number(point.y)))
        .collect::<Vec<_>>()
        .join(" ")
}

pub(crate) fn uses_hand_stroke(weight: Weight) -> bool {
    weight != Weight::Rotring
}

fn instruction_support(instruction: &Instruction, support: Support) -> Support {
    if is_closed(instruction.primitive) {
        return support;
    }
    instruction.surface.as_ref().map_or(support, |surface| {
        support_with_mark_word(support, surface.texture)
    })
}

pub(crate) fn grid_step(weight: Weight, canvas: CanvasSize) -> f64 {
    let quantize = crate::stroke::grammar(weight).quantize;
    if quantize > 0.0 {
        canvas.unit() * quantize
    } else {
        0.0
    }
}

pub(crate) fn amplitude(instruction: &Instruction, canvas: CanvasSize) -> f64 {
    let Some(variation) = instruction.variation.as_ref() else {
        return 0.0;
    };
    let widths = amplitude_width(variation.amplitude);
    let representative =
        match instruction.primitive {
            Primitive::Circle | Primitive::Polygon | Primitive::Arc | Primitive::Point => {
                instruction.radius.unwrap_or(0.02) * canvas.unit()
            }
            Primitive::Ellipse => instruction.size.map_or(canvas.unit() * 0.02, |size| {
                let size = size_to_pixels(size, canvas);
                ((size.x / 2.0) * (size.y / 2.0)).max(0.0).sqrt()
            }),
            Primitive::Square | Primitive::Triangle | Primitive::Cloudform => {
                instruction.size.map_or(canvas.unit() * 0.02, |size| {
                    size_to_pixels(size, canvas)
                        .x
                        .min(size_to_pixels(size, canvas).y)
                        / 2.0
                })
            }
            Primitive::Line => instruction.from_.zip(instruction.to).map_or(
                canvas.unit() * 0.02,
                |(start, end)| {
                    let start = point_to_pixels(start, canvas);
                    let end = point_to_pixels(end, canvas);
                    (end.x - start.x).hypot(end.y - start.y)
                },
            ),
        }
        .max(canvas.unit() * 0.02);
    (widths * mark_width(instruction, canvas)).min(0.40 * representative)
}

pub(crate) const fn amplitude_width(amplitude: Amplitude) -> f64 {
    match amplitude {
        Amplitude::Fine => 0.35,
        Amplitude::Medium => 0.6,
        Amplitude::Broad => 2.0,
    }
}

/// Fix the visible centerline for a Line that an explicit path connection targets.
///
/// The result is in physical short-side units. Its variation is resolved before
/// later affine transforms so relation execution and final rendering can share
/// one curve and transform it together with dependents.
pub(crate) fn connected_line_centerline(
    instruction: &Instruction,
    seed: crate::types::Seed,
    canvas: CanvasSize,
    transform: crate::affine::AffineTransform,
) -> Option<Vec<Point>> {
    let variation = instruction
        .variation
        .as_ref()
        .filter(|variation| needs_path_variation(variation))?;
    if instruction.primitive != Primitive::Line || !uses_hand_stroke(instruction.weight) {
        return None;
    }
    let unit = canvas.unit();
    if !unit.is_finite() || unit <= 0.0 {
        return None;
    }
    let start = point_to_pixels(instruction.from_?, canvas);
    let end = point_to_pixels(instruction.to?, canvas);
    let mut centerline = line_with_variation(
        start,
        end,
        variation,
        seed,
        amplitude(instruction, canvas),
        canvas,
    );
    if let Some(degrees) = instruction
        .rotation
        .filter(|degrees| degrees.abs() >= 1.0e-9)
    {
        let pivot = point_to_pixels(
            instruction_anchor_on_canvas(instruction, Some(canvas)),
            canvas,
        );
        let (sin, cos) = degrees.to_radians().sin_cos();
        for point in &mut centerline {
            let dx = point.x - pivot.x;
            let dy = point.y - pivot.y;
            *point = Point::new(pivot.x + dx * cos - dy * sin, pivot.y + dx * sin + dy * cos);
        }
    }
    let transform = transform.in_pixels(unit);
    centerline
        .into_iter()
        .map(|point| {
            let point = transform.apply(point);
            let point = Point::new(point.x / unit, point.y / unit);
            (point.x.is_finite() && point.y.is_finite()).then_some(point)
        })
        .collect()
}

/// Fix the visible centerline for an Arc that an interior path connection targets.
///
/// The result is in physical short-side units and includes the instruction rotation
/// and every enclosing affine transform so execution and rendering share one path.
pub(crate) fn connected_arc_centerline(
    instruction: &Instruction,
    seed: crate::types::Seed,
    canvas: CanvasSize,
    transform: crate::affine::AffineTransform,
) -> Option<Vec<Point>> {
    if instruction.primitive != Primitive::Arc || instruction.arc_form.is_some() {
        return None;
    }
    let unit = canvas.unit();
    if !unit.is_finite() || unit <= 0.0 {
        return None;
    }
    let center = point_to_pixels(instruction.center?, canvas);
    let radius = instruction.radius? * unit;
    let start = instruction.angle_start?;
    let end = instruction.angle_end?;
    let length = radius * (end - start).to_radians().abs();
    let mut centerline = instruction
        .variation
        .as_ref()
        .filter(|variation| needs_contour_variation(variation))
        .map_or_else(
            || {
                arc_points(
                    center,
                    radius,
                    start,
                    end,
                    stroke_sample_count(length, canvas),
                )
            },
            |variation| {
                arc_points_with_variation(
                    ArcGeometry {
                        center,
                        radius,
                        start_degrees: start,
                        end_degrees: end,
                    },
                    variation,
                    seed,
                    amplitude(instruction, canvas),
                    canvas,
                )
            },
        );
    if let Some(degrees) = instruction
        .rotation
        .filter(|degrees| degrees.abs() >= 1.0e-9)
    {
        let pivot = point_to_pixels(
            instruction_anchor_on_canvas(instruction, Some(canvas)),
            canvas,
        );
        let (sin, cos) = degrees.to_radians().sin_cos();
        for point in &mut centerline {
            let dx = point.x - pivot.x;
            let dy = point.y - pivot.y;
            *point = Point::new(pivot.x + dx * cos - dy * sin, pivot.y + dx * sin + dy * cos);
        }
    }
    let transform = transform.in_pixels(unit);
    centerline
        .into_iter()
        .map(|point| {
            let point = transform.apply(point);
            let point = Point::new(point.x / unit, point.y / unit);
            (point.x.is_finite() && point.y.is_finite()).then_some(point)
        })
        .collect()
}

pub(crate) fn hand_line(
    instruction: &Instruction,
    start: Point,
    end: Point,
    connected_centerline: Option<&[Point]>,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    let seed = context.seed_for(instruction);
    let connected_centerline = connected_centerline.map(|points| {
        points
            .iter()
            .map(|point| {
                Point::new(
                    point.x * context.canvas.unit(),
                    point.y * context.canvas.unit(),
                )
            })
            .collect::<Vec<_>>()
    });
    let has_connected_centerline = connected_centerline.is_some();
    let (start, end) = connected_centerline
        .as_deref()
        .and_then(|points| points.first().copied().zip(points.last().copied()))
        .unwrap_or((start, end));
    let sample_count =
        stroke_sample_count((end.x - start.x).hypot(end.y - start.y), context.canvas);
    let support = instruction_support(instruction, context.support);
    let stroke = synthesize_stroke(StrokeRequest {
        start,
        end,
        base_width: style.width,
        weight: instruction.weight,
        seed,
        sample_count,
        wild: context.wild,
        grid_step: grid_step(instruction.weight, context.canvas),
        support,
    });
    let centerline = connected_centerline.or_else(|| {
        instruction
            .variation
            .as_ref()
            .filter(|variation| needs_path_variation(variation))
            .map(|variation| {
                line_with_variation(
                    start,
                    end,
                    variation,
                    seed,
                    amplitude(instruction, context.canvas),
                    context.canvas,
                )
            })
    });
    let outline = if let Some(centerline) = centerline {
        let varied = synthesize_stroke(StrokeRequest {
            start,
            end,
            base_width: style.width,
            weight: instruction.weight,
            seed,
            sample_count: centerline.len(),
            wild: context.wild,
            grid_step: grid_step(instruction.weight, context.canvas),
            support,
        });
        let widths = varied
            .samples
            .iter()
            .map(|sample| sample.width)
            .collect::<Vec<_>>();
        outline_for_centerline(&centerline, &widths, &varied.cuts)
    } else {
        stroke.outline
    };
    let mut group = Element::new("g").attr(
        "class",
        format!(
            "stroke-engine-v1 controls-{} events-{}",
            stroke.samples.len(),
            stroke.event_count
        ),
    );
    if instruction.weight == Weight::OilPaint {
        let middle = outline.len() / 2;
        let right = outline[middle..].iter().rev().copied().collect::<Vec<_>>();
        group.push(oil_paint_stroke(
            polygon_path(&outline),
            &outline[..middle],
            &right,
            OilPaintStyle::plain(&style.color, style.stroke_opacity),
            seed,
            false,
        ));
    } else {
        group.push(
            Element::new("path")
                .attr("d", polygon_path(&outline))
                .attr("fill", &style.color)
                .attr("fill-opacity", format_number(style.stroke_opacity))
                .attr("stroke", "none"),
        );
    }
    if instruction.style != LineStyle::Solid {
        let mut line_style = style.clone();
        line_style.width = (context.canvas.unit() / 1000.0 * 0.45).max(style.width * 0.42);
        group.push(apply_style(
            Element::new("line")
                .attr("x1", format_number(start.x))
                .attr("y1", format_number(start.y))
                .attr("x2", format_number(end.x))
                .attr("y2", format_number(end.y)),
            &line_style,
            false,
        ));
    }
    let group = with_texture_filter(group, instruction.weight, context.use_filters);
    if !has_connected_centerline && context.geometry_transform.is_identity() {
        rotate(group, instruction, context.canvas)
    } else {
        group
    }
}

pub(crate) fn hand_contour(
    instruction: &Instruction,
    centerline: &[Point],
    anchors: &BTreeSet<usize>,
    style: &MarkStyle,
    context: MarkContext<'_>,
    closed: bool,
) -> Element {
    let stroke = synthesize_contour(ContourStrokeRequest {
        centerline,
        base_width: style.width,
        weight: instruction.weight,
        seed: context.seed_for(instruction),
        closed,
        anchors,
        grid_step: grid_step(instruction.weight, context.canvas),
        wild: context.wild,
        support: instruction_support(instruction, context.support),
        terminal: StrokeTerminal::Taper,
    });
    if instruction.weight == Weight::OilPaint {
        return oil_paint_stroke(
            contour_stroke_path(&stroke),
            &stroke.left,
            &stroke.right,
            if closed && style.fill && crate::accepted_fills::solid_fill(instruction) {
                OilPaintStyle::filled(
                    &style.color,
                    style.stroke_opacity,
                    instruction.surface_intensity,
                    context.canvas,
                    false,
                )
            } else {
                OilPaintStyle::plain(&style.color, style.stroke_opacity)
            },
            context.seed_for(instruction),
            closed,
        );
    }
    with_texture_filter(
        Element::new("g")
            .attr(
                "class",
                format!(
                    "contour-stroke-v1 controls-{} events-{}",
                    stroke.samples.len(),
                    stroke.event_count
                ),
            )
            .tap(|group| {
                group.push(
                    Element::new("path")
                        .attr("d", contour_stroke_path(&stroke))
                        .attr("fill", &style.color)
                        .attr("fill-opacity", format_number(style.stroke_opacity))
                        .attr("fill-rule", if closed { "evenodd" } else { "nonzero" })
                        .attr("stroke", "none"),
                );
            }),
        instruction.weight,
        context.use_filters,
    )
}

trait ElementTap {
    fn tap(self, action: impl FnOnce(&mut Self)) -> Self;
}

impl ElementTap for Element {
    fn tap(mut self, action: impl FnOnce(&mut Self)) -> Self {
        action(&mut self);
        self
    }
}

pub(crate) fn cloudform_path(points: &[Point]) -> String {
    if points.len() < 3 {
        return closed_subpath(points);
    }
    let count = points.len();
    let mut commands = vec![format!(
        "M {} {}",
        format_number(points[0].x),
        format_number(points[0].y)
    )];
    for index in 0..count {
        let p0 = points[(index + count - 1) % count];
        let p1 = points[index];
        let p2 = points[(index + 1) % count];
        let p3 = points[(index + 2) % count];
        let c1 = Point::new(p1.x + (p2.x - p0.x) / 6.0, p1.y + (p2.y - p0.y) / 6.0);
        let c2 = Point::new(p2.x - (p3.x - p1.x) / 6.0, p2.y - (p3.y - p1.y) / 6.0);
        commands.push(format!(
            "C {} {} {} {} {} {}",
            format_number(c1.x),
            format_number(c1.y),
            format_number(c2.x),
            format_number(c2.y),
            format_number(p2.x),
            format_number(p2.y)
        ));
    }
    commands.push("Z".to_owned());
    commands.join(" ")
}
