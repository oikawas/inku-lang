//! SVG path construction and performed stroke emission for primitive marks.

use std::collections::BTreeSet;

use crate::determinism::{needs_contour_variation, needs_path_variation};
use crate::flat_brush::{FlatBandRequest, FlatHold, flat_band, flat_band_element, sweeps_flat};
use crate::geometry::{
    ArcGeometry, arc_points, arc_points_with_variation, frequency_cycles, open_line_with_variation,
    point_to_pixels, size_to_pixels, stroke_sample_count,
};
use crate::marks::{
    MarkContext, MarkStyle, apply_style, is_closed, is_open_band, mark_width, open_band_width,
    round_width,
};
use crate::materials::{OilPaintStyle, oil_paint_stroke, with_texture_filter};
use crate::planning::instruction_anchor_on_canvas;
use crate::stroke::{
    BandHand, ContourStrokeRequest, ContourStrokeResult, StrokeRequest, StrokeSample,
    StrokeTerminal, outline_for_centerline, stroke_event_count, synthesize_contour_by,
    synthesize_stroke_by,
};
use crate::support::{Support, support_with_mark_word};
use crate::svg::{Element, closed_polyline_path, format_number, points_list, write_number};
use crate::types::{
    Amplitude, CanvasSize, Instruction, LineStyle, Point, Primitive, Quality, Weight,
};

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
    closed_polyline_path(points)
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
    points_list(points)
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

/// How far a varied contour may stray, from the tool's width and the mark's size.
///
/// The size comes from the Score's own fields, not from `MarkGeometry`, because
/// execution calls this before drawing too. A field the Score leaves out counts
/// as 0.02 short-side units, which is also the floor. That includes a Line's
/// omitted end, which drawing places on the canvas's midline, and a crescent's
/// radius, which a valid crescent never carries.
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
            Primitive::Line | Primitive::FreeLine => instruction.from_.zip(instruction.to).map_or(
                canvas.unit() * 0.02,
                |(start, end)| {
                    let start = point_to_pixels(start, canvas);
                    let end = point_to_pixels(end, canvas);
                    (end.x - start.x).hypot(end.y - start.y)
                },
            ),
        }
        .max(canvas.unit() * 0.02);
    let trace = widths * mark_width(instruction, canvas);
    // A line's variation also shapes its path: a wave, a noise or a jitter
    // strays by a share of its wavelength, so a stated wave stays one on a long
    // line, and the tool's width stays the floor (render engine 83).
    let path = if instruction.primitive == Primitive::Line
        && matches!(
            variation.quality,
            Quality::Wave | Quality::Perlin | Quality::White
        ) {
        line_path_share(variation.amplitude) * representative
            / frequency_cycles(variation.frequency)
    } else {
        0.0
    };
    trace.max(path).min(0.40 * representative)
}

/// How far a Line's varied path strays, as a share of its wavelength: the
/// line's length over the frequency's cycles (render engine 83).
pub(crate) const fn line_path_share(amplitude: Amplitude) -> f64 {
    match amplitude {
        Amplitude::Fine => 0.032,
        Amplitude::Medium => 0.054,
        Amplitude::Broad => 0.135,
    }
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
/// one curve and transform it together with dependents. A rotring line, drawn
/// along its varied centerline too, shares it the same way (render engine 83).
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
    if instruction.primitive != Primitive::Line {
        return None;
    }
    let unit = canvas.unit();
    if !unit.is_finite() || unit <= 0.0 {
        return None;
    }
    let start = point_to_pixels(instruction.from_?, canvas);
    let end = point_to_pixels(instruction.to?, canvas);
    let mut centerline = open_line_with_variation(
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

/// The computer's material, the remainder of sampling (render engines 13 to 40,
/// restored in 84). A computer mark draws no body: each point of its drawn path
/// is rounded onto the one lattice of the canvas, and the cell it is rounded
/// into is laid in the mark's color, toned by how far the rounding moved it
/// (`COMPUTER_CELL_OPACITY` at half a cell, never below
/// `COMPUTER_CELL_OPACITY_FLOOR`). The tone does not take the mark's stroke
/// opacity, so neither intensity nor an arrangement's fade reaches the cells.
pub(crate) const COMPUTER_CELL_OPACITY: f64 = 0.45;
pub(crate) const COMPUTER_CELL_OPACITY_FLOOR: f64 = 0.15;

fn lattice(value: f64, step: f64) -> f64 {
    if step <= 0.0 {
        value
    } else {
        (value / step).round_ties_even() * step
    }
}

/// A stroke's points, each with how far the rounding onto the lattice moved it.
fn sample_cells(samples: &[StrokeSample]) -> Vec<(Point, f64)> {
    samples
        .iter()
        .map(|sample| (sample.point, sample.residual))
        .collect()
}

/// The drawn centerline at `count` points spaced evenly along its length, each
/// rounded onto the lattice like a stroke sample; both ends stay pinned.
fn centerline_cells(points: &[Point], count: usize, step: f64) -> Vec<(Point, f64)> {
    if points.len() < 2 || count < 2 {
        return Vec::new();
    }
    let mut lengths = vec![0.0];
    let mut total = 0.0;
    for pair in points.windows(2) {
        total += (pair[1].x - pair[0].x).hypot(pair[1].y - pair[0].y);
        lengths.push(total);
    }
    let mut segment = 0;
    (0..count)
        .map(|index| {
            let target = total * index as f64 / (count - 1) as f64;
            while segment + 2 < points.len() && lengths[segment + 1] < target {
                segment += 1;
            }
            let span = lengths[segment + 1] - lengths[segment];
            let t = if span > 0.0 {
                ((target - lengths[segment]) / span).clamp(0.0, 1.0)
            } else {
                0.0
            };
            let (a, b) = (points[segment], points[segment + 1]);
            let point = Point::new(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
            if index == 0 || index == count - 1 {
                return (point, 0.0);
            }
            let rounded = Point::new(lattice(point.x, step), lattice(point.y, step));
            (rounded, (point.x - rounded.x).hypot(point.y - rounded.y))
        })
        .collect()
}

/// The cells of a computer mark, in the order of its path. A point the stroke
/// pins to the intention (an end or a corner) is not moved by the rounding, so
/// it is toned by its own distance from the lattice. Every point is re-snapped
/// onto the lattice, as engine 40's cells were, because a closed contour's seam
/// correction moves its samples. Where two consecutive cells are a cell or more
/// apart, the cells on the straight run between them are laid at the mean of
/// the two tones; a closed mark also joins its last cell to its first.
fn computer_cells(points: &[(Point, f64)], step: f64, color: &str, closed: bool) -> Vec<Element> {
    if step <= 0.0 {
        return Vec::new();
    }
    let half = step / 2.0;
    let mut cells = points
        .iter()
        .map(|&(point, residual)| {
            let rounded = Point::new(lattice(point.x, step), lattice(point.y, step));
            let moved = if residual > 0.0 {
                residual
            } else {
                (point.x - rounded.x).hypot(point.y - rounded.y)
            };
            let tone =
                (COMPUTER_CELL_OPACITY * (moved / half).min(1.0)).max(COMPUTER_CELL_OPACITY_FLOOR);
            ((rounded.x / step).round(), (rounded.y / step).round(), tone)
        })
        .collect::<Vec<_>>();
    if cells.len() >= 2 {
        let pairs = if closed { cells.len() } else { cells.len() - 1 };
        let mut joined = Vec::with_capacity(cells.len() * 2);
        for (index, &cell) in cells.iter().enumerate() {
            joined.push(cell);
            if index >= pairs {
                continue;
            }
            let next = cells[(index + 1) % cells.len()];
            let gap = (next.0 - cell.0).abs().max((next.1 - cell.1).abs());
            for part in 1..(gap as usize) {
                let t = part as f64 / gap;
                joined.push((
                    (cell.0 + (next.0 - cell.0) * t).round(),
                    (cell.1 + (next.1 - cell.1) * t).round(),
                    (cell.2 + next.2) / 2.0,
                ));
            }
        }
        cells = joined;
    }
    cells
        .into_iter()
        .map(|(x, y, tone)| {
            Element::new("rect")
                .attr("class", "raster-bleed")
                .attr("x", format_number(x * step - half))
                .attr("y", format_number(y * step - half))
                .attr("width", format_number(step))
                .attr("height", format_number(step))
                .attr("fill", color)
                .attr("fill-opacity", format_number(tone))
                .attr("stroke", "none")
        })
        .collect()
}

/// The hand a line or an arc is performed with: an open band (a sweep or a
/// wash) sways by its round tool's width and keeps the octaves its samples
/// can draw (render engine 92); any other mark keeps the round hand.
fn band_hand(instruction: &Instruction, style: &MarkStyle, context: MarkContext<'_>) -> BandHand {
    if !is_open_band(instruction) || style.width <= 0.0 {
        return BandHand::ROUND;
    }
    BandHand {
        sway_share: round_width(instruction, context.canvas) / style.width,
        smooth: true,
    }
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
    let hand = band_hand(instruction, style, context);
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
    let centerline = connected_centerline.or_else(|| {
        instruction
            .variation
            .as_ref()
            .filter(|variation| needs_path_variation(variation))
            .map(|variation| {
                open_line_with_variation(
                    start,
                    end,
                    variation,
                    seed,
                    amplitude(instruction, context.canvas),
                    context.canvas,
                )
            })
    });
    // The class records the straight stroke's controls and events. With a
    // varied centerline only the stroke along that centerline is drawn, so the
    // straight one is not synthesized just for these two counts.
    // A sweep of the thin or thick brush lays a flat band along the same
    // centerline; the straight stroke still gives its pressure and the counts.
    let flat = sweeps_flat(instruction);
    let lay_flat = |points: &[Point], energies: &[f64], hold: FlatHold| {
        flat_band(FlatBandRequest {
            centerline: points,
            energies,
            hold,
            base_width: style.width,
            weight: instruction.weight,
            seed,
            support,
            scale: context.canvas.unit() / 1000.0,
            brush_size: open_band_width(instruction, context.canvas),
            fine_streaks: true,
        })
    };
    // Only the computer rounds onto a lattice; its cells follow the path drawn.
    let step = grid_step(instruction.weight, context.canvas);
    let (outline, event_count, band, cells) = if let Some(centerline) = centerline {
        let varied = synthesize_stroke_by(
            StrokeRequest {
                start,
                end,
                base_width: style.width,
                weight: instruction.weight,
                seed,
                sample_count: centerline.len(),
                wild: context.wild,
                grid_step: grid_step(instruction.weight, context.canvas),
                support,
            },
            hand,
        );
        let event_count = stroke_event_count(instruction.weight, seed, sample_count);
        let band = if flat {
            let energies = varied
                .samples
                .iter()
                .map(|sample| sample.energy)
                .collect::<Vec<_>>();
            lay_flat(&centerline, &energies, FlatHold::Turning)
        } else {
            None
        };
        let cells = if step > 0.0 {
            centerline_cells(&centerline, sample_count, step)
        } else {
            Vec::new()
        };
        if band.is_some() {
            (Vec::new(), event_count, band, cells)
        } else {
            let widths = varied
                .samples
                .iter()
                .map(|sample| sample.width)
                .collect::<Vec<_>>();
            (
                outline_for_centerline(&centerline, &widths, &varied.cuts),
                event_count,
                None,
                cells,
            )
        }
    } else {
        let stroke = synthesize_stroke_by(
            StrokeRequest {
                start,
                end,
                base_width: style.width,
                weight: instruction.weight,
                seed,
                sample_count,
                wild: context.wild,
                grid_step: grid_step(instruction.weight, context.canvas),
                support,
            },
            hand,
        );
        let band = if flat {
            let points = stroke
                .samples
                .iter()
                .map(|sample| sample.point)
                .collect::<Vec<_>>();
            let energies = stroke
                .samples
                .iter()
                .map(|sample| sample.energy)
                .collect::<Vec<_>>();
            lay_flat(&points, &energies, FlatHold::Fixed)
        } else {
            None
        };
        let cells = if step > 0.0 {
            sample_cells(&stroke.samples)
        } else {
            Vec::new()
        };
        (stroke.outline, stroke.event_count, band, cells)
    };
    let mut group = Element::new("g").attr(
        "class",
        format!("stroke-engine-v1 controls-{sample_count} events-{event_count}"),
    );
    for cell in computer_cells(&cells, step, &style.color, false) {
        group.push(cell);
    }
    if let Some(band) = band {
        group.set_attr("opacity", format_number(style.stroke_opacity));
        group.push(flat_band_element(&band, &style.color, "flat-brush-v1"));
    } else if instruction.weight == Weight::OilPaint {
        let middle = outline.len() / 2;
        let right = outline[middle..].iter().rev().copied().collect::<Vec<_>>();
        group.push(oil_paint_stroke(
            polygon_path(&outline),
            &outline[..middle],
            &right,
            OilPaintStyle::stroke(&style.color, style.stroke_opacity, context.canvas),
            seed,
            false,
        ));
    } else if instruction.weight != Weight::Computer {
        // A computer line is drawn by its lattice cells alone (render engine 84).
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
    let hand = if closed {
        BandHand::ROUND
    } else {
        band_hand(instruction, style, context)
    };
    let stroke = synthesize_contour_by(
        ContourStrokeRequest {
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
        },
        hand,
    );
    if !closed && sweeps_flat(instruction) {
        let points = stroke
            .samples
            .iter()
            .map(|sample| sample.point)
            .collect::<Vec<_>>();
        let energies = stroke
            .samples
            .iter()
            .map(|sample| sample.energy)
            .collect::<Vec<_>>();
        if let Some(band) = flat_band(FlatBandRequest {
            centerline: &points,
            energies: &energies,
            hold: FlatHold::Turning,
            base_width: style.width,
            weight: instruction.weight,
            seed: context.seed_for(instruction),
            support: instruction_support(instruction, context.support),
            scale: context.canvas.unit() / 1000.0,
            brush_size: open_band_width(instruction, context.canvas),
            fine_streaks: true,
        }) {
            let mut group = Element::new("g")
                .attr(
                    "class",
                    format!(
                        "contour-stroke-v1 controls-{} events-{}",
                        stroke.samples.len(),
                        stroke.event_count
                    ),
                )
                .attr("opacity", format_number(style.stroke_opacity));
            group.push(flat_band_element(&band, &style.color, "flat-brush-v1"));
            return with_texture_filter(group, instruction.weight, context.use_filters);
        }
    }
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
                )
            } else {
                OilPaintStyle::stroke(&style.color, style.stroke_opacity, context.canvas)
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
                if instruction.weight == Weight::Computer {
                    // A computer contour is drawn by its lattice cells alone
                    // (render engine 84).
                    for cell in computer_cells(
                        &sample_cells(&stroke.samples),
                        grid_step(instruction.weight, context.canvas),
                        &style.color,
                        closed,
                    ) {
                        group.push(cell);
                    }
                } else {
                    group.push(
                        Element::new("path")
                            .attr("d", contour_stroke_path(&stroke))
                            .attr("fill", &style.color)
                            .attr("fill-opacity", format_number(style.stroke_opacity))
                            .attr("fill-rule", if closed { "evenodd" } else { "nonzero" })
                            .attr("stroke", "none"),
                    );
                }
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
    let mut path = String::with_capacity(count * 72 + 16);
    path.push_str("M ");
    write_number(&mut path, points[0].x);
    path.push(' ');
    write_number(&mut path, points[0].y);
    for index in 0..count {
        let p0 = points[(index + count - 1) % count];
        let p1 = points[index];
        let p2 = points[(index + 1) % count];
        let p3 = points[(index + 2) % count];
        let c1 = Point::new(p1.x + (p2.x - p0.x) / 6.0, p1.y + (p2.y - p0.y) / 6.0);
        let c2 = Point::new(p2.x - (p3.x - p1.x) / 6.0, p2.y - (p3.y - p1.y) / 6.0);
        path.push_str(" C");
        for value in [c1.x, c1.y, c2.x, c2.y, p2.x, p2.y] {
            path.push(' ');
            write_number(&mut path, value);
        }
    }
    path.push_str(" Z");
    path
}

#[cfg(test)]
mod tests {
    use super::*;

    fn instruction(fields: &str, variation: &str) -> Instruction {
        serde_json::from_str(&format!(
            r#"{{{fields},"variation":{{{variation},"dimensions":["position_x","position_y"]}}}}"#
        ))
        .unwrap()
    }

    #[test]
    fn a_line_variation_strays_by_a_share_of_its_wavelength_above_the_tool_width() {
        let canvas = CanvasSize::new(1000.0, 1000.0);
        let pen_line = r#""primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"pen""#;
        // An 800px slow medium wave: 0.054 of its 400px wavelength.
        let wave = instruction(
            pen_line,
            r#""quality":"wave","frequency":"slow","amplitude":"medium""#,
        );
        assert!((amplitude(&wave, canvas) - 21.6).abs() < 1.0e-9);
        // A high fine noise: 0.032 of 800 / 14, above the pen's 0.35 widths.
        let noise = instruction(
            pen_line,
            r#""quality":"perlin","frequency":"high","amplitude":"fine""#,
        );
        assert!((amplitude(&noise, canvas) - 0.032 * 800.0 / 14.0).abs() < 1.0e-9);
        assert!(amplitude(&noise, canvas) > 0.35 * mark_width(&noise, canvas));
        // An arc keeps the tool's widths.
        let arc = instruction(
            r#""primitive":"arc","center":[0.5,0.5],"radius":0.3,"angle_start":0,"angle_end":180,"weight":"pen""#,
            r#""quality":"wave","frequency":"slow","amplitude":"medium""#,
        );
        assert_eq!(amplitude(&arc, canvas), 0.6 * mark_width(&arc, canvas));
        // A short thick brush line keeps its width-based value as the floor.
        let short = instruction(
            r#""primitive":"line","from":[0.45,0.5],"to":[0.55,0.5],"weight":"brush_thick""#,
            r#""quality":"wave","frequency":"slow","amplitude":"fine""#,
        );
        assert_eq!(amplitude(&short, canvas), 0.35 * mark_width(&short, canvas));
    }

    #[test]
    fn a_computer_centerline_lays_its_cells_within_a_cell_of_the_path() {
        let step = 18.0;
        // Two periods of a 40px sine over 600px, as a varied centerline is drawn.
        let wave = (0..=120)
            .map(|index| {
                let x = 100.0 + 5.0 * f64::from(index);
                let phase = std::f64::consts::TAU * (x - 100.0) / 300.0;
                Point::new(x, 500.0 + 40.0 * phase.sin())
            })
            .collect::<Vec<_>>();
        let distance = |point: Point| {
            wave.windows(2)
                .map(|pair| {
                    let (a, b) = (pair[0], pair[1]);
                    let (dx, dy) = (b.x - a.x, b.y - a.y);
                    let t = (((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy))
                        .clamp(0.0, 1.0);
                    (point.x - a.x - t * dx).hypot(point.y - a.y - t * dy)
                })
                .fold(f64::INFINITY, f64::min)
        };
        let cells = centerline_cells(&wave, 31, step);
        assert_eq!(cells.len(), 31);
        assert_eq!(cells[0], (wave[0], 0.0));
        assert_eq!(cells[30], (wave[120], 0.0));
        for &(cell, moved) in &cells[1..30] {
            assert_eq!(
                cell,
                Point::new(lattice(cell.x, step), lattice(cell.y, step))
            );
            assert!(moved > 0.0 && moved <= step / 2.0 * std::f64::consts::SQRT_2 + 1.0e-9);
            assert!(distance(cell) <= moved + 1.0e-9);
        }
    }
}
