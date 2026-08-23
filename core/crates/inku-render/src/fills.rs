//! Interior fill fields for closed hand-tool marks.

use std::collections::BTreeSet;

use sha2::{Digest, Sha256};

use crate::determinism::{hash01, instruction_seed};
use crate::geometry::stroke_sample_count;
use crate::marks::{
    MarkContext, MarkStyle, contour_stroke_path, grid_step, polygon_path, uses_hand_stroke,
};
use crate::stroke::{ContourStrokeRequest, StrokeTerminal, synthesize_contour};
use crate::svg::{Element, format_number};
use crate::types::{Instruction, Point, Seed, SurfaceTexture};

const FILL_MIN_SCANLINES: usize = 3;
const FILL_COVERAGE_TARGET: f64 = 0.90;
const FILL_UNDERLAY_OPACITY_RATIO: f64 = 0.75;
const FILL_SCAN_CONTRAST: f64 = 1.15;

fn fill_seed(seed: Seed, index: usize) -> Seed {
    let digest = Sha256::digest(format!("{seed}:fill-stroke:{index}").as_bytes());
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn scanline_segments(
    contour: &[Point],
    angle: f64,
    spacing: f64,
    seed: Seed,
) -> Vec<(usize, Point, Point)> {
    let direction = Point::new(angle.cos(), angle.sin());
    let normal = Point::new(-direction.y, direction.x);
    let projections = contour
        .iter()
        .map(|point| point.x * normal.x + point.y * normal.y)
        .collect::<Vec<_>>();
    let low = projections.iter().copied().fold(f64::INFINITY, f64::min);
    let high = projections
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let mut offset = low + spacing * 0.5;
    let mut row = 0_usize;
    let mut result = Vec::new();
    while offset < high && row < 4096 {
        let mut hits = Vec::new();
        for edge in 0..contour.len() {
            let a = contour[edge];
            let b = contour[(edge + 1) % contour.len()];
            let da = a.x * normal.x + a.y * normal.y - offset;
            let db = b.x * normal.x + b.y * normal.y - offset;
            if (da <= 0.0 && db > 0.0) || (db <= 0.0 && da > 0.0) {
                let t = da / (da - db);
                let point = Point::new(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
                hits.push(point.x * direction.x + point.y * direction.y);
            }
        }
        hits.sort_by(f64::total_cmp);
        for pair in (0..hits.len().saturating_sub(1)).step_by(2) {
            result.push((
                row,
                Point::new(
                    normal.x * offset + direction.x * hits[pair],
                    normal.y * offset + direction.y * hits[pair],
                ),
                Point::new(
                    normal.x * offset + direction.x * hits[pair + 1],
                    normal.y * offset + direction.y * hits[pair + 1],
                ),
            ));
        }
        let pitch = 1.0 + (hash01(row as i64, seed, "fill-spacing") - 0.5) * 0.84;
        offset += spacing * pitch;
        row += 1;
    }
    result
}

fn stroke_path(
    instruction: &Instruction,
    context: MarkContext<'_>,
    centerline: &[Point],
    style: &MarkStyle,
    opacity: f64,
    seed: Seed,
) -> Element {
    let stroke = synthesize_contour(ContourStrokeRequest {
        centerline,
        base_width: style.width,
        weight: instruction.weight,
        seed,
        closed: false,
        anchors: &BTreeSet::new(),
        grid_step: grid_step(instruction.weight, context.canvas),
        wild: context.wild,
        support: context.support,
        terminal: StrokeTerminal::Loaded,
    });
    Element::new("path")
        .attr("d", contour_stroke_path(&stroke))
        .attr("fill", &style.color)
        .attr("fill-opacity", format_number(opacity))
        .attr("stroke", "none")
}

/// Render the interior requested by a filled closed mark.
#[must_use]
pub(crate) fn render_interior_fill(
    instruction: &Instruction,
    contour: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Option<Element> {
    if !style.fill || contour.len() < 3 || !uses_hand_stroke(instruction.weight) {
        return None;
    }
    let opacity = style.fill_opacity.unwrap_or(style.stroke_opacity);
    if instruction
        .surface
        .as_ref()
        .is_some_and(|surface| surface.texture == SurfaceTexture::Solid)
    {
        let mut group = Element::new("g").attr("class", "solid-fill-v1");
        group.push(
            Element::new("path")
                .attr("d", polygon_path(contour))
                .attr("class", "solid-base-fill-v1")
                .attr("fill", &style.color)
                .attr("fill-opacity", format_number(opacity))
                .attr("stroke", "none"),
        );
        return Some(group);
    }
    let seed = instruction_seed(instruction, context.render_seed);
    let spacing = style.width / FILL_COVERAGE_TARGET;
    let angle = hash01(0, seed, "fill-angle") * std::f64::consts::PI;
    let segments = scanline_segments(contour, angle, spacing, seed);
    let row_count = segments
        .iter()
        .map(|(row, _, _)| *row)
        .collect::<BTreeSet<_>>()
        .len();
    let mut group = Element::new("g").attr("class", "fill-v2");
    if row_count >= FILL_MIN_SCANLINES {
        group.push(
            Element::new("path")
                .attr("d", polygon_path(contour))
                .attr("class", "fill-underlay-v1")
                .attr("fill", &style.color)
                .attr(
                    "fill-opacity",
                    format_number(opacity * FILL_UNDERLAY_OPACITY_RATIO),
                )
                .attr("stroke", "none"),
        );
    }
    let mark_opacity = opacity.min(opacity * FILL_UNDERLAY_OPACITY_RATIO * FILL_SCAN_CONTRAST);
    let mut strokes = Element::new("g").attr("class", "fill-stroke-v1");
    let mut count = 0_usize;
    for (order, (row, mut start, mut end)) in segments.into_iter().enumerate() {
        let length = (end.x - start.x).hypot(end.y - start.y);
        if length <= style.width * 1.2 {
            continue;
        }
        if row % 2 == 1 {
            std::mem::swap(&mut start, &mut end);
        }
        let samples = stroke_sample_count(length, context.canvas).max(2);
        let centerline = (0..samples)
            .map(|index| {
                let t = index as f64 / (samples - 1) as f64;
                Point::new(
                    start.x + (end.x - start.x) * t,
                    start.y + (end.y - start.y) * t,
                )
            })
            .collect::<Vec<_>>();
        strokes.push(stroke_path(
            instruction,
            context,
            &centerline,
            style,
            mark_opacity,
            fill_seed(seed, order),
        ));
        count += 1;
    }
    if count == 0 {
        return None;
    }
    strokes.set_attr("class", format!("fill-stroke-v1 strokes-{count}"));
    group.push(strokes);
    Some(group)
}
