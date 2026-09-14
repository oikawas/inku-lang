//! Checked pre-draw endpoint relations while legacy relations keep their warnings.

use inku_score::{
    Canvas, ConnectedPositionAuthority, Instruction, Layout, Primitive, RelationGap, RelationType,
    Score, ScoreErrorPolicy, ScoreExecutionDiagnostic, ScoreExecutionDisposition,
    ScoreExecutionReason, ScoreExecutionSummary, TransformGroup, canonical_score_digest,
};

use crate::affine::AffineTransform;
use crate::performance::{
    PerformancePlan, PerformanceRequest, expand_composite_groups_with_indices, resolve_performance,
};
use crate::planning::{
    endpoint_geometry, ensure_line_coordinates, instruction_anchor_on_canvas,
    performed_arc_sagitta, performed_instruction_bounds_on_canvas, resolve_at_region,
    resolve_relation_on_canvas, touching_candidate_with_transform,
    translate_endpoint_instruction_on_canvas,
};

#[path = "anchor_execution.rs"]
pub(crate) mod anchor_execution;

const GEOMETRY_EPSILON: f64 = 1.0e-9;

fn checked_touching_candidate(
    instruction: &Instruction,
    prior: &Instruction,
    canvas: Option<crate::types::CanvasSize>,
    prior_transform: AffineTransform,
) -> Result<Instruction, ScoreExecutionReason> {
    let relation = instruction.relation.as_ref().expect("checked Touching");
    let facts = relation
        .touching_constraints
        .ok_or(ScoreExecutionReason::MissingTouchingConstraints)?;
    let authority = relation
        .position_authority
        .ok_or(ScoreExecutionReason::MissingTouchingPositionAuthority)?;
    let candidate = touching_candidate_with_transform(instruction, prior, canvas, prior_transform)
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

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CheckedPerformanceWithResourcesError {
    Resources(inku_score::SavedScoreResourceError),
    Performance(CheckedPerformanceError),
}

impl From<inku_score::SavedScoreResourceError> for CheckedPerformanceWithResourcesError {
    fn from(value: inku_score::SavedScoreResourceError) -> Self {
        Self::Resources(value)
    }
}

impl From<CheckedPerformanceError> for CheckedPerformanceWithResourcesError {
    fn from(value: CheckedPerformanceError) -> Self {
        Self::Performance(value)
    }
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

fn is_bounds_relation(relation: &inku_score::Relation) -> bool {
    matches!(
        relation.kind,
        RelationType::NotTouching | RelationType::Between
    )
}

fn is_checked_bounds_relation(relation: &inku_score::Relation) -> bool {
    is_bounds_relation(relation)
        && (relation.target_instruction_index.is_some()
            || relation.target_anchor_index.is_some()
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
    prior_transform: AffineTransform,
) -> Result<Instruction, ScoreExecutionReason> {
    let authority = relation
        .position_authority
        .ok_or(ScoreExecutionReason::MissingAlongPositionAuthority)?;
    let (prior_start, prior_end, _, _) =
        crate::affine_geometry::endpoints(prior, canvas, prior_transform)
            .ok_or(ScoreExecutionReason::UnsupportedAlongPrimitive)?;
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
    prior_transform: AffineTransform,
) -> Result<Instruction, ScoreExecutionReason> {
    let authority = relation
        .position_authority
        .ok_or(ScoreExecutionReason::MissingCuttingPositionAuthority)?;
    let (prior_start, prior_end, _, _) =
        crate::affine_geometry::endpoints(prior, canvas, prior_transform)
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
        anchor_index: None,
        dependency_instruction_index: dependency,
        reason,
        disposition: if policy == ScoreErrorPolicy::OmitAndContinue {
            ScoreExecutionDisposition::Omitted
        } else {
            ScoreExecutionDisposition::Stopped
        },
    }
}

fn relation_failure(
    score: &Score,
    index: usize,
    reason: ScoreExecutionReason,
) -> ScoreExecutionDiagnostic {
    ScoreExecutionDiagnostic {
        instruction_index: index,
        anchor_index: None,
        dependency_instruction_index: score.instructions[index]
            .relation
            .as_ref()
            .and_then(|relation| relation.target_instruction_index),
        reason,
        disposition: ScoreExecutionDisposition::RelationOmitted,
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

fn enclosing_external_group(
    groups: &[TransformGroup],
    source: usize,
    dependency: usize,
) -> Option<usize> {
    groups
        .iter()
        .enumerate()
        .filter(|(_, group)| {
            group.start <= source
                && source < group.end
                && !(group.start <= dependency && dependency < group.end)
        })
        .min_by(|(left_index, left), (right_index, right)| {
            left.start
                .cmp(&right.start)
                .then_with(|| right.end.cmp(&left.end))
                .then_with(|| right_index.cmp(left_index))
        })
        .map(|(index, _)| index)
}

fn in_any_transform_group(groups: &[TransformGroup], index: usize) -> bool {
    groups
        .iter()
        .any(|group| group.start <= index && index < group.end)
}

fn uses_compact_resource_contract(score: &inku_score::Score) -> bool {
    score.version == "0.10.0"
        || (matches!(score.version.as_str(), "0.11.0" | "0.12.0" | "0.13.0")
            && score.resource_policy.is_some())
}

/// Resolve checked relations and transform scopes through one dependency executor.
pub fn resolve_checked_performance(
    request: PerformanceRequest<'_>,
    policy: ScoreErrorPolicy,
) -> Result<PerformancePlan, CheckedPerformanceError> {
    if uses_compact_resource_contract(request.score) {
        return Err(CheckedPerformanceError {
            diagnostics: vec![ScoreExecutionDiagnostic {
                instruction_index: 0,
                anchor_index: None,
                dependency_instruction_index: None,
                reason: ScoreExecutionReason::InvalidCompactPerformance,
                disposition: ScoreExecutionDisposition::Stopped,
            }],
        });
    }
    let needs_checked_execution = !request.score.anchors.is_empty()
        || !request.score.placement_groups.is_empty()
        || !request.score.transform_groups.is_empty()
        || request.score.instructions.iter().any(|instruction| {
            instruction.relation.as_ref().is_some_and(|relation| {
                relation.kind == RelationType::Connected
                    || relation.target_anchor_index.is_some()
                    || is_checked_touching(relation)
                    || is_checked_bounds_relation(relation)
                    || is_checked_line_relation(relation, RelationType::Along)
                    || is_checked_line_relation(relation, RelationType::Cutting)
            })
        });
    if needs_checked_execution {
        anchor_execution::resolve(request, policy)
    } else {
        Ok(resolve_performance(request))
    }
}

/// Perform compact Score only after caller-owned hard and operational authority.
/// Legacy editions retain their established checked-performance path.
pub fn resolve_checked_performance_with_resources(
    request: PerformanceRequest<'_>,
    policy: ScoreErrorPolicy,
    hard_policy: &inku_score::HardResourcePolicy,
    operational_budget: inku_score::OperationalResourceBudget,
) -> Result<PerformancePlan, CheckedPerformanceWithResourcesError> {
    resolve_checked_performance_with_resources_and_omissions(
        request,
        policy,
        hard_policy,
        operational_budget,
        &[],
    )
}

fn remap_finalized_diagnostics(
    diagnostics: &mut [ScoreExecutionDiagnostic],
    finalized_to_original_instructions: &[usize],
    finalized_to_original_anchors: &[usize],
) {
    for diagnostic in diagnostics {
        if let Some(&original) =
            finalized_to_original_instructions.get(diagnostic.instruction_index)
        {
            diagnostic.instruction_index = original;
        }
        if let Some(finalized) = diagnostic.dependency_instruction_index
            && let Some(&original) = finalized_to_original_instructions.get(finalized)
        {
            diagnostic.dependency_instruction_index = Some(original);
        }
        if let Some(finalized) = diagnostic.anchor_index
            && let Some(&original) = finalized_to_original_anchors.get(finalized)
        {
            diagnostic.anchor_index = Some(original);
        }
    }
}

pub(crate) fn resolve_checked_performance_with_resources_and_omissions(
    request: PerformanceRequest<'_>,
    policy: ScoreErrorPolicy,
    hard_policy: &inku_score::HardResourcePolicy,
    operational_budget: inku_score::OperationalResourceBudget,
    omitted_original_instruction_indices: &[usize],
) -> Result<PerformancePlan, CheckedPerformanceWithResourcesError> {
    if !uses_compact_resource_contract(request.score) {
        return resolve_checked_performance(request, policy).map_err(Into::into);
    }
    let finalized = inku_score::finalize_saved_score_with_omitted_instructions(
        request.score,
        hard_policy,
        operational_budget,
        omitted_original_instruction_indices,
    )?;
    let input_digest =
        canonical_score_digest(request.score).map_err(|_| inku_score::SavedScoreResourceError {
            owner: inku_score::SavedScoreResourceOwner::Score,
            reason: inku_score::SavedScoreResourceFailure::InvalidContract("non-canonical Score"),
        })?;
    let mut new_to_old = vec![0; finalized.score.instructions.len()];
    for (old, new) in finalized.index_maps.instructions.iter().enumerate() {
        if let Some(new) = new {
            new_to_old[*new] = old;
        }
    }
    let mut new_anchor_to_old = vec![0; finalized.score.anchors.len()];
    for (old, new) in finalized.index_maps.anchors.iter().enumerate() {
        if let Some(new) = new {
            new_anchor_to_old[*new] = old;
        }
    }
    let finalized_request = PerformanceRequest {
        score: &finalized.score,
        ..request
    };
    let mut performance = match crate::typed_performance::resolve(finalized_request, policy) {
        Ok(performance) => performance,
        Err(mut error) => {
            remap_finalized_diagnostics(&mut error.diagnostics, &new_to_old, &new_anchor_to_old);
            return Err(error.into());
        }
    };
    for owner in &mut performance.original_instruction_indices {
        *owner = new_to_old[*owner];
    }
    // The later paint/clip stage must be able to append a local failure even
    // when geometry execution itself produced no diagnostics.
    let execution = performance
        .execution
        .get_or_insert_with(|| ScoreExecutionSummary {
            input_score_digest: input_digest.clone(),
            diagnostics: Vec::new(),
            rendered_instruction_indices: Vec::new(),
        });
    execution.input_score_digest = input_digest;
    execution.rendered_instruction_indices = performance.original_instruction_indices.clone();
    execution.rendered_instruction_indices.sort_unstable();
    execution.rendered_instruction_indices.dedup();
    remap_finalized_diagnostics(&mut execution.diagnostics, &new_to_old, &new_anchor_to_old);
    performance.resource_demand = Some(finalized.demand);
    performance.resource_diagnostics = finalized.resource_diagnostics;
    performance.relation_diagnostics = finalized.relation_diagnostics;
    Ok(performance)
}
