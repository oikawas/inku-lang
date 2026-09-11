//! Event execution keeps point targets and drawable targets in the same scope.

use super::*;
use crate::anchor_schedule::{AnchorSchedule, ScheduleNode, group_contains, schedule};
use crate::planning::{Bounds, PlanningWarning};
use crate::types::Point;

struct Performed {
    instruction: Instruction,
    ordinal: usize,
    seed_override: Option<crate::types::Seed>,
}

struct Execution<'a> {
    request: PerformanceRequest<'a>,
    schedule: AnchorSchedule,
    performed: Vec<Vec<Performed>>,
    transforms: Vec<AffineTransform>,
    anchors: Vec<Option<Point>>,
    omitted: Vec<bool>,
    omitted_groups: Vec<bool>,
    structural: Vec<bool>,
    warnings: Vec<PlanningWarning>,
}

fn distance(point: Point) -> f64 {
    point.x.hypot(point.y)
}

fn finite_point(point: Point) -> Result<Point, ScoreExecutionReason> {
    (point.x.is_finite() && point.y.is_finite())
        .then_some(point)
        .ok_or(ScoreExecutionReason::InvalidTransformGroup)
}

fn node_failure(
    score: &Score,
    node: ScheduleNode,
    reason: ScoreExecutionReason,
    policy: ScoreErrorPolicy,
) -> ScoreExecutionDiagnostic {
    let (source, anchor) = match node {
        ScheduleNode::Instruction(index) => (index, None),
        ScheduleNode::Group(index) => {
            let group = &score.transform_groups[index];
            if group.start == group.end {
                (0, group.anchor_indices.first().copied())
            } else {
                (group.start, None)
            }
        }
    };
    let dependency = anchor
        .is_none()
        .then(|| {
            score
                .instructions
                .get(source)
                .and_then(|instruction| instruction.relation.as_ref())
                .and_then(|relation| relation.target_instruction_index)
        })
        .flatten();
    let mut diagnostic = connected_failure(source, dependency, reason, policy);
    diagnostic.anchor_index = anchor;
    diagnostic
}

fn merge_bounds(bounds: &mut Option<Bounds>, next: Bounds) {
    *bounds = Some(match *bounds {
        Some(current) => Bounds {
            min: Point::new(current.min.x.min(next.min.x), current.min.y.min(next.min.y)),
            max: Point::new(current.max.x.max(next.max.x), current.max.y.max(next.max.y)),
        },
        None => next,
    });
}

impl Execution<'_> {
    fn prior(&self, index: usize) -> Option<&Instruction> {
        self.performed
            .get(index)?
            .last()
            .map(|value| &value.instruction)
    }

    fn omit_group(&mut self, index: usize) {
        let groups = &self.request.score.transform_groups;
        let outermost = (index..groups.len())
            .rev()
            .find(|&outer| group_contains(&groups[outer], &groups[index]))
            .unwrap_or(index);
        let group = &groups[outermost];
        for member in group.start..group.end {
            self.omitted[member] = true;
            self.performed[member].clear();
        }
        for &anchor in &group.anchor_indices {
            self.anchors[anchor] = None;
        }
        for (child, candidate) in groups.iter().enumerate() {
            if child == outermost || group_contains(group, candidate) {
                self.omitted_groups[child] = true;
            }
        }
    }

    fn omit_instruction(&mut self, index: usize) {
        if let Some(group) = self
            .request
            .score
            .transform_groups
            .iter()
            .rposition(|group| group.start <= index && index < group.end)
        {
            self.omit_group(group);
        } else {
            self.omitted[index] = true;
            self.performed[index].clear();
        }
    }

    fn connected_target(
        &self,
        source: usize,
        relation: &inku_score::Relation,
    ) -> Result<Point, ScoreExecutionReason> {
        if let Some(anchor) = relation.target_anchor_index {
            if relation.target_instruction_index.is_some() || anchor >= self.anchors.len() {
                return Err(ScoreExecutionReason::MissingConnectedReference);
            }
            return self.anchors[anchor].ok_or(ScoreExecutionReason::ConnectedReferenceOmitted);
        }
        let target = relation
            .target_instruction_index
            .filter(|&target| Some(target) == source.checked_sub(1))
            .ok_or(ScoreExecutionReason::MissingConnectedReference)?;
        let prior = self
            .prior(target)
            .ok_or(ScoreExecutionReason::ConnectedReferenceOmitted)?;
        if !supports_connected(prior) {
            return Err(ScoreExecutionReason::UnsupportedConnectedPrimitive);
        }
        crate::affine_geometry::endpoints(prior, self.request.canvas, self.transforms[target])
            .map(|geometry| geometry.1)
            .ok_or(ScoreExecutionReason::UnsupportedConnectedPrimitive)
    }

    fn prepare_connected(
        &self,
        index: usize,
        mut instruction: Instruction,
    ) -> Result<Instruction, ScoreExecutionReason> {
        let relation = instruction.relation.as_ref().expect("Connected relation");
        if self.structural[index]
            || relation
                .target_instruction_index
                .is_some_and(|target| self.structural.get(target).copied().unwrap_or(false))
            || !supports_connected(&instruction)
        {
            return Err(ScoreExecutionReason::UnsupportedConnectedStructure);
        }
        if relation.position_authority.is_none() {
            return Err(ScoreExecutionReason::MissingConnectedPositionAuthority);
        }
        if let Some(anchor) = relation.target_anchor_index {
            if anchor >= self.anchors.len() || relation.target_instruction_index.is_some() {
                return Err(ScoreExecutionReason::MissingConnectedReference);
            }
        } else if relation.target_instruction_index.is_none()
            || relation.target_instruction_index != index.checked_sub(1)
        {
            return Err(ScoreExecutionReason::MissingConnectedReference);
        }
        if self.schedule.external_groups[index].is_some() {
            // The target may be in an unfinished sibling group. The group event
            // checks its final position and applies one common correction.
            return Ok(instruction);
        }
        let target = self.connected_target(index, relation)?;
        let start = endpoint_geometry(&instruction, self.request.canvas)
            .ok_or(ScoreExecutionReason::UnsupportedConnectedPrimitive)?
            .0;
        let delta = finite_point(Point::new(target.x - start.x, target.y - start.y))?;
        if relation.position_authority == Some(ConnectedPositionAuthority::NumericFixed)
            && distance(delta) > GEOMETRY_EPSILON
        {
            return Err(ScoreExecutionReason::NumericConnectedPositionConflict);
        }
        let delta = if relation.position_authority == Some(ConnectedPositionAuthority::NumericFixed)
        {
            Point::new(0.0, 0.0)
        } else {
            delta
        };
        instruction =
            translate_endpoint_instruction_on_canvas(&instruction, delta, self.request.canvas)
                .ok_or(ScoreExecutionReason::UnsupportedConnectedPrimitive)?;
        instruction.relation = None;
        Ok(instruction)
    }

    fn prepare_instruction(
        &mut self,
        index: usize,
        ordinal: usize,
        original: &Instruction,
    ) -> Result<Instruction, ScoreExecutionReason> {
        let mut instruction = ensure_line_coordinates(original);
        if let Some(seed) = self.request.performance_seed {
            instruction = resolve_at_region(&instruction, seed, ordinal, self.request.canvas);
        }
        let Some(relation) = instruction.relation.as_ref() else {
            return Ok(instruction);
        };
        if relation.target_anchor_index.is_some() && relation.kind != RelationType::Connected {
            return Err(ScoreExecutionReason::UnsupportedAnchorRelation);
        }
        if relation.kind == RelationType::Connected {
            return self.prepare_connected(index, instruction);
        }
        let target = relation.target_instruction_index;
        let legacy_target = target.or_else(|| {
            index.checked_sub(if relation.kind == RelationType::Between {
                2
            } else {
                1
            })
        });
        if legacy_target.is_some_and(|target| {
            enclosing_external_group(&self.request.score.transform_groups, index, target).is_some()
        }) {
            return Err(ScoreExecutionReason::UnsupportedTransformGroupRelation);
        }
        if is_checked_touching(relation) {
            if self.structural[index]
                || target
                    .is_some_and(|target| self.structural.get(target).copied().unwrap_or(false))
            {
                return Err(ScoreExecutionReason::UnsupportedTouchingStructure);
            }
            let target = target
                .filter(|&target| Some(target) == index.checked_sub(1))
                .ok_or(ScoreExecutionReason::MissingTouchingReference)?;
            let prior = self
                .prior(target)
                .ok_or(ScoreExecutionReason::TouchingReferenceOmitted)?;
            return checked_touching_candidate(
                &instruction,
                prior,
                self.request.canvas,
                self.transforms[target],
            );
        }
        let along = is_checked_line_relation(relation, RelationType::Along);
        let cutting = is_checked_line_relation(relation, RelationType::Cutting);
        if along || cutting {
            let (structure, missing, omitted, primitive) = if along {
                (
                    ScoreExecutionReason::UnsupportedAlongStructure,
                    ScoreExecutionReason::MissingAlongReference,
                    ScoreExecutionReason::AlongReferenceOmitted,
                    ScoreExecutionReason::UnsupportedAlongPrimitive,
                )
            } else {
                (
                    ScoreExecutionReason::UnsupportedCuttingStructure,
                    ScoreExecutionReason::MissingCuttingReference,
                    ScoreExecutionReason::CuttingReferenceOmitted,
                    ScoreExecutionReason::UnsupportedCuttingPrimitive,
                )
            };
            if self.structural[index]
                || target
                    .is_some_and(|target| self.structural.get(target).copied().unwrap_or(false))
            {
                return Err(structure);
            }
            let target = target
                .filter(|&target| Some(target) == index.checked_sub(1))
                .ok_or(missing)?;
            let prior = self.prior(target).ok_or(omitted)?;
            if instruction.primitive != Primitive::Line || prior.primitive != Primitive::Line {
                return Err(primitive);
            }
            let candidate = if along {
                checked_along_candidate
            } else {
                checked_cutting_candidate
            };
            return candidate(
                &instruction,
                prior,
                relation,
                self.request.performance_seed.unwrap_or_default(),
                ordinal,
                self.request.canvas,
                self.transforms[target],
            );
        }
        if let Some(seed) = self.request.performance_seed {
            let needed = usize::from(relation.kind == RelationType::Between) + 1;
            if index >= needed
                && self.omitted[index - needed..index]
                    .iter()
                    .any(|omitted| *omitted)
            {
                return Err(ScoreExecutionReason::ConnectedReferenceOmitted);
            }
            if (index.saturating_sub(needed)..index)
                .any(|target| !self.transforms[target].is_identity())
            {
                return Err(ScoreExecutionReason::UnsupportedTransformGroupRelation);
            }
            // Execution order may differ from drawing order; legacy predecessor
            // relations still receive their original predecessors, never future nodes.
            let previous = self.performed[..index]
                .iter()
                .flatten()
                .map(|value| value.instruction.clone())
                .collect::<Vec<_>>();
            let resolved = resolve_relation_on_canvas(
                &instruction,
                &previous,
                seed,
                ordinal,
                self.request.canvas,
            );
            instruction = resolved.instruction;
            if let Some(warning) = resolved.warning {
                self.warnings.push(warning);
            }
        }
        Ok(instruction)
    }

    fn perform_group(&mut self, index: usize) -> Result<(), ScoreExecutionReason> {
        let group = &self.request.score.transform_groups[index];
        if (group.start..group.end)
            .any(|member| self.omitted[member] || self.performed[member].is_empty())
            || group
                .anchor_indices
                .iter()
                .any(|&anchor| self.anchors[anchor].is_none())
        {
            return Err(ScoreExecutionReason::ConnectedReferenceOmitted);
        }
        let mut bounds = None;
        for member in group.start..group.end {
            for value in &self.performed[member] {
                let next = crate::affine_geometry::bounds(
                    &value.instruction,
                    self.request.performance_seed,
                    value.ordinal,
                    self.request.canvas,
                    value.seed_override,
                    self.transforms[member],
                )
                .ok_or(ScoreExecutionReason::UnsupportedTransformGroupRelation)?;
                merge_bounds(&mut bounds, next);
            }
        }
        // Named/numeric point targets do not enlarge the shape pivot. An
        // anchor-only scope uses its points' bbox, including already transformed children.
        if bounds.is_none() {
            for &anchor in &group.anchor_indices {
                let point =
                    self.anchors[anchor].ok_or(ScoreExecutionReason::ConnectedReferenceOmitted)?;
                merge_bounds(
                    &mut bounds,
                    Bounds {
                        min: point,
                        max: point,
                    },
                );
            }
        }
        let bounds = bounds.ok_or(ScoreExecutionReason::InvalidTransformGroup)?;
        let transform = AffineTransform::around(
            bounds.center(),
            group.scale_x,
            group.scale_y,
            group.rotation_degrees,
            crate::geometry::point_to_short_side_units(
                Point::new(group.translate_x, group.translate_y),
                self.request.canvas,
            ),
        );
        if !transform.is_finite() {
            return Err(ScoreExecutionReason::InvalidTransformGroup);
        }
        for member in group.start..group.end {
            let composed = transform.compose(self.transforms[member]);
            if !composed.is_finite() {
                return Err(ScoreExecutionReason::InvalidTransformGroup);
            }
            self.transforms[member] = composed;
        }
        for &anchor in &group.anchor_indices {
            self.anchors[anchor] = self.anchors[anchor]
                .map(|point| finite_point(transform.apply(point)))
                .transpose()?;
        }
        let mut correction: Option<Point> = None;
        for source in group.start..group.end {
            if self.schedule.external_groups[source] != Some(index) {
                continue;
            }
            let instruction = self
                .prior(source)
                .ok_or(ScoreExecutionReason::ConnectedReferenceOmitted)?;
            let relation = instruction
                .relation
                .as_ref()
                .ok_or(ScoreExecutionReason::MissingConnectedReference)?;
            let target = self.connected_target(source, relation)?;
            let start = crate::affine_geometry::endpoints(
                instruction,
                self.request.canvas,
                self.transforms[source],
            )
            .ok_or(ScoreExecutionReason::UnsupportedConnectedPrimitive)?
            .0;
            let delta = finite_point(Point::new(target.x - start.x, target.y - start.y))?;
            if (relation.position_authority == Some(ConnectedPositionAuthority::NumericFixed)
                || !group.fixed_position_indices.is_empty()
                || group
                    .anchor_indices
                    .iter()
                    .any(|&anchor| self.request.score.anchors[anchor].position.is_some()))
                && distance(delta) > GEOMETRY_EPSILON
            {
                return Err(ScoreExecutionReason::NumericConnectedPositionConflict);
            }
            if correction.is_some_and(|prior| {
                distance(Point::new(prior.x - delta.x, prior.y - delta.y)) > GEOMETRY_EPSILON
            }) {
                return Err(ScoreExecutionReason::ConflictingConnectedConstraints);
            }
            correction.get_or_insert(delta);
        }
        if let Some(delta) = correction {
            let delta = if distance(delta) <= GEOMETRY_EPSILON {
                Point::new(0.0, 0.0)
            } else {
                delta
            };
            let translation = AffineTransform::translation(delta);
            for member in group.start..group.end {
                let composed = translation.compose(self.transforms[member]);
                if !composed.is_finite() {
                    return Err(ScoreExecutionReason::InvalidTransformGroup);
                }
                self.transforms[member] = composed;
                if self.schedule.external_groups[member] == Some(index) {
                    for value in &mut self.performed[member] {
                        value.instruction.relation = None;
                    }
                }
            }
            for &anchor in &group.anchor_indices {
                self.anchors[anchor] = self.anchors[anchor]
                    .map(|point| finite_point(translation.apply(point)))
                    .transpose()?;
            }
        }
        let has_outer = self.request.score.transform_groups[index + 1..]
            .iter()
            .any(|outer| group_contains(outer, group));
        if !has_outer {
            let extent = crate::geometry::short_side_scales(self.request.canvas);
            let inside = |point: Point| {
                point.x >= -GEOMETRY_EPSILON
                    && point.y >= -GEOMETRY_EPSILON
                    && point.x <= extent.x + GEOMETRY_EPSILON
                    && point.y <= extent.y + GEOMETRY_EPSILON
            };
            for &anchor in &group.anchor_indices {
                if self.request.score.anchors[anchor].position.is_some()
                    && !self.anchors[anchor].is_some_and(inside)
                {
                    return Err(ScoreExecutionReason::NumericTransformGroupPositionConflict);
                }
            }
            for &member in &group.fixed_position_indices {
                for value in &self.performed[member] {
                    if !crate::affine_geometry::bounds(
                        &value.instruction,
                        self.request.performance_seed,
                        value.ordinal,
                        self.request.canvas,
                        value.seed_override,
                        self.transforms[member],
                    )
                    .is_some_and(|bounds| inside(bounds.min) && inside(bounds.max))
                    {
                        return Err(ScoreExecutionReason::NumericTransformGroupPositionConflict);
                    }
                }
            }
        }
        Ok(())
    }
}

pub(super) fn resolve(
    request: PerformanceRequest<'_>,
    policy: ScoreErrorPolicy,
) -> Result<PerformancePlan, CheckedPerformanceError> {
    if request.score.validate_transform_groups().is_err() {
        return Err(CheckedPerformanceError {
            diagnostics: vec![connected_failure(
                0,
                None,
                ScoreExecutionReason::InvalidTransformGroup,
                ScoreErrorPolicy::Stop,
            )],
        });
    }
    let (expanded, owners) = expand_composite_groups_with_indices(
        request.score,
        request.composition_seed.or(request.performance_seed),
        request.performance_seed,
        request.canvas,
    );
    let mut ordinals = vec![Vec::new(); request.score.instructions.len()];
    for (ordinal, &owner) in owners.iter().enumerate() {
        ordinals[owner].push(ordinal);
    }
    let anchors = request
        .score
        .anchors
        .iter()
        .enumerate()
        .map(|(index, anchor)| {
            if let Some(position) = anchor.position {
                return anchor
                    .at
                    .is_none()
                    .then(|| crate::geometry::point_to_short_side_units(position, request.canvas));
            }
            let at = anchor.at.as_ref()?;
            let [x0, y0, x1, y1] =
                crate::placement::region_in_short_side_units(at.region, request.canvas);
            let seed = request.performance_seed.unwrap_or_default();
            Some(Point::new(
                x0 + (x1 - x0) * crate::determinism::hash01(index as i64, seed, "anchor-region-x"),
                y0 + (y1 - y0) * crate::determinism::hash01(index as i64, seed, "anchor-region-y"),
            ))
        })
        .collect();
    let mut execution = Execution {
        request,
        schedule: schedule(request.score),
        performed: (0..request.score.instructions.len())
            .map(|_| Vec::new())
            .collect(),
        transforms: vec![AffineTransform::identity(); request.score.instructions.len()],
        anchors,
        omitted: vec![false; request.score.instructions.len()],
        omitted_groups: vec![false; request.score.transform_groups.len()],
        structural: structural_instruction_indices(request.score),
        warnings: Vec::new(),
    };
    let mut diagnostics = Vec::new();
    for node in execution.schedule.cyclic.clone() {
        match node {
            ScheduleNode::Instruction(index) => {
                execution.omit_instruction(index);
            }
            ScheduleNode::Group(index) => {
                execution.omit_group(index);
            }
        };
        diagnostics.push(node_failure(
            request.score,
            node,
            ScoreExecutionReason::CyclicConnectedDependency,
            policy,
        ));
    }
    if policy == ScoreErrorPolicy::Stop && !diagnostics.is_empty() {
        return Err(CheckedPerformanceError { diagnostics });
    }
    for node in execution.schedule.order.clone() {
        let failure = match node {
            ScheduleNode::Instruction(index) => {
                if execution.omitted[index] {
                    continue;
                }
                let mut failure = None;
                for &ordinal in &ordinals[index] {
                    match execution.prepare_instruction(
                        index,
                        ordinal,
                        &expanded.instructions[ordinal],
                    ) {
                        Ok(instruction) => {
                            let seed_override =
                                in_any_transform_group(&request.score.transform_groups, index)
                                    .then(|| {
                                        crate::determinism::instruction_seed(
                                            &instruction,
                                            request.performance_seed,
                                        )
                                    });
                            execution.performed[index].push(Performed {
                                instruction,
                                ordinal,
                                seed_override,
                            });
                        }
                        Err(reason) => {
                            execution.omit_instruction(index);
                            failure = Some((index, reason));
                            break;
                        }
                    }
                }
                failure
            }
            ScheduleNode::Group(index) => {
                if execution.omitted_groups[index] {
                    continue;
                }
                match execution.perform_group(index) {
                    Ok(()) => None,
                    Err(reason) => {
                        execution.omit_group(index);
                        Some((request.score.transform_groups[index].start, reason))
                    }
                }
            }
        };
        if let Some((_, reason)) = failure {
            diagnostics.push(node_failure(request.score, node, reason, policy));
            if policy == ScoreErrorPolicy::Stop {
                return Err(CheckedPerformanceError { diagnostics });
            }
        }
    }
    let mut rendered = Vec::new();
    for (owner, values) in execution.performed.into_iter().enumerate() {
        for value in values {
            rendered.push((owner, value));
        }
    }
    rendered.sort_by_key(|(_, value)| value.ordinal);
    if rendered.is_empty()
        && !matches!(&request.score.canvas, Canvas::Spec(spec) if spec.ground.is_some())
    {
        let mut diagnostic = connected_failure(
            request.score.instructions.len().saturating_sub(1),
            None,
            ScoreExecutionReason::NoDrawableInstructions,
            ScoreErrorPolicy::Stop,
        );
        if request.score.instructions.is_empty() && !request.score.anchors.is_empty() {
            diagnostic.anchor_index = Some(0);
        }
        diagnostics.push(diagnostic);
        return Err(CheckedPerformanceError { diagnostics });
    }
    let original_instruction_indices = rendered.iter().map(|(owner, _)| *owner).collect::<Vec<_>>();
    let instruction_indices = rendered.iter().map(|(_, value)| value.ordinal).collect();
    let instruction_seed_overrides = rendered
        .iter()
        .map(|(_, value)| value.seed_override)
        .collect();
    let instruction_transforms = rendered
        .iter()
        .map(|(owner, _)| execution.transforms[*owner])
        .collect();
    let mut score = request.score.clone();
    score.instructions = rendered
        .into_iter()
        .map(|(_, value)| value.instruction)
        .collect();
    score.transform_groups.clear();
    let summary = (!diagnostics.is_empty()).then(|| ScoreExecutionSummary {
        input_score_digest: canonical_score_digest(request.score)
            .expect("typed Score canonicalization"),
        diagnostics,
        rendered_instruction_indices: original_instruction_indices.clone(),
    });
    Ok(PerformancePlan {
        score,
        warnings: execution.warnings,
        instruction_indices,
        original_instruction_indices,
        instruction_seed_overrides,
        instruction_transforms,
        execution: summary,
    })
}
