//! Checked pre-draw endpoint relations while legacy relations keep their warnings.

use inku_score::{
    Canvas, ConnectedPositionAuthority, Instruction, Layout, Primitive, RelationGap, RelationType,
    Score, ScoreErrorPolicy, ScoreExecutionDiagnostic, ScoreExecutionDisposition,
    ScoreExecutionReason, ScoreExecutionSummary, canonical_score_digest,
};

use crate::performance::{
    PerformancePlan, PerformanceRequest, expand_composite_groups_with_indices, resolve_performance,
};
use crate::planning::{
    endpoint_geometry, ensure_line_coordinates, instruction_anchor_on_canvas,
    performed_arc_sagitta, performed_instruction_bounds_on_canvas, resolve_at_region,
    resolve_relation_on_canvas, touching_candidate, translate_endpoint_instruction_on_canvas,
};

const GEOMETRY_EPSILON: f64 = 1.0e-9;

fn checked_touching_candidate(
    instruction: &Instruction,
    prior: &Instruction,
    canvas: Option<crate::types::CanvasSize>,
) -> Result<Instruction, ScoreExecutionReason> {
    let relation = instruction.relation.as_ref().expect("checked Touching");
    let facts = relation
        .touching_constraints
        .ok_or(ScoreExecutionReason::MissingTouchingConstraints)?;
    let authority = relation
        .position_authority
        .ok_or(ScoreExecutionReason::MissingTouchingPositionAuthority)?;
    let candidate = touching_candidate(instruction, prior, canvas)
        .map_err(|_| ScoreExecutionReason::UnsupportedTouchingPrimitive)?;
    let endpoints = |value: &Instruction| {
        endpoint_geometry(value, canvas).ok_or(ScoreExecutionReason::UnsupportedTouchingPrimitive)
    };
    let (start, end, _, _) = endpoints(instruction)?;
    let (candidate_start, candidate_end, _, _) = endpoints(&candidate)?;
    let direction = |a: crate::types::Point, b: crate::types::Point| {
        let length = (b.x - a.x).hypot(b.y - a.y);
        (length, (b.x - a.x) / length, (b.y - a.y) / length)
    };
    let (length, dx, dy) = direction(start, end);
    let (candidate_length, candidate_dx, candidate_dy) = direction(candidate_start, candidate_end);
    if !length.is_finite()
        || !candidate_length.is_finite()
        || length <= GEOMETRY_EPSILON
        || candidate_length <= GEOMETRY_EPSILON
    {
        return Err(ScoreExecutionReason::UnsupportedTouchingPrimitive);
    }
    if facts.dimensions_fixed {
        let sagitta_matches = instruction.primitive != Primitive::Arc
            || performed_arc_sagitta(instruction, canvas)
                .zip(performed_arc_sagitta(&candidate, canvas))
                .is_some_and(|(before, after)| {
                    (before.abs() - after.abs()).abs() <= GEOMETRY_EPSILON
                });
        if (length - candidate_length).abs() > GEOMETRY_EPSILON || !sagitta_matches {
            return Err(ScoreExecutionReason::TouchingGeometryConflict);
        }
    }
    if facts.direction_fixed && (dx - candidate_dx).hypot(dy - candidate_dy) > GEOMETRY_EPSILON {
        return Err(ScoreExecutionReason::TouchingDirectionConflict);
    }
    if authority == ConnectedPositionAuthority::NumericFixed {
        let anchor = crate::geometry::point_to_short_side_units(
            instruction_anchor_on_canvas(instruction, canvas),
            canvas,
        );
        let candidate_anchor = crate::geometry::point_to_short_side_units(
            instruction_anchor_on_canvas(&candidate, canvas),
            canvas,
        );
        if (anchor.x - candidate_anchor.x).hypot(anchor.y - candidate_anchor.y) > GEOMETRY_EPSILON {
            return Err(ScoreExecutionReason::NumericTouchingPositionConflict);
        }
        let bounds = performed_instruction_bounds_on_canvas(&candidate, None, 0, canvas)
            .ok_or(ScoreExecutionReason::UnsupportedTouchingPrimitive)?;
        let extent = crate::geometry::short_side_scales(canvas);
        if bounds.min.x < -GEOMETRY_EPSILON
            || bounds.min.y < -GEOMETRY_EPSILON
            || bounds.max.x > extent.x + GEOMETRY_EPSILON
            || bounds.max.y > extent.y + GEOMETRY_EPSILON
        {
            return Err(ScoreExecutionReason::NumericTouchingBoundsConflict);
        }
    }
    Ok(candidate)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CheckedPerformanceError {
    pub diagnostics: Vec<ScoreExecutionDiagnostic>,
}

fn supports_connected(instruction: &Instruction) -> bool {
    matches!(
        instruction.primitive,
        Primitive::Line | Primitive::Arc | Primitive::Point
    )
}

fn is_checked_touching(relation: &inku_score::Relation) -> bool {
    relation.kind == RelationType::Touching
        && (relation.touching_constraints.is_some()
            || relation.target_instruction_index.is_some()
            || relation.position_authority.is_some())
}

fn is_checked_line_relation(relation: &inku_score::Relation, kind: RelationType) -> bool {
    relation.kind == kind
        && (relation.target_instruction_index.is_some() || relation.position_authority.is_some())
}

fn without_performed_relation(instruction: &Instruction) -> Instruction {
    let mut resolved = instruction.clone();
    resolved.at = None;
    resolved.relation = None;
    resolved
}

fn line_with_center_and_direction(
    instruction: &Instruction,
    center: crate::types::Point,
    direction: crate::types::Point,
    canvas: Option<crate::types::CanvasSize>,
) -> Option<Instruction> {
    let (start, end, _, _) = endpoint_geometry(instruction, canvas)?;
    let length = (end.x - start.x).hypot(end.y - start.y);
    let direction_length = direction.x.hypot(direction.y);
    if !length.is_finite()
        || !direction_length.is_finite()
        || length <= GEOMETRY_EPSILON
        || direction_length <= GEOMETRY_EPSILON
        || instruction.rotation.is_some()
    {
        return None;
    }
    let unit = crate::types::Point::new(
        direction.x / direction_length,
        direction.y / direction_length,
    );
    let half = length / 2.0;
    let mut resolved = without_performed_relation(instruction);
    resolved.from_ = Some(crate::geometry::point_from_short_side_units(
        crate::types::Point::new(center.x - unit.x * half, center.y - unit.y * half),
        canvas,
    ));
    resolved.to = Some(crate::geometry::point_from_short_side_units(
        crate::types::Point::new(center.x + unit.x * half, center.y + unit.y * half),
        canvas,
    ));
    Some(resolved)
}

fn closest_point_on_segment(
    point: crate::types::Point,
    start: crate::types::Point,
    end: crate::types::Point,
) -> crate::types::Point {
    let delta = crate::types::Point::new(end.x - start.x, end.y - start.y);
    let squared = delta.x * delta.x + delta.y * delta.y;
    if squared <= GEOMETRY_EPSILON {
        return start;
    }
    let factor =
        (((point.x - start.x) * delta.x + (point.y - start.y) * delta.y) / squared).clamp(0.0, 1.0);
    crate::types::Point::new(start.x + delta.x * factor, start.y + delta.y * factor)
}

fn closest_interior_point_on_segment(
    point: crate::types::Point,
    start: crate::types::Point,
    end: crate::types::Point,
) -> crate::types::Point {
    let delta = crate::types::Point::new(end.x - start.x, end.y - start.y);
    let squared = delta.x * delta.x + delta.y * delta.y;
    if squared <= GEOMETRY_EPSILON {
        return start;
    }
    let factor = (((point.x - start.x) * delta.x + (point.y - start.y) * delta.y) / squared)
        .clamp(1.0e-6, 1.0 - 1.0e-6);
    crate::types::Point::new(start.x + delta.x * factor, start.y + delta.y * factor)
}

fn cross(
    origin: crate::types::Point,
    first: crate::types::Point,
    second: crate::types::Point,
) -> f64 {
    (first.x - origin.x) * (second.y - origin.y) - (first.y - origin.y) * (second.x - origin.x)
}

fn segments_properly_cross(
    first_start: crate::types::Point,
    first_end: crate::types::Point,
    second_start: crate::types::Point,
    second_end: crate::types::Point,
) -> bool {
    let first_left = cross(first_start, first_end, second_start);
    let first_right = cross(first_start, first_end, second_end);
    let second_left = cross(second_start, second_end, first_start);
    let second_right = cross(second_start, second_end, first_end);
    (first_left > GEOMETRY_EPSILON && first_right < -GEOMETRY_EPSILON
        || first_left < -GEOMETRY_EPSILON && first_right > GEOMETRY_EPSILON)
        && (second_left > GEOMETRY_EPSILON && second_right < -GEOMETRY_EPSILON
            || second_left < -GEOMETRY_EPSILON && second_right > GEOMETRY_EPSILON)
}

fn candidate_properly_cuts(
    candidate: &Instruction,
    prior_start: crate::types::Point,
    prior_end: crate::types::Point,
    canvas: Option<crate::types::CanvasSize>,
) -> bool {
    endpoint_geometry(candidate, canvas).is_some_and(|(start, end, _, _)| {
        segments_properly_cross(start, end, prior_start, prior_end)
    })
}

fn along_band_contains(
    point: crate::types::Point,
    prior_start: crate::types::Point,
    prior_end: crate::types::Point,
    gap: RelationGap,
) -> bool {
    let (lower, upper) = match gap {
        RelationGap::Narrow => (0.02, 0.05),
        RelationGap::Medium => (0.06, 0.12),
        RelationGap::Wide => (0.15, 0.30),
    };
    let nearest = closest_point_on_segment(point, prior_start, prior_end);
    let distance = (point.x - nearest.x).hypot(point.y - nearest.y);
    distance + GEOMETRY_EPSILON >= lower && distance <= upper + GEOMETRY_EPSILON
}

fn relation_gap_amount(gap: RelationGap, seed: crate::types::Seed, index: usize) -> f64 {
    let (lower, upper) = match gap {
        RelationGap::Narrow => (0.02, 0.05),
        RelationGap::Medium => (0.06, 0.12),
        RelationGap::Wide => (0.15, 0.30),
    };
    lower + (upper - lower) * crate::determinism::hash01(index as i64, seed, "relation-gap")
}

fn clamp_short_side_point(
    point: crate::types::Point,
    canvas: Option<crate::types::CanvasSize>,
) -> crate::types::Point {
    let extent = crate::geometry::short_side_scales(canvas);
    crate::types::Point::new(point.x.clamp(0.0, extent.x), point.y.clamp(0.0, extent.y))
}

fn fits_canvas_bounds(instruction: &Instruction, canvas: Option<crate::types::CanvasSize>) -> bool {
    let Some(bounds) = performed_instruction_bounds_on_canvas(instruction, None, 0, canvas) else {
        return false;
    };
    let extent = crate::geometry::short_side_scales(canvas);
    bounds.min.x >= -GEOMETRY_EPSILON
        && bounds.min.y >= -GEOMETRY_EPSILON
        && bounds.max.x <= extent.x + GEOMETRY_EPSILON
        && bounds.max.y <= extent.y + GEOMETRY_EPSILON
}

fn typed_along_target(
    prior_start: crate::types::Point,
    prior_end: crate::types::Point,
    gap: RelationGap,
    seed: crate::types::Seed,
    index: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Option<crate::types::Point> {
    let delta = crate::types::Point::new(prior_end.x - prior_start.x, prior_end.y - prior_start.y);
    let length = delta.x.hypot(delta.y);
    if !length.is_finite() || length <= GEOMETRY_EPSILON {
        return None;
    }
    let factor = 0.18 + 0.64 * crate::determinism::hash01(index as i64, seed, "along-t");
    let point = crate::types::Point::new(
        prior_start.x + delta.x * factor,
        prior_start.y + delta.y * factor,
    );
    let amount = relation_gap_amount(gap, seed, index);
    let side = if crate::determinism::hash01(index as i64, seed, "along-side") < 0.5 {
        -1.0
    } else {
        1.0
    };
    Some(clamp_short_side_point(
        crate::types::Point::new(
            point.x - delta.y / length * amount * side,
            point.y + delta.x / length * amount * side,
        ),
        canvas,
    ))
}

fn checked_along_candidate(
    instruction: &Instruction,
    prior: &Instruction,
    relation: &inku_score::Relation,
    seed: crate::types::Seed,
    index: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Result<Instruction, ScoreExecutionReason> {
    let authority = relation
        .position_authority
        .ok_or(ScoreExecutionReason::MissingAlongPositionAuthority)?;
    let (prior_start, prior_end, _, _) =
        endpoint_geometry(prior, canvas).ok_or(ScoreExecutionReason::UnsupportedAlongPrimitive)?;
    let (start, end, _, _) = endpoint_geometry(instruction, canvas)
        .ok_or(ScoreExecutionReason::UnsupportedAlongPrimitive)?;
    let center = crate::types::Point::new((start.x + end.x) / 2.0, (start.y + end.y) / 2.0);
    if authority == ConnectedPositionAuthority::NumericFixed
        && !along_band_contains(center, prior_start, prior_end, relation.gap)
    {
        return Err(ScoreExecutionReason::NumericAlongPositionConflict);
    }
    let candidate = if authority == ConnectedPositionAuthority::NamedMovable {
        let target = typed_along_target(prior_start, prior_end, relation.gap, seed, index, canvas)
            .ok_or(ScoreExecutionReason::UnsupportedAlongPrimitive)?;
        translate_endpoint_instruction_on_canvas(
            instruction,
            crate::types::Point::new(target.x - center.x, target.y - center.y),
            canvas,
        )
        .ok_or(ScoreExecutionReason::UnsupportedAlongPrimitive)?
    } else {
        without_performed_relation(instruction)
    };
    let candidate = if instruction.rotation.is_some() {
        candidate
    } else {
        let (candidate_start, candidate_end, _, _) = endpoint_geometry(&candidate, canvas)
            .ok_or(ScoreExecutionReason::UnsupportedAlongPrimitive)?;
        let candidate_center = crate::types::Point::new(
            (candidate_start.x + candidate_end.x) / 2.0,
            (candidate_start.y + candidate_end.y) / 2.0,
        );
        line_with_center_and_direction(
            &candidate,
            candidate_center,
            crate::types::Point::new(prior_end.x - prior_start.x, prior_end.y - prior_start.y),
            canvas,
        )
        .ok_or(ScoreExecutionReason::UnsupportedAlongPrimitive)?
    };
    if authority == ConnectedPositionAuthority::NumericFixed
        && !fits_canvas_bounds(&candidate, canvas)
    {
        return Err(ScoreExecutionReason::NumericAlongPositionConflict);
    }
    Ok(candidate)
}

fn checked_cutting_candidate(
    instruction: &Instruction,
    prior: &Instruction,
    relation: &inku_score::Relation,
    seed: crate::types::Seed,
    index: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Result<Instruction, ScoreExecutionReason> {
    let authority = relation
        .position_authority
        .ok_or(ScoreExecutionReason::MissingCuttingPositionAuthority)?;
    let (prior_start, prior_end, _, _) = endpoint_geometry(prior, canvas)
        .ok_or(ScoreExecutionReason::UnsupportedCuttingPrimitive)?;
    let (start, end, _, _) = endpoint_geometry(instruction, canvas)
        .ok_or(ScoreExecutionReason::UnsupportedCuttingPrimitive)?;
    let center = crate::types::Point::new((start.x + end.x) / 2.0, (start.y + end.y) / 2.0);
    let length = (end.x - start.x).hypot(end.y - start.y);
    if !length.is_finite() || length <= GEOMETRY_EPSILON {
        return Err(ScoreExecutionReason::UnsupportedCuttingPrimitive);
    }
    if authority == ConnectedPositionAuthority::NumericFixed {
        if instruction.rotation.is_some() {
            if !segments_properly_cross(start, end, prior_start, prior_end) {
                return Err(ScoreExecutionReason::CuttingDirectionConflict);
            }
            let candidate = without_performed_relation(instruction);
            return fits_canvas_bounds(&candidate, canvas)
                .then_some(candidate)
                .ok_or(ScoreExecutionReason::NumericCuttingPositionConflict);
        }
        let target = closest_interior_point_on_segment(center, prior_start, prior_end);
        let direction = crate::types::Point::new(target.x - center.x, target.y - center.y);
        if direction.x.hypot(direction.y) > length / 2.0 + GEOMETRY_EPSILON {
            return Err(ScoreExecutionReason::NumericCuttingPositionConflict);
        }
        let direction = if direction.x.hypot(direction.y) <= GEOMETRY_EPSILON {
            crate::types::Point::new(-(prior_end.y - prior_start.y), prior_end.x - prior_start.x)
        } else {
            direction
        };
        let candidate = line_with_center_and_direction(instruction, center, direction, canvas)
            .ok_or(ScoreExecutionReason::UnsupportedCuttingPrimitive)?;
        if !fits_canvas_bounds(&candidate, canvas) {
            return Err(ScoreExecutionReason::NumericCuttingPositionConflict);
        }
        return candidate_properly_cuts(&candidate, prior_start, prior_end, canvas)
            .then_some(candidate)
            .ok_or(ScoreExecutionReason::CuttingDirectionConflict);
    }
    let factor = 0.18 + 0.64 * crate::determinism::hash01(index as i64, seed, "cutting-t");
    let target = crate::types::Point::new(
        prior_start.x + (prior_end.x - prior_start.x) * factor,
        prior_start.y + (prior_end.y - prior_start.y) * factor,
    );
    if instruction.rotation.is_some() {
        let candidate = translate_endpoint_instruction_on_canvas(
            instruction,
            crate::types::Point::new(target.x - center.x, target.y - center.y),
            canvas,
        )
        .ok_or(ScoreExecutionReason::UnsupportedCuttingPrimitive)?;
        let (candidate_start, candidate_end, _, _) = endpoint_geometry(&candidate, canvas)
            .ok_or(ScoreExecutionReason::UnsupportedCuttingPrimitive)?;
        return segments_properly_cross(candidate_start, candidate_end, prior_start, prior_end)
            .then_some(candidate)
            .ok_or(ScoreExecutionReason::CuttingDirectionConflict);
    }
    let angle = std::f64::consts::TAU * crate::determinism::hash01(index as i64, seed, "cut-angle");
    let candidate = line_with_center_and_direction(
        instruction,
        target,
        crate::types::Point::new(angle.cos(), angle.sin()),
        canvas,
    )
    .ok_or(ScoreExecutionReason::UnsupportedCuttingPrimitive)?;
    candidate_properly_cuts(&candidate, prior_start, prior_end, canvas)
        .then_some(candidate)
        .ok_or(ScoreExecutionReason::CuttingDirectionConflict)
}

fn connected_failure(
    index: usize,
    dependency: Option<usize>,
    reason: ScoreExecutionReason,
    policy: ScoreErrorPolicy,
) -> ScoreExecutionDiagnostic {
    ScoreExecutionDiagnostic {
        instruction_index: index,
        dependency_instruction_index: dependency,
        reason,
        disposition: if policy == ScoreErrorPolicy::OmitAndContinue {
            ScoreExecutionDisposition::Omitted
        } else {
            ScoreExecutionDisposition::Stopped
        },
    }
}

fn structural_instruction_indices(score: &Score) -> Vec<bool> {
    let mut structural = vec![false; score.instructions.len()];
    let mut index = 0;
    while index < score.instructions.len() {
        let instruction = &score.instructions[index];
        let Some(arrangement) = instruction.arrangement.as_ref() else {
            index += 1;
            continue;
        };
        let group_size = arrangement.group_size as usize;
        if group_size > 1 {
            let end = (index + group_size).min(score.instructions.len());
            structural[index..end].fill(true);
            index = end;
        } else {
            structural[index] = arrangement.layout == Layout::Grid;
            index += 1;
        }
    }
    structural
}

/// Resolve checked endpoint relations before SVG construction with original Score indices.
pub fn resolve_checked_performance(
    request: PerformanceRequest<'_>,
    policy: ScoreErrorPolicy,
) -> Result<PerformancePlan, CheckedPerformanceError> {
    let has_checked_relation = request.score.instructions.iter().any(|instruction| {
        instruction.relation.as_ref().is_some_and(|relation| {
            relation.kind == RelationType::Connected
                || is_checked_touching(relation)
                || is_checked_line_relation(relation, RelationType::Along)
                || is_checked_line_relation(relation, RelationType::Cutting)
        })
    });
    if !has_checked_relation {
        return Ok(resolve_performance(request));
    }

    let seed = request.performance_seed;
    let relation_seed = seed.unwrap_or_default();
    let placement_seed = request.composition_seed.or(request.performance_seed);
    let (expanded, expanded_original_instruction_indices) = expand_composite_groups_with_indices(
        request.score,
        placement_seed,
        request.performance_seed,
        request.canvas,
    );
    let structural = structural_instruction_indices(request.score);
    let mut structural_diagnosed = vec![false; request.score.instructions.len()];
    let mut omitted_original = vec![false; request.score.instructions.len()];
    let mut by_original_index: Vec<Option<Instruction>> =
        vec![None; request.score.instructions.len()];
    let mut resolved = Vec::with_capacity(expanded.instructions.len());
    let mut instruction_indices = Vec::with_capacity(expanded.instructions.len());
    let mut original_instruction_indices = Vec::with_capacity(expanded.instructions.len());
    let mut warnings = Vec::new();
    let mut diagnostics = Vec::new();

    for (performance_index, (original_index, original)) in expanded_original_instruction_indices
        .iter()
        .copied()
        .zip(&expanded.instructions)
        .enumerate()
    {
        let mut instruction = ensure_line_coordinates(original);
        if let Some(seed) = seed {
            instruction = resolve_at_region(&instruction, seed, performance_index, request.canvas);
        }
        let connected = instruction
            .relation
            .as_ref()
            .is_some_and(|relation| relation.kind == RelationType::Connected);
        let touching = instruction
            .relation
            .as_ref()
            .is_some_and(is_checked_touching);
        let along = instruction
            .relation
            .as_ref()
            .is_some_and(|relation| is_checked_line_relation(relation, RelationType::Along));
        let cutting = instruction
            .relation
            .as_ref()
            .is_some_and(|relation| is_checked_line_relation(relation, RelationType::Cutting));
        if touching {
            let relation = instruction.relation.as_ref().expect("checked above");
            let dependency = relation.target_instruction_index;
            let candidate = if structural[original_index]
                || dependency.is_some_and(|index| structural.get(index).copied().unwrap_or(false))
            {
                Err(ScoreExecutionReason::UnsupportedTouchingStructure)
            } else if dependency != original_index.checked_sub(1) || dependency.is_none() {
                Err(ScoreExecutionReason::MissingTouchingReference)
            } else if let Some(prior) = dependency
                .and_then(|index| by_original_index.get(index))
                .and_then(Option::as_ref)
            {
                checked_touching_candidate(&instruction, prior, request.canvas)
            } else {
                Err(ScoreExecutionReason::TouchingReferenceOmitted)
            };
            match candidate {
                Ok(candidate) => instruction = candidate,
                Err(reason) => {
                    if !structural[original_index] || !structural_diagnosed[original_index] {
                        diagnostics.push(connected_failure(
                            original_index,
                            dependency,
                            reason,
                            policy,
                        ));
                        structural_diagnosed[original_index] = true;
                    }
                    if policy == ScoreErrorPolicy::Stop {
                        return Err(CheckedPerformanceError { diagnostics });
                    }
                    omitted_original[original_index] = true;
                    by_original_index[original_index] = None;
                    continue;
                }
            }
        } else if along || cutting {
            let relation = instruction.relation.as_ref().expect("checked above");
            let dependency = relation.target_instruction_index;
            let (
                missing_reference,
                omitted_reference,
                unsupported_primitive,
                unsupported_structure,
                missing_authority,
            ) = if along {
                (
                    ScoreExecutionReason::MissingAlongReference,
                    ScoreExecutionReason::AlongReferenceOmitted,
                    ScoreExecutionReason::UnsupportedAlongPrimitive,
                    ScoreExecutionReason::UnsupportedAlongStructure,
                    ScoreExecutionReason::MissingAlongPositionAuthority,
                )
            } else {
                (
                    ScoreExecutionReason::MissingCuttingReference,
                    ScoreExecutionReason::CuttingReferenceOmitted,
                    ScoreExecutionReason::UnsupportedCuttingPrimitive,
                    ScoreExecutionReason::UnsupportedCuttingStructure,
                    ScoreExecutionReason::MissingCuttingPositionAuthority,
                )
            };
            let reason = if structural[original_index]
                || dependency
                    .is_some_and(|dependency| structural.get(dependency).copied().unwrap_or(false))
            {
                Some(unsupported_structure)
            } else if dependency != original_index.checked_sub(1) {
                Some(missing_reference)
            } else if dependency
                .and_then(|dependency| by_original_index.get(dependency))
                .and_then(Option::as_ref)
                .is_none()
            {
                Some(omitted_reference)
            } else if relation.position_authority.is_none() {
                Some(missing_authority)
            } else {
                None
            };
            if let Some(reason) = reason {
                if !structural[original_index] || !structural_diagnosed[original_index] {
                    diagnostics.push(connected_failure(
                        original_index,
                        dependency,
                        reason,
                        policy,
                    ));
                    structural_diagnosed[original_index] = true;
                }
                if policy == ScoreErrorPolicy::Stop {
                    return Err(CheckedPerformanceError { diagnostics });
                }
                omitted_original[original_index] = true;
                by_original_index[original_index] = None;
                continue;
            }
            let dependency = dependency.expect("validated previous dependency");
            let prior = by_original_index[dependency]
                .as_ref()
                .expect("validated surviving dependency");
            if instruction.primitive != Primitive::Line || prior.primitive != Primitive::Line {
                diagnostics.push(connected_failure(
                    original_index,
                    Some(dependency),
                    unsupported_primitive,
                    policy,
                ));
                if policy == ScoreErrorPolicy::Stop {
                    return Err(CheckedPerformanceError { diagnostics });
                }
                omitted_original[original_index] = true;
                by_original_index[original_index] = None;
                continue;
            }
            let candidate = if along {
                checked_along_candidate(
                    &instruction,
                    prior,
                    relation,
                    relation_seed,
                    performance_index,
                    request.canvas,
                )
            } else {
                checked_cutting_candidate(
                    &instruction,
                    prior,
                    relation,
                    relation_seed,
                    performance_index,
                    request.canvas,
                )
            };
            match candidate {
                Ok(candidate) => instruction = candidate,
                Err(reason) => {
                    diagnostics.push(connected_failure(
                        original_index,
                        Some(dependency),
                        reason,
                        policy,
                    ));
                    if policy == ScoreErrorPolicy::Stop {
                        return Err(CheckedPerformanceError { diagnostics });
                    }
                    omitted_original[original_index] = true;
                    by_original_index[original_index] = None;
                    continue;
                }
            }
        } else if connected {
            let relation = instruction.relation.as_ref().expect("checked above");
            let dependency = relation.target_instruction_index;
            let reason = if structural[original_index]
                || dependency
                    .is_some_and(|dependency| structural.get(dependency).copied().unwrap_or(false))
                || !supports_connected(&instruction)
            {
                Some(ScoreExecutionReason::UnsupportedConnectedStructure)
            } else if dependency != original_index.checked_sub(1) {
                Some(ScoreExecutionReason::MissingConnectedReference)
            } else if dependency
                .and_then(|dependency| by_original_index.get(dependency))
                .and_then(Option::as_ref)
                .is_none()
            {
                Some(ScoreExecutionReason::ConnectedReferenceOmitted)
            } else if relation.position_authority.is_none() {
                Some(ScoreExecutionReason::MissingConnectedPositionAuthority)
            } else {
                None
            };
            if let Some(reason) = reason {
                if !structural[original_index] || !structural_diagnosed[original_index] {
                    diagnostics.push(connected_failure(
                        original_index,
                        dependency,
                        reason,
                        policy,
                    ));
                    structural_diagnosed[original_index] = true;
                }
                if policy == ScoreErrorPolicy::Stop {
                    return Err(CheckedPerformanceError { diagnostics });
                }
                omitted_original[original_index] = true;
                by_original_index[original_index] = None;
                continue;
            }

            let dependency = dependency.expect("validated previous dependency");
            let prior = by_original_index[dependency]
                .as_ref()
                .expect("validated surviving dependency");
            if !supports_connected(prior) {
                diagnostics.push(connected_failure(
                    original_index,
                    Some(dependency),
                    ScoreExecutionReason::UnsupportedConnectedPrimitive,
                    policy,
                ));
                if policy == ScoreErrorPolicy::Stop {
                    return Err(CheckedPerformanceError { diagnostics });
                }
                omitted_original[original_index] = true;
                by_original_index[original_index] = None;
                continue;
            }
            let geometry = endpoint_geometry(prior, request.canvas)
                .zip(endpoint_geometry(&instruction, request.canvas));
            let Some((prior_geometry, current_geometry)) = geometry else {
                diagnostics.push(connected_failure(
                    original_index,
                    Some(dependency),
                    ScoreExecutionReason::UnsupportedConnectedPrimitive,
                    policy,
                ));
                if policy == ScoreErrorPolicy::Stop {
                    return Err(CheckedPerformanceError { diagnostics });
                }
                omitted_original[original_index] = true;
                by_original_index[original_index] = None;
                continue;
            };
            let delta = crate::types::Point::new(
                prior_geometry.1.x - current_geometry.0.x,
                prior_geometry.1.y - current_geometry.0.y,
            );
            if relation.position_authority == Some(ConnectedPositionAuthority::NumericFixed)
                && delta.x.hypot(delta.y) > GEOMETRY_EPSILON
            {
                diagnostics.push(connected_failure(
                    original_index,
                    Some(dependency),
                    ScoreExecutionReason::NumericConnectedPositionConflict,
                    policy,
                ));
                if policy == ScoreErrorPolicy::Stop {
                    return Err(CheckedPerformanceError { diagnostics });
                }
                omitted_original[original_index] = true;
                by_original_index[original_index] = None;
                continue;
            }
            instruction = translate_endpoint_instruction_on_canvas(
                &instruction,
                if relation.position_authority == Some(ConnectedPositionAuthority::NumericFixed) {
                    crate::types::Point::new(0.0, 0.0)
                } else {
                    delta
                },
                request.canvas,
            )
            .expect("validated endpoint family");
        } else if seed.is_some() {
            let dependency_was_omitted = instruction.relation.as_ref().is_some_and(|relation| {
                let dependency_count = usize::from(relation.kind == RelationType::Between) + 1;
                original_index >= dependency_count
                    && omitted_original[original_index - dependency_count..original_index]
                        .iter()
                        .any(|omitted| *omitted)
            });
            if dependency_was_omitted {
                diagnostics.push(connected_failure(
                    original_index,
                    original_index.checked_sub(1),
                    ScoreExecutionReason::ConnectedReferenceOmitted,
                    policy,
                ));
                if policy == ScoreErrorPolicy::Stop {
                    return Err(CheckedPerformanceError { diagnostics });
                }
                omitted_original[original_index] = true;
                by_original_index[original_index] = None;
                continue;
            }
            let relation = resolve_relation_on_canvas(
                &instruction,
                &resolved,
                relation_seed,
                performance_index,
                request.canvas,
            );
            instruction = relation.instruction;
            if let Some(warning) = relation.warning {
                warnings.push(warning);
            }
        }
        by_original_index[original_index] = Some(instruction.clone());
        instruction_indices.push(performance_index);
        original_instruction_indices.push(original_index);
        resolved.push(instruction);
    }

    let has_drawable_content = !resolved.is_empty()
        || matches!(&request.score.canvas, Canvas::Spec(spec) if spec.ground.is_some());
    if !has_drawable_content {
        diagnostics.push(ScoreExecutionDiagnostic {
            instruction_index: request.score.instructions.len().saturating_sub(1),
            dependency_instruction_index: None,
            reason: ScoreExecutionReason::NoDrawableInstructions,
            disposition: ScoreExecutionDisposition::Stopped,
        });
        return Err(CheckedPerformanceError { diagnostics });
    }

    let mut score: Score = request.score.clone();
    score.instructions = resolved;
    let execution = (!diagnostics.is_empty()).then(|| ScoreExecutionSummary {
        input_score_digest: canonical_score_digest(request.score)
            .expect("typed Score canonicalization is infallible"),
        diagnostics,
        rendered_instruction_indices: original_instruction_indices.clone(),
    });
    Ok(PerformancePlan {
        score,
        warnings,
        instruction_indices,
        original_instruction_indices,
        execution,
    })
}
