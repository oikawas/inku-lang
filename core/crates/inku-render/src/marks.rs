//! Primitive-to-SVG mark rendering built on the portable stroke and geometry domains.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

use crate::cloudform::{CloudformRequest, generate_cloudform_contour, sample_closed_catmull_rom};
use crate::determinism::{instruction_seed, needs_contour_variation};
use crate::fills::{is_noncomputer_solid_fill, render_interior_fill};
use crate::geometry::{
    ArcGeometry, arc_points, arc_points_with_variation, circle_points,
    closed_contour_with_variation, edge_contour_with_anchors, ellipse_perimeter, point_to_pixels,
    polygon_points, size_to_pixels, stroke_sample_count,
};
use crate::mark_paths::{
    amplitude, cloudform_path, hand_contour, hand_line, points_attribute, rotate, uses_hand_stroke,
};
use crate::palette::resolve_color;
use crate::support::Support;
use crate::svg::{Element, format_number};
use crate::types::{
    CanvasSize, CarveDepth, Instruction, LineStyle, Point, Primitive, Seed, SurfaceTexture,
    SvgProfile, Thinness, Weight,
};

pub(crate) const MIN_STROKE_WIDTH: f64 = 0.5;

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
    pub instruction_index: usize,
    pub mark_index: usize,
    pub wild: bool,
    pub use_filters: bool,
    pub profile: SvgProfile,
    pub support: Support,
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
        Weight::Burin => 3.2,
        Weight::Drypoint => 2.6,
    }
}

pub(crate) fn thinness_scale(thinness: Option<Thinness>) -> f64 {
    match thinness {
        None => 1.0,
        Some(Thinness::Fine) => 0.6,
        Some(Thinness::ExtraFine) => 0.35,
    }
}

pub(crate) fn is_closed(primitive: Primitive) -> bool {
    matches!(
        primitive,
        Primitive::Circle
            | Primitive::Ellipse
            | Primitive::Square
            | Primitive::Triangle
            | Primitive::Polygon
            | Primitive::Cloudform
    )
}

fn is_wash_mark(instruction: &Instruction) -> bool {
    !is_closed(instruction.primitive)
        && instruction
            .surface
            .as_ref()
            .is_some_and(|surface| surface.texture == SurfaceTexture::Wash)
}

pub(crate) fn mark_width(instruction: &Instruction, canvas: CanvasSize) -> f64 {
    let width = (weight_width(instruction.weight) * thinness_scale(instruction.thinness))
        .max(MIN_STROKE_WIDTH)
        * canvas.unit()
        / 1000.0;
    width * if is_wash_mark(instruction) { 3.0 } else { 1.0 }
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
        Weight::Burin => 0.96,
        Weight::Drypoint => 0.92,
    }
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

fn fade_level(hint: &str) -> Option<f64> {
    let start = hint.find("fade_level=")? + "fade_level=".len();
    let value = hint[start..]
        .chars()
        .take_while(|character| character.is_ascii_digit() || *character == '.')
        .collect::<String>();
    value.parse().ok()
}

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
    let mut stroke_opacity = weight_opacity(instruction.weight);
    let mut fill_opacity = None;
    let hint = instruction
        .color_hint
        .as_deref()
        .unwrap_or_default()
        .to_lowercase();
    let has = |tokens: &[&str]| tokens.iter().any(|token| hint.contains(token));
    if has(&[
        "membrane",
        "haze",
        "fog",
        "mist",
        "atmosphere",
        "膜",
        "霞",
        "霧",
        "靄",
    ]) {
        stroke_opacity = stroke_opacity.min(0.26);
        fill_opacity = fill.then_some(0.12);
    } else if has(&["soft light", "柔らかな光", "陽光", "日差し"]) {
        stroke_opacity = stroke_opacity.min(0.30);
        fill_opacity = fill.then_some(0.14);
    } else if has(&["scent", "fragrance", "香り", "匂"]) {
        stroke_opacity = stroke_opacity.min(0.38);
        fill_opacity = fill.then_some(0.20);
    } else if has(&["waiting buds", "開花を待つ蕾", "蕾", "つぼみ"]) {
        stroke_opacity = stroke_opacity.min(0.72);
        fill_opacity = fill.then_some(0.58);
    } else if has(&["five-sense", "五感"]) {
        stroke_opacity = stroke_opacity.min(0.44);
        fill_opacity = fill.then_some(0.18);
    } else if has(&["fade directional", "fade=directional"]) {
        let ceiling = fade_level(&hint).unwrap_or(0.48);
        stroke_opacity = stroke_opacity.min(ceiling);
        fill_opacity = fill.then(|| {
            fade_level(&hint).map_or(0.30, |level| (level * 0.625 * 10_000.0).round() / 10_000.0)
        });
    } else if has(&["fade outward", "fade=outward"]) {
        let ceiling = fade_level(&hint).unwrap_or(0.40);
        stroke_opacity = stroke_opacity.min(ceiling);
        fill_opacity = fill.then(|| {
            fade_level(&hint).map_or(0.22, |level| (level * 0.55 * 10_000.0).round() / 10_000.0)
        });
    }
    if has(&["reflection", "反射", "映り"]) {
        stroke_opacity = stroke_opacity.min(0.52);
    }
    if is_wash_mark(instruction) {
        stroke_opacity = (stroke_opacity * 0.35 * 1_000_000.0).round() / 1_000_000.0;
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

fn mechanical_closed_mark(
    instruction: &Instruction,
    contour: &[Point],
    geometry: Element,
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Element {
    if !is_noncomputer_solid_fill(instruction) {
        return apply_style(geometry, style, true);
    }
    let mut group = Element::new("g");
    if let Some(fill) = render_interior_fill(instruction, contour, style, context) {
        group.push(fill);
    }
    group.push(apply_style(geometry, style, false));
    group
}

fn missing(instruction: &Instruction, field: &'static str) -> MarkError {
    MarkError {
        primitive: instruction.primitive,
        missing_field: field,
    }
}

/// Render one expanded, performed instruction into an SVG-specific element tree.
pub fn render_instruction(
    instruction: &Instruction,
    context: MarkContext<'_>,
) -> Result<Element, MarkError> {
    let style = mark_style(instruction, context);
    match instruction.primitive {
        Primitive::Line => {
            let start = point_to_pixels(
                instruction.from_.unwrap_or(Point::new(0.5, 0.0)),
                context.canvas,
            );
            let end = point_to_pixels(
                instruction.to.unwrap_or(Point::new(0.5, 1.0)),
                context.canvas,
            );
            if uses_hand_stroke(instruction.weight) {
                Ok(hand_line(instruction, start, end, &style, context))
            } else {
                Ok(rotate(
                    apply_style(
                        Element::new("line")
                            .attr("x1", format_number(start.x))
                            .attr("y1", format_number(start.y))
                            .attr("x2", format_number(end.x))
                            .attr("y2", format_number(end.y)),
                        &style,
                        false,
                    ),
                    instruction,
                    context.canvas,
                ))
            }
        }
        Primitive::Circle | Primitive::Ellipse => {
            let center = point_to_pixels(
                instruction
                    .center
                    .ok_or_else(|| missing(instruction, "center"))?,
                context.canvas,
            );
            let (rx, ry) = if instruction.primitive == Primitive::Circle {
                let radius = instruction
                    .radius
                    .ok_or_else(|| missing(instruction, "radius"))?
                    * context.canvas.unit();
                (radius, radius)
            } else {
                let size = size_to_pixels(
                    instruction
                        .size
                        .ok_or_else(|| missing(instruction, "size"))?,
                    context.canvas,
                );
                (size.x / 2.0, size.y / 2.0)
            };
            let length = if instruction.primitive == Primitive::Circle {
                std::f64::consts::TAU * rx
            } else {
                ellipse_perimeter(rx, ry)
            };
            let mut contour =
                circle_points(center, rx, ry, stroke_sample_count(length, context.canvas));
            if let Some(variation) = instruction
                .variation
                .as_ref()
                .filter(|variation| needs_contour_variation(variation))
            {
                contour = closed_contour_with_variation(
                    &contour,
                    center,
                    variation,
                    instruction_seed(instruction, context.render_seed),
                    amplitude(instruction, context.canvas),
                );
            }
            let geometry = if instruction.primitive == Primitive::Circle {
                Element::new("circle")
                    .attr("cx", format_number(center.x))
                    .attr("cy", format_number(center.y))
                    .attr("r", format_number(rx))
            } else {
                Element::new("ellipse")
                    .attr("cx", format_number(center.x))
                    .attr("cy", format_number(center.y))
                    .attr("rx", format_number(rx))
                    .attr("ry", format_number(ry))
            };
            if uses_hand_stroke(instruction.weight) {
                let mut group = Element::new("g");
                if let Some(fill) = render_interior_fill(instruction, &contour, &style, context) {
                    group.push(fill);
                }
                group.push(hand_contour(
                    instruction,
                    &contour,
                    &BTreeSet::new(),
                    &style,
                    context,
                    true,
                ));
                Ok(rotate(group, instruction, context.canvas))
            } else {
                Ok(rotate(
                    mechanical_closed_mark(instruction, &contour, geometry, &style, context),
                    instruction,
                    context.canvas,
                ))
            }
        }
        Primitive::Square | Primitive::Triangle => {
            let position = point_to_pixels(
                instruction
                    .position
                    .ok_or_else(|| missing(instruction, "position"))?,
                context.canvas,
            );
            let size = size_to_pixels(
                instruction
                    .size
                    .ok_or_else(|| missing(instruction, "size"))?,
                context.canvas,
            );
            let corners = if instruction.primitive == Primitive::Square {
                vec![
                    position,
                    Point::new(position.x + size.x, position.y),
                    Point::new(position.x + size.x, position.y + size.y),
                    Point::new(position.x, position.y + size.y),
                ]
            } else {
                vec![
                    Point::new(position.x + size.x / 2.0, position.y),
                    Point::new(position.x, position.y + size.y),
                    Point::new(position.x + size.x, position.y + size.y),
                ]
            };
            render_corner_shape(instruction, &corners, &style, context)
        }
        Primitive::Polygon => {
            let center = point_to_pixels(
                instruction
                    .center
                    .ok_or_else(|| missing(instruction, "center"))?,
                context.canvas,
            );
            let radius = instruction
                .radius
                .ok_or_else(|| missing(instruction, "radius"))?
                * context.canvas.unit();
            let corners = polygon_points(
                center,
                radius,
                usize::from(instruction.sides.unwrap_or(5)),
                0.0,
            );
            render_corner_shape(instruction, &corners, &style, context)
        }
        Primitive::Arc => {
            let center = point_to_pixels(
                instruction
                    .center
                    .ok_or_else(|| missing(instruction, "center"))?,
                context.canvas,
            );
            let radius = instruction
                .radius
                .ok_or_else(|| missing(instruction, "radius"))?
                * context.canvas.unit();
            let start = instruction
                .angle_start
                .ok_or_else(|| missing(instruction, "angle_start"))?;
            let end = instruction
                .angle_end
                .ok_or_else(|| missing(instruction, "angle_end"))?;
            if uses_hand_stroke(instruction.weight) {
                let length = radius * (end - start).to_radians().abs();
                let centerline = if let Some(variation) = instruction
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
                        instruction_seed(instruction, context.render_seed),
                        amplitude(instruction, context.canvas),
                        context.canvas,
                    )
                } else {
                    arc_points(
                        center,
                        radius,
                        start,
                        end,
                        stroke_sample_count(length, context.canvas),
                    )
                };
                Ok(rotate(
                    hand_contour(
                        instruction,
                        &centerline,
                        &BTreeSet::new(),
                        &style,
                        context,
                        false,
                    ),
                    instruction,
                    context.canvas,
                ))
            } else {
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
                Ok(rotate(
                    apply_style(Element::new("path").attr("d", path), &style, false),
                    instruction,
                    context.canvas,
                ))
            }
        }
        Primitive::Cloudform => {
            let center = instruction
                .center
                .ok_or_else(|| missing(instruction, "center"))?;
            let size = instruction
                .size
                .ok_or_else(|| missing(instruction, "size"))?;
            let controls = generate_cloudform_contour(CloudformRequest {
                center: point_to_pixels(center, context.canvas),
                size: size_to_pixels(size, context.canvas),
                performance_seed: Some(instruction_seed(instruction, context.render_seed)),
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
                &style,
                true,
            );
            if uses_hand_stroke(instruction.weight) {
                let mut group = Element::new("g");
                if let Some(fill) = render_interior_fill(instruction, &sampled, &style, context) {
                    group.push(fill);
                }
                group.push(hand_contour(
                    instruction,
                    &sampled,
                    &BTreeSet::new(),
                    &style,
                    context,
                    true,
                ));
                Ok(rotate(group, instruction, context.canvas))
            } else {
                Ok(rotate(
                    mechanical_closed_mark(instruction, &sampled, geometry, &style, context),
                    instruction,
                    context.canvas,
                ))
            }
        }
    }
}

fn render_corner_shape(
    instruction: &Instruction,
    corners: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Result<Element, MarkError> {
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
        instruction_seed(instruction, context.render_seed),
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
        let mut group = Element::new("g");
        if let Some(fill) = render_interior_fill(instruction, &contour.points, style, context) {
            group.push(fill);
        }
        group.push(hand_contour(
            instruction,
            &contour.points,
            &contour.anchors,
            style,
            context,
            true,
        ));
        Ok(rotate(group, instruction, context.canvas))
    } else {
        Ok(rotate(
            mechanical_closed_mark(instruction, &contour.points, geometry, style, context),
            instruction,
            context.canvas,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
