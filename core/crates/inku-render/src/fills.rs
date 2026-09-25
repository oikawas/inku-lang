//! Interior fill fields for closed hand-tool marks.

use std::collections::BTreeSet;

use sha2::{Digest, Sha256};

use crate::determinism::{hash01, seed_salt_index_digest};
use crate::geometry::{point_to_pixels, stroke_sample_count};
use crate::mark_paths::{contour_stroke_path, grid_step, polygon_path, uses_hand_stroke};
use crate::marks::{MarkContext, MarkStyle};
use crate::materials::{OilPaintStyle, oil_paint_shade, oil_paint_stroke, with_texture_filter};
use crate::planning::instruction_anchor_on_canvas;
use crate::stroke::{ContourStrokeRequest, StrokeTerminal, synthesize_contour};
use crate::svg::{Element, format_number};
use crate::types::{Instruction, Point, Seed, SurfaceTexture, SvgProfile, Weight};

const FILL_MIN_SCANLINES: usize = 3;
const FILL_SPACING_WIDTH_GAIN: f64 = 1.5;
const FILL_SPACING_UNIT_RATIO: f64 = 0.012;
const FILL_COVERAGE_TARGET: f64 = 0.90;
const FILL_UNDERLAY_OPACITY_RATIO: f64 = 0.75;
const FILL_SCAN_CONTRAST: f64 = 1.15;
const FILL_DAB_SAMPLES: usize = 5;
const FILL_DAB_MIN_TRAVEL: f64 = 0.90;
const SOLID_MOTTLE_OVERLAY_OPACITY: f64 = 0.22;

fn fill_seed(seed: Seed, index: usize) -> Seed {
    let index = i128::try_from(index).expect("usize fits i128");
    let digest = seed_salt_index_digest(seed, "fill-stroke", index);
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn scanline_segments(
    contour: &[Point],
    angle: f64,
    spacing: f64,
    seed: Seed,
    jitter: f64,
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
        let pitch = 1.0 + (hash01(row as i64, seed, "fill-spacing") - 0.5) * jitter;
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
    base_width: f64,
) -> Element {
    let stroke = synthesize_contour(ContourStrokeRequest {
        centerline,
        base_width,
        weight: instruction.weight,
        seed,
        closed: false,
        anchors: &BTreeSet::new(),
        grid_step: grid_step(instruction.weight, context.canvas),
        wild: context.wild,
        support: context.support,
        terminal: StrokeTerminal::Loaded,
    });
    if instruction.weight == Weight::OilPaint {
        return oil_paint_stroke(
            contour_stroke_path(&stroke),
            &stroke.left,
            &stroke.right,
            if style.fill && crate::accepted_fills::solid_fill(instruction) {
                OilPaintStyle::filled(
                    &style.color,
                    opacity,
                    instruction.surface_intensity,
                    context.canvas,
                    true,
                )
            } else {
                OilPaintStyle::plain(&style.color, opacity)
            },
            seed,
            false,
        );
    }
    with_texture_filter(
        Element::new("path")
            .attr("d", contour_stroke_path(&stroke))
            .attr("fill", &style.color)
            .attr("fill-opacity", format_number(opacity))
            .attr("stroke", "none"),
        instruction.weight,
        context.use_filters,
    )
}

/// Loaded passes one oil fill lays down at most, and the document-wide total
/// that many oil fills share. Each pass writes a body and eight ridge paths.
pub(crate) const MAX_OIL_FILL_PASSES: usize = 24;
const OIL_FILL_PASS_BUDGET: usize = 120;
const MIN_OIL_FILL_PASSES: usize = 3;

/// Passes each oil interior fill may use so all of a document's oil fills
/// together stay within the budget. Counts every performed member.
pub(crate) fn oil_fill_pass_limit(instructions: &[Instruction]) -> usize {
    let fills: usize = instructions
        .iter()
        .filter(|instruction| {
            instruction.weight == Weight::OilPaint
                && (instruction.filled || is_noncomputer_solid_fill(instruction))
        })
        .map(|instruction| {
            instruction
                .arrangement
                .as_ref()
                .map_or(1, |arrangement| arrangement.count.max(1) as usize)
        })
        .sum();
    (OIL_FILL_PASS_BUDGET / fills.max(1)).clamp(MIN_OIL_FILL_PASSES, MAX_OIL_FILL_PASSES)
}

pub(crate) fn is_noncomputer_solid_fill(instruction: &Instruction) -> bool {
    instruction
        .surface
        .as_ref()
        .is_some_and(|surface| surface.texture == SurfaceTexture::Solid)
        && instruction.weight != Weight::Computer
}

#[must_use]
pub(crate) fn solid_mottle_filter_id(
    instruction: &Instruction,
    context: MarkContext<'_>,
) -> (String, u32) {
    let seed = context.seed_for(instruction);
    let identity = format!(
        "{seed}:{}:{}:solid-mottle",
        context.instruction_index, context.mark_index
    );
    let digest = Sha256::digest(identity.as_bytes());
    let filter_seed = u32::from_le_bytes(digest[..4].try_into().expect("four digest bytes"));
    (
        format!(
            "solid-mottle-{:03}-{:03}-{filter_seed:08x}",
            context.instruction_index, context.mark_index
        ),
        filter_seed,
    )
}

#[must_use]
pub(crate) fn solid_mottle_filter(filter_id: &str, seed: u32) -> Element {
    let mut filter = Element::new("filter")
        .attr("id", filter_id)
        .attr("x", "-2%")
        .attr("y", "-2%")
        .attr("width", "104%")
        .attr("height", "104%")
        .attr("color-interpolation-filters", "sRGB");
    filter.push(
        Element::new("feTurbulence")
            .attr("type", "fractalNoise")
            .attr("baseFrequency", "0.035000")
            .attr("numOctaves", "3")
            .attr("seed", seed.to_string())
            .attr("result", "solidMottleNoise"),
    );
    filter.push(
        Element::new("feColorMatrix")
            .attr("in", "solidMottleNoise")
            .attr("type", "luminanceToAlpha")
            .attr("result", "solidMottleAlpha"),
    );
    let mut transfer = Element::new("feComponentTransfer")
        .attr("in", "solidMottleAlpha")
        .attr("result", "solidMottleFloor");
    transfer.push(
        Element::new("feFuncA")
            .attr("type", "table")
            .attr("tableValues", "0.310000 1"),
    );
    filter.push(transfer);
    filter.push(
        Element::new("feComposite")
            .attr("in", "SourceGraphic")
            .attr("in2", "solidMottleFloor")
            .attr("operator", "in"),
    );
    filter
}

fn fill_dab(
    instruction: &Instruction,
    contour: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
    opacity: f64,
    seed: Seed,
) -> Option<Element> {
    let min_x = contour
        .iter()
        .map(|point| point.x)
        .fold(f64::INFINITY, f64::min);
    let max_x = contour
        .iter()
        .map(|point| point.x)
        .fold(f64::NEG_INFINITY, f64::max);
    let min_y = contour
        .iter()
        .map(|point| point.y)
        .fold(f64::INFINITY, f64::min);
    let max_y = contour
        .iter()
        .map(|point| point.y)
        .fold(f64::NEG_INFINITY, f64::max);
    let width = max_x - min_x;
    let height = max_y - min_y;
    if width <= 0.0 && height <= 0.0 {
        return None;
    }
    let along_x = width >= height;
    let long_axis = if along_x { width } else { height };
    let short_axis = if along_x { height } else { width };
    let travel = (long_axis - short_axis).max(long_axis * FILL_DAB_MIN_TRAVEL);
    let center = Point::new((min_x + max_x) / 2.0, (min_y + max_y) / 2.0);
    let half = travel / 2.0;
    let start = if along_x {
        Point::new(center.x - half, center.y)
    } else {
        Point::new(center.x, center.y - half)
    };
    let end = if along_x {
        Point::new(center.x + half, center.y)
    } else {
        Point::new(center.x, center.y + half)
    };
    let centerline = (0..FILL_DAB_SAMPLES)
        .map(|index| {
            let t = index as f64 / (FILL_DAB_SAMPLES - 1) as f64;
            Point::new(
                start.x + (end.x - start.x) * t,
                start.y + (end.y - start.y) * t,
            )
        })
        .collect::<Vec<_>>();
    let mut group = Element::new("g").attr("class", "fill-dab-v1");
    group.push(stroke_path(
        instruction,
        context,
        &centerline,
        style,
        opacity,
        fill_seed(seed, 0),
        style.width.max(short_axis),
    ));
    Some(group)
}

fn oil_paint_fill(
    instruction: &Instruction,
    contour: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
    opacity: f64,
) -> Element {
    let accepted = style.fill && crate::accepted_fills::solid_fill(instruction);
    let seed = context.seed_for(instruction);
    let angle = hash01(0, seed, "oil-fill-angle") * std::f64::consts::PI;
    let normal = Point::new(-angle.sin(), angle.cos());
    let (low, high) = contour
        .iter()
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(low, high), p| {
            let projection = p.x * normal.x + p.y * normal.y;
            (low.min(projection), high.max(projection))
        });
    // Wider loaded passes keep the work bounded even for large filled shapes.
    let span = high - low;
    let width = (style.width * 2.0)
        .min(span / 3.0)
        .max(span / context.oil_fill_pass_limit.max(1) as f64)
        .max(context.canvas.unit() * 0.0001);
    let spacing = width * 0.82;
    let mut group = Element::new("g")
        .attr("class", "oil-paint-fill-v1")
        .attr("opacity", format_number(opacity));
    group.push(
        Element::new("path")
            .attr("d", polygon_path(contour))
            .attr("class", "oil-paint-fill-body-v1")
            .attr("fill", &style.color)
            .attr("stroke", "none"),
    );
    let mut passes = Vec::new();
    let (mut xx, mut xy, mut yy) = (0.0_f64, 0.0_f64, 0.0_f64);
    for (order, (row, mut start, mut end)) in scanline_segments(contour, angle, spacing, seed, 0.24)
        .into_iter()
        .enumerate()
    {
        let length = (end.x - start.x).hypot(end.y - start.y);
        if length <= width {
            continue;
        }
        // Leave a small boundary margin for the deposited paint's loaded ends.
        let inset = (width * 0.45 / length).min(0.45);
        let delta = Point::new(end.x - start.x, end.y - start.y);
        start = Point::new(start.x + delta.x * inset, start.y + delta.y * inset);
        end = Point::new(end.x - delta.x * inset, end.y - delta.y * inset);
        if row % 2 == 1 {
            std::mem::swap(&mut start, &mut end);
        }
        let samples = stroke_sample_count(length, context.canvas).clamp(2, 65);
        let centerline = (0..samples)
            .map(|index| {
                let t = index as f64 / (samples - 1) as f64;
                Point::new(
                    start.x + (end.x - start.x) * t,
                    start.y + (end.y - start.y) * t,
                )
            })
            .collect::<Vec<_>>();
        let mut pass_style = style.clone();
        pass_style.color = oil_paint_shade(
            &style.color,
            (hash01(order as i64, seed, "oil-fill-load") - 0.5) * 0.10,
        );
        let pass_seed = fill_seed(seed, order);
        let stroke = synthesize_contour(ContourStrokeRequest {
            centerline: &centerline,
            base_width: width,
            weight: instruction.weight,
            seed: pass_seed,
            closed: false,
            anchors: &BTreeSet::new(),
            grid_step: grid_step(instruction.weight, context.canvas),
            wild: context.wild,
            support: context.support,
            terminal: StrokeTerminal::Loaded,
        });
        let centers = stroke
            .left
            .iter()
            .zip(&stroke.right)
            .map(|(a, b)| Point::new((a.x + b.x) * 0.5, (a.y + b.y) * 0.5))
            .collect::<Vec<_>>();
        if !centers.is_empty() {
            let center = Point::new(
                centers.iter().map(|p| p.x).sum::<f64>() / centers.len() as f64,
                centers.iter().map(|p| p.y).sum::<f64>() / centers.len() as f64,
            );
            for point in centers {
                let dx = point.x - center.x;
                let dy = point.y - center.y;
                xx += dx * dx;
                xy += dx * dy;
                yy += dy * dy;
            }
        }
        passes.push(oil_paint_stroke(
            contour_stroke_path(&stroke),
            &stroke.left,
            &stroke.right,
            if accepted {
                OilPaintStyle::filled(
                    &pass_style.color,
                    1.0,
                    instruction.surface_intensity,
                    context.canvas,
                    true,
                )
            } else {
                OilPaintStyle::plain(&pass_style.color, 1.0)
            },
            pass_seed,
            false,
        ));
    }
    // A single bank-derived field widens passes and their spacing together.
    // Degenerate marks retain their native passes and solid underlay.
    if context.profile != SvgProfile::Compat
        && accepted
        && !passes.is_empty()
        && xx + yy > 0.0
        && (xx - yy).hypot(2.0 * xy) >= 0.9 * (xx + yy)
    {
        let tangent = (2.0 * xy).atan2(xx - yy) * 0.5;
        let nx = -tangent.sin();
        let ny = tangent.cos();
        let a = 1.0 + 2.0 * nx * nx;
        let b = 2.0 * nx * ny;
        let d = 1.0 + 2.0 * ny * ny;
        let center = point_to_pixels(
            instruction_anchor_on_canvas(instruction, Some(context.canvas)),
            context.canvas,
        );
        let clip_id = format!(
            "oil-fill-clip-{}-{}",
            context.instruction_index, context.mark_index
        );
        let mut clip = Element::new("clipPath")
            .attr("id", &clip_id)
            .attr("clipPathUnits", "userSpaceOnUse");
        clip.push(Element::new("path").attr("d", polygon_path(contour)));
        let mut defs = Element::new("defs");
        defs.push(clip);
        group.push(defs);
        let matrix = [
            a,
            b,
            b,
            d,
            center.x * (1.0 - a) - b * center.y,
            center.y * (1.0 - d) - b * center.x,
        ]
        .map(format_number)
        .join(" ");
        let mut field = Element::new("g")
            .attr("class", "oil-intensity-width-field-v1")
            .attr("transform", format!("matrix({matrix})"));
        for pass in passes {
            field.push(pass);
        }
        let mut clipped = Element::new("g")
            .attr("class", "oil-intensity-width-clip-v1")
            .attr("clip-path", format!("url(#{clip_id})"));
        clipped.push(field);
        group.push(clipped);
    } else {
        for pass in passes {
            group.push(pass);
        }
    }
    group
}

/// Render the interior requested by a filled closed mark.
#[must_use]
pub(crate) fn render_interior_fill(
    instruction: &Instruction,
    contour: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Option<Element> {
    if !style.fill || contour.len() < 3 {
        return None;
    }
    let opacity = style.fill_opacity.unwrap_or(style.stroke_opacity);
    if instruction.weight == Weight::OilPaint {
        return Some(oil_paint_fill(
            instruction,
            contour,
            style,
            context,
            opacity,
        ));
    }
    if let Some(fill) = crate::accepted_fills::interior(instruction, contour, style, context) {
        return Some(fill);
    }
    if is_noncomputer_solid_fill(instruction) {
        let mut group = Element::new("g").attr("class", "solid-fill-v1");
        let path = polygon_path(contour);
        group.push(
            Element::new("path")
                .attr("d", &path)
                .attr("class", "solid-base-fill-v1")
                .attr("fill", &style.color)
                .attr("fill-opacity", format_number(opacity))
                .attr("stroke", "none"),
        );
        if context.profile != SvgProfile::Compat {
            let (filter_id, _) = solid_mottle_filter_id(instruction, context);
            group.push(
                Element::new("path")
                    .attr("d", path)
                    .attr("class", "solid-mottle-overlay-v1")
                    .attr("fill", &style.color)
                    .attr(
                        "fill-opacity",
                        format_number(opacity * SOLID_MOTTLE_OVERLAY_OPACITY),
                    )
                    .attr("stroke", "none")
                    .attr("filter", format!("url(#{filter_id})")),
            );
        }
        return Some(group);
    }
    if !uses_hand_stroke(instruction.weight) {
        return None;
    }
    let seed = context.seed_for(instruction);
    let angle = hash01(0, seed, "fill-angle") * std::f64::consts::PI;
    let classic_spacing = (style.width * FILL_SPACING_WIDTH_GAIN)
        .max(context.canvas.unit() * FILL_SPACING_UNIT_RATIO);
    let classic_segments = scanline_segments(contour, angle, classic_spacing, seed, 0.24);
    let row_count = classic_segments
        .iter()
        .map(|(row, _, _)| *row)
        .collect::<BTreeSet<_>>()
        .len();
    if row_count < FILL_MIN_SCANLINES {
        return fill_dab(instruction, contour, style, context, opacity, seed);
    }
    let (spacing, jitter) = if instruction.weight == Weight::Computer {
        (classic_spacing, 0.0)
    } else {
        (style.width / FILL_COVERAGE_TARGET, 0.84)
    };
    let segments = scanline_segments(contour, angle, spacing, seed, jitter);
    let mut group = Element::new("g").attr("class", "fill-v2");
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
            style.width,
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
