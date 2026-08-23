//! Canvas-level ground and abstract presence layers.

use std::collections::BTreeMap;

use sha2::{Digest, Sha256};

use crate::determinism::hash01;
use crate::palette::default_color;
use crate::svg::{Element, format_number};
use crate::types::{
    CanvasSize, Color, ContourDensity, GazePressure, PresenceIntensity, PresenceKind,
    PresenceSymmetry, Score, Seed,
};

fn assigned_color(assignment: &BTreeMap<String, String>, name: &str, fallback: Color) -> String {
    assignment
        .get(name)
        .cloned()
        .unwrap_or_else(|| default_color(fallback).to_owned())
}

fn visual_load(score: &Score) -> usize {
    score
        .instructions
        .iter()
        .map(|instruction| {
            instruction
                .arrangement
                .as_ref()
                .map_or(1, |arrangement| arrangement.count.max(1) as usize)
        })
        .sum()
}

fn presence_center(score: &Score, canvas: CanvasSize) -> (f64, f64) {
    score
        .presence
        .as_ref()
        .and_then(|presence| presence.center)
        .map_or((canvas.width * 0.52, canvas.height * 0.50), |center| {
            (
                center.x.clamp(0.0, 1.0) * canvas.width,
                center.y.clamp(0.0, 1.0) * canvas.height,
            )
        })
}

fn primitive_name(primitive: crate::types::Primitive) -> &'static str {
    match primitive {
        crate::types::Primitive::Line => "line",
        crate::types::Primitive::Circle => "circle",
        crate::types::Primitive::Ellipse => "ellipse",
        crate::types::Primitive::Triangle => "triangle",
        crate::types::Primitive::Square => "square",
        crate::types::Primitive::Polygon => "polygon",
        crate::types::Primitive::Arc => "arc",
        crate::types::Primitive::Cloudform => "cloudform",
    }
}

fn color_name(color: Color) -> &'static str {
    match color {
        Color::White => "white",
        Color::Black => "black",
        Color::Blue => "blue",
        Color::Red => "red",
        Color::Green => "green",
        Color::Gray => "gray",
        Color::Yellow => "yellow",
        Color::Orange => "orange",
        Color::Purple => "purple",
    }
}

fn weight_name(weight: crate::types::Weight) -> &'static str {
    match weight {
        crate::types::Weight::Silverpoint => "silverpoint",
        crate::types::Weight::Pencil => "pencil",
        crate::types::Weight::Pen => "pen",
        crate::types::Weight::Rotring => "rotring",
        crate::types::Weight::Crayon => "crayon",
        crate::types::Weight::Chalk => "chalk",
        crate::types::Weight::BrushThin => "brush_thin",
        crate::types::Weight::BrushThick => "brush_thick",
        crate::types::Weight::Burin => "burin",
        crate::types::Weight::Drypoint => "drypoint",
        crate::types::Weight::Computer => "computer",
    }
}

fn presence_seed(score: &Score) -> Seed {
    let presence = score
        .presence
        .as_ref()
        .map_or_else(String::new, |presence| {
            serde_json::to_string(presence).expect("canonical presence is serializable")
        });
    let instructions = score
        .instructions
        .iter()
        .map(|instruction| {
            format!(
                "{}:{}:{}:{}",
                primitive_name(instruction.primitive),
                color_name(instruction.color),
                weight_name(instruction.weight),
                instruction
                    .arrangement
                    .as_ref()
                    .map_or(1, |arrangement| arrangement.count)
            )
        })
        .collect::<Vec<_>>()
        .join("|");
    let digest = Sha256::digest(format!("{presence}|{instructions}").as_bytes());
    Seed::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn line(start: (f64, f64), end: (f64, f64), color: &str, width: f64, opacity: f64) -> Element {
    Element::new("line")
        .attr("x1", format_number(start.0))
        .attr("y1", format_number(start.1))
        .attr("x2", format_number(end.0))
        .attr("y2", format_number(end.1))
        .attr("stroke", color)
        .attr("stroke-width", format_number(width))
        .attr("stroke-opacity", format_number(opacity))
        .attr("stroke-linecap", "round")
}

/// Render only abstract compositional pressure; concrete figures remain forbidden.
#[must_use]
pub fn render_presence_layer(
    score: &Score,
    canvas: CanvasSize,
    assignment: &BTreeMap<String, String>,
) -> Option<Element> {
    let presence = score.presence.as_ref()?;
    if presence.kind == PresenceKind::None {
        return None;
    }
    let (center_x, center_y) = presence_center(score, canvas);
    let unit = canvas.unit();
    let color = assigned_color(assignment, "gray", Color::Gray);
    let dark = assigned_color(assignment, "black", Color::Black);
    let load_opacity = match visual_load(score) {
        120.. => 0.52,
        60.. => 0.70,
        _ => 1.0,
    };
    let intensity = match presence.intensity {
        PresenceIntensity::Low => 0.13,
        PresenceIntensity::Medium => 0.21,
        PresenceIntensity::High => 0.30,
    } * load_opacity;
    let gaze = match presence.gaze_pressure {
        GazePressure::None => 0.0,
        GazePressure::Low => 0.11,
        GazePressure::Medium => 0.18,
        GazePressure::High => 0.26,
    } * load_opacity;
    let contour_count = match presence.contour_density {
        ContourDensity::Low => 4,
        ContourDensity::Medium => 7,
        ContourDensity::High => 11,
    };
    let radius_x = unit
        * match presence.intensity {
            PresenceIntensity::Low => 0.18,
            PresenceIntensity::Medium => 0.24,
            PresenceIntensity::High => 0.30,
        };
    let radius_y = unit
        * match presence.intensity {
            PresenceIntensity::Low => 0.24,
            PresenceIntensity::Medium => 0.32,
            PresenceIntensity::High => 0.40,
        };
    let stroke = 1.2_f64.max(unit * 0.003);
    let seed = presence_seed(score);
    let phase = std::f64::consts::TAU * hash01(0, seed, "presence-phase");
    let tilt = (hash01(1, seed, "presence-tilt") - 0.5) * 1.2;
    let mut layer = Element::new("g").attr("id", "presence_layer");

    match presence.symmetry {
        PresenceSymmetry::Bilateral => {
            for (index, side) in [-1.0, 1.0, -1.0, 1.0].into_iter().enumerate() {
                let y_shift = (-0.36 + index as f64 * 0.24) * radius_y;
                let outer = side * radius_x * (0.34 + 0.10 * hash01(index as i64, seed, "sym-x"));
                let inner =
                    side * radius_x * (0.10 + 0.08 * hash01(index as i64, seed, "sym-inner"));
                layer.push(line(
                    (center_x + outer, center_y + y_shift - radius_y * 0.06),
                    (
                        center_x + inner,
                        center_y + y_shift + radius_y * (0.10 + tilt * 0.06),
                    ),
                    &color,
                    stroke,
                    intensity * 0.58,
                ));
            }
        }
        PresenceSymmetry::Radial => {
            for index in 0..6 {
                let angle = phase + std::f64::consts::TAU * index as f64 / 6.0;
                layer.push(line(
                    (
                        center_x + angle.cos() * radius_x * 0.28,
                        center_y + angle.sin() * radius_x * 0.28,
                    ),
                    (
                        center_x + angle.cos() * radius_x * 0.86,
                        center_y + angle.sin() * radius_x * 0.86,
                    ),
                    &color,
                    stroke,
                    intensity * 0.72,
                ));
            }
        }
        PresenceSymmetry::None => {}
    }

    if presence.gaze_pressure != GazePressure::None {
        for (index, side) in [-1.0, 1.0, -1.0, 1.0, -1.0, 1.0].into_iter().enumerate() {
            let t = (index + 1) as f64 / 7.0;
            let angle = phase + side * (0.34 + 0.08 * index as f64);
            layer.push(line(
                (
                    center_x + angle.cos() * radius_x * (1.05 + 0.18 * (index % 2) as f64),
                    center_y + angle.sin() * radius_y * (0.72 + 0.08 * index as f64),
                ),
                (
                    center_x + (angle + std::f64::consts::PI).cos() * radius_x * 0.12,
                    center_y + (t - 0.5) * radius_y * 0.16,
                ),
                &dark,
                stroke * 0.8,
                gaze,
            ));
        }
    }

    let flow_angle = phase * 0.35 + tilt;
    let (tangent_x, tangent_y) = (flow_angle.cos(), flow_angle.sin());
    let (normal_x, normal_y) = (-tangent_y, tangent_x);
    for index in 0..contour_count {
        let t = (index as f64 + 0.5) / contour_count as f64;
        let along =
            (t - 0.5) * radius_x * (1.18 + 0.18 * hash01(index as i64, seed, "presence-flow-span"));
        let cross = (t * std::f64::consts::PI * 1.7 + phase).sin() * radius_y * 0.32
            + (hash01(index as i64, seed, "presence-flow-cross") - 0.5) * radius_y * 0.28;
        let point_x = center_x + tangent_x * along + normal_x * cross;
        let point_y = center_y + tangent_y * along + normal_y * cross;
        let half = radius_x * (0.09 + 0.04 * hash01(index as i64, seed, "presence-flow-half"));
        let lift = radius_y * (0.05 + 0.04 * hash01(index as i64, seed, "presence-flow-lift"));
        let side = if index % 2 == 0 { 1.0 } else { -1.0 };
        let start = (
            point_x - tangent_x * half - normal_x * lift * side,
            point_y - tangent_y * half - normal_y * lift * side,
        );
        let end = (
            point_x + tangent_x * half + normal_x * lift * side,
            point_y + tangent_y * half + normal_y * lift * side,
        );
        let middle = (
            point_x + normal_x * lift * side * 1.4,
            point_y + normal_y * lift * side * 1.4,
        );
        layer.push(
            Element::new("path")
                .attr(
                    "d",
                    format!(
                        "M {} {} Q {} {} {} {}",
                        format_number(start.0),
                        format_number(start.1),
                        format_number(middle.0),
                        format_number(middle.1),
                        format_number(end.0),
                        format_number(end.1)
                    ),
                )
                .attr("fill", "none")
                .attr("stroke", &color)
                .attr("stroke-width", format_number(stroke))
                .attr("stroke-opacity", format_number(intensity * 0.82))
                .attr("stroke-linecap", "round"),
        );
    }

    match presence.kind {
        PresenceKind::GroupLike => {
            for index in 0..7 {
                let t = (index as f64 - 3.0) / 3.5;
                let point_x = center_x
                    + tangent_x * t * radius_x * 0.78
                    + normal_x * (hash01(index, seed, "group-x") - 0.5) * radius_x * 0.20;
                let point_y = center_y
                    + tangent_y * t * radius_x * 0.78
                    + normal_y * (hash01(index, seed, "group-y") - 0.5) * radius_y * 0.58;
                layer.push(
                    Element::new("circle")
                        .attr("cx", format_number(point_x))
                        .attr("cy", format_number(point_y))
                        .attr("r", format_number(2.0_f64.max(unit * 0.006)))
                        .attr("fill", &color)
                        .attr("fill-opacity", format_number(intensity * 0.72)),
                );
            }
        }
        PresenceKind::CreatureLike => {
            for index in 0..3 {
                let t = (index as f64 - 1.0) * 0.34;
                layer.push(line(
                    (
                        center_x - radius_x * 0.30 + t * radius_x,
                        center_y + radius_y * 0.32,
                    ),
                    (
                        center_x - radius_x * 0.05 + t * radius_x,
                        center_y + radius_y * 0.44,
                    ),
                    &color,
                    stroke,
                    intensity * 0.76,
                ));
            }
        }
        PresenceKind::None | PresenceKind::FigureLike => {}
    }
    Some(layer)
}
