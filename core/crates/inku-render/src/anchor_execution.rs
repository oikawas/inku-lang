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
    omitted_relations: Vec<bool>,
    diagnostics: Vec<ScoreExecutionDiagnostic>,
}

enum TranslationPredicate {
    Exact(Point),
    NotTouching {
        center: Point,
        target: Point,
        minimum: f64,
    },
    Between {
        center: Point,
        first: Point,
        second: Point,
        moving_targets: [bool; 2],
    },
    Along {
        center: Point,
        start: Point,
        end: Point,
        gap: inku_score::RelationGap,
    },
    Cutting {
        start: Point,
        end: Point,
        target_start: Point,
        target_end: Point,
    },
}

struct ExternalConstraint {
    source: usize,
    preferred: Point,
    predicate: TranslationPredicate,
    numeric_reason: ScoreExecutionReason,
}

impl ExternalConstraint {
    fn accepts(&self, delta: Point) -> bool {
        let moved = |point: Point| Point::new(point.x + delta.x, point.y + delta.y);
        match self.predicate {
            TranslationPredicate::NotTouching {
                center,
                target,
                minimum,
            } => {
                distance(Point::new(
                    center.x + delta.x - target.x,
                    center.y + delta.y - target.y,
                )) + GEOMETRY_EPSILON
                    >= minimum
            }
            TranslationPredicate::Between {
                center,
                first,
                second,
                moving_targets,
            } => between_contains(
                moved(center),
                if moving_targets[0] {
                    moved(first)
                } else {
                    first
                },
                if moving_targets[1] {
                    moved(second)
                } else {
                    second
                },
            ),
            TranslationPredicate::Exact(required) => {
                distance(Point::new(required.x - delta.x, required.y - delta.y)) <= GEOMETRY_EPSILON
            }
            TranslationPredicate::Along {
                center,
                start,
                end,
                gap,
            } => along_band_contains(moved(center), start, end, gap),
            TranslationPredicate::Cutting {
                start,
                end,
                target_start,
                target_end,
            } => segments_properly_cross(moved(start), moved(end), target_start, target_end),
        }
    }
}

fn distance(point: Point) -> f64 {
    point.x.hypot(point.y)
}

/// The two-center segment with the existing diagonal jitter, independent of
/// which point the performance seed happens to select for a movable source.
fn between_contains(point: Point, first: Point, second: Point) -> bool {
    let vector = Point::new(second.x - first.x, second.y - first.y);
    let offset = Point::new(point.x - first.x, point.y - first.y);
    let sum = vector.x + vector.y;
    if sum.abs() <= GEOMETRY_EPSILON {
        return (offset.x + offset.y).abs() <= GEOMETRY_EPSILON
            && offset.x >= vector.x.min(0.0) - 0.04 - GEOMETRY_EPSILON
            && offset.x <= vector.x.max(0.0) + 0.04 + GEOMETRY_EPSILON;
    }
    let factor = (offset.x + offset.y) / sum;
    let jitter = offset.x - vector.x * factor;
    (-GEOMETRY_EPSILON..=1.0 + GEOMETRY_EPSILON).contains(&factor)
        && jitter.abs() <= 0.04 + GEOMETRY_EPSILON
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
    fn drop_relation(&mut self, index: usize, reason: ScoreExecutionReason) {
        if !self.omitted_relations[index] {
            self.diagnostics
                .push(relation_failure(self.request.score, index, reason));
            self.omitted_relations[index] = true;
        }
        for value in &mut self.performed[index] {
            value.instruction.relation = None;
        }
    }

    fn placed_instruction(&self, ordinal: usize, original: &Instruction) -> Instruction {
        let mut instruction = ensure_line_coordinates(original);
        if let Some(seed) = self.request.performance_seed {
            instruction = resolve_at_region(&instruction, seed, ordinal, self.request.canvas);
        }
        instruction
    }

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
        let mut instruction = self.placed_instruction(ordinal, original);
        if self.omitted_relations[index] {
            instruction.relation = None;
        }
        let Some(relation) = instruction.relation.as_ref() else {
            return Ok(instruction);
        };
        if relation.target_anchor_index.is_some() && relation.kind != RelationType::Connected {
            return Err(ScoreExecutionReason::UnsupportedAnchorRelation);
        }
        if self.request.score.placement_groups.iter().any(|group| {
            group.start <= index
                && index < group.end
                && self.schedule.external_groups[index].is_none()
        }) {
            // Internal arrangement has priority. Check this relation against
            // the completed local layout instead of moving a child beforehand.
            return Ok(instruction);
        }
        if relation.kind == RelationType::Connected {
            return self.prepare_connected(index, instruction);
        }
        if self.schedule.external_groups[index].is_some()
            && (is_bounds_relation(relation)
                || is_checked_touching(relation)
                || is_checked_line_relation(relation, RelationType::Along)
                || is_checked_line_relation(relation, RelationType::Cutting))
        {
            // Preserve the member geometry until the scope's own transform has
            // completed. Only a common translation can satisfy this relation.
            return Ok(instruction);
        }
        if is_bounds_relation(relation)
            && (is_checked_bounds_relation(relation)
                || (index.saturating_sub(if relation.kind == RelationType::Between {
                    2
                } else {
                    1
                })..index)
                    .any(|target| !self.transforms[target].is_identity()))
        {
            let constraint = self.bounds_constraint(index, ordinal, &instruction, None)?;
            let zero = Point::new(0.0, 0.0);
            let delta = if constraint.accepts(zero) {
                zero
            } else {
                if relation.position_authority == Some(ConnectedPositionAuthority::NumericFixed) {
                    return Err(constraint.numeric_reason);
                }
                if !constraint.accepts(constraint.preferred) {
                    return Err(ScoreExecutionReason::ConflictingRelationConstraints);
                }
                constraint.preferred
            };
            self.transforms[index] =
                AffineTransform::translation(delta).compose(self.transforms[index]);
            instruction.relation = None;
            return Ok(instruction);
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

    fn bounds_constraint(
        &self,
        source: usize,
        ordinal: usize,
        instruction: &Instruction,
        scope: Option<usize>,
    ) -> Result<ExternalConstraint, ScoreExecutionReason> {
        let relation = instruction.relation.as_ref().expect("bounds relation");
        let between = relation.kind == RelationType::Between;
        let (missing, omitted, geometry, numeric_reason) = if between {
            (
                ScoreExecutionReason::MissingBetweenReference,
                ScoreExecutionReason::BetweenReferenceOmitted,
                ScoreExecutionReason::UnsupportedBetweenGeometry,
                ScoreExecutionReason::NumericBetweenPositionConflict,
            )
        } else {
            (
                ScoreExecutionReason::MissingNotTouchingReference,
                ScoreExecutionReason::NotTouchingReferenceOmitted,
                ScoreExecutionReason::UnsupportedNotTouchingGeometry,
                ScoreExecutionReason::NumericNotTouchingPositionConflict,
            )
        };
        let needed = if between { 2 } else { 1 };
        let first_index = source.checked_sub(needed).ok_or(missing)?;
        if relation.target_anchor_index.is_some()
            || relation
                .target_instruction_index
                .is_some_and(|target| Some(target) != source.checked_sub(1))
        {
            return Err(missing);
        }
        if self.structural[source] || (first_index..source).any(|target| self.structural[target]) {
            return Err(geometry);
        }
        let bounds = |value: &Instruction, index, ordinal, seed_override| {
            crate::affine_geometry::bounds(
                value,
                self.request.performance_seed,
                ordinal,
                self.request.canvas,
                seed_override,
                self.transforms[index],
            )
            .ok_or(geometry)
        };
        let own = bounds(
            instruction,
            source,
            ordinal,
            self.performed[source]
                .last()
                .and_then(|value| value.seed_override),
        )?;
        let target = |index: usize| {
            let value = self.performed[index].last().ok_or(omitted)?;
            bounds(
                &value.instruction,
                index,
                value.ordinal,
                value.seed_override,
            )
        };
        let prior = target(source - 1)?;
        let center = own.center();
        let seed = self.request.performance_seed.unwrap_or_default();
        if !between {
            let radius = own.radius() + prior.radius();
            let gap = relation_gap_amount(relation.gap, seed, ordinal);
            let minimum_gap = match relation.gap {
                RelationGap::Narrow => 0.02,
                RelationGap::Medium => 0.06,
                RelationGap::Wide => 0.15,
            };
            let angle = std::f64::consts::TAU
                * crate::determinism::hash01(ordinal as i64, seed, "not-touching-angle");
            let target = clamp_short_side_point(
                Point::new(
                    prior.center().x + angle.cos() * (radius + gap),
                    prior.center().y + angle.sin() * (radius + gap),
                ),
                self.request.canvas,
            );
            return Ok(ExternalConstraint {
                source,
                preferred: Point::new(target.x - center.x, target.y - center.y),
                predicate: TranslationPredicate::NotTouching {
                    center,
                    target: prior.center(),
                    minimum: radius + minimum_gap,
                },
                numeric_reason,
            });
        }
        let other = target(source - 2)?;
        let moving_targets = scope.map_or([false; 2], |scope| {
            let group = &self.request.score.transform_groups[scope];
            [source - 2, source - 1].map(|target| group.start <= target && target < group.end)
        });
        let jitter =
            0.08 * (crate::determinism::hash01(ordinal as i64, seed, "between-jitter") - 0.5);
        let target = Point::new(
            (prior.center().x + other.center().x) / 2.0 + jitter,
            (prior.center().y + other.center().y) / 2.0 - jitter,
        );
        let factor = 1.0 - moving_targets.iter().filter(|&&moving| moving).count() as f64 / 2.0;
        if factor <= 0.0 {
            return Err(geometry);
        }
        let target = clamp_short_side_point(
            Point::new(
                center.x + (target.x - center.x) / factor,
                center.y + (target.y - center.y) / factor,
            ),
            self.request.canvas,
        );
        Ok(ExternalConstraint {
            source,
            preferred: Point::new(target.x - center.x, target.y - center.y),
            predicate: TranslationPredicate::Between {
                center,
                first: other.center(),
                second: prior.center(),
                moving_targets,
            },
            numeric_reason,
        })
    }

    fn external_constraint(
        &self,
        source: usize,
    ) -> Result<ExternalConstraint, ScoreExecutionReason> {
        let instruction = self
            .prior(source)
            .ok_or(ScoreExecutionReason::ConnectedReferenceOmitted)?;
        let relation = instruction.relation.as_ref().expect("deferred relation");
        if is_bounds_relation(relation) {
            return self.bounds_constraint(
                source,
                self.performed[source]
                    .last()
                    .expect("performed member")
                    .ordinal,
                instruction,
                self.schedule.external_groups[source],
            );
        }
        let canvas = self.request.canvas;
        let (unsupported, structure, missing, omitted, authority_missing, numeric_reason) =
            match relation.kind {
                RelationType::Connected => (
                    ScoreExecutionReason::UnsupportedConnectedPrimitive,
                    ScoreExecutionReason::UnsupportedConnectedStructure,
                    ScoreExecutionReason::MissingConnectedReference,
                    ScoreExecutionReason::ConnectedReferenceOmitted,
                    ScoreExecutionReason::MissingConnectedPositionAuthority,
                    ScoreExecutionReason::NumericConnectedPositionConflict,
                ),
                RelationType::Touching => (
                    ScoreExecutionReason::UnsupportedTouchingPrimitive,
                    ScoreExecutionReason::UnsupportedTouchingStructure,
                    ScoreExecutionReason::MissingTouchingReference,
                    ScoreExecutionReason::TouchingReferenceOmitted,
                    ScoreExecutionReason::MissingTouchingPositionAuthority,
                    ScoreExecutionReason::NumericTouchingPositionConflict,
                ),
                RelationType::Along => (
                    ScoreExecutionReason::UnsupportedAlongPrimitive,
                    ScoreExecutionReason::UnsupportedAlongStructure,
                    ScoreExecutionReason::MissingAlongReference,
                    ScoreExecutionReason::AlongReferenceOmitted,
                    ScoreExecutionReason::MissingAlongPositionAuthority,
                    ScoreExecutionReason::NumericAlongPositionConflict,
                ),
                RelationType::Cutting => (
                    ScoreExecutionReason::UnsupportedCuttingPrimitive,
                    ScoreExecutionReason::UnsupportedCuttingStructure,
                    ScoreExecutionReason::MissingCuttingReference,
                    ScoreExecutionReason::CuttingReferenceOmitted,
                    ScoreExecutionReason::MissingCuttingPositionAuthority,
                    ScoreExecutionReason::NumericCuttingPositionConflict,
                ),
                _ => return Err(ScoreExecutionReason::UnsupportedTransformGroupRelation),
            };
        if self.structural[source]
            || relation
                .target_instruction_index
                .is_some_and(|target| self.structural.get(target).copied().unwrap_or(false))
        {
            return Err(structure);
        }
        relation.position_authority.ok_or(authority_missing)?;
        let (start, end, _, _) =
            crate::affine_geometry::endpoints(instruction, canvas, self.transforms[source])
                .ok_or(unsupported)?;
        let exact = |target: Point| ExternalConstraint {
            source,
            preferred: Point::new(target.x - start.x, target.y - start.y),
            predicate: TranslationPredicate::Exact(Point::new(
                target.x - start.x,
                target.y - start.y,
            )),
            numeric_reason,
        };
        if relation.kind == RelationType::Connected {
            return Ok(exact(self.connected_target(source, relation)?));
        }
        let target = relation
            .target_instruction_index
            .filter(|&target| Some(target) == source.checked_sub(1))
            .ok_or(missing)?;
        let prior = self.prior(target).ok_or(omitted)?;
        let (target_start, target_end, _, _) =
            crate::affine_geometry::endpoints(prior, canvas, self.transforms[target])
                .ok_or(unsupported)?;
        let vector = Point::new(end.x - start.x, end.y - start.y);
        let target_vector =
            Point::new(target_end.x - target_start.x, target_end.y - target_start.y);
        let length = distance(vector);
        let target_length = distance(target_vector);
        if length <= GEOMETRY_EPSILON || target_length <= GEOMETRY_EPSILON {
            return Err(unsupported);
        }
        if relation.kind == RelationType::Touching {
            relation
                .touching_constraints
                .ok_or(ScoreExecutionReason::MissingTouchingConstraints)?;
            if !matches!(instruction.primitive, Primitive::Line | Primitive::Arc)
                || !matches!(prior.primitive, Primitive::Line | Primitive::Arc)
            {
                return Err(unsupported);
            }
            if (length - target_length).abs() > GEOMETRY_EPSILON {
                return Err(ScoreExecutionReason::TouchingGeometryConflict);
            }
            if distance(Point::new(
                vector.x - target_vector.x,
                vector.y - target_vector.y,
            )) > GEOMETRY_EPSILON
            {
                return Err(ScoreExecutionReason::TouchingDirectionConflict);
            }
            return Ok(exact(target_start));
        }
        if instruction.primitive != Primitive::Line || prior.primitive != Primitive::Line {
            return Err(unsupported);
        }
        let center = Point::new((start.x + end.x) / 2.0, (start.y + end.y) / 2.0);
        let parallel = (vector.x * target_vector.y - vector.y * target_vector.x).abs()
            / (length * target_length)
            <= GEOMETRY_EPSILON;
        let seed = self.request.performance_seed.unwrap_or_default();
        let ordinal = self.performed[source]
            .last()
            .expect("performed member")
            .ordinal;
        if relation.kind == RelationType::Along {
            if instruction.rotation.is_none() && !parallel {
                return Err(ScoreExecutionReason::AlongDirectionConflict);
            }
            let target = typed_along_target(
                target_start,
                target_end,
                relation.gap,
                seed,
                ordinal,
                canvas,
            )
            .ok_or(unsupported)?;
            return Ok(ExternalConstraint {
                source,
                preferred: Point::new(target.x - center.x, target.y - center.y),
                predicate: TranslationPredicate::Along {
                    center,
                    start: target_start,
                    end: target_end,
                    gap: relation.gap,
                },
                numeric_reason,
            });
        }
        if parallel {
            return Err(ScoreExecutionReason::CuttingDirectionConflict);
        }
        let factor = 0.18 + 0.64 * crate::determinism::hash01(ordinal as i64, seed, "cutting-t");
        let target = Point::new(
            target_start.x + target_vector.x * factor,
            target_start.y + target_vector.y * factor,
        );
        Ok(ExternalConstraint {
            source,
            preferred: Point::new(target.x - center.x, target.y - center.y),
            predicate: TranslationPredicate::Cutting {
                start,
                end,
                target_start,
                target_end,
            },
            numeric_reason,
        })
    }

    fn correct_external_relations(&mut self, index: usize) -> Result<(), ScoreExecutionReason> {
        let group = &self.request.score.transform_groups[index];
        let mut constraints = Vec::new();
        for source in group.start..group.end {
            if self.schedule.external_groups[source] != Some(index)
                || self.omitted_relations[source]
            {
                continue;
            }
            match self.external_constraint(source) {
                Ok(constraint) => constraints.push(constraint),
                Err(reason) => self.drop_relation(source, reason),
            }
        }
        let zero = Point::new(0.0, 0.0);
        let fixed = !group.fixed_position_indices.is_empty()
            || group
                .anchor_indices
                .iter()
                .any(|&anchor| self.request.score.anchors[anchor].position.is_some())
            || (group.start..group.end).any(|source| {
                self.request.score.instructions[source]
                    .relation
                    .as_ref()
                    .is_some_and(|relation| {
                        relation.position_authority
                            == Some(ConnectedPositionAuthority::NumericFixed)
                    })
            });
        // Check semantic predicates at every proposed translation. Two Along or
        // Cutting relations need not choose the same preferred point to coexist.
        let correction = std::iter::once(zero)
            .chain(
                constraints
                    .iter()
                    .filter(|_| !fixed)
                    .map(|constraint| constraint.preferred),
            )
            .find(|&candidate| {
                candidate.x.is_finite()
                    && candidate.y.is_finite()
                    && constraints
                        .iter()
                        .all(|constraint| constraint.accepts(candidate))
            });
        let delta = correction.unwrap_or(zero);
        if correction.is_none() {
            for constraint in &constraints {
                if !constraint.accepts(zero) {
                    self.drop_relation(
                        constraint.source,
                        if fixed {
                            constraint.numeric_reason
                        } else {
                            ScoreExecutionReason::ConflictingRelationConstraints
                        },
                    );
                }
            }
        }
        // No mutation precedes the common decision, so a failed relation cannot
        // leave behind a partial translation or change any member's geometry.
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
        Ok(())
    }

    fn perform_group(&mut self, index: usize) -> Result<(), ScoreExecutionReason> {
        if index < self.request.score.placement_groups.len() {
            return self.perform_placement(index);
        }
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
        self.correct_external_relations(index)?;
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

    fn perform_placement(&mut self, index: usize) -> Result<(), ScoreExecutionReason> {
        let group = &self.request.score.placement_groups[index];
        let mut placed = None;
        let mut domain =
            crate::geometry::point_to_short_side_units(Point::new(1.0, 1.0), self.request.canvas);
        let count = group.end - group.start;
        let seed = self.request.performance_seed.unwrap_or_default();
        if group.layout == inku_score::GroupLayout::Tile {
            domain.x *= group.at.region[2] - group.at.region[0];
            domain.y *= group.at.region[3] - group.at.region[1];
        }
        let columns = if group.layout == inku_score::GroupLayout::Tile {
            let landscape = domain.x >= domain.y;
            let long_count = if domain.x == 0.0 || domain.y == 0.0 {
                count
            } else {
                let aspect = if landscape {
                    domain.x / domain.y
                } else {
                    domain.y / domain.x
                };
                ((count as f64 * aspect).sqrt().ceil() as usize).min(count)
            };
            if landscape {
                long_count
            } else {
                count.div_ceil(long_count)
            }
        } else {
            1
        };
        let rows = count.div_ceil(columns);
        for member in group.start..group.end {
            let value = self.performed[member]
                .last()
                .ok_or(ScoreExecutionReason::UnsupportedTransformGroupRelation)?;
            let bounds = crate::affine_geometry::bounds(
                &value.instruction,
                self.request.performance_seed,
                value.ordinal,
                self.request.canvas,
                value.seed_override,
                self.transforms[member],
            )
            .ok_or(ScoreExecutionReason::UnsupportedTransformGroupRelation)?;
            let center = bounds.center();
            let ordinal = member - group.start;
            let target = match group.layout {
                inku_score::GroupLayout::Overlap => Point::new(0.0, 0.0),
                inku_score::GroupLayout::HorizontalSourceOrder => {
                    Point::new(ordinal as f64 * domain.x / count as f64, 0.0)
                }
                inku_score::GroupLayout::Scatter => {
                    let sampled = crate::placement::scatter_position(ordinal, seed, 0.0);
                    Point::new(sampled.x * domain.x, sampled.y * domain.y)
                }
                inku_score::GroupLayout::Tile => Point::new(
                    (ordinal % columns) as f64 * domain.x / columns as f64,
                    (ordinal / columns) as f64 * domain.y / rows as f64,
                ),
            };
            let delta = Point::new(target.x - center.x, target.y - center.y);
            self.transforms[member] =
                AffineTransform::translation(delta).compose(self.transforms[member]);
            merge_bounds(
                &mut placed,
                Bounds {
                    min: Point::new(bounds.min.x + delta.x, bounds.min.y + delta.y),
                    max: Point::new(bounds.max.x + delta.x, bounds.max.y + delta.y),
                },
            );
        }
        let [x0, y0, x1, y1] = group.at.region;
        let target = crate::geometry::point_to_short_side_units(
            Point::new(
                x0 + (x1 - x0)
                    * crate::determinism::hash01(index as i64, seed, "placement-group-x"),
                y0 + (y1 - y0)
                    * crate::determinism::hash01(index as i64, seed, "placement-group-y"),
            ),
            self.request.canvas,
        );
        let center = placed.expect("validated nonempty placement").center();
        let translation =
            AffineTransform::translation(Point::new(target.x - center.x, target.y - center.y));
        for member in group.start..group.end {
            self.transforms[member] = translation.compose(self.transforms[member]);
        }
        for member in group.start..group.end {
            if self.schedule.external_groups[member].is_none()
                && self
                    .prior(member)
                    .is_some_and(|instruction| instruction.relation.is_some())
            {
                match self.external_constraint(member) {
                    Ok(constraint) if constraint.accepts(Point::new(0.0, 0.0)) => {}
                    Ok(_) => self.drop_relation(
                        member,
                        ScoreExecutionReason::ConflictingRelationConstraints,
                    ),
                    Err(reason) => self.drop_relation(member, reason),
                }
                for value in &mut self.performed[member] {
                    value.instruction.relation = None;
                }
            }
        }
        self.correct_external_relations(index)
    }
}

pub(super) fn resolve(
    request: PerformanceRequest<'_>,
    _policy: ScoreErrorPolicy,
) -> Result<PerformancePlan, CheckedPerformanceError> {
    let policy = ScoreErrorPolicy::OmitAndContinue;
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
    // Placement and affine transforms have separate wire contracts, while their
    // dependency scopes share the existing scheduler and relation recovery.
    let original_score = request.score;
    let scoped_score = if original_score.placement_groups.is_empty() {
        std::borrow::Cow::Borrowed(original_score)
    } else {
        let mut scoped_score = original_score.clone();
        let mut scopes = original_score
            .placement_groups
            .iter()
            .map(|group| TransformGroup {
                start: group.start,
                end: group.end,
                rotation_degrees: 0.0,
                scale_x: 1.0,
                scale_y: 1.0,
                translate_x: 0.0,
                translate_y: 0.0,
                fixed_position_indices: Vec::new(),
                anchor_indices: Vec::new(),
            })
            .collect::<Vec<_>>();
        scopes.extend(scoped_score.transform_groups.iter().cloned());
        scoped_score.transform_groups = scopes;
        std::borrow::Cow::Owned(scoped_score)
    };
    let request = PerformanceRequest {
        score: &scoped_score,
        ..request
    };
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
    let mut omitted_relations = vec![false; request.score.instructions.len()];
    let mut diagnostics = Vec::new();
    let mut dependency_schedule = schedule(request.score, &omitted_relations);
    while !dependency_schedule.cyclic_relations.is_empty() {
        for &source in &dependency_schedule.cyclic_relations {
            omitted_relations[source] = true;
            diagnostics.push(relation_failure(
                request.score,
                source,
                ScoreExecutionReason::CyclicConnectedDependency,
            ));
        }
        dependency_schedule = schedule(request.score, &omitted_relations);
    }
    let mut execution = Execution {
        request,
        schedule: dependency_schedule,
        performed: (0..request.score.instructions.len())
            .map(|_| Vec::new())
            .collect(),
        transforms: vec![AffineTransform::identity(); request.score.instructions.len()],
        anchors,
        omitted: vec![false; request.score.instructions.len()],
        omitted_groups: vec![false; request.score.transform_groups.len()],
        structural: structural_instruction_indices(request.score),
        warnings: Vec::new(),
        omitted_relations,
        diagnostics,
    };
    for node in execution.schedule.order.clone() {
        let failure = match node {
            ScheduleNode::Instruction(index) => {
                if execution.omitted[index] {
                    continue;
                }
                for &ordinal in &ordinals[index] {
                    let instruction = match execution.prepare_instruction(
                        index,
                        ordinal,
                        &expanded.instructions[ordinal],
                    ) {
                        Ok(instruction) => instruction,
                        Err(reason) => {
                            execution.drop_relation(index, reason);
                            let mut instruction = execution
                                .placed_instruction(ordinal, &expanded.instructions[ordinal]);
                            instruction.relation = None;
                            instruction
                        }
                    };
                    let seed_override =
                        in_any_transform_group(&request.score.transform_groups, index).then(|| {
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
                None
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
            execution
                .diagnostics
                .push(node_failure(request.score, node, reason, policy));
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
        execution.diagnostics.push(diagnostic);
        return Err(CheckedPerformanceError {
            diagnostics: execution.diagnostics,
        });
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
    score.placement_groups.clear();
    let summary = (!execution.diagnostics.is_empty()).then(|| ScoreExecutionSummary {
        input_score_digest: canonical_score_digest(original_score)
            .expect("typed Score canonicalization"),
        diagnostics: execution.diagnostics,
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
