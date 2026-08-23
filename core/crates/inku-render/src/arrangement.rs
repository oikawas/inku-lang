//! Expansion and placement of canonical arrangements.

use crate::determinism::instruction_seed;
use crate::group::finish_group;
use crate::placement::{
    ClusterPlacement, clustered_position, path_position, region_in_short_side_units,
    rhythm_parameter, short_side_scales,
};
use crate::planning::{ensure_line_coordinates, instruction_anchor};
use crate::types::{
    ArrangementPath, CanvasSize, Density, Fade, Instruction, Layout, Point, Primitive, Seed,
};

const FRAME_LOW: f64 = 0.02;
const FRAME_HIGH: f64 = 0.98;
const ARRANGEMENT_SCALE: f64 = 1_000_000_000.0;

fn density_name(density: Density) -> &'static str {
    match density {
        Density::None => "none",
        Density::Low => "low",
        Density::Medium => "medium",
        Density::High => "high",
    }
}

fn fade_name(fade: Fade) -> &'static str {
    match fade {
        Fade::None => "none",
        Fade::Outward => "outward",
        Fade::Directional => "directional",
    }
}

fn shift_instruction(instruction: &Instruction, delta: Point) -> Instruction {
    let mut shifted = instruction.clone();
    shifted.arrangement = None;
    if let Some(arrangement) = instruction.arrangement.as_ref() {
        let mut notes = Vec::new();
        if arrangement.density != Density::None {
            notes.push(format!("density={}", density_name(arrangement.density)));
        }
        if arrangement.fade != Fade::None {
            notes.push(format!("fade={}", fade_name(arrangement.fade)));
        }
        if arrangement.preserve_space {
            notes.push("preserve_space".to_owned());
        }
        if !notes.is_empty() {
            let effect = notes.join("; ");
            shifted.color_hint = Some(
                instruction
                    .color_hint
                    .as_ref()
                    .map_or(effect.clone(), |hint| format!("{hint}; {effect}")),
            );
        }
    }
    match instruction.primitive {
        Primitive::Line => {
            if let (Some(start), Some(end)) = (instruction.from_, instruction.to) {
                shifted.from_ = Some(Point::new(start.x + delta.x, start.y + delta.y));
                shifted.to = Some(Point::new(end.x + delta.x, end.y + delta.y));
            }
        }
        Primitive::Circle
        | Primitive::Ellipse
        | Primitive::Arc
        | Primitive::Polygon
        | Primitive::Cloudform => {
            if let Some(center) = instruction.center {
                shifted.center = Some(Point::new(center.x + delta.x, center.y + delta.y));
            }
        }
        Primitive::Square | Primitive::Triangle => {
            if let Some(position) = instruction.position {
                shifted.position = Some(Point::new(position.x + delta.x, position.y + delta.y));
            }
        }
    }
    shifted
}

fn axis_scales(anchor: f64, offsets: impl Iterator<Item = f64> + Clone) -> (f64, f64) {
    let positive = offsets
        .clone()
        .filter(|offset| *offset > 0.0)
        .fold(0.0, f64::max);
    let negative = offsets.filter(|offset| *offset < 0.0).fold(0.0, f64::min);
    let forward = if positive > 0.0 {
        ((FRAME_HIGH - anchor) / positive).min(1.0)
    } else {
        1.0
    };
    let backward = if negative < 0.0 {
        ((FRAME_LOW - anchor) / negative).min(1.0)
    } else {
        1.0
    };
    (forward.max(0.0), backward.max(0.0))
}

fn fit_group_to_anchor(stated: &Instruction, expanded: Vec<Instruction>) -> Vec<Instruction> {
    let anchor = instruction_anchor(stated);
    let points: Vec<Point> = expanded.iter().map(instruction_anchor).collect();
    let center = Point::new(
        points.iter().map(|point| point.x).sum::<f64>() / points.len() as f64,
        points.iter().map(|point| point.y).sum::<f64>() / points.len() as f64,
    );
    let offsets: Vec<Point> = points
        .iter()
        .map(|point| Point::new(point.x - center.x, point.y - center.y))
        .collect();
    let (x_forward, x_backward) = axis_scales(anchor.x, offsets.iter().map(|point| point.x));
    let (y_forward, y_backward) = axis_scales(anchor.y, offsets.iter().map(|point| point.y));
    expanded
        .into_iter()
        .zip(points)
        .zip(offsets)
        .map(|((item, point), offset)| {
            let target = Point::new(
                anchor.x
                    + offset.x
                        * if offset.x > 0.0 {
                            x_forward
                        } else {
                            x_backward
                        },
                anchor.y
                    + offset.y
                        * if offset.y > 0.0 {
                            y_forward
                        } else {
                            y_backward
                        },
            );
            shift_instruction(&item, Point::new(target.x - point.x, target.y - point.y))
        })
        .collect()
}

fn quantize(value: f64) -> f64 {
    (value * ARRANGEMENT_SCALE).round_ties_even() / ARRANGEMENT_SCALE
}

fn quantize_point(point: Point) -> Point {
    Point::new(quantize(point.x), quantize(point.y))
}

/// Remove platform libm noise before expanded coordinates can enter a seed payload.
#[must_use]
pub fn quantize_instruction(instruction: &Instruction) -> Instruction {
    let mut result = instruction.clone();
    result.from_ = instruction.from_.map(quantize_point);
    result.to = instruction.to.map(quantize_point);
    result.center = instruction.center.map(quantize_point);
    result.position = instruction.position.map(quantize_point);
    result.size = instruction.size.map(quantize_point);
    result.radius = instruction.radius.map(quantize);
    result.angle_start = instruction.angle_start.map(quantize);
    result.angle_end = instruction.angle_end.map(quantize);
    result.rotation = instruction.rotation.map(quantize);
    if let Some(at) = result.at.as_mut() {
        at.region = at.region.map(quantize);
    }
    if let Some(surface) = result.surface.as_mut() {
        surface.density = quantize(surface.density);
        surface.scale = quantize(surface.scale);
        surface.opacity = quantize(surface.opacity);
        surface.bleed = quantize(surface.bleed);
    }
    if let Some(arrangement) = result.arrangement.as_mut() {
        arrangement.jitter = quantize(arrangement.jitter);
        arrangement.margin = quantize(arrangement.margin);
        arrangement.center = arrangement.center.map(quantize_point);
        arrangement.radius = arrangement.radius.map(quantize);
    }
    result
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ArrangementRequest<'a> {
    pub instruction: &'a Instruction,
    pub placement_seed: Option<Seed>,
    pub performance_seed: Option<Seed>,
    pub canvas: Option<CanvasSize>,
}

fn grid_targets(
    arrangement: &crate::types::Arrangement,
    instruction: &Instruction,
    count: usize,
    margin: f64,
    seed: Seed,
    canvas: Option<CanvasSize>,
) -> Vec<Point> {
    let [x0, y0, x1, y1] = instruction
        .at
        .as_ref()
        .map_or([margin, margin, 1.0 - margin, 1.0 - margin], |at| {
            region_in_short_side_units(at.region, canvas)
        });
    let width = (x1 - x0).max(1.0e-9);
    let height = (y1 - y0).max(1.0e-9);
    let (rows, columns) = match (arrangement.rows, arrangement.cols) {
        (Some(rows), Some(columns)) => (rows as usize, columns as usize),
        (Some(rows), None) => (rows as usize, count.div_ceil(rows as usize).clamp(1, 64)),
        (None, Some(columns)) => (
            count.div_ceil(columns as usize).clamp(1, 64),
            columns as usize,
        ),
        (None, None) => {
            let physical_aspect =
                width / height * canvas.map_or(1.0, |canvas| canvas.width / canvas.height);
            let columns = ((count as f64 * physical_aspect).sqrt().ceil() as usize).clamp(1, 64);
            (count.div_ceil(columns).clamp(1, 64), columns)
        }
    };
    let cell_width = width / columns as f64;
    let cell_height = height / rows as f64;
    let mut targets = Vec::with_capacity(rows * columns);
    for row in 0..rows {
        let row_t = rhythm_parameter(row, rows, seed ^ 0xA53C, arrangement.rhythm_spacing);
        let y = y0 + (0.5 + row_t * (rows - 1) as f64) * cell_height;
        for column in 0..columns {
            let column_t =
                rhythm_parameter(column, columns, seed ^ 0xC3A5, arrangement.rhythm_spacing);
            let x = x0 + (0.5 + column_t * (columns - 1) as f64) * cell_width;
            let flat_index = row * columns + column;
            let dx = (crate::determinism::hash01(flat_index as i64, seed, "grid-jitter-x") - 0.5)
                * arrangement.jitter
                * cell_width;
            let dy = (crate::determinism::hash01(flat_index as i64, seed, "grid-jitter-y") - 0.5)
                * arrangement.jitter
                * cell_height;
            targets.push(Point::new((x + dx).clamp(x0, x1), (y + dy).clamp(y0, y1)));
        }
    }
    targets
}

/// Expand an arrangement into deterministic performed members.
#[must_use]
pub fn expand_arrangement(request: ArrangementRequest<'_>) -> Vec<Instruction> {
    let Some(arrangement) = request.instruction.arrangement.as_ref() else {
        return vec![request.instruction.clone()];
    };
    let prepared = ensure_line_coordinates(request.instruction);
    let member_seed = Some(instruction_seed(&prepared, request.performance_seed));
    if arrangement.count == 1 && arrangement.layout != Layout::Grid {
        let mut single = prepared;
        single.arrangement = None;
        return finish_group(vec![single], arrangement, None, member_seed);
    }
    let count = arrangement.count as usize;
    let margin = if arrangement.preserve_space {
        arrangement.margin.max(0.20)
    } else {
        arrangement.margin
    };
    let anchor = instruction_anchor(&prepared);
    let seed = instruction_seed(&prepared, request.placement_seed);

    let (targets, layout_center) = if arrangement.layout == Layout::Grid {
        (
            grid_targets(arrangement, &prepared, count, margin, seed, request.canvas),
            None,
        )
    } else if arrangement.cluster_count.unwrap_or(0) > 0
        && matches!(
            arrangement.layout,
            Layout::Scatter | Layout::Horizontal | Layout::Vertical
        )
    {
        let path = match (arrangement.path, arrangement.layout) {
            (ArrangementPath::None, Layout::Horizontal) => ArrangementPath::LeftToRight,
            (ArrangementPath::None, Layout::Vertical) => ArrangementPath::TopToBottom,
            (path, _) => path,
        };
        (
            (0..count)
                .map(|index| {
                    clustered_position(ClusterPlacement {
                        index,
                        count,
                        seed,
                        margin,
                        path,
                        cluster_count: arrangement.cluster_count.unwrap_or(1) as usize,
                        density: arrangement.density,
                        preserve_space: arrangement.preserve_space,
                        rhythm_spacing: arrangement.rhythm_spacing,
                        canvas: request.canvas,
                    })
                })
                .collect(),
            None,
        )
    } else {
        match arrangement.layout {
            Layout::Horizontal if arrangement.path == ArrangementPath::None => (
                (0..count)
                    .map(|index| {
                        Point::new(
                            margin
                                + rhythm_parameter(index, count, seed, arrangement.rhythm_spacing)
                                    * (1.0 - 2.0 * margin),
                            anchor.y,
                        )
                    })
                    .collect(),
                None,
            ),
            Layout::Vertical if arrangement.path == ArrangementPath::None => (
                (0..count)
                    .map(|index| {
                        Point::new(
                            anchor.x,
                            margin
                                + rhythm_parameter(index, count, seed, arrangement.rhythm_spacing)
                                    * (1.0 - 2.0 * margin),
                        )
                    })
                    .collect(),
                None,
            ),
            Layout::Radial => {
                let center = arrangement.center.unwrap_or(anchor);
                let radius = arrangement.radius.unwrap_or(0.3);
                let scale = short_side_scales(request.canvas);
                (
                    (0..count)
                        .map(|index| {
                            let angle =
                                rhythm_parameter(index, count, seed, arrangement.rhythm_spacing)
                                    * std::f64::consts::TAU;
                            Point::new(
                                center.x + radius * scale.x * angle.cos(),
                                center.y - radius * scale.y * angle.sin(),
                            )
                        })
                        .collect(),
                    Some(center),
                )
            }
            _ => (
                (0..count)
                    .map(|index| {
                        path_position(
                            index,
                            count,
                            seed,
                            margin,
                            arrangement.path,
                            arrangement.rhythm_spacing,
                            request.canvas,
                        )
                    })
                    .collect(),
                None,
            ),
        }
    };

    let mut expanded: Vec<Instruction> = targets
        .into_iter()
        .map(|target| {
            let mut item = shift_instruction(
                &prepared,
                Point::new(target.x - anchor.x, target.y - anchor.y),
            );
            if arrangement.layout == Layout::Grid {
                item.at = None;
                item.relation = None;
            }
            item
        })
        .collect();
    expanded = finish_group(expanded, arrangement, layout_center, member_seed);
    if arrangement.layout != Layout::Grid {
        expanded = fit_group_to_anchor(&prepared, expanded);
    }
    expanded.iter().map(quantize_instruction).collect()
}
