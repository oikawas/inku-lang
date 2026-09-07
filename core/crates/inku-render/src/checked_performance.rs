//! Checked pre-draw endpoint relations while legacy relations keep their warnings.

use inku_score::{
    Canvas, ConnectedPositionAuthority, Instruction, Layout, Primitive, RelationType, Score,
    ScoreErrorPolicy, ScoreExecutionDiagnostic, ScoreExecutionDisposition, ScoreExecutionReason,
    ScoreExecutionSummary, canonical_score_digest,
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
    let has_connected = request.score.instructions.iter().any(|instruction| {
        instruction.relation.as_ref().is_some_and(|relation| {
            relation.kind == RelationType::Connected || is_checked_touching(relation)
        })
    });
    if !has_connected {
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
