//! Bounded Score 0.10 template performance.

use std::collections::{BTreeMap, HashSet};

use inku_score::{
    FillGroup, FillTargetAnchor, FillTargetGeometry, MirrorBodyRef, MirrorFollowerFactsV1,
    PlacementMember, ResolvedPlacementAnchor, ResolvedPlacementRecipe, ScoreExecutionDiagnostic,
    ScoreExecutionDisposition, ScoreExecutionReason, SymbolicMemberKind, TransformGroup,
};
use sha2::{Digest, Sha256};

use crate::fill_geometry::{PreparedRegion, RegionError};
use crate::performance::{PerformancePlan, PerformanceRequest, PerformedFillScope};
use crate::types::{ArcForm, Point, Primitive, Score, Seed};

#[derive(Clone, Debug)]
pub(crate) struct TypedPlacementScope {
    /// Exact final center for each dense member, in canvas-short-edge units.
    pub member_centers: Vec<Point>,
    /// Nested fill targets translated with each complete member body.
    pub member_fill_scope_indices: Vec<Vec<usize>>,
}

#[derive(Clone, Debug)]
pub(crate) struct TypedExecutionPlan {
    /// Canonical digest of the validated compact Score before materialization.
    pub input_score_digest: String,
    /// Parallel to the dense Score's placement groups.
    pub placement_scopes: Vec<TypedPlacementScope>,
    /// Fill targets translated by a placement scope's external relation only.
    pub placement_fill_scope_indices: Vec<Vec<usize>>,
    /// Fill targets transformed by each dense affine group.
    pub transform_fill_scope_indices: Vec<Vec<usize>>,
    /// Stable brush seeds parallel to dense instructions.
    pub instruction_seed_overrides: Vec<Option<crate::types::Seed>>,
    /// Innermost fill scope parallel to dense instructions.
    pub instruction_fill_scope_indices: Vec<Option<usize>>,
    /// Prepared contours in canvas-short-edge units until execution completes.
    pub fill_scopes: Vec<PerformedFillScope>,
    /// Recoverable contour omissions discovered before dependency execution.
    pub diagnostics: Vec<ScoreExecutionDiagnostic>,
    /// Dense bodies selected from fixed Score mirror references.
    pub mirror_relations: Vec<TypedMirrorRelation>,
}

#[derive(Clone, Debug)]
pub(crate) struct TypedMirrorBody {
    pub instruction_indices: Vec<usize>,
    pub anchor_indices: Vec<usize>,
    pub fill_scope_indices: Vec<usize>,
    /// Runtime expansion identity; it never appears in the saved Score wire.
    pub context_path: Vec<u64>,
    pub semantic_anchor: Option<Point>,
    pub placement_pending: bool,
    pub primitive_body: bool,
}

#[derive(Clone, Debug)]
pub(crate) struct TypedMirrorRelation {
    pub target_bodies: Vec<TypedMirrorBody>,
    pub follower_bodies: Vec<TypedMirrorBody>,
    pub follower_facts: MirrorFollowerFactsV1,
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
enum GroupId {
    Placement(usize),
    Fill(usize),
    Repetition(usize),
}

#[derive(Default)]
struct ContextMap {
    instructions: BTreeMap<usize, Vec<usize>>,
    anchors: BTreeMap<usize, usize>,
    path: Vec<u64>,
    parent: Option<usize>,
}

#[derive(Default)]
struct Fragment {
    start: usize,
    end: usize,
    scopes: Vec<usize>,
}

struct PendingRelation {
    output: usize,
    context: usize,
    instruction_target: Option<usize>,
    anchor_target: Option<usize>,
}

struct DensePlacement {
    group: inku_score::PlacementGroup,
    execution: TypedPlacementScope,
    fill_scopes: Vec<usize>,
    source_placement_group_index: Option<usize>,
    source_member_indices: Vec<usize>,
}

/// Materializes a compact Score into the dense Score the shared executor runs.
///
/// Instruction-indexed vectors run parallel to `output.instructions`; anchor
/// vectors to `output.anchors`. "Source" indices refer to the compact Score.
struct Builder<'a> {
    request: PerformanceRequest<'a>,
    /// Dense Score being built; its groups are rebuilt from the compact ones.
    output: Score,
    original_instruction_indices: Vec<usize>,
    original_anchor_indices: Vec<usize>,
    /// Instance seeds from the source owner, context path and instance ordinal.
    instruction_seed_overrides: Vec<Option<Seed>>,
    /// Innermost fill scope of each dense instruction.
    instruction_fill_scope_indices: Vec<Option<usize>>,
    /// Ordinals of the enclosing repetitions that produced each instruction.
    instruction_context_paths: Vec<Vec<u64>>,
    /// Placement target or source anchor, in short-side units; mirror bodies use it.
    instruction_semantic_anchors: Vec<Option<Point>>,
    /// Expansion contexts; each maps source indices to its copies and those of its children.
    contexts: Vec<ContextMap>,
    /// Every dense copy of each source instruction and anchor.
    global_instructions: BTreeMap<usize, Vec<usize>>,
    global_anchors: BTreeMap<usize, Vec<usize>>,
    /// Relation targets remapped once every copy exists.
    pending_relations: Vec<PendingRelation>,
    placements: Vec<DensePlacement>,
    /// Mirror bodies produced by each repetition group.
    repetition_bodies: Vec<Vec<TypedMirrorBody>>,
    /// Fill scopes transformed with each dense transform group.
    transform_fill_scope_indices: Vec<Vec<usize>>,
    fill_scopes: Vec<PerformedFillScope>,
    /// Source instruction range of each fill scope.
    scope_sources: Vec<(usize, usize)>,
    diagnostics: Vec<ScoreExecutionDiagnostic>,
    /// Top-level transform groups already cloned into `output`.
    cloned_top_transforms: HashSet<usize>,
}

impl<'a> Builder<'a> {
    fn new(request: PerformanceRequest<'a>) -> Self {
        let mut output = request.score.clone();
        output.instructions.clear();
        output.anchors.clear();
        output.transform_groups.clear();
        output.placement_groups.clear();
        output.repetition_groups.clear();
        output.fill_groups.clear();
        output.mirror_relations.clear();
        output.resource_policy = None;
        Self {
            request,
            output,
            original_instruction_indices: Vec::new(),
            original_anchor_indices: Vec::new(),
            instruction_seed_overrides: Vec::new(),
            instruction_fill_scope_indices: Vec::new(),
            instruction_context_paths: Vec::new(),
            instruction_semantic_anchors: Vec::new(),
            contexts: vec![ContextMap::default()],
            global_instructions: BTreeMap::new(),
            global_anchors: BTreeMap::new(),
            pending_relations: Vec::new(),
            placements: Vec::new(),
            repetition_bodies: vec![Vec::new(); request.score.repetition_groups.len()],
            transform_fill_scope_indices: Vec::new(),
            fill_scopes: Vec::new(),
            scope_sources: Vec::new(),
            diagnostics: Vec::new(),
            cloned_top_transforms: HashSet::new(),
        }
    }

    fn seed(&self) -> Seed {
        self.request.performance_seed.unwrap_or_default()
    }

    fn new_context(&mut self, parent: usize, ordinal: u64) -> usize {
        let mut path = self.contexts[parent].path.clone();
        path.push(ordinal);
        let index = self.contexts.len();
        self.contexts.push(ContextMap {
            path,
            parent: Some(parent),
            ..ContextMap::default()
        });
        index
    }

    fn clone_anchor(&mut self, context: usize, old: usize) -> usize {
        if let Some(&existing) = self.contexts[context].anchors.get(&old) {
            return existing;
        }
        let new = self.output.anchors.len();
        self.output
            .anchors
            .push(self.request.score.anchors[old].clone());
        self.original_anchor_indices.push(old);
        self.contexts[context].anchors.insert(old, new);
        self.global_anchors.entry(old).or_default().push(new);
        new
    }

    fn clone_instruction(
        &mut self,
        context: usize,
        old: usize,
        instance_ordinal: u64,
        target: Option<Point>,
        innermost_fill: Option<usize>,
    ) {
        let original = &self.request.score.instructions[old];
        let arrangement = original
            .arrangement
            .as_ref()
            .expect("validated Score 0.10 arrangement");
        let resolved = arrangement
            .resolved
            .as_ref()
            .expect("validated Score 0.10 arrangement");
        let mut instruction = crate::planning::ensure_line_coordinates(original);
        crate::group::apply_color_cycle_at_ordinal(
            &mut instruction,
            &arrangement.color_cycle,
            instance_ordinal,
        );
        instruction.arrangement = None;
        if let Some(target) = target {
            instruction = translate_instruction_to(&instruction, target, self.request.canvas);
        } else {
            let neutral_anchor = crate::geometry::point_to_short_side_units(
                crate::planning::instruction_anchor_on_canvas(&instruction, self.request.canvas),
                self.request.canvas,
            );
            instruction =
                translate_instruction_to(&instruction, neutral_anchor, self.request.canvas);
        }
        let output = self.output.instructions.len();
        let relation = instruction.relation.as_ref();
        self.pending_relations.push(PendingRelation {
            output,
            context,
            instruction_target: relation.and_then(|value| value.target_instruction_index),
            anchor_target: relation.and_then(|value| value.target_anchor_index),
        });
        self.output.instructions.push(instruction);
        self.original_instruction_indices.push(old);
        self.instruction_seed_overrides.push(Some(instance_seed(
            &resolved.owner,
            &self.contexts[context].path,
            instance_ordinal,
            self.request.performance_seed,
        )));
        self.instruction_fill_scope_indices.push(innermost_fill);
        self.instruction_context_paths
            .push(self.contexts[context].path.clone());
        self.instruction_semantic_anchors
            .push(Some(target.unwrap_or_else(|| {
                crate::geometry::point_to_short_side_units(
                    crate::planning::instruction_anchor_on_canvas(original, self.request.canvas),
                    self.request.canvas,
                )
            })));
        // Enclosing Macro transforms also own instructions expanded in an
        // inner fill's child context. Retain their full descendant span.
        let mut enclosing = Some(context);
        while let Some(index) = enclosing {
            self.contexts[index]
                .instructions
                .entry(old)
                .or_default()
                .push(output);
            enclosing = self.contexts[index].parent;
        }
        self.global_instructions
            .entry(old)
            .or_default()
            .push(output);
    }

    fn expand_instruction(
        &mut self,
        context: usize,
        old: usize,
        innermost_fill: Option<usize>,
    ) -> Fragment {
        let arrangement = self.request.score.instructions[old]
            .arrangement
            .as_ref()
            .expect("validated Score 0.10 arrangement");
        let resolved = arrangement
            .resolved
            .as_ref()
            .expect("validated Score 0.10 resolved arrangement");
        let count = usize::try_from(arrangement.count).expect("u32 fits usize");
        let placement_seed = scoped_seed(
            self.seed(),
            "arrangement",
            &resolved.owner,
            &self.contexts[context].path,
        );
        let centers = recipe_centers(
            &resolved.recipe,
            &resolved.anchor,
            resolved.domain,
            count,
            resolved.first_instance_ordinal,
            placement_seed,
            0,
            self.request.canvas,
        );
        let centers = crate::arrangement_performance::shape_centers(
            arrangement,
            &resolved.recipe,
            centers,
            resolved.domain,
            placement_seed,
        );
        // recipe_centers makes one center per member and shape_centers only
        // moves them, so the centers number the members.
        debug_assert_eq!(centers.len(), count);
        let anchored = !matches!(resolved.anchor, ResolvedPlacementAnchor::EnclosingGroup);
        let start = self.output.instructions.len();
        for (instance, &center) in centers.iter().enumerate() {
            self.clone_instruction(
                context,
                old,
                resolved.first_instance_ordinal + instance as u64,
                anchored.then_some(center),
                innermost_fill,
            );
        }
        let end = self.output.instructions.len();
        let arrangement = self.request.score.instructions[old]
            .arrangement
            .as_ref()
            .expect("validated Score 0.10 arrangement");
        crate::arrangement_performance::finish_members(
            &mut self.output.instructions[start..end],
            arrangement,
            &arrangement.resolved.as_ref().expect("validated").recipe,
            placement_seed,
            self.request.canvas,
        );
        Fragment {
            start,
            end,
            ..Fragment::default()
        }
    }

    fn group_range(&self, id: GroupId) -> (usize, usize) {
        match id {
            GroupId::Placement(index) => {
                let group = &self.request.score.placement_groups[index];
                (group.start, group.end)
            }
            GroupId::Fill(index) => {
                let group = &self.request.score.fill_groups[index];
                (group.start, group.end)
            }
            GroupId::Repetition(index) => {
                let member = &self.request.score.repetition_groups[index].member;
                (member.start, member.end)
            }
        }
    }

    fn group_is_macro(&self, id: GroupId) -> bool {
        match id {
            GroupId::Placement(index) => &self.request.score.placement_groups[index].members,
            GroupId::Fill(index) => &self.request.score.fill_groups[index].members,
            GroupId::Repetition(index) => {
                return self.request.score.repetition_groups[index]
                    .member
                    .symbolic
                    .as_ref()
                    .is_some_and(|value| value.kind == SymbolicMemberKind::Macro);
            }
        }
        .iter()
        .any(|member| {
            member
                .symbolic
                .as_ref()
                .is_some_and(|value| value.kind == SymbolicMemberKind::Macro)
        })
    }

    fn group_at(&self, start: usize, end: usize, skipped: &[GroupId]) -> Option<GroupId> {
        let candidates = self
            .request
            .score
            .placement_groups
            .iter()
            .enumerate()
            .map(|(index, _)| GroupId::Placement(index))
            .chain(
                self.request
                    .score
                    .fill_groups
                    .iter()
                    .enumerate()
                    .map(|(index, _)| GroupId::Fill(index)),
            )
            .chain(
                self.request
                    .score
                    .repetition_groups
                    .iter()
                    .enumerate()
                    .map(|(index, _)| GroupId::Repetition(index)),
            );
        candidates
            .filter(|id| !skipped.contains(id))
            .filter(|&id| {
                let range = self.group_range(id);
                range.0 == start && range.1 <= end
            })
            .max_by_key(|&id| {
                let range = self.group_range(id);
                (
                    range.1 - range.0,
                    self.group_is_macro(id),
                    matches!(id, GroupId::Fill(_)),
                )
            })
    }

    fn expand_range(
        &mut self,
        context: usize,
        start: usize,
        end: usize,
        skipped: &[GroupId],
        innermost_fill: Option<usize>,
    ) -> Fragment {
        let output_start = self.output.instructions.len();
        let scope_start = self.fill_scopes.len();
        let mut cursor = start;
        while cursor < end {
            if let Some(group) = self.group_at(cursor, end, skipped) {
                let group_end = self.group_range(group).1;
                self.expand_group(context, group, skipped, innermost_fill);
                cursor = group_end;
            } else {
                self.expand_instruction(context, cursor, innermost_fill);
                cursor += 1;
            }
        }
        Fragment {
            start: output_start,
            end: self.output.instructions.len(),
            scopes: (scope_start..self.fill_scopes.len()).collect(),
        }
    }

    fn expand_group(
        &mut self,
        parent_context: usize,
        id: GroupId,
        skipped: &[GroupId],
        parent_fill: Option<usize>,
    ) {
        let mut next_skipped = skipped.to_vec();
        next_skipped.push(id);
        match id {
            GroupId::Placement(index) => {
                let group = self.request.score.placement_groups[index].clone();
                let resolved = group
                    .resolved
                    .as_ref()
                    .expect("validated placement metadata");
                let placement_seed = scoped_seed(
                    self.seed(),
                    "placement-group",
                    &resolved.owner,
                    &self.contexts[parent_context].path,
                );
                let centers = recipe_centers(
                    &resolved.recipe,
                    &resolved.anchor,
                    resolved.domain,
                    usize::try_from(resolved.logical_count).expect("admitted count fits usize"),
                    0,
                    placement_seed,
                    0,
                    self.request.canvas,
                );
                let (members, fragment, member_fill_scope_indices, source_member_indices) =
                    if let Some(cycle) = &group.cycle_members {
                        self.expand_cycle_members(
                            parent_context,
                            &group.members,
                            cycle.occurrence_count,
                            &next_skipped,
                            parent_fill,
                        )
                    } else {
                        self.expand_members(
                            parent_context,
                            &group.members,
                            &next_skipped,
                            parent_fill,
                        )
                    };
                let dense = inku_score::PlacementGroup {
                    start: fragment.start,
                    end: fragment.end,
                    members,
                    cycle_members: None,
                    ..group
                };
                self.placements.push(DensePlacement {
                    group: dense,
                    execution: TypedPlacementScope {
                        member_centers: centers,
                        member_fill_scope_indices,
                    },
                    fill_scopes: fragment.scopes,
                    source_placement_group_index: Some(index),
                    source_member_indices,
                });
                let scopes = self
                    .placements
                    .last()
                    .expect("just pushed placement")
                    .fill_scopes
                    .clone();
                self.assign_atomic_unit(&scopes, fragment.start, fragment.end);
            }
            GroupId::Fill(index) => {
                let group = self.request.score.fill_groups[index].clone();
                let fill_seed = scoped_seed(
                    self.seed(),
                    "fill-group",
                    &group.owner,
                    &self.contexts[parent_context].path,
                );
                let region = match prepare_fill_target(&group, fill_seed, 0, self.request.canvas) {
                    Ok(region) => region,
                    Err(_) => {
                        self.diagnostics.push(ScoreExecutionDiagnostic {
                            instruction_index: group.start,
                            anchor_index: None,
                            dependency_instruction_index: None,
                            reason: ScoreExecutionReason::InvalidFillTarget,
                            disposition: ScoreExecutionDisposition::Omitted,
                        });
                        return;
                    }
                };
                let scope = self.fill_scopes.len();
                self.fill_scopes.push(PerformedFillScope {
                    owner: group.owner.clone(),
                    prepared_region: region.clone(),
                    parent_scope_index: parent_fill,
                    instruction_indices: Vec::new(),
                    atomic_instruction_groups: Vec::new(),
                });
                self.scope_sources.push((group.start, group.end));
                let mut centers = Vec::with_capacity(
                    usize::try_from(group.logical_count).expect("admitted count fits usize"),
                );
                if let Some(cycle) = &group.cycle_members {
                    for occurrence in 0..cycle.occurrence_count {
                        centers.push(region.sample(
                            fill_seed,
                            0,
                            0,
                            usize::try_from(occurrence).expect("admitted count fits usize"),
                        ));
                    }
                } else {
                    for member in &group.members {
                        let symbolic = member.symbolic.as_ref().expect("validated fill member");
                        let count = usize::try_from(symbolic.instance_count)
                            .expect("admitted count fits usize");
                        for instance in 0..count {
                            centers.push(region.sample(
                                fill_seed,
                                0,
                                usize::try_from(symbolic.member_ordinal).unwrap_or(usize::MAX),
                                instance,
                            ));
                        }
                    }
                }
                let (members, mut fragment, member_fill_scope_indices, _) = if let Some(cycle) =
                    &group.cycle_members
                {
                    self.expand_cycle_members(
                        parent_context,
                        &group.members,
                        cycle.occurrence_count,
                        &next_skipped,
                        Some(scope),
                    )
                } else {
                    self.expand_members(parent_context, &group.members, &next_skipped, Some(scope))
                };
                fragment.scopes.push(scope);
                let dense = inku_score::PlacementGroup {
                    start: fragment.start,
                    end: fragment.end,
                    layout: inku_score::GroupLayout::Scatter,
                    at: inku_score::AtRegion {
                        region: [0.0, 0.0, 1.0, 1.0],
                    },
                    members,
                    cycle_members: None,
                    resolved: None,
                };
                self.placements.push(DensePlacement {
                    group: dense,
                    execution: TypedPlacementScope {
                        member_centers: centers,
                        member_fill_scope_indices,
                    },
                    fill_scopes: fragment.scopes,
                    source_placement_group_index: None,
                    source_member_indices: Vec::new(),
                });
                let scopes = self
                    .placements
                    .last()
                    .expect("just pushed fill placement")
                    .fill_scopes
                    .clone();
                self.assign_atomic_unit(&scopes, fragment.start, fragment.end);
            }
            GroupId::Repetition(index) => {
                let member = self.request.score.repetition_groups[index].member.clone();
                let (members, fragment, member_fill_scope_indices, _) = self.expand_members(
                    parent_context,
                    std::slice::from_ref(&member),
                    &next_skipped,
                    parent_fill,
                );
                self.repetition_bodies[index].extend(
                    members
                        .iter()
                        .zip(member_fill_scope_indices.iter())
                        .map(|(member, scopes)| TypedMirrorBody {
                            instruction_indices: (member.start..member.end).collect(),
                            anchor_indices: member.anchor_indices.clone(),
                            fill_scope_indices: scopes.clone(),
                            context_path: self.instruction_context_paths[member.start].clone(),
                            semantic_anchor: self.instruction_semantic_anchors[member.start],
                            placement_pending: false,
                            primitive_body: false,
                        }),
                );
                self.assign_atomic_unit(&fragment.scopes, fragment.start, fragment.end);
            }
        }
    }

    fn assign_atomic_unit(&mut self, scopes: &[usize], start: usize, end: usize) {
        let instructions = (start..end).collect::<Vec<_>>();
        for &scope in scopes {
            if self.fill_scopes[scope].atomic_instruction_groups.last() != Some(&instructions) {
                self.fill_scopes[scope]
                    .atomic_instruction_groups
                    .push(instructions.clone());
            }
        }
    }

    fn expand_members(
        &mut self,
        parent_context: usize,
        members: &[PlacementMember],
        skipped: &[GroupId],
        innermost_fill: Option<usize>,
    ) -> (Vec<PlacementMember>, Fragment, Vec<Vec<usize>>, Vec<usize>) {
        let output_start = self.output.instructions.len();
        let scope_start = self.fill_scopes.len();
        let mut dense_members = Vec::new();
        let mut member_fill_scope_indices = Vec::new();
        let mut source_member_indices = Vec::new();
        for (source_member_index, member) in members.iter().enumerate() {
            let symbolic = member.symbolic.as_ref().expect("validated symbolic member");
            for instance in 0..symbolic.instance_count {
                let (member, scopes) = self.expand_member_occurrence(
                    parent_context,
                    member,
                    symbolic.first_instance_ordinal + instance,
                    skipped,
                    innermost_fill,
                );
                member_fill_scope_indices.push(scopes);
                dense_members.push(member);
                source_member_indices.push(source_member_index);
            }
        }
        (
            dense_members,
            Fragment {
                start: output_start,
                end: self.output.instructions.len(),
                scopes: (scope_start..self.fill_scopes.len()).collect(),
            },
            member_fill_scope_indices,
            source_member_indices,
        )
    }

    fn expand_cycle_members(
        &mut self,
        parent_context: usize,
        members: &[PlacementMember],
        occurrence_count: u64,
        skipped: &[GroupId],
        innermost_fill: Option<usize>,
    ) -> (Vec<PlacementMember>, Fragment, Vec<Vec<usize>>, Vec<usize>) {
        let output_start = self.output.instructions.len();
        let scope_start = self.fill_scopes.len();
        let mut dense_members = Vec::with_capacity(
            usize::try_from(occurrence_count).expect("admitted count fits usize"),
        );
        let mut member_fill_scope_indices = Vec::with_capacity(dense_members.capacity());
        let mut source_member_indices = Vec::with_capacity(dense_members.capacity());
        for occurrence in 0..occurrence_count {
            let source_member_index = usize::try_from(occurrence % members.len() as u64)
                .expect("cycle member index fits usize");
            let member = &members[source_member_index];
            let (member, scopes) = self.expand_member_occurrence(
                parent_context,
                member,
                occurrence,
                skipped,
                innermost_fill,
            );
            member_fill_scope_indices.push(scopes);
            dense_members.push(member);
            source_member_indices.push(source_member_index);
        }
        (
            dense_members,
            Fragment {
                start: output_start,
                end: self.output.instructions.len(),
                scopes: (scope_start..self.fill_scopes.len()).collect(),
            },
            member_fill_scope_indices,
            source_member_indices,
        )
    }

    fn expand_member_occurrence(
        &mut self,
        parent_context: usize,
        member: &PlacementMember,
        occurrence: u64,
        skipped: &[GroupId],
        innermost_fill: Option<usize>,
    ) -> (PlacementMember, Vec<usize>) {
        let context = self.new_context(parent_context, occurrence);
        let anchors = member
            .anchor_indices
            .iter()
            .map(|&old| self.clone_anchor(context, old))
            .collect::<Vec<_>>();
        let fragment =
            self.expand_range(context, member.start, member.end, skipped, innermost_fill);
        let transforms =
            self.clone_transforms(context, &member.transform_group_indices, &fragment.scopes);
        (
            PlacementMember {
                start: fragment.start,
                end: fragment.end,
                anchor_indices: anchors,
                transform_group_indices: transforms,
                symbolic: None,
            },
            fragment.scopes,
        )
    }

    fn clone_transforms(
        &mut self,
        context: usize,
        transforms: &[usize],
        candidate_scopes: &[usize],
    ) -> Vec<usize> {
        let mut result = Vec::new();
        for &old in transforms {
            let source = &self.request.score.transform_groups[old];
            let instructions = &self.contexts[context].instructions;
            let mut contained = instructions
                .range(source.start..source.end)
                .flat_map(|(_, values)| values.iter().copied());
            let (start, end) = if let Some(first) = contained.next() {
                (first, contained.last().unwrap_or(first) + 1)
            } else if source.start == source.end && !source.anchor_indices.is_empty() {
                let boundary = instructions
                    .range(..source.start)
                    .next_back()
                    .and_then(|(_, values)| values.last().map(|value| value + 1))
                    .or_else(|| {
                        instructions
                            .range(source.start..)
                            .next()
                            .and_then(|(_, values)| values.first().copied())
                    })
                    .unwrap_or(self.output.instructions.len());
                (boundary, boundary)
            } else {
                continue;
            };
            let fixed_position_indices = source
                .fixed_position_indices
                .iter()
                .flat_map(|old| {
                    self.contexts[context]
                        .instructions
                        .get(old)
                        .into_iter()
                        .flatten()
                        .copied()
                })
                .collect();
            let anchor_indices = source
                .anchor_indices
                .iter()
                .map(|&anchor| self.clone_anchor(context, anchor))
                .collect();
            let dense = TransformGroup {
                start,
                end,
                fixed_position_indices,
                anchor_indices,
                ..source.clone()
            };
            let fill_scopes = candidate_scopes
                .iter()
                .copied()
                .filter(|&scope| {
                    let (fill_start, fill_end) = self.scope_sources[scope];
                    source.start <= fill_start && fill_end <= source.end
                })
                .collect();
            result.push(self.output.transform_groups.len());
            self.output.transform_groups.push(dense);
            self.transform_fill_scope_indices.push(fill_scopes);
        }
        result
    }

    fn clone_top_level_state(&mut self) {
        let owned_anchors = self
            .request
            .score
            .placement_groups
            .iter()
            .flat_map(|group| &group.members)
            .chain(
                self.request
                    .score
                    .fill_groups
                    .iter()
                    .flat_map(|group| &group.members),
            )
            .chain(
                self.request
                    .score
                    .repetition_groups
                    .iter()
                    .map(|group| &group.member),
            )
            .flat_map(|member| member.anchor_indices.iter().copied())
            .collect::<HashSet<_>>();
        for old in 0..self.request.score.anchors.len() {
            if !owned_anchors.contains(&old) {
                self.clone_anchor(0, old);
            }
        }
        let owned_transforms = self
            .request
            .score
            .placement_groups
            .iter()
            .flat_map(|group| &group.members)
            .chain(
                self.request
                    .score
                    .fill_groups
                    .iter()
                    .flat_map(|group| &group.members),
            )
            .chain(
                self.request
                    .score
                    .repetition_groups
                    .iter()
                    .map(|group| &group.member),
            )
            .flat_map(|member| member.transform_group_indices.iter().copied())
            .collect::<HashSet<_>>();
        for old in 0..self.request.score.transform_groups.len() {
            if owned_transforms.contains(&old) || !self.cloned_top_transforms.insert(old) {
                continue;
            }
            let source = &self.request.score.transform_groups[old];
            let Some(start) = self
                .global_instructions
                .get(&source.start)
                .and_then(|values| values.first())
                .copied()
            else {
                continue;
            };
            let Some(end) = source
                .end
                .checked_sub(1)
                .and_then(|last| self.global_instructions.get(&last))
                .and_then(|values| values.last())
                .map(|value| value + 1)
            else {
                continue;
            };
            let fixed_position_indices = source
                .fixed_position_indices
                .iter()
                .flat_map(|old| {
                    self.global_instructions
                        .get(old)
                        .into_iter()
                        .flatten()
                        .copied()
                })
                .collect();
            let anchor_indices = source
                .anchor_indices
                .iter()
                .filter_map(|old| {
                    self.global_anchors
                        .get(old)
                        .and_then(|values| values.first())
                })
                .copied()
                .collect();
            let fill_scopes = (0..self.fill_scopes.len())
                .filter(|&scope| {
                    let (fill_start, fill_end) = self.scope_sources[scope];
                    source.start <= fill_start && fill_end <= source.end
                })
                .collect();
            self.output.transform_groups.push(TransformGroup {
                start,
                end,
                fixed_position_indices,
                anchor_indices,
                ..source.clone()
            });
            self.transform_fill_scope_indices.push(fill_scopes);
        }
    }

    fn remap_relations(&mut self) {
        for pending in &self.pending_relations {
            let relation = self.output.instructions[pending.output].relation.as_mut();
            let Some(relation) = relation else {
                continue;
            };
            if let Some(old) = pending.instruction_target {
                relation.target_instruction_index = self.contexts[pending.context]
                    .instructions
                    .get(&old)
                    .and_then(|values| values.iter().rev().find(|&&value| value < pending.output))
                    .copied()
                    .or_else(|| {
                        self.global_instructions
                            .get(&old)
                            .and_then(|values| {
                                values.iter().rev().find(|&&value| value < pending.output)
                            })
                            .copied()
                    });
                if relation.target_instruction_index.is_none() {
                    self.output.instructions[pending.output].relation = None;
                    continue;
                }
            }
            if let Some(old) = pending.anchor_target {
                relation.target_anchor_index = self.contexts[pending.context]
                    .anchors
                    .get(&old)
                    .copied()
                    .or_else(|| {
                        let mut parent = self.contexts[pending.context].parent;
                        while let Some(index) = parent {
                            if let Some(&anchor) = self.contexts[index].anchors.get(&old) {
                                return Some(anchor);
                            }
                            parent = self.contexts[index].parent;
                        }
                        None
                    })
                    .or_else(|| {
                        self.global_anchors
                            .get(&old)
                            .and_then(|values| values.first())
                            .copied()
                    });
                if relation.target_anchor_index.is_none() {
                    self.output.instructions[pending.output].relation = None;
                }
            }
        }
    }

    fn mirror_member_body(
        &self,
        member: &PlacementMember,
        fill_scope_indices: &[usize],
        semantic_anchor: Option<Point>,
        primitive_body: bool,
    ) -> TypedMirrorBody {
        TypedMirrorBody {
            instruction_indices: (member.start..member.end).collect(),
            anchor_indices: member.anchor_indices.clone(),
            fill_scope_indices: fill_scope_indices.to_vec(),
            context_path: self.instruction_context_paths[member.start].clone(),
            semantic_anchor,
            placement_pending: true,
            primitive_body,
        }
    }

    fn mirror_bodies_for(&self, reference: &MirrorBodyRef) -> Vec<TypedMirrorBody> {
        match reference {
            MirrorBodyRef::Instruction { instruction_index } => self
                .global_instructions
                .get(instruction_index)
                .into_iter()
                .flatten()
                .map(|&index| TypedMirrorBody {
                    instruction_indices: vec![index],
                    anchor_indices: Vec::new(),
                    fill_scope_indices: self.instruction_fill_scope_indices[index]
                        .into_iter()
                        .collect(),
                    context_path: self.instruction_context_paths[index].clone(),
                    semantic_anchor: self.instruction_semantic_anchors[index],
                    placement_pending: false,
                    primitive_body: true,
                })
                .collect(),
            MirrorBodyRef::RepetitionGroup {
                repetition_group_index,
            } => self
                .repetition_bodies
                .get(*repetition_group_index)
                .cloned()
                .unwrap_or_default(),
            MirrorBodyRef::PlacementMember {
                placement_group_index,
                member_index,
            } => {
                let Some(source_member) = self
                    .request
                    .score
                    .placement_groups
                    .get(*placement_group_index)
                    .and_then(|group| group.members.get(*member_index))
                else {
                    return Vec::new();
                };
                let primitive_body = source_member
                    .symbolic
                    .as_ref()
                    .is_some_and(|member| member.kind == SymbolicMemberKind::Primitive);
                self.placements
                    .iter()
                    .filter(|placement| {
                        placement.source_placement_group_index == Some(*placement_group_index)
                    })
                    .flat_map(|placement| {
                        placement
                            .group
                            .members
                            .iter()
                            .zip(placement.execution.member_fill_scope_indices.iter())
                            .zip(placement.source_member_indices.iter())
                            .enumerate()
                            .filter(|&(_, (_, source_member))| *source_member == *member_index)
                            .map(|(dense_index, ((member, scopes), _))| {
                                self.mirror_member_body(
                                    member,
                                    scopes,
                                    placement.execution.member_centers.get(dense_index).copied(),
                                    primitive_body,
                                )
                            })
                    })
                    .collect()
            }
            MirrorBodyRef::PlacementGroup {
                placement_group_index,
            } => self
                .placements
                .iter()
                .filter(|placement| {
                    placement.source_placement_group_index == Some(*placement_group_index)
                })
                .map(|placement| {
                    let mut body = TypedMirrorBody {
                        instruction_indices: Vec::new(),
                        anchor_indices: Vec::new(),
                        fill_scope_indices: Vec::new(),
                        context_path: Vec::new(),
                        semantic_anchor: (!placement.execution.member_centers.is_empty())
                            .then(|| mean(&placement.execution.member_centers)),
                        placement_pending: true,
                        primitive_body: false,
                    };
                    for (member, scopes) in placement
                        .group
                        .members
                        .iter()
                        .zip(placement.execution.member_fill_scope_indices.iter())
                    {
                        body.instruction_indices.extend(member.start..member.end);
                        body.anchor_indices.extend(&member.anchor_indices);
                        body.fill_scope_indices.extend(scopes);
                        if body.context_path.is_empty() {
                            body.context_path =
                                self.instruction_context_paths[member.start].clone();
                        }
                    }
                    body
                })
                .collect(),
        }
    }

    fn build_mirror_relations(&self) -> Vec<TypedMirrorRelation> {
        self.request
            .score
            .mirror_relations
            .iter()
            .map(|relation| TypedMirrorRelation {
                target_bodies: self.mirror_bodies_for(&relation.target),
                follower_bodies: self.mirror_bodies_for(&relation.follower),
                follower_facts: relation.follower_facts.clone(),
            })
            .collect()
    }

    fn finish(mut self) -> (Score, TypedExecutionPlan, Vec<usize>, Vec<usize>) {
        self.expand_range(0, 0, self.request.score.instructions.len(), &[], None);
        self.clone_top_level_state();
        self.remap_relations();
        self.placements.sort_by_key(|placement| {
            (
                placement.group.end - placement.group.start,
                placement.group.start,
            )
        });
        let mirror_relations = self.build_mirror_relations();
        let mut placement_scopes = Vec::with_capacity(self.placements.len());
        let mut placement_fill_scope_indices = Vec::with_capacity(self.placements.len());
        for placement in self.placements {
            self.output.placement_groups.push(placement.group);
            placement_scopes.push(placement.execution);
            placement_fill_scope_indices.push(placement.fill_scopes);
        }
        (
            self.output,
            TypedExecutionPlan {
                input_score_digest: inku_score::canonical_score_digest(self.request.score)
                    .expect("finalized compact Score is canonical"),
                placement_scopes,
                placement_fill_scope_indices,
                transform_fill_scope_indices: self.transform_fill_scope_indices,
                instruction_seed_overrides: self.instruction_seed_overrides,
                instruction_fill_scope_indices: self.instruction_fill_scope_indices,
                fill_scopes: self.fill_scopes,
                diagnostics: self.diagnostics,
                mirror_relations,
            },
            self.original_instruction_indices,
            self.original_anchor_indices,
        )
    }
}

fn mean(points: &[Point]) -> Point {
    let total = points.iter().fold(Point::new(0.0, 0.0), |sum, point| {
        Point::new(sum.x + point.x, sum.y + point.y)
    });
    Point::new(total.x / points.len() as f64, total.y / points.len() as f64)
}

fn named_anchor(
    region: [f64; 4],
    seed: Seed,
    owner: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Point {
    let [x0, y0, x1, y1] = named_region_in_short_side_units(region, canvas);
    Point::new(
        x0 + (x1 - x0) * crate::determinism::hash01(owner as i64, seed, "typed-anchor-x"),
        y0 + (y1 - y0) * crate::determinism::hash01(owner as i64, seed, "typed-anchor-y"),
    )
}

fn named_region_in_short_side_units(
    region: [f64; 4],
    canvas: Option<crate::types::CanvasSize>,
) -> [f64; 4] {
    let [x0, y0, x1, y1] = crate::placement::region_in_short_side_units(region, canvas);
    let start = crate::geometry::point_to_short_side_units(Point::new(x0, y0), canvas);
    let end = crate::geometry::point_to_short_side_units(Point::new(x1, y1), canvas);
    [start.x, start.y, end.x, end.y]
}

fn resolved_anchor(
    anchor: &ResolvedPlacementAnchor,
    seed: Seed,
    owner: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Option<Point> {
    match anchor {
        ResolvedPlacementAnchor::Numeric { point }
        | ResolvedPlacementAnchor::GeneratedNumeric { point } => {
            Some(crate::geometry::point_to_short_side_units(*point, canvas))
        }
        ResolvedPlacementAnchor::Named { region } => {
            Some(named_anchor(*region, seed, owner, canvas))
        }
        ResolvedPlacementAnchor::EnclosingGroup => None,
    }
}

#[allow(clippy::too_many_arguments)]
fn recipe_centers(
    recipe: &ResolvedPlacementRecipe,
    anchor: &ResolvedPlacementAnchor,
    domain: Point,
    count: usize,
    first_ordinal: u64,
    seed: Seed,
    owner: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Vec<Point> {
    if count == 0 {
        return Vec::new();
    }
    let target = resolved_anchor(anchor, seed, owner, canvas);
    let mut centers = match recipe {
        ResolvedPlacementRecipe::Place => vec![Point::new(0.0, 0.0); count],
        ResolvedPlacementRecipe::HorizontalLine { cell_width } => (0..count)
            .map(|index| Point::new((index as f64 + 0.5) * cell_width, domain.y / 2.0))
            .collect(),
        ResolvedPlacementRecipe::VerticalLine { cell_height } => (0..count)
            .map(|index| Point::new(domain.x / 2.0, (index as f64 + 0.5) * cell_height))
            .collect(),
        ResolvedPlacementRecipe::DiagonalLine { step } => (0..count)
            .map(|index| Point::new(index as f64 * step.x, index as f64 * step.y))
            .collect(),
        ResolvedPlacementRecipe::Grid {
            columns,
            cell_width,
            cell_height,
            ..
        } => (0..count)
            .map(|index| {
                let index = index as u64;
                Point::new(
                    (index % columns) as f64 * cell_width + cell_width / 2.0,
                    (index / columns) as f64 * cell_height + cell_height / 2.0,
                )
            })
            .collect(),
        ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation => (0..count)
            .map(|index| {
                let ordinal = usize::try_from(first_ordinal + index as u64).unwrap_or(usize::MAX);
                let sampled = crate::placement::scatter_position(ordinal, seed, 0.0);
                Point::new(sampled.x * domain.x, sampled.y * domain.y)
            })
            .collect(),
    };
    match (recipe, anchor, target) {
        (
            ResolvedPlacementRecipe::Grid {
                centroid,
                translate_to_numeric_anchor: true,
                ..
            },
            ResolvedPlacementAnchor::Numeric { .. }
            | ResolvedPlacementAnchor::GeneratedNumeric { .. },
            Some(target),
        ) => {
            for point in &mut centers {
                point.x += target.x - centroid.x;
                point.y += target.y - centroid.y;
            }
        }
        (
            ResolvedPlacementRecipe::Grid {
                translate_to_numeric_anchor: false,
                ..
            },
            ResolvedPlacementAnchor::Named { region },
            _,
        ) => {
            let [x0, y0, _, _] = named_region_in_short_side_units(*region, canvas);
            for center in &mut centers {
                center.x += x0;
                center.y += y0;
            }
        }
        (_, ResolvedPlacementAnchor::EnclosingGroup, _) => {}
        (_, _, Some(target)) => {
            let center = mean(&centers);
            for point in &mut centers {
                point.x += target.x - center.x;
                point.y += target.y - center.y;
            }
        }
        _ => {}
    }
    centers
}

fn translate_instruction_to(
    instruction: &inku_score::Instruction,
    target: Point,
    canvas: Option<crate::types::CanvasSize>,
) -> inku_score::Instruction {
    let anchor = crate::geometry::point_to_short_side_units(
        crate::planning::instruction_anchor_on_canvas(instruction, canvas),
        canvas,
    );
    let delta = Point::new(target.x - anchor.x, target.y - anchor.y);
    let normalized = crate::geometry::point_from_short_side_units(delta, canvas);
    let moved = |point: Point| Point::new(point.x + normalized.x, point.y + normalized.y);
    let mut result = instruction.clone();
    result.at = None;
    result.from_ = result.from_.map(moved);
    result.to = result.to.map(moved);
    result.center = result.center.map(moved);
    result.position = result.position.map(moved);
    let target = crate::geometry::point_from_short_side_units(target, canvas);
    match result.primitive {
        Primitive::Line => {}
        Primitive::Square | Primitive::Triangle => {
            if result.position.is_none()
                && let Some(size) = result.size
            {
                let size = crate::geometry::size_in_normalized_axes(size, canvas);
                result.position =
                    Some(Point::new(target.x - size.x / 2.0, target.y - size.y / 2.0));
            }
        }
        _ => {
            result.center.get_or_insert(target);
        }
    }
    result
}

fn instance_seed(
    owner: &inku_score::ScoreSourceOwner,
    context: &[u64],
    ordinal: u64,
    performance_seed: Option<Seed>,
) -> Seed {
    let mut payload = serde_json::to_vec(&(owner, context, ordinal))
        .expect("typed instance seed payload is serializable");
    if let Some(seed) = performance_seed {
        payload.extend_from_slice(format!(":render:{seed}").as_bytes());
    }
    let digest = Sha256::digest(payload);
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn scoped_seed<T: serde::Serialize>(seed: Seed, purpose: &str, owner: &T, context: &[u64]) -> Seed {
    let payload = serde_json::to_vec(&(purpose, owner, context, seed))
        .expect("typed scoped seed payload is serializable");
    let digest = Sha256::digest(payload);
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn fill_anchor(
    anchor: &FillTargetAnchor,
    seed: Seed,
    owner: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Point {
    match anchor {
        FillTargetAnchor::Numeric { point } | FillTargetAnchor::GeneratedNumeric { point } => {
            crate::geometry::point_to_short_side_units(*point, canvas)
        }
        FillTargetAnchor::Named { region } => named_anchor(*region, seed, owner, canvas),
    }
}

fn rotate_contour(points: &mut [Point], center: Point, degrees: Option<f64>) {
    let Some(degrees) = degrees.filter(|value| *value != 0.0) else {
        return;
    };
    for point in points {
        *point = crate::planning::rotate_point(*point, center, degrees);
    }
}

fn target_contour(
    target: &inku_score::FillTarget,
    seed: Seed,
    owner: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Result<Vec<Point>, RegionError> {
    match &target.geometry {
        FillTargetGeometry::Rectangle { bounds } => {
            let [x0, y0, x1, y1] = *bounds;
            Ok([
                Point::new(x0, y0),
                Point::new(x1, y0),
                Point::new(x1, y1),
                Point::new(x0, y1),
            ]
            .map(|point| crate::geometry::point_to_short_side_units(point, canvas))
            .to_vec())
        }
        FillTargetGeometry::Shape {
            primitive,
            dimensions,
            arc_form,
            anchor,
            rotation_degrees,
            contour_variation,
        } => {
            let center = fill_anchor(anchor, seed, owner, canvas);
            let (mut contour, extent) = match dimensions {
                inku_score::ResolvedShapeDimensions::Circle { radius }
                | inku_score::ResolvedShapeDimensions::Point { radius } => (
                    crate::geometry::circle_points(center, *radius, *radius, 96),
                    radius * 2.0,
                ),
                inku_score::ResolvedShapeDimensions::Polygon { radius, sides } => (
                    crate::geometry::polygon_points(center, *radius, usize::from(*sides), 0.0),
                    radius * 2.0,
                ),
                inku_score::ResolvedShapeDimensions::Square { side } => (
                    vec![
                        Point::new(center.x - side / 2.0, center.y - side / 2.0),
                        Point::new(center.x + side / 2.0, center.y - side / 2.0),
                        Point::new(center.x + side / 2.0, center.y + side / 2.0),
                        Point::new(center.x - side / 2.0, center.y + side / 2.0),
                    ],
                    *side,
                ),
                inku_score::ResolvedShapeDimensions::RegularTriangle { side } => {
                    let height = side * 3.0_f64.sqrt() / 2.0;
                    (
                        vec![
                            Point::new(center.x, center.y - height / 2.0),
                            Point::new(center.x + side / 2.0, center.y + height / 2.0),
                            Point::new(center.x - side / 2.0, center.y + height / 2.0),
                        ],
                        *side,
                    )
                }
                inku_score::ResolvedShapeDimensions::Bbox { width, height }
                | inku_score::ResolvedShapeDimensions::CenteredSize { width, height } => {
                    let contour = match primitive {
                        Primitive::Ellipse => {
                            crate::geometry::circle_points(center, width / 2.0, height / 2.0, 96)
                        }
                        Primitive::Triangle => vec![
                            Point::new(center.x, center.y - height / 2.0),
                            Point::new(center.x + width / 2.0, center.y + height / 2.0),
                            Point::new(center.x - width / 2.0, center.y + height / 2.0),
                        ],
                        Primitive::Arc if *arc_form == Some(ArcForm::Crescent) => {
                            crate::geometry::crescent_contour_points(
                                center,
                                Point::new(*width, *height),
                                24,
                            )
                        }
                        Primitive::Cloudform => crate::cloudform::generate_cloudform_contour(
                            crate::cloudform::CloudformRequest {
                                center,
                                size: Point::new(*width, *height),
                                performance_seed: Some(seed),
                                instruction_index: owner,
                                mark_index: 0,
                                variation: contour_variation.as_ref(),
                                weight: inku_score::Weight::Pen,
                                point_count: 97,
                            },
                        ),
                        Primitive::Square => vec![
                            Point::new(center.x - width / 2.0, center.y - height / 2.0),
                            Point::new(center.x + width / 2.0, center.y - height / 2.0),
                            Point::new(center.x + width / 2.0, center.y + height / 2.0),
                            Point::new(center.x - width / 2.0, center.y + height / 2.0),
                        ],
                        _ => return Err(RegionError::Degenerate),
                    };
                    (contour, width.min(*height))
                }
                _ => return Err(RegionError::Degenerate),
            };
            if *primitive != Primitive::Cloudform
                && let Some(variation) = contour_variation
                    .as_ref()
                    .filter(|value| crate::determinism::needs_contour_variation(value))
            {
                let amplitude =
                    crate::mark_paths::amplitude_width(variation.amplitude) * extent * 0.02;
                contour = crate::geometry::closed_contour_with_variation(
                    &contour, center, variation, seed, amplitude,
                );
            }
            rotate_contour(&mut contour, center, *rotation_degrees);
            Ok(contour)
        }
    }
}

fn prepare_fill_target(
    group: &FillGroup,
    seed: Seed,
    owner: usize,
    canvas: Option<crate::types::CanvasSize>,
) -> Result<PreparedRegion, RegionError> {
    PreparedRegion::new(&target_contour(&group.target, seed, owner, canvas)?)
}

fn remap_dense_diagnostics(
    diagnostics: &mut [ScoreExecutionDiagnostic],
    source_prefix: &[ScoreExecutionDiagnostic],
    dense_to_original: &[usize],
    dense_anchor_to_original: &[usize],
) {
    let dense_start = if diagnostics.starts_with(source_prefix) {
        source_prefix.len()
    } else {
        0
    };
    for diagnostic in &mut diagnostics[dense_start..] {
        if let Some(&original) = dense_to_original.get(diagnostic.instruction_index) {
            diagnostic.instruction_index = original;
        }
        if let Some(dense) = diagnostic.dependency_instruction_index
            && let Some(&original) = dense_to_original.get(dense)
        {
            diagnostic.dependency_instruction_index = Some(original);
        }
        if let Some(dense) = diagnostic.anchor_index
            && let Some(&original) = dense_anchor_to_original.get(dense)
        {
            diagnostic.anchor_index = Some(original);
        }
    }
}

pub(crate) fn resolve(
    request: PerformanceRequest<'_>,
    policy: inku_score::ScoreErrorPolicy,
) -> Result<PerformancePlan, crate::checked_performance::CheckedPerformanceError> {
    let performance_seed = request.performance_seed;
    let composition_seed = request.composition_seed;
    let canvas = request.canvas;
    let (dense, typed, dense_to_original, dense_anchor_to_original) =
        Builder::new(request).finish();
    let source_diagnostics = typed.diagnostics.clone();
    let dense_request = PerformanceRequest {
        score: &dense,
        performance_seed,
        composition_seed,
        canvas,
    };
    let mut performance = match crate::checked_performance::anchor_execution::resolve_typed(
        dense_request,
        policy,
        typed,
    ) {
        Ok(performance) => performance,
        Err(mut error) => {
            remap_dense_diagnostics(
                &mut error.diagnostics,
                &source_diagnostics,
                &dense_to_original,
                &dense_anchor_to_original,
            );
            return Err(error);
        }
    };
    if let Some(execution) = &mut performance.execution {
        remap_dense_diagnostics(
            &mut execution.diagnostics,
            &source_diagnostics,
            &dense_to_original,
            &dense_anchor_to_original,
        );
    }
    for entry in &mut performance.performed {
        entry.original_instruction_index = dense_to_original[entry.original_instruction_index];
    }
    let rendered_instruction_indices = performance.original_instruction_indices();
    if let Some(execution) = &mut performance.execution {
        execution.rendered_instruction_indices = rendered_instruction_indices;
        execution.rendered_instruction_indices.sort_unstable();
        execution.rendered_instruction_indices.dedup();
    }
    Ok(performance)
}

#[cfg(test)]
mod tests {
    use inku_score::{
        HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand,
        ScoreErrorPolicy, ScoreResourcePolicy,
    };
    use serde_json::json;

    use super::*;

    fn budget(maximum: u64) -> ResourceBudget {
        ResourceBudget {
            maximum: ResourceDemand {
                logical_objects: maximum,
                primitive_marks: maximum,
                object_templates: maximum,
                maximum_per_template_primitive_marks: maximum,
                maximum_resolved_count: maximum,
                template_nodes: maximum,
                anchor_instances: maximum,
                transform_instances: maximum,
                placement_instances: maximum,
                fill_instances: maximum,
            },
        }
    }

    fn hard(maximum: u64) -> HardResourcePolicy {
        HardResourcePolicy {
            identity: "test.typed-performance-policy.v1".into(),
            budget: budget(maximum),
        }
    }

    fn instruction(owner: serde_json::Value, enclosing: bool) -> inku_score::Instruction {
        serde_json::from_value(json!({
            "primitive": "circle",
            "center": [0.5, 0.5],
            "radius": 0.05,
            "arrangement": {
                "count": 1,
                "resolved": {
                    "owner": owner,
                    "first_instance_ordinal": 0,
                    "count_origin": {"kind": if enclosing {"template_single"} else {"explicit"}},
                    "domain": [1.0, 1.0],
                    "anchor": if enclosing {
                        json!({"kind": "enclosing_group"})
                    } else {
                        json!({"kind": "numeric", "point": [0.8, 0.8]})
                    },
                    "recipe": {"kind": "place"},
                    "ordinal_scheme": "source_member_then_instance_v1"
                }
            }
        }))
        .unwrap()
    }

    fn symbolic_member(
        start: usize,
        end: usize,
        owner: serde_json::Value,
        kind: &str,
        count: u64,
    ) -> inku_score::PlacementMember {
        serde_json::from_value(json!({
            "start": start,
            "end": end,
            "symbolic": {
                "owner": owner,
                "kind": kind,
                "member_ordinal": 0,
                "first_instance_ordinal": 0,
                "instance_count": count,
                "count_origin": {"kind": "explicit"}
            }
        }))
        .unwrap()
    }

    fn representative_score(policy: HardResourcePolicy) -> Score {
        let inner_owner = json!({
            "kind": "macro_emit",
            "source_instruction_index": 0,
            "invocation_ordinal": 0,
            "generated_ordinal": 0
        });
        let mut outer_fill_member = symbolic_member(
            0,
            2,
            json!({"kind": "source_instruction", "instruction_index": 0}),
            "macro",
            2,
        );
        outer_fill_member.transform_group_indices = vec![0];
        let inner_fill_member = symbolic_member(0, 1, inner_owner.clone(), "primitive", 2);
        let mut instructions = vec![
            instruction(inner_owner, true),
            instruction(
                json!({
                    "kind": "macro_emit",
                    "source_instruction_index": 0,
                    "invocation_ordinal": 0,
                    "generated_ordinal": 1
                }),
                true,
            ),
            instruction(
                json!({
                    "kind": "macro_emit",
                    "source_instruction_index": 2,
                    "invocation_ordinal": 0,
                    "generated_ordinal": 0
                }),
                true,
            ),
            instruction(
                json!({
                    "kind": "macro_emit",
                    "source_instruction_index": 2,
                    "invocation_ordinal": 0,
                    "generated_ordinal": 1
                }),
                true,
            ),
            instruction(
                json!({"kind": "source_instruction", "instruction_index": 4}),
                false,
            ),
        ];
        // Real named/EnclosingGroup compiler templates have no center yet.
        instructions[0].center = None;
        instructions[4].relation = serde_json::from_value(json!({
            "type": "connected",
            "target_instruction_index": 0
        }))
        .unwrap();
        Score {
            version: "0.10.0".into(),
            canvas: inku_score::Canvas::Id("square".into()),
            background: inku_score::Color::Black,
            presence: None,
            instructions,
            anchors: Vec::new(),
            transform_groups: vec![TransformGroup {
                start: 0,
                end: 2,
                rotation_degrees: 30.0,
                scale_x: 1.2,
                scale_y: 0.8,
                translate_x: 0.1,
                translate_y: 0.0,
                fixed_position_indices: vec![],
                anchor_indices: vec![],
            }],
            placement_groups: Vec::new(),
            repetition_groups: vec![inku_score::RepetitionGroup {
                member: symbolic_member(
                    2,
                    4,
                    json!({"kind": "source_instruction", "instruction_index": 2}),
                    "macro",
                    2,
                ),
                ordinal_scheme: inku_score::InstanceOrdinalScheme::SourceMemberThenInstanceV1,
            }],
            fill_groups: vec![
                serde_json::from_value(json!({
                    "start": 0,
                    "end": 2,
                    "owner": {"kind": "instruction", "source_instruction_index": 0},
                    "logical_count": 2,
                    "recipe": "uniform_in_region",
                    "target": {
                        "owner": {"kind": "omitted_canvas"},
                        "geometry": {"kind": "rectangle", "bounds": [0.0, 0.0, 1.0, 1.0]},
                        "reference_area": 1.0
                    },
                    "boundary": "clip_to_target",
                    "ordinal_scheme": "source_member_then_instance_v1",
                    "members": [outer_fill_member]
                }))
                .unwrap(),
                serde_json::from_value(json!({
                    "start": 0,
                    "end": 1,
                    "owner": {"kind": "instruction", "source_instruction_index": 0},
                    "logical_count": 2,
                    "recipe": "uniform_in_region",
                    "target": {
                        "owner": {"kind": "omitted_canvas"},
                        "geometry": {"kind": "rectangle", "bounds": [0.2, 0.2, 0.4, 0.4]},
                        "reference_area": 0.04
                    },
                    "boundary": "clip_to_target",
                    "ordinal_scheme": "source_member_then_instance_v1",
                    "members": [inner_fill_member]
                }))
                .unwrap(),
            ],
            mirror_relations: Vec::new(),
            resource_policy: Some(ScoreResourcePolicy {
                accounting_id: inku_score::RESOURCE_ACCOUNTING_ID.into(),
                hard_policy: policy,
                operational_budget: OperationalResourceBudget(budget(100)),
            }),
        }
    }

    #[test]
    fn compact_fill_repeat_and_later_source_materialize_deterministically() {
        let policy = hard(100);
        let score = representative_score(policy.clone());
        assert_eq!(score.validate_schema_edition(), Ok(()));
        let request = PerformanceRequest {
            score: &score,
            performance_seed: Some(7),
            composition_seed: Some(11),
            canvas: None,
        };
        let operational = OperationalResourceBudget(budget(100));
        let first = crate::checked_performance::resolve_checked_performance_with_resources(
            request,
            ScoreErrorPolicy::OmitAndContinue,
            &policy,
            operational,
        )
        .unwrap();
        let second = crate::checked_performance::resolve_checked_performance_with_resources(
            request,
            ScoreErrorPolicy::OmitAndContinue,
            &policy,
            operational,
        )
        .unwrap();

        assert_eq!(first, second);
        assert_eq!(first.score.instructions.len(), 11);
        assert_eq!(
            first.original_instruction_indices(),
            vec![0, 0, 1, 0, 0, 1, 2, 3, 2, 3, 4]
        );
        assert!(
            first
                .score
                .instructions
                .iter()
                .all(|value| value.arrangement.is_none())
        );
        assert!(first.score.placement_groups.is_empty());
        assert!(first.score.repetition_groups.is_empty());
        assert!(first.score.fill_groups.is_empty());
        assert_eq!(first.fill_scopes.len(), 3);
        assert!(first.instruction_transforms()[0].b.abs() > 0.1);
        assert_eq!(
            first.fill_scopes[0].instruction_indices,
            vec![0, 1, 2, 3, 4, 5]
        );
        assert_eq!(first.fill_scopes[1].instruction_indices, vec![0, 1]);
        assert_eq!(first.fill_scopes[2].instruction_indices, vec![3, 4]);
        assert_eq!(first.fill_scopes[1].parent_scope_index, Some(0));
        assert_eq!(first.fill_scopes[2].parent_scope_index, Some(0));
        assert_eq!(
            first.fill_scopes[1].atomic_instruction_groups.last(),
            Some(&vec![0, 1, 2, 3, 4, 5])
        );
        assert_eq!(
            first
                .performed
                .iter()
                .map(|entry| entry.fill_scope_index)
                .collect::<Vec<_>>(),
            vec![
                Some(1),
                Some(1),
                Some(0),
                Some(2),
                Some(2),
                Some(0),
                None,
                None,
                None,
                None,
                None,
            ]
        );
        for index in [0, 1, 3, 4] {
            let center = crate::geometry::point_to_short_side_units(
                crate::planning::instruction_anchor_on_canvas(
                    &first.score.instructions[index],
                    None,
                ),
                None,
            );
            assert!(
                first.fill_scopes[first.performed[index].fill_scope_index.unwrap()]
                    .prepared_region
                    .contains(first.instruction_transforms()[index].apply(center))
            );
        }

        let omitted =
            crate::checked_performance::resolve_checked_performance_with_resources_and_omissions(
                request,
                ScoreErrorPolicy::OmitAndContinue,
                &policy,
                operational,
                &[2],
            )
            .unwrap();
        assert_eq!(
            omitted.original_instruction_indices(),
            vec![0, 0, 1, 0, 0, 1, 4]
        );
        let execution = omitted.execution.unwrap();
        assert_eq!(execution.rendered_instruction_indices, vec![0, 1, 4]);
        assert!(execution.diagnostics.iter().any(|diagnostic| {
            diagnostic.instruction_index == 4 && diagnostic.dependency_instruction_index == Some(0)
        }));

        let empty =
            crate::checked_performance::resolve_checked_performance_with_resources_and_omissions(
                request,
                ScoreErrorPolicy::OmitAndContinue,
                &policy,
                operational,
                &[0, 2, 4],
            )
            .unwrap();
        assert!(empty.score.instructions.is_empty());
        assert!(empty.original_instruction_indices().is_empty());
    }

    #[test]
    fn compact_color_cycle_uses_local_ordinal_and_preserves_performance_identity() {
        let policy = hard(100);
        let mut repeated = instruction(
            json!({"kind": "source_instruction", "instruction_index": 0}),
            false,
        );
        let arrangement = repeated.arrangement.as_mut().unwrap();
        arrangement.count = 5;
        arrangement.jitter = 0.0;
        arrangement.color_cycle = vec![inku_score::Color::Red, inku_score::Color::Blue];
        let resolved = arrangement.resolved.as_mut().unwrap();
        resolved.domain = Point::new(2.35, 1.0);
        resolved.anchor = ResolvedPlacementAnchor::Named {
            region: [0.5, 0.5, 0.5, 0.5],
        };
        resolved.recipe = ResolvedPlacementRecipe::HorizontalLine { cell_width: 0.47 };
        repeated.color_hint = Some("red reflection".into());
        let score = Score {
            version: "0.10.0".into(),
            canvas: inku_score::Canvas::Id("wide".into()),
            background: inku_score::Color::Black,
            presence: None,
            instructions: vec![repeated],
            anchors: Vec::new(),
            transform_groups: Vec::new(),
            placement_groups: Vec::new(),
            repetition_groups: Vec::new(),
            fill_groups: Vec::new(),
            mirror_relations: Vec::new(),
            resource_policy: Some(ScoreResourcePolicy {
                accounting_id: inku_score::RESOURCE_ACCOUNTING_ID.into(),
                hard_policy: policy.clone(),
                operational_budget: OperationalResourceBudget(budget(100)),
            }),
        };
        assert_eq!(score.validate_schema_edition(), Ok(()));
        let request = PerformanceRequest {
            score: &score,
            performance_seed: Some(7),
            composition_seed: Some(11),
            canvas: Some(crate::types::CanvasSize::new(2.35, 1.0)),
        };
        let operational = OperationalResourceBudget(budget(100));
        let cycled = crate::checked_performance::resolve_checked_performance_with_resources(
            request,
            ScoreErrorPolicy::OmitAndContinue,
            &policy,
            operational,
        )
        .unwrap();

        let mut baseline_score = score.clone();
        baseline_score.instructions[0]
            .arrangement
            .as_mut()
            .unwrap()
            .color_cycle
            .clear();
        let baseline = crate::checked_performance::resolve_checked_performance_with_resources(
            PerformanceRequest {
                score: &baseline_score,
                ..request
            },
            ScoreErrorPolicy::OmitAndContinue,
            &policy,
            operational,
        )
        .unwrap();

        assert_eq!(
            cycled
                .score
                .instructions
                .iter()
                .map(|instruction| instruction.color)
                .collect::<Vec<_>>(),
            vec![
                inku_score::Color::Red,
                inku_score::Color::Blue,
                inku_score::Color::Red,
                inku_score::Color::Blue,
                inku_score::Color::Red,
            ]
        );
        assert!(
            cycled
                .score
                .instructions
                .iter()
                .all(|instruction| instruction.color_hint.as_deref() == Some("reflection"))
        );
        let centers = cycled
            .score
            .instructions
            .iter()
            .map(|instruction| instruction.center.unwrap())
            .collect::<Vec<_>>();
        assert_eq!(centers.len(), 5);
        assert!(
            centers.iter().all(|center| {
                (0.0..=1.0).contains(&center.x) && (0.0..=1.0).contains(&center.y)
            })
        );
        assert!(
            centers
                .windows(2)
                .all(|pair| (pair[1].x - pair[0].x - 0.2).abs() < 1.0e-12)
        );
        assert_eq!(cycled.original_instruction_indices(), vec![0; 5]);
        assert_eq!(
            cycled.instruction_seed_overrides(),
            baseline.instruction_seed_overrides()
        );
        assert_eq!(cycled.resource_demand, baseline.resource_demand);
        assert_eq!(
            cycled
                .score
                .instructions
                .iter()
                .map(|instruction| instruction.center)
                .collect::<Vec<_>>(),
            baseline
                .score
                .instructions
                .iter()
                .map(|instruction| instruction.center)
                .collect::<Vec<_>>()
        );

        let mut outer_repeated = representative_score(policy.clone());
        outer_repeated.instructions[2]
            .arrangement
            .as_mut()
            .unwrap()
            .color_cycle = vec![inku_score::Color::Red, inku_score::Color::Blue];
        let performance = crate::checked_performance::resolve_checked_performance_with_resources(
            PerformanceRequest {
                score: &outer_repeated,
                performance_seed: Some(7),
                composition_seed: Some(11),
                canvas: None,
            },
            ScoreErrorPolicy::OmitAndContinue,
            &policy,
            operational,
        )
        .unwrap();
        assert_eq!(
            performance
                .score
                .instructions
                .iter()
                .zip(&performance.original_instruction_indices())
                .filter_map(|(instruction, &owner)| { (owner == 2).then_some(instruction.color) })
                .collect::<Vec<_>>(),
            vec![inku_score::Color::Red, inku_score::Color::Red]
        );
    }

    fn mirrored_line(owner: usize, anchor_x: f64) -> inku_score::Instruction {
        let mut line = instruction(
            json!({"kind": "source_instruction", "instruction_index": owner}),
            false,
        );
        line.primitive = Primitive::Line;
        line.center = None;
        line.radius = None;
        line.from_ = Some(Point::new(0.4, 0.4));
        line.to = Some(Point::new(0.6, 0.6));
        line.arrangement
            .as_mut()
            .unwrap()
            .resolved
            .as_mut()
            .unwrap()
            .anchor = ResolvedPlacementAnchor::Numeric {
            point: Point::new(anchor_x, 0.5),
        };
        line
    }

    fn mirror_score(
        policy: HardResourcePolicy,
        instructions: Vec<inku_score::Instruction>,
        dimensions_fixed: bool,
    ) -> Score {
        Score {
            version: "0.15.0".into(),
            canvas: inku_score::Canvas::Id("square".into()),
            background: inku_score::Color::Black,
            presence: None,
            instructions,
            anchors: Vec::new(),
            transform_groups: Vec::new(),
            placement_groups: Vec::new(),
            repetition_groups: Vec::new(),
            fill_groups: Vec::new(),
            mirror_relations: vec![inku_score::MirrorRelationV1 {
                target: inku_score::MirrorBodyRef::Instruction {
                    instruction_index: 0,
                },
                follower: inku_score::MirrorBodyRef::Instruction {
                    instruction_index: 1,
                },
                follower_facts: inku_score::MirrorFollowerFactsV1 {
                    dimensions_fixed,
                    direction_degrees: None,
                },
            }],
            resource_policy: Some(ScoreResourcePolicy {
                accounting_id: inku_score::RESOURCE_ACCOUNTING_ID.into(),
                hard_policy: policy,
                operational_budget: OperationalResourceBudget(budget(100)),
            }),
        }
    }

    fn performed_point(
        performance: &crate::performance::PerformancePlan,
        index: usize,
        point: Point,
    ) -> Point {
        performance.instruction_transforms()[index].apply(point)
    }

    #[test]
    fn compact_mirror_preserves_seeds_and_precedes_common_outer_transform() {
        let policy = hard(100);
        let mut shorter = mirrored_line(1, 0.2);
        shorter.from_ = Some(Point::new(0.45, 0.45));
        shorter.to = Some(Point::new(0.55, 0.55));
        let score = mirror_score(policy.clone(), vec![mirrored_line(0, 0.8), shorter], false);
        assert_eq!(score.validate_schema_edition(), Ok(()));
        let request = PerformanceRequest {
            score: &score,
            performance_seed: Some(7),
            composition_seed: Some(11),
            canvas: None,
        };
        let base = resolve(request, ScoreErrorPolicy::OmitAndContinue).unwrap();
        assert!(
            base.execution
                .as_ref()
                .is_none_or(|execution| execution.diagnostics.is_empty())
        );
        let target_from = performed_point(&base, 0, base.score.instructions[0].from_.unwrap());
        let follower_from = performed_point(&base, 1, base.score.instructions[1].from_.unwrap());
        assert!((follower_from.x - (1.0 - target_from.x)).abs() < 1.0e-12);
        assert!((follower_from.y - target_from.y).abs() < 1.0e-12);

        let mut outer_score = score.clone();
        outer_score.transform_groups.push(TransformGroup {
            start: 0,
            end: 2,
            rotation_degrees: 0.0,
            scale_x: 1.2,
            scale_y: 1.0,
            translate_x: 0.0,
            translate_y: 0.0,
            fixed_position_indices: Vec::new(),
            anchor_indices: Vec::new(),
        });
        let outer = resolve(
            PerformanceRequest {
                score: &outer_score,
                ..request
            },
            ScoreErrorPolicy::OmitAndContinue,
        )
        .unwrap();
        assert_eq!(
            outer.instruction_seed_overrides(),
            base.instruction_seed_overrides()
        );
        let outer_target = performed_point(&outer, 0, outer.score.instructions[0].from_.unwrap());
        let outer_follower = performed_point(&outer, 1, outer.score.instructions[1].from_.unwrap());
        let scale_x = |point: Point| Point::new(0.5 + (point.x - 0.5) * 1.2, point.y);
        for (actual, expected) in [
            (outer_target, scale_x(target_from)),
            (outer_follower, scale_x(follower_from)),
        ] {
            assert!((actual.x - expected.x).abs() < 1.0e-12);
            assert!((actual.y - expected.y).abs() < 1.0e-12);
        }
    }

    #[test]
    fn compact_mirror_explicit_conflict_omits_only_relation() {
        let policy = hard(100);
        let mut follower = mirrored_line(1, 0.2);
        follower.to = Some(Point::new(0.55, 0.55));
        let score = mirror_score(
            policy.clone(),
            vec![
                mirrored_line(0, 0.8),
                follower,
                instruction(
                    json!({"kind": "source_instruction", "instruction_index": 2}),
                    false,
                ),
            ],
            true,
        );
        let performance = resolve(
            PerformanceRequest {
                score: &score,
                performance_seed: Some(7),
                composition_seed: Some(11),
                canvas: None,
            },
            ScoreErrorPolicy::OmitAndContinue,
        )
        .unwrap();
        assert_eq!(performance.score.instructions.len(), 3);
        assert_eq!(performance.original_instruction_indices(), vec![0, 1, 2]);
        assert!(
            performance
                .execution
                .as_ref()
                .unwrap()
                .diagnostics
                .iter()
                .any(|diagnostic| {
                    diagnostic.reason == ScoreExecutionReason::MirrorExplicitConflict
                        && diagnostic.disposition == ScoreExecutionDisposition::RelationOmitted
                })
        );
        let mut baseline_score = score.clone();
        baseline_score.mirror_relations.clear();
        let baseline = resolve(
            PerformanceRequest {
                score: &baseline_score,
                performance_seed: Some(7),
                composition_seed: Some(11),
                canvas: None,
            },
            ScoreErrorPolicy::OmitAndContinue,
        )
        .unwrap();
        let unchanged = performed_point(
            &performance,
            1,
            performance.score.instructions[1].from_.unwrap(),
        );
        let baseline_point =
            performed_point(&baseline, 1, baseline.score.instructions[1].from_.unwrap());
        assert_eq!(unchanged, baseline_point);
    }

    fn mirrored_arc(
        owner: usize,
        anchor_x: f64,
        width: f64,
        rotation: f64,
    ) -> inku_score::Instruction {
        let mut arc = mirrored_line(owner, anchor_x);
        let geometry = crate::arc::arc_from_endpoints_and_sagitta(
            Point::new(0.5 - width / 2.0, 0.5),
            Point::new(0.5 + width / 2.0, 0.5),
            width / 5.0,
        )
        .unwrap();
        arc.primitive = Primitive::Arc;
        arc.from_ = None;
        arc.to = None;
        arc.position = Some(Point::new(0.5, 0.5));
        arc.center = Some(geometry.center);
        arc.radius = Some(geometry.radius);
        arc.angle_start = Some(geometry.angle_start);
        arc.angle_end = Some(geometry.angle_end);
        arc.rotation = Some(rotation);
        arc
    }

    fn mirror_resolve(score: &Score) -> crate::performance::PerformancePlan {
        resolve(
            PerformanceRequest {
                score,
                performance_seed: Some(7),
                composition_seed: Some(11),
                canvas: None,
            },
            ScoreErrorPolicy::OmitAndContinue,
        )
        .unwrap()
    }

    fn arc_ideal_point(
        performance: &crate::performance::PerformancePlan,
        index: usize,
        fraction: f64,
    ) -> Point {
        let instruction = &performance.score.instructions[index];
        let angle = instruction.angle_start.unwrap()
            + (instruction.angle_end.unwrap() - instruction.angle_start.unwrap()) * fraction;
        let raw = crate::arc::arc_point(
            instruction.center.unwrap(),
            instruction.radius.unwrap(),
            angle,
        );
        let rotated = crate::planning::rotate_point(
            raw,
            instruction.position.unwrap(),
            instruction.rotation.unwrap_or(0.0),
        );
        performed_point(performance, index, rotated)
    }

    #[test]
    fn compact_mirror_arc_uses_ideal_pose_and_preserves_semantic_position() {
        let mut follower = mirrored_arc(1, 0.2, 0.08, 145.0);
        follower.color = inku_score::Color::Blue;
        let mut score = mirror_score(
            hard(100),
            vec![mirrored_arc(0, 0.8, 0.2, 35.0), follower],
            false,
        );
        score.mirror_relations[0].follower_facts.direction_degrees = Some(145.0);
        let mut baseline_score = score.clone();
        baseline_score.mirror_relations.clear();
        let baseline = mirror_resolve(&baseline_score);
        let mirrored = mirror_resolve(&score);
        assert!(
            mirrored
                .execution
                .as_ref()
                .is_none_or(|execution| execution.diagnostics.is_empty())
        );
        assert_eq!(
            mirrored.instruction_seed_overrides(),
            baseline.instruction_seed_overrides()
        );
        assert_eq!(
            mirrored.score.instructions[1].color,
            inku_score::Color::Blue
        );
        let anchor = performed_point(
            &mirrored,
            1,
            mirrored.score.instructions[1].position.unwrap(),
        );
        let original = performed_point(
            &baseline,
            1,
            baseline.score.instructions[1].position.unwrap(),
        );
        assert!((anchor.x - original.x).hypot(anchor.y - original.y) < 1.0e-12);
        for fraction in [0.0, 0.5, 1.0] {
            let target = arc_ideal_point(&mirrored, 0, fraction);
            let follower = arc_ideal_point(&mirrored, 1, fraction);
            assert!((follower.x - (1.0 - target.x)).hypot(follower.y - target.y) < 1.0e-12);
        }
        // Candidate size changes must not leak when the explicit pose fails.
        score.mirror_relations[0].follower_facts.direction_degrees = Some(35.0);
        let rejected = mirror_resolve(&score);
        assert!(rejected.execution.as_ref().unwrap().diagnostics.iter()
            .any(|diagnostic| diagnostic.reason == ScoreExecutionReason::MirrorExplicitConflict));
        assert_eq!(
            rejected.score.instructions[1],
            baseline.score.instructions[1]
        );
        assert_eq!(
            rejected.instruction_transforms()[1],
            baseline.instruction_transforms()[1]
        );
    }

    #[test]
    fn compact_mirror_concentric_body_requires_one_pose_for_internal_geometry() {
        let mut instructions = vec![
            mirrored_line(0, 0.8),
            mirrored_line(1, 0.8),
            mirrored_line(2, 0.2),
            mirrored_line(3, 0.2),
        ];
        instructions[1].rotation = Some(60.0);
        instructions[3].rotation = Some(60.0);
        let mut score = mirror_score(hard(100), instructions, true);
        score.repetition_groups = [0, 2]
            .into_iter()
            .map(|start| inku_score::RepetitionGroup {
                member: symbolic_member(
                    start,
                    start + 2,
                    json!({"kind": "source_instruction", "instruction_index": start}),
                    "macro",
                    1,
                ),
                ordinal_scheme: inku_score::InstanceOrdinalScheme::SourceMemberThenInstanceV1,
            })
            .collect();
        score.mirror_relations[0].target = inku_score::MirrorBodyRef::RepetitionGroup {
            repetition_group_index: 0,
        };
        score.mirror_relations[0].follower = inku_score::MirrorBodyRef::RepetitionGroup {
            repetition_group_index: 1,
        };
        assert_eq!(score.validate_schema_edition(), Ok(()));
        let mirrored = mirror_resolve(&score);
        assert!(
            mirrored
                .execution
                .as_ref()
                .is_none_or(|execution| execution.diagnostics.is_empty())
        );
        for (target_index, follower_index) in [(0, 2), (1, 3)] {
            let ideal_endpoint = |index| {
                let instruction = &mirrored.score.instructions[index];
                let (start, _, _, _) =
                    crate::planning::endpoint_geometry(instruction, None).unwrap();
                performed_point(&mirrored, index, start)
            };
            let target = ideal_endpoint(target_index);
            let follower = ideal_endpoint(follower_index);
            assert!((follower.x - (1.0 - target.x)).hypot(follower.y - target.y) < 1.0e-12);
        }
        // Identical leaf centers and raw sizes are insufficient: the second
        // leaf's internal pose must also correspond under that same reflection.
        score.instructions[3].rotation = Some(30.0);
        let mut baseline_score = score.clone();
        baseline_score.mirror_relations.clear();
        let baseline = mirror_resolve(&baseline_score);
        let rejected = mirror_resolve(&score);
        assert!(rejected.execution.as_ref().unwrap().diagnostics.iter()
            .any(|diagnostic| diagnostic.reason == ScoreExecutionReason::MirrorExplicitConflict));
        assert_eq!(
            rejected.score.instructions[2..],
            baseline.score.instructions[2..]
        );
        assert_eq!(
            rejected.instruction_transforms()[2..],
            baseline.instruction_transforms()[2..]
        );
    }

    #[test]
    fn compact_member_cycle_reuses_complete_ordinary_body_at_global_ordinals() {
        let policy = hard(100);
        let source = |index| json!({"kind": "source_instruction", "instruction_index": index});
        let mut circle = instruction(source(0), true);
        let circle_resolved = circle
            .arrangement
            .as_mut()
            .unwrap()
            .resolved
            .as_mut()
            .unwrap();
        circle_resolved.count_origin = inku_score::CountOrigin::OmittedDefault;
        circle_resolved.anchor = ResolvedPlacementAnchor::Named {
            region: [0.5, 0.5, 0.5, 0.5],
        };
        circle.color = inku_score::Color::Red;
        let mut line = instruction(source(1), true);
        let line_resolved = line
            .arrangement
            .as_mut()
            .unwrap()
            .resolved
            .as_mut()
            .unwrap();
        line_resolved.count_origin = inku_score::CountOrigin::OmittedDefault;
        line_resolved.anchor = ResolvedPlacementAnchor::Named {
            region: [0.5, 0.5, 0.5, 0.5],
        };
        line.primitive = Primitive::Line;
        line.center = None;
        line.radius = None;
        line.from_ = Some(Point::new(0.45, 0.5));
        line.to = Some(Point::new(0.55, 0.5));
        line.color = inku_score::Color::Blue;
        let mut arc = instruction(source(2), true);
        arc.primitive = Primitive::Arc;
        arc.radius = Some(0.05);
        arc.angle_start = Some(0.0);
        arc.angle_end = Some(90.0);
        arc.color = inku_score::Color::Gray;
        let group = serde_json::from_value(json!({
            "start": 0,
            "end": 3,
            "layout": "horizontal_source_order",
            "at": {"region": [0.0, 0.0, 1.0, 1.0]},
            "members": [
                {
                    "start": 0,
                    "end": 2,
                    "symbolic": {
                        "owner": {"kind": "ordinary_group", "source_instruction_indices": [0, 1]},
                        "kind": "ordinary_group",
                        "member_ordinal": 0,
                        "first_instance_ordinal": 0,
                        "instance_count": 1,
                        "count_origin": {"kind": "explicit"}
                    }
                },
                {
                    "start": 2,
                    "end": 3,
                    "symbolic": {
                        "owner": {"kind": "source_instruction", "instruction_index": 2},
                        "kind": "primitive",
                        "member_ordinal": 1,
                        "first_instance_ordinal": 1,
                        "instance_count": 1,
                        "count_origin": {"kind": "explicit"}
                    }
                }
            ],
            "cycle_members": {"occurrence_count": 5},
            "resolved": {
                "owner": {"kind": "coordinated_group", "group_index": 0},
                "logical_count": 5,
                "domain": [1.0, 1.0],
                "anchor": {"kind": "numeric", "point": [0.5, 0.5]},
                "recipe": {"kind": "horizontal_line", "cell_width": 0.2},
                "ordinal_scheme": "source_member_then_instance_v1"
            }
        }))
        .unwrap();
        let score = Score {
            version: "0.14.0".into(),
            canvas: inku_score::Canvas::Id("square".into()),
            background: inku_score::Color::Black,
            presence: None,
            instructions: vec![circle, line, arc],
            anchors: Vec::new(),
            transform_groups: Vec::new(),
            placement_groups: vec![group],
            repetition_groups: Vec::new(),
            fill_groups: Vec::new(),
            mirror_relations: Vec::new(),
            resource_policy: Some(ScoreResourcePolicy {
                accounting_id: inku_score::RESOURCE_ACCOUNTING_ID.into(),
                hard_policy: policy.clone(),
                operational_budget: OperationalResourceBudget(budget(100)),
            }),
        };
        assert_eq!(score.validate_schema_edition(), Ok(()));
        let admitted = inku_score::finalize_saved_score(
            &score,
            &policy,
            OperationalResourceBudget(budget(100)),
        )
        .unwrap();
        assert_eq!(
            admitted.score.placement_groups[0]
                .cycle_members
                .as_ref()
                .unwrap()
                .occurrence_count,
            5
        );
        let (dense, _, dense_to_original, _) = Builder::new(PerformanceRequest {
            score: &admitted.score,
            performance_seed: Some(7),
            composition_seed: Some(11),
            canvas: None,
        })
        .finish();
        assert_eq!(dense_to_original, vec![0, 1, 2, 0, 1, 2, 0, 1]);
        assert_eq!(dense.instructions.len(), 8);
        let request = PerformanceRequest {
            score: &score,
            performance_seed: Some(7),
            composition_seed: Some(11),
            canvas: None,
        };
        let first = crate::checked_performance::resolve_checked_performance_with_resources(
            request,
            ScoreErrorPolicy::OmitAndContinue,
            &policy,
            OperationalResourceBudget(budget(100)),
        )
        .unwrap();
        let second = crate::checked_performance::resolve_checked_performance_with_resources(
            request,
            ScoreErrorPolicy::OmitAndContinue,
            &policy,
            OperationalResourceBudget(budget(100)),
        )
        .unwrap();

        assert_eq!(first, second);
        assert_eq!(
            first.original_instruction_indices(),
            vec![0, 1, 2, 0, 1, 2, 0, 1]
        );
        assert_eq!(
            first
                .score
                .instructions
                .iter()
                .map(|instruction| instruction.primitive)
                .collect::<Vec<_>>(),
            vec![
                Primitive::Circle,
                Primitive::Line,
                Primitive::Arc,
                Primitive::Circle,
                Primitive::Line,
                Primitive::Arc,
                Primitive::Circle,
                Primitive::Line,
            ]
        );
        let circle_centers = [0, 3, 6].map(|index| {
            first.instruction_transforms()[index]
                .apply(first.score.instructions[index].center.unwrap())
        });
        let line_midpoints = [1, 4, 7].map(|index| {
            let instruction = &first.score.instructions[index];
            let from = instruction.from_.unwrap();
            let to = instruction.to.unwrap();
            first.instruction_transforms()[index]
                .apply(Point::new((from.x + to.x) / 2.0, (from.y + to.y) / 2.0))
        });
        let arc_centers = [2, 5].map(|index| {
            first.instruction_transforms()[index]
                .apply(first.score.instructions[index].center.unwrap())
        });
        for centers in [&circle_centers[..], &line_midpoints[..], &arc_centers[..]] {
            assert!(centers.windows(2).all(|pair| {
                (pair[1].x - pair[0].x - 0.4).abs() < 1.0e-12
                    && (pair[1].y - pair[0].y).abs() < 1.0e-12
            }));
        }
        assert_eq!(first.resource_demand.as_ref().unwrap().logical_objects, 5);
        assert_eq!(first.resource_demand.as_ref().unwrap().primitive_marks, 8);
        assert_eq!(
            first.instruction_seed_overrides(),
            [
                (0, 0),
                (1, 0),
                (2, 1),
                (0, 2),
                (1, 2),
                (2, 3),
                (0, 4),
                (1, 4)
            ]
            .map(|(owner, occurrence)| {
                Some(instance_seed(
                    &inku_score::ScoreSourceOwner::SourceInstruction {
                        instruction_index: owner,
                    },
                    &[occurrence],
                    0,
                    Some(7),
                ))
            })
            .to_vec(),
        );
    }
}
