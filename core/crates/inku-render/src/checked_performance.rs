//! Checked pre-draw execution for Connected while legacy relations keep their warnings.

use inku_score::{
    Canvas, ConnectedPositionAuthority, Instruction, Layout, Primitive, RelationType, Score,
    ScoreErrorPolicy, ScoreExecutionDiagnostic, ScoreExecutionDisposition, ScoreExecutionReason,
    ScoreExecutionSummary, canonical_score_digest,
};

use crate::performance::{
    PerformancePlan, PerformanceRequest, expand_composite_groups_with_indices, resolve_performance,
};
use crate::planning::{
    endpoint_geometry, ensure_line_coordinates, resolve_at_region, resolve_relation_on_canvas,
    translate_endpoint_instruction_on_canvas,
};

const GEOMETRY_EPSILON: f64 = 1.0e-9;

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

/// Resolve Connected before SVG construction while retaining original Score indices.
pub fn resolve_checked_performance(
    request: PerformanceRequest<'_>,
    policy: ScoreErrorPolicy,
) -> Result<PerformancePlan, CheckedPerformanceError> {
    let has_connected = request.score.instructions.iter().any(|instruction| {
        instruction
            .relation
            .as_ref()
            .is_some_and(|relation| relation.kind == RelationType::Connected)
    });
    if !has_connected {
        return Ok(resolve_performance(request));
    }

    let seed = request.performance_seed;
    let relation_seed = seed.unwrap_or_default();
    let placement_seed = request.composition_seed.or(request.performance_seed);
    let (expanded, original_instruction_indices) = expand_composite_groups_with_indices(
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
    let mut warnings = Vec::new();
    let mut diagnostics = Vec::new();

    for (performance_index, (original_index, original)) in original_instruction_indices
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
        if connected {
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
        instruction_indices.push(original_index);
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
        rendered_instruction_indices: instruction_indices.clone(),
    });
    Ok(PerformancePlan {
        score,
        warnings,
        instruction_indices,
        execution,
    })
}
