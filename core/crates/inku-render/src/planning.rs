//! Pure transformation of canonical instructions into performed instructions.

use crate::arc::{arc_from_endpoints_and_sagitta, arc_point, minor_arc_delta};
use crate::cloudform::{CloudformRequest, generate_cloudform_contour};
use crate::determinism::{hash01, instruction_seed};
use crate::geometry::{
    point_from_short_side_units, point_to_short_side_units, size_in_normalized_axes,
};
use crate::placement::region_in_short_side_units;
use crate::types::{
    CanvasSize, Instruction, Layout, Point, Primitive, RelationGap, RelationType, Seed,
};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Bounds {
    pub min: Point,
    pub max: Point,
}

impl Bounds {
    #[must_use]
    pub fn center(self) -> Point {
        Point::new(
            (self.min.x + self.max.x) / 2.0,
            (self.min.y + self.max.y) / 2.0,
        )
    }

    #[must_use]
    pub fn radius(self) -> f64 {
        ((self.max.x - self.min.x).hypot(self.max.y - self.min.y) / 2.0).max(0.015)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct PlanningWarning {
    pub instruction_index: usize,
    pub relation: RelationType,
    pub reason: &'static str,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RelationResolution {
    pub instruction: Instruction,
    pub warning: Option<PlanningWarning>,
}

fn clamp_point(point: Point) -> Point {
    Point::new(point.x.clamp(0.0, 1.0), point.y.clamp(0.0, 1.0))
}

#[must_use]
pub fn ensure_line_coordinates(instruction: &Instruction) -> Instruction {
    if instruction.primitive != Primitive::Line
        || (instruction.from_.is_some() && instruction.to.is_some())
    {
        return instruction.clone();
    }
    let mut resolved = instruction.clone();
    let vertical_layout = instruction
        .arrangement
        .as_ref()
        .is_some_and(|arrangement| arrangement.layout == Layout::Vertical);
    if vertical_layout {
        resolved.from_ = Some(Point::new(0.0, 0.5));
        resolved.to = Some(Point::new(1.0, 0.5));
    } else {
        resolved.from_ = Some(Point::new(0.5, 0.0));
        resolved.to = Some(Point::new(0.5, 1.0));
    }
    resolved
}

#[must_use]
pub fn instruction_anchor(instruction: &Instruction) -> Point {
    instruction_anchor_on_canvas(instruction, None)
}

/// Return the semantic anchor in normalized canvas axes while interpreting sizes on the short side.
#[must_use]
pub fn instruction_anchor_on_canvas(
    instruction: &Instruction,
    canvas: Option<CanvasSize>,
) -> Point {
    match instruction.primitive {
        Primitive::Line => instruction
            .from_
            .zip(instruction.to)
            .map_or(Point::new(0.5, 0.5), |(start, end)| {
                Point::new((start.x + end.x) / 2.0, (start.y + end.y) / 2.0)
            }),
        Primitive::Circle
        | Primitive::Ellipse
        | Primitive::Arc
        | Primitive::Polygon
        | Primitive::Cloudform => instruction.center.unwrap_or(Point::new(0.5, 0.5)),
        Primitive::Square | Primitive::Triangle => instruction
            .position
            .zip(instruction.size)
            .map_or(Point::new(0.5, 0.5), |(position, size)| {
                let size = size_in_normalized_axes(size, canvas);
                Point::new(position.x + size.x / 2.0, position.y + size.y / 2.0)
            }),
    }
}

#[must_use]
pub fn move_anchor_to(
    instruction: &Instruction,
    target: Point,
    keep_relation: bool,
) -> Instruction {
    move_anchor_to_on_canvas(instruction, target, keep_relation, None)
}

#[must_use]
pub fn move_anchor_to_on_canvas(
    instruction: &Instruction,
    target: Point,
    keep_relation: bool,
    canvas: Option<CanvasSize>,
) -> Instruction {
    let anchor = instruction_anchor_on_canvas(instruction, canvas);
    let delta = Point::new(target.x - anchor.x, target.y - anchor.y);
    let mut moved = instruction.clone();
    moved.at = None;
    if !keep_relation {
        moved.relation = None;
    }
    match instruction.primitive {
        Primitive::Line => {
            if let (Some(start), Some(end)) = (instruction.from_, instruction.to) {
                moved.from_ = Some(clamp_point(Point::new(
                    start.x + delta.x,
                    start.y + delta.y,
                )));
                moved.to = Some(clamp_point(Point::new(end.x + delta.x, end.y + delta.y)));
            }
        }
        Primitive::Circle
        | Primitive::Ellipse
        | Primitive::Arc
        | Primitive::Polygon
        | Primitive::Cloudform => {
            moved.center = Some(clamp_point(instruction.center.map_or(target, |center| {
                Point::new(center.x + delta.x, center.y + delta.y)
            })));
        }
        Primitive::Square | Primitive::Triangle => {
            let size = instruction.size.unwrap_or(Point::new(0.2, 0.2));
            let normalized_size = size_in_normalized_axes(size, canvas);
            moved.size = Some(size);
            moved.position = Some(clamp_point(instruction.position.map_or_else(
                || {
                    Point::new(
                        target.x - normalized_size.x / 2.0,
                        target.y - normalized_size.y / 2.0,
                    )
                },
                |position| Point::new(position.x + delta.x, position.y + delta.y),
            )));
        }
    }
    moved
}

#[must_use]
pub fn resolve_at_region(
    instruction: &Instruction,
    seed: Seed,
    index: usize,
    canvas: Option<CanvasSize>,
) -> Instruction {
    let Some(at) = instruction.at.as_ref() else {
        return instruction.clone();
    };
    let [x0, y0, x1, y1] = region_in_short_side_units(at.region, canvas);
    let target = Point::new(
        x0 + (x1 - x0) * hash01(index as i64, seed, "region-x"),
        y0 + (y1 - y0) * hash01(index as i64, seed, "region-y"),
    );
    move_anchor_to_on_canvas(instruction, target, true, canvas)
}

fn rotate_point(point: Point, center: Point, degrees: f64) -> Point {
    let angle = degrees.to_radians();
    let delta = Point::new(point.x - center.x, point.y - center.y);
    Point::new(
        center.x + delta.x * angle.cos() - delta.y * angle.sin(),
        center.y + delta.x * angle.sin() + delta.y * angle.cos(),
    )
}

fn rotate_vector(vector: Point, degrees: f64) -> Point {
    let angle = degrees.to_radians();
    Point::new(
        vector.x * angle.cos() - vector.y * angle.sin(),
        vector.x * angle.sin() + vector.y * angle.cos(),
    )
}

fn bounds_for_points(points: &[Point]) -> Option<Bounds> {
    let first = *points.first()?;
    Some(points.iter().copied().skip(1).fold(
        Bounds {
            min: first,
            max: first,
        },
        |mut bounds, point| {
            bounds.min.x = bounds.min.x.min(point.x);
            bounds.min.y = bounds.min.y.min(point.y);
            bounds.max.x = bounds.max.x.max(point.x);
            bounds.max.y = bounds.max.y.max(point.y);
            bounds
        },
    ))
}

#[must_use]
pub fn instruction_bounds(instruction: &Instruction) -> Option<Bounds> {
    performed_instruction_bounds(instruction, None, 0)
}

#[must_use]
pub fn performed_instruction_bounds(
    instruction: &Instruction,
    performance_seed: Option<Seed>,
    instruction_index: usize,
) -> Option<Bounds> {
    performed_instruction_bounds_on_canvas(instruction, performance_seed, instruction_index, None)
}

#[must_use]
pub fn performed_instruction_bounds_on_canvas(
    instruction: &Instruction,
    performance_seed: Option<Seed>,
    instruction_index: usize,
    canvas: Option<CanvasSize>,
) -> Option<Bounds> {
    let rotation = instruction.rotation.unwrap_or(0.0);
    match instruction.primitive {
        Primitive::Line => {
            let points = [instruction.from_?, instruction.to?]
                .map(|point| point_to_short_side_units(point, canvas));
            let anchor = point_to_short_side_units(
                instruction_anchor_on_canvas(instruction, canvas),
                canvas,
            );
            bounds_for_points(&points.map(|point| rotate_point(point, anchor, rotation)))
        }
        Primitive::Circle | Primitive::Arc | Primitive::Polygon => {
            let center = point_to_short_side_units(instruction.center?, canvas);
            let radius = instruction.radius?;
            Some(Bounds {
                min: Point::new(center.x - radius, center.y - radius),
                max: Point::new(center.x + radius, center.y + radius),
            })
        }
        Primitive::Ellipse => {
            let center = point_to_short_side_units(instruction.center?, canvas);
            let size = instruction.size?;
            let angle = rotation.to_radians();
            let half = Point::new(size.x / 2.0, size.y / 2.0);
            let width = (half.x * angle.cos()).hypot(half.y * angle.sin());
            let height = (half.x * angle.sin()).hypot(half.y * angle.cos());
            Some(Bounds {
                min: Point::new(center.x - width, center.y - height),
                max: Point::new(center.x + width, center.y + height),
            })
        }
        Primitive::Square | Primitive::Triangle => {
            let position = point_to_short_side_units(instruction.position?, canvas);
            let size = instruction.size?;
            let points = if instruction.primitive == Primitive::Triangle {
                vec![
                    Point::new(position.x + size.x / 2.0, position.y),
                    Point::new(position.x, position.y + size.y),
                    Point::new(position.x + size.x, position.y + size.y),
                ]
            } else {
                vec![
                    position,
                    Point::new(position.x + size.x, position.y),
                    Point::new(position.x + size.x, position.y + size.y),
                    Point::new(position.x, position.y + size.y),
                ]
            };
            let anchor = point_to_short_side_units(
                instruction_anchor_on_canvas(instruction, canvas),
                canvas,
            );
            let points: Vec<Point> = points
                .into_iter()
                .map(|point| rotate_point(point, anchor, rotation))
                .collect();
            bounds_for_points(&points)
        }
        Primitive::Cloudform => {
            let center = point_to_short_side_units(instruction.center?, canvas);
            let size = instruction.size?;
            let contour = generate_cloudform_contour(CloudformRequest {
                center,
                size,
                performance_seed: Some(instruction_seed(instruction, performance_seed)),
                instruction_index,
                mark_index: 0,
                variation: instruction.variation.as_ref(),
                weight: instruction.weight,
                point_count: 49,
            });
            let points: Vec<Point> = contour
                .into_iter()
                .map(|point| rotate_point(point, center, rotation))
                .collect();
            bounds_for_points(&points)
        }
    }
}

fn endpoint_geometry(
    instruction: &Instruction,
    canvas: Option<CanvasSize>,
) -> Option<(Point, Point, Point, Point)> {
    let rotation = instruction.rotation.unwrap_or(0.0);
    match instruction.primitive {
        Primitive::Line => {
            let center = point_to_short_side_units(
                instruction_anchor_on_canvas(instruction, canvas),
                canvas,
            );
            let start = rotate_point(
                point_to_short_side_units(instruction.from_?, canvas),
                center,
                rotation,
            );
            let end = rotate_point(
                point_to_short_side_units(instruction.to?, canvas),
                center,
                rotation,
            );
            let tangent = Point::new(end.x - start.x, end.y - start.y);
            (tangent.x.hypot(tangent.y) >= 1.0e-9).then_some((start, end, tangent, tangent))
        }
        Primitive::Arc => {
            let center = point_to_short_side_units(instruction.center?, canvas);
            let radius = instruction.radius?;
            let start_angle = instruction.angle_start?;
            let end_angle = instruction.angle_end?;
            let start_radians = start_angle.to_radians();
            let end_radians = end_angle.to_radians();
            let direction = if end_angle > start_angle { 1.0 } else { -1.0 };
            Some((
                rotate_point(arc_point(center, radius, start_angle), center, rotation),
                rotate_point(arc_point(center, radius, end_angle), center, rotation),
                rotate_vector(
                    Point::new(
                        -start_radians.sin() * direction,
                        -start_radians.cos() * direction,
                    ),
                    rotation,
                ),
                rotate_vector(
                    Point::new(
                        -end_radians.sin() * direction,
                        -end_radians.cos() * direction,
                    ),
                    rotation,
                ),
            ))
        }
        _ => None,
    }
}

fn performed_arc_sagitta(instruction: &Instruction, canvas: Option<CanvasSize>) -> Option<f64> {
    if instruction.primitive != Primitive::Arc {
        return None;
    }
    let center = point_to_short_side_units(instruction.center?, canvas);
    let radius = instruction.radius?;
    let start_angle = instruction.angle_start?;
    let end_angle = instruction.angle_end?;
    let (start, end, _, _) = endpoint_geometry(instruction, canvas)?;
    let delta = minor_arc_delta(start_angle, end_angle);
    let apex = rotate_point(
        arc_point(center, radius, start_angle + delta / 2.0),
        center,
        instruction.rotation.unwrap_or(0.0),
    );
    let chord = Point::new(end.x - start.x, end.y - start.y);
    let length = chord.x.hypot(chord.y);
    if length <= 1.0e-12 {
        return None;
    }
    let midpoint = Point::new((start.x + end.x) / 2.0, (start.y + end.y) / 2.0);
    let normal = Point::new(-chord.y / length, chord.x / length);
    Some((apex.x - midpoint.x) * normal.x + (apex.y - midpoint.y) * normal.y)
}

fn stripped(instruction: &Instruction) -> Instruction {
    let mut stripped = instruction.clone();
    stripped.at = None;
    stripped.relation = None;
    stripped
}

fn dropped(instruction: &Instruction, index: usize, reason: &'static str) -> RelationResolution {
    RelationResolution {
        instruction: stripped(instruction),
        warning: instruction
            .relation
            .as_ref()
            .map(|relation| PlanningWarning {
                instruction_index: index,
                relation: relation.kind,
                reason,
            }),
    }
}

fn relation_gap(seed: Seed, index: usize, gap: RelationGap) -> f64 {
    let (lower, upper) = match gap {
        RelationGap::Narrow => (0.02, 0.05),
        RelationGap::Medium => (0.06, 0.12),
        RelationGap::Wide => (0.15, 0.30),
    };
    lower + (upper - lower) * hash01(index as i64, seed, "relation-gap")
}

fn line_perpendicular(start: Point, end: Point, amount: f64) -> Point {
    let delta = Point::new(end.x - start.x, end.y - start.y);
    let length = delta.x.hypot(delta.y);
    if length < 1.0e-6 {
        Point::new(0.0, 0.0)
    } else {
        Point::new(-delta.y / length * amount, delta.x / length * amount)
    }
}

fn touching_relation(
    instruction: &Instruction,
    previous: &[Instruction],
    index: usize,
    canvas: Option<CanvasSize>,
) -> RelationResolution {
    if !matches!(instruction.primitive, Primitive::Line | Primitive::Arc) || previous.is_empty() {
        return dropped(
            instruction,
            index,
            "touching requires a line or arc with a prior",
        );
    }
    let prior = &previous[previous.len() - 1];
    if !matches!(prior.primitive, Primitive::Line | Primitive::Arc) {
        return dropped(instruction, index, "prior is not a line or arc");
    }
    let Some((start, end, _, _)) = endpoint_geometry(prior, canvas) else {
        return dropped(instruction, index, "prior has no endpoint geometry");
    };
    let mut resolved = stripped(instruction);
    resolved.rotation = None;
    if instruction.primitive == Primitive::Line {
        resolved.from_ = Some(point_from_short_side_units(start, canvas));
        resolved.to = Some(point_from_short_side_units(end, canvas));
        return RelationResolution {
            instruction: resolved,
            warning: None,
        };
    }
    let Some(own_sagitta) = performed_arc_sagitta(instruction, canvas) else {
        return dropped(instruction, index, "degenerate own sagitta");
    };
    let sagitta = if prior.primitive == Primitive::Arc {
        let Some(prior_sagitta) = performed_arc_sagitta(prior, canvas) else {
            return dropped(instruction, index, "degenerate prior sagitta");
        };
        -own_sagitta.abs().copysign(prior_sagitta)
    } else {
        own_sagitta
    };
    let Ok(arc) = arc_from_endpoints_and_sagitta(start, end, sagitta) else {
        return dropped(instruction, index, "minor arc reconstruction failed");
    };
    resolved.center = Some(point_from_short_side_units(arc.center, canvas));
    resolved.radius = Some(arc.radius);
    resolved.angle_start = Some(arc.angle_start);
    resolved.angle_end = Some(arc.angle_end);
    RelationResolution {
        instruction: resolved,
        warning: None,
    }
}

#[must_use]
pub fn resolve_relation(
    instruction: &Instruction,
    previous: &[Instruction],
    seed: Seed,
    index: usize,
) -> RelationResolution {
    resolve_relation_on_canvas(instruction, previous, seed, index, None)
}

#[must_use]
pub fn resolve_relation_on_canvas(
    instruction: &Instruction,
    previous: &[Instruction],
    seed: Seed,
    index: usize,
    canvas: Option<CanvasSize>,
) -> RelationResolution {
    let Some(relation) = instruction.relation.as_ref() else {
        return RelationResolution {
            instruction: stripped(instruction),
            warning: None,
        };
    };
    if relation.kind == RelationType::Touching {
        return touching_relation(instruction, previous, index, canvas);
    }
    if relation.kind == RelationType::Between && previous.len() < 2 {
        return dropped(instruction, index, "between requires two priors");
    }
    if relation.kind != RelationType::Between && previous.is_empty() {
        return dropped(instruction, index, "no prior instruction");
    }
    let Some(prior_bounds) = previous.last().and_then(|prior| {
        performed_instruction_bounds_on_canvas(prior, Some(seed), index.saturating_sub(1), canvas)
    }) else {
        return dropped(instruction, index, "prior has no performed bounds");
    };
    let prior_center = prior_bounds.center();
    let gap = relation_gap(seed, index, relation.gap);
    let target = match relation.kind {
        RelationType::Between => {
            let Some(other_bounds) = previous.get(previous.len() - 2).and_then(|other| {
                performed_instruction_bounds_on_canvas(
                    other,
                    Some(seed),
                    index.saturating_sub(2),
                    canvas,
                )
            }) else {
                return RelationResolution {
                    instruction: stripped(instruction),
                    warning: None,
                };
            };
            let jitter = 0.08 * (hash01(index as i64, seed, "between-jitter") - 0.5);
            clamp_short_side_point(
                Point::new(
                    (prior_center.x + other_bounds.center().x) / 2.0 + jitter,
                    (prior_center.y + other_bounds.center().y) / 2.0 - jitter,
                ),
                canvas,
            )
        }
        RelationType::Along => {
            let prior = &previous[previous.len() - 1];
            if prior.primitive == Primitive::Line {
                let Some((start, end, _, _)) = endpoint_geometry(prior, canvas) else {
                    return RelationResolution {
                        instruction: stripped(instruction),
                        warning: None,
                    };
                };
                let t = 0.18 + 0.64 * hash01(index as i64, seed, "along-t");
                let point = Point::new(
                    start.x + (end.x - start.x) * t,
                    start.y + (end.y - start.y) * t,
                );
                let offset = line_perpendicular(start, end, gap);
                let side = if hash01(index as i64, seed, "along-side") < 0.5 {
                    -1.0
                } else {
                    1.0
                };
                clamp_short_side_point(
                    Point::new(point.x + offset.x * side, point.y + offset.y * side),
                    canvas,
                )
            } else if prior.primitive == Primitive::Cloudform {
                let Some(center) = prior
                    .center
                    .map(|center| point_to_short_side_units(center, canvas))
                else {
                    return dropped(instruction, index, "prior cloudform has no center");
                };
                let Some(size) = prior.size else {
                    return dropped(instruction, index, "prior cloudform has no size");
                };
                let contour = generate_cloudform_contour(CloudformRequest {
                    center,
                    size,
                    performance_seed: Some(instruction_seed(prior, Some(seed))),
                    instruction_index: index.saturating_sub(1),
                    mark_index: 0,
                    variation: prior.variation.as_ref(),
                    weight: prior.weight,
                    point_count: 49,
                });
                let point_index = (hash01(index as i64, seed, "along-cloudform")
                    * contour.len() as f64) as usize
                    % contour.len();
                let point =
                    rotate_point(contour[point_index], center, prior.rotation.unwrap_or(0.0));
                let delta = Point::new(point.x - prior_center.x, point.y - prior_center.y);
                let distance = delta.x.hypot(delta.y).max(1.0e-9);
                clamp_short_side_point(
                    Point::new(
                        point.x + delta.x / distance * gap,
                        point.y + delta.y / distance * gap,
                    ),
                    canvas,
                )
            } else {
                let angle = std::f64::consts::TAU * hash01(index as i64, seed, "along-angle");
                clamp_short_side_point(
                    Point::new(
                        prior_center.x + angle.cos() * (prior_bounds.radius() + gap),
                        prior_center.y + angle.sin() * (prior_bounds.radius() + gap),
                    ),
                    canvas,
                )
            }
        }
        RelationType::Cutting => {
            if instruction.primitive == Primitive::Line {
                let angle = std::f64::consts::TAU * hash01(index as i64, seed, "cut-angle");
                let length = 0.28 + 0.18 * hash01(index as i64, seed, "cut-length");
                let mut resolved = stripped(instruction);
                resolved.from_ = Some(point_from_short_side_units(
                    clamp_short_side_point(
                        Point::new(
                            prior_center.x - angle.cos() * length / 2.0,
                            prior_center.y - angle.sin() * length / 2.0,
                        ),
                        canvas,
                    ),
                    canvas,
                ));
                resolved.to = Some(point_from_short_side_units(
                    clamp_short_side_point(
                        Point::new(
                            prior_center.x + angle.cos() * length / 2.0,
                            prior_center.y + angle.sin() * length / 2.0,
                        ),
                        canvas,
                    ),
                    canvas,
                ));
                return RelationResolution {
                    instruction: resolved,
                    warning: None,
                };
            }
            prior_center
        }
        RelationType::NotTouching => {
            let own_radius =
                performed_instruction_bounds_on_canvas(instruction, Some(seed), index, canvas)
                    .map_or(0.0, Bounds::radius);
            let distance = prior_bounds.radius() + own_radius + gap;
            let angle = std::f64::consts::TAU * hash01(index as i64, seed, "not-touching-angle");
            clamp_short_side_point(
                Point::new(
                    prior_center.x + angle.cos() * distance,
                    prior_center.y + angle.sin() * distance,
                ),
                canvas,
            )
        }
        RelationType::Touching => unreachable!("touching handled above"),
    };
    RelationResolution {
        instruction: move_anchor_to_on_canvas(
            instruction,
            point_from_short_side_units(target, canvas),
            false,
            canvas,
        ),
        warning: None,
    }
}

fn clamp_short_side_point(point: Point, canvas: Option<CanvasSize>) -> Point {
    point_to_short_side_units(
        clamp_point(point_from_short_side_units(point, canvas)),
        canvas,
    )
}

#[must_use]
pub fn scale_instruction(instruction: &Instruction, scale: f64) -> Instruction {
    if (scale - 1.0).abs() < 1.0e-12 {
        return instruction.clone();
    }
    let mut scaled = instruction.clone();
    let anchor = instruction_anchor(instruction);
    if let (Some(start), Some(end)) = (instruction.from_, instruction.to) {
        scaled.from_ = Some(Point::new(
            anchor.x + (start.x - anchor.x) * scale,
            anchor.y + (start.y - anchor.y) * scale,
        ));
        scaled.to = Some(Point::new(
            anchor.x + (end.x - anchor.x) * scale,
            anchor.y + (end.y - anchor.y) * scale,
        ));
    }
    scaled.radius = instruction.radius.map(|radius| radius * scale);
    scaled.size = instruction
        .size
        .map(|size| Point::new(size.x * scale, size.y * scale));
    scaled
}

#[must_use]
pub fn scale_instruction_on_canvas(
    instruction: &Instruction,
    scale: f64,
    canvas: Option<CanvasSize>,
) -> Instruction {
    let Some(canvas) = canvas else {
        return scale_instruction(instruction, scale);
    };
    if (scale - 1.0).abs() < 1.0e-12 {
        return instruction.clone();
    }
    let anchor = point_to_short_side_units(
        instruction_anchor_on_canvas(instruction, Some(canvas)),
        Some(canvas),
    );
    let mut scaled = instruction.clone();
    if let (Some(start), Some(end)) = (instruction.from_, instruction.to) {
        let start = point_to_short_side_units(start, Some(canvas));
        let end = point_to_short_side_units(end, Some(canvas));
        scaled.from_ = Some(point_from_short_side_units(
            Point::new(
                anchor.x + (start.x - anchor.x) * scale,
                anchor.y + (start.y - anchor.y) * scale,
            ),
            Some(canvas),
        ));
        scaled.to = Some(point_from_short_side_units(
            Point::new(
                anchor.x + (end.x - anchor.x) * scale,
                anchor.y + (end.y - anchor.y) * scale,
            ),
            Some(canvas),
        ));
    }
    scaled.radius = instruction.radius.map(|radius| radius * scale);
    scaled.size = instruction
        .size
        .map(|size| Point::new(size.x * scale, size.y * scale));
    if matches!(
        instruction.primitive,
        Primitive::Square | Primitive::Triangle
    ) && scaled.position.is_some()
        && scaled.size.is_some()
    {
        let normalized_size = size_in_normalized_axes(scaled.size.unwrap(), Some(canvas));
        let anchor = point_from_short_side_units(anchor, Some(canvas));
        scaled.position = Some(Point::new(
            anchor.x - normalized_size.x / 2.0,
            anchor.y - normalized_size.y / 2.0,
        ));
    }
    scaled
}
