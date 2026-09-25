//! Validate and admit a compact saved Score under caller-owned resource authority.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, HashSet};

use crate::{
    FillGroupOwner, HardResourcePolicy, OperationalResourceBudget, PlacementGroupOwner,
    PlacementMember, RESOURCE_ACCOUNTING_ID, ResourceAuthority, ResourceBudget,
    ResourceBudgetExceeded, ResourceDemand, ResourceDimension, Score, ScoreSourceOwner,
    SymbolicMemberKind,
};

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SavedScoreResourceOwner {
    Score,
    SourceInstruction {
        source_instruction_index: usize,
    },
    Instruction {
        instruction_index: usize,
        owner: ScoreSourceOwner,
    },
    Anchor {
        anchor_index: usize,
        source_instruction_index: usize,
    },
    TransformGroup {
        transform_group_index: usize,
        source_instruction_index: usize,
    },
    PlacementGroup {
        placement_group_index: usize,
        owner: PlacementGroupOwner,
    },
    FillGroup {
        fill_group_index: usize,
        owner: FillGroupOwner,
    },
    RepetitionGroup {
        repetition_group_index: usize,
        source_instruction_index: usize,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SavedScoreResourceFailure {
    InvalidContract(&'static str),
    InvalidOmittedInstructionIndex {
        instruction_index: usize,
        instruction_count: usize,
    },
    MissingResourcePolicy,
    AccountingIdMismatch {
        saved: String,
    },
    HardPolicyMismatch {
        saved: HardResourcePolicy,
        authorized: HardResourcePolicy,
    },
    ArithmeticOverflow(ResourceDimension),
    BudgetExceeded(ResourceBudgetExceeded),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SavedScoreResourceError {
    pub owner: SavedScoreResourceOwner,
    pub reason: SavedScoreResourceFailure,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SavedScoreResourceDisposition {
    Omitted,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SavedScoreResourceDiagnostic {
    /// The complete atomic source or coordinated group that was omitted.
    pub owner: SavedScoreResourceOwner,
    /// The exact saved descriptor whose demand caused the refusal.
    pub cause_owner: SavedScoreResourceOwner,
    pub failure: SavedScoreResourceFailure,
    pub disposition: SavedScoreResourceDisposition,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SavedScoreRelationDisposition {
    Omitted,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct SavedScoreRelationDiagnostic {
    pub instruction_index: usize,
    pub owner: ScoreSourceOwner,
    pub target_instruction_index: Option<usize>,
    pub target_anchor_index: Option<usize>,
    pub disposition: SavedScoreRelationDisposition,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct SavedScoreIndexMaps {
    pub instructions: Vec<Option<usize>>,
    pub anchors: Vec<Option<usize>>,
    pub transform_groups: Vec<Option<usize>>,
    pub placement_groups: Vec<Option<usize>>,
    pub fill_groups: Vec<Option<usize>>,
    pub repetition_groups: Vec<Option<usize>>,
}

#[derive(Clone, Debug)]
pub struct FinalizedScore {
    pub score: Score,
    pub demand: ResourceDemand,
    pub index_maps: SavedScoreIndexMaps,
    pub resource_diagnostics: Vec<SavedScoreResourceDiagnostic>,
    pub relation_diagnostics: Vec<SavedScoreRelationDiagnostic>,
}

/// The four limits supplied by the renderer before resource accounting v1.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct LegacyFourResourceLimits {
    pub primitive_marks: u64,
    pub maximum_per_template_primitive_marks: u64,
    pub maximum_resolved_count: u64,
    pub object_templates: u64,
}

/// The remaining accounting-v1 limits. Callers must choose every value.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AdditionalResourceLimits {
    pub logical_objects: u64,
    pub template_nodes: u64,
    pub anchor_instances: u64,
    pub transform_instances: u64,
    pub placement_instances: u64,
    pub fill_instances: u64,
}

#[must_use]
pub const fn resource_budget_from_legacy_four_limits(
    legacy: LegacyFourResourceLimits,
    additional: AdditionalResourceLimits,
) -> ResourceBudget {
    ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: additional.logical_objects,
            primitive_marks: legacy.primitive_marks,
            object_templates: legacy.object_templates,
            maximum_per_template_primitive_marks: legacy.maximum_per_template_primitive_marks,
            maximum_resolved_count: legacy.maximum_resolved_count,
            template_nodes: additional.template_nodes,
            anchor_instances: additional.anchor_instances,
            transform_instances: additional.transform_instances,
            placement_instances: additional.placement_instances,
            fill_instances: additional.fill_instances,
        },
    }
}

fn error(
    owner: SavedScoreResourceOwner,
    reason: SavedScoreResourceFailure,
) -> SavedScoreResourceError {
    SavedScoreResourceError { owner, reason }
}

fn invalid(owner: SavedScoreResourceOwner, reason: &'static str) -> SavedScoreResourceError {
    error(owner, SavedScoreResourceFailure::InvalidContract(reason))
}

fn source_index(owner: &ScoreSourceOwner) -> usize {
    match owner {
        ScoreSourceOwner::SourceInstruction { instruction_index } => *instruction_index,
        ScoreSourceOwner::OrdinaryGroup {
            source_instruction_indices,
        } => *source_instruction_indices
            .first()
            .expect("validated ordinary group owner has a source"),
        ScoreSourceOwner::MacroEmit {
            source_instruction_index,
            ..
        } => *source_instruction_index,
    }
}

fn symbolic_sources(symbolic: &crate::SymbolicMember) -> Vec<usize> {
    match &symbolic.owner {
        ScoreSourceOwner::OrdinaryGroup {
            source_instruction_indices,
        } => source_instruction_indices.clone(),
        owner => vec![source_index(owner)],
    }
}

fn cycle_repetitions(
    cycle: Option<&crate::CycleMembersV1>,
    member_ordinal: u64,
    member_count: usize,
    default: u64,
) -> u64 {
    let Some(cycle) = cycle else {
        return default;
    };
    let width = u64::try_from(member_count).expect("member count fits u64");
    if member_ordinal >= cycle.occurrence_count {
        0
    } else {
        1 + (cycle.occurrence_count - 1 - member_ordinal) / width
    }
}

#[derive(Clone, Copy)]
struct OuterClaim {
    source: usize,
    repetitions: u64,
    kind: SymbolicMemberKind,
    cycle: bool,
}

#[derive(Clone)]
struct DirectFill {
    group_index: usize,
    source: usize,
    count: u64,
}

struct Contribution {
    source: usize,
    owner: SavedScoreResourceOwner,
    demand: ResourceDemand,
}

struct PendingFailure {
    source: usize,
    owner: SavedScoreResourceOwner,
    dimension: ResourceDimension,
}

struct Analysis {
    sources: BTreeSet<usize>,
    source_units: BTreeMap<usize, usize>,
    unit_owners: BTreeMap<usize, SavedScoreResourceOwner>,
    grouped_sources: HashSet<usize>,
    outer_sources: HashSet<usize>,
    instruction_sources: Vec<usize>,
    instruction_claims: Vec<Option<OuterClaim>>,
    anchor_claims: Vec<Option<OuterClaim>>,
    transform_claims: Vec<Option<OuterClaim>>,
    direct_fills: Vec<Option<DirectFill>>,
    placement_sources: Vec<usize>,
    fill_sources: Vec<usize>,
    repetition_sources: Vec<usize>,
    contributions: Vec<Contribution>,
    pending_failures: Vec<PendingFailure>,
}

impl Analysis {
    fn new(score: &Score) -> Result<Self, SavedScoreResourceError> {
        let mut sources = BTreeSet::new();
        let mut direct_sources = HashSet::new();
        let mut macro_sources = HashSet::new();
        let mut macro_owners = HashSet::new();
        let mut instruction_sources = Vec::with_capacity(score.instructions.len());
        for (instruction_index, instruction) in score.instructions.iter().enumerate() {
            let arrangement = instruction.arrangement.as_ref().ok_or_else(|| {
                invalid(
                    SavedScoreResourceOwner::Instruction {
                        instruction_index,
                        owner: ScoreSourceOwner::SourceInstruction {
                            instruction_index: 0,
                        },
                    },
                    "Score 0.10 instruction is missing arrangement",
                )
            })?;
            let resolved = arrangement.resolved.as_ref().ok_or_else(|| {
                invalid(
                    SavedScoreResourceOwner::Score,
                    "Score 0.10 arrangement is missing resolved metadata",
                )
            })?;
            if resolved.first_instance_ordinal != 0 {
                return Err(invalid(
                    SavedScoreResourceOwner::Instruction {
                        instruction_index,
                        owner: resolved.owner.clone(),
                    },
                    "arrangement first instance ordinal must be zero",
                ));
            }
            let source = source_index(&resolved.owner);
            sources.insert(source);
            instruction_sources.push(source);
            match &resolved.owner {
                ScoreSourceOwner::SourceInstruction { .. } => {
                    direct_sources.insert(source);
                    if macro_sources.contains(&source) {
                        return Err(invalid(
                            SavedScoreResourceOwner::Instruction {
                                instruction_index,
                                owner: resolved.owner.clone(),
                            },
                            "source instruction owns multiple incompatible templates",
                        ));
                    }
                }
                ScoreSourceOwner::OrdinaryGroup { .. } => {
                    return Err(invalid(
                        SavedScoreResourceOwner::Instruction {
                            instruction_index,
                            owner: resolved.owner.clone(),
                        },
                        "instruction template cannot own an ordinary group",
                    ));
                }
                ScoreSourceOwner::MacroEmit {
                    invocation_ordinal,
                    generated_ordinal,
                    ..
                } => {
                    if direct_sources.contains(&source)
                        || !macro_owners.insert((source, *invocation_ordinal, *generated_ordinal))
                    {
                        return Err(invalid(
                            SavedScoreResourceOwner::Instruction {
                                instruction_index,
                                owner: resolved.owner.clone(),
                            },
                            "Macro emitted template owner is duplicated or inconsistent",
                        ));
                    }
                    macro_sources.insert(source);
                }
            }
        }
        let source_units = sources.iter().map(|&source| (source, source)).collect();
        Ok(Self {
            sources,
            source_units,
            unit_owners: BTreeMap::new(),
            grouped_sources: HashSet::new(),
            outer_sources: HashSet::new(),
            instruction_sources,
            instruction_claims: vec![None; score.instructions.len()],
            anchor_claims: vec![None; score.anchors.len()],
            transform_claims: vec![None; score.transform_groups.len()],
            direct_fills: vec![None; score.instructions.len()],
            placement_sources: Vec::with_capacity(score.placement_groups.len()),
            fill_sources: Vec::with_capacity(score.fill_groups.len()),
            repetition_sources: Vec::with_capacity(score.repetition_groups.len()),
            contributions: Vec::new(),
            pending_failures: Vec::new(),
        })
    }

    fn add_source(&mut self, source: usize) {
        if self.sources.insert(source) {
            self.source_units.insert(source, source);
        }
    }

    fn set_unit_owner(
        &mut self,
        source: usize,
        owner: SavedScoreResourceOwner,
    ) -> Result<(), SavedScoreResourceError> {
        if self.unit_owners.insert(source, owner.clone()).is_some() {
            return Err(invalid(owner, "resource unit has multiple outer owners"));
        }
        Ok(())
    }

    fn register_group(
        &mut self,
        sources: &[usize],
        allow_duplicate_sources: bool,
        owner: SavedScoreResourceOwner,
    ) -> Result<usize, SavedScoreResourceError> {
        let Some(&first) = sources.first() else {
            return Err(invalid(owner, "resource group has no members"));
        };
        let mut previous = None;
        let mut seen = HashSet::new();
        for &source in sources {
            if !seen.insert(source) {
                if allow_duplicate_sources {
                    continue;
                }
                return Err(invalid(
                    owner,
                    "resource group sources must be unique and in source order",
                ));
            }
            if previous.is_some_and(|previous| source <= previous)
                || !self.grouped_sources.insert(source)
            {
                return Err(invalid(
                    owner,
                    "resource group sources must be unique and in source order",
                ));
            }
            self.add_source(source);
            self.source_units.insert(source, first);
            previous = Some(source);
        }
        self.set_unit_owner(first, owner)?;
        Ok(first)
    }

    fn register_outer_member(
        &mut self,
        score: &Score,
        member: &PlacementMember,
        repetitions: u64,
        cycle: bool,
        owner: SavedScoreResourceOwner,
    ) -> Result<usize, SavedScoreResourceError> {
        let symbolic = member
            .symbolic
            .as_ref()
            .ok_or_else(|| invalid(owner.clone(), "outer member has no symbolic metadata"))?;
        let source = match &symbolic.owner {
            ScoreSourceOwner::SourceInstruction { instruction_index } => *instruction_index,
            ScoreSourceOwner::OrdinaryGroup {
                source_instruction_indices,
            } => *source_instruction_indices
                .first()
                .ok_or_else(|| invalid(owner.clone(), "ordinary group owner has no sources"))?,
            ScoreSourceOwner::MacroEmit { .. } => {
                return Err(invalid(
                    owner,
                    "outer member owner must identify its source instruction",
                ));
            }
        };
        self.add_source(source);
        if !self.outer_sources.insert(source) && !cycle {
            return Err(invalid(
                owner,
                "source has multiple outer repetition owners",
            ));
        }
        if member.start > member.end
            || member.end > score.instructions.len()
            || (member.start == member.end && member.anchor_indices.is_empty())
        {
            return Err(invalid(owner, "outer member has an invalid span"));
        }
        if symbolic.kind == SymbolicMemberKind::Primitive
            && (member.end - member.start != 1
                || !member.anchor_indices.is_empty()
                || !member.transform_group_indices.is_empty())
        {
            return Err(invalid(
                owner,
                "primitive outer member must own exactly one instruction",
            ));
        }
        let claim = OuterClaim {
            source,
            repetitions,
            kind: symbolic.kind,
            cycle,
        };
        let mut ordinary_member_sources = BTreeSet::new();
        for instruction_index in member.start..member.end {
            let resolved_owner = &score.instructions[instruction_index]
                .arrangement
                .as_ref()
                .unwrap()
                .resolved
                .as_ref()
                .unwrap()
                .owner;
            let owner_matches = match (symbolic.kind, resolved_owner) {
                (
                    SymbolicMemberKind::Primitive,
                    ScoreSourceOwner::SourceInstruction { instruction_index },
                ) => *instruction_index == source,
                (
                    SymbolicMemberKind::Macro,
                    ScoreSourceOwner::MacroEmit {
                        source_instruction_index,
                        ..
                    },
                ) => *source_instruction_index == source,
                (
                    SymbolicMemberKind::OrdinaryGroup,
                    ScoreSourceOwner::SourceInstruction { instruction_index },
                )
                | (
                    SymbolicMemberKind::OrdinaryGroup,
                    ScoreSourceOwner::MacroEmit {
                        source_instruction_index: instruction_index,
                        ..
                    },
                ) => {
                    ordinary_member_sources.insert(*instruction_index);
                    matches!(
                        &symbolic.owner,
                        ScoreSourceOwner::OrdinaryGroup {
                            source_instruction_indices,
                        } if source_instruction_indices.contains(instruction_index)
                    )
                }
                _ => false,
            };
            if !owner_matches
                || self.instruction_claims[instruction_index]
                    .replace(claim)
                    .is_some()
            {
                return Err(invalid(
                    owner,
                    "outer member instruction ownership is inconsistent or overlapping",
                ));
            }
        }
        if let ScoreSourceOwner::OrdinaryGroup {
            source_instruction_indices,
        } = &symbolic.owner
            && (ordinary_member_sources.len() != source_instruction_indices.len()
                || !source_instruction_indices
                    .iter()
                    .copied()
                    .eq(ordinary_member_sources.into_iter()))
        {
            return Err(invalid(
                owner,
                "ordinary group member sources must exactly match its body",
            ));
        }
        let mut anchors = HashSet::new();
        for &anchor_index in &member.anchor_indices {
            if anchor_index >= score.anchors.len()
                || !anchors.insert(anchor_index)
                || self.anchor_claims[anchor_index].replace(claim).is_some()
            {
                return Err(invalid(
                    owner,
                    "outer member anchor ownership is invalid or overlapping",
                ));
            }
        }
        let mut transforms = HashSet::new();
        for &transform_index in &member.transform_group_indices {
            let Some(transform) = score.transform_groups.get(transform_index) else {
                return Err(invalid(owner, "outer member transform index is invalid"));
            };
            if !transforms.insert(transform_index)
                || transform.start < member.start
                || transform.end > member.end
                || !transform
                    .anchor_indices
                    .iter()
                    .all(|index| anchors.contains(index))
                || self.transform_claims[transform_index]
                    .replace(claim)
                    .is_some()
            {
                return Err(invalid(
                    owner,
                    "outer member transform ownership is invalid or overlapping",
                ));
            }
        }
        self.contributions.push(Contribution {
            source,
            owner: SavedScoreResourceOwner::SourceInstruction {
                source_instruction_index: source,
            },
            demand: ResourceDemand {
                logical_objects: repetitions,
                maximum_resolved_count: repetitions,
                ..ResourceDemand::default()
            },
        });
        Ok(source)
    }

    fn analyze_groups(&mut self, score: &Score) -> Result<(), SavedScoreResourceError> {
        let mut coordinated_group_ids = HashSet::new();
        for (group_index, group) in score.placement_groups.iter().enumerate() {
            let resolved = group.resolved.as_ref().unwrap();
            let PlacementGroupOwner::CoordinatedGroup {
                group_index: source_group_index,
            } = resolved.owner;
            let owner = SavedScoreResourceOwner::PlacementGroup {
                placement_group_index: group_index,
                owner: resolved.owner.clone(),
            };
            if !coordinated_group_ids.insert(source_group_index) {
                return Err(invalid(owner, "coordinated group identity is duplicated"));
            }
            let mut member_sources = Vec::new();
            for member in &group.members {
                let symbolic = member
                    .symbolic
                    .as_ref()
                    .ok_or_else(|| invalid(owner.clone(), "placement member is not symbolic"))?;
                member_sources.extend(symbolic_sources(symbolic));
            }
            let unit = self.register_group(
                &member_sources,
                group.cycle_members.is_some(),
                owner.clone(),
            )?;
            self.placement_sources.push(unit);
            for (ordinal, member) in group.members.iter().enumerate() {
                let symbolic = member.symbolic.as_ref().unwrap();
                self.register_outer_member(
                    score,
                    member,
                    cycle_repetitions(
                        group.cycle_members.as_ref(),
                        u64::try_from(ordinal).expect("member ordinal fits u64"),
                        group.members.len(),
                        symbolic.instance_count,
                    ),
                    group.cycle_members.is_some(),
                    owner.clone(),
                )?;
            }
            self.contributions.push(Contribution {
                source: unit,
                owner,
                demand: ResourceDemand {
                    template_nodes: 1,
                    placement_instances: 1,
                    ..ResourceDemand::default()
                },
            });
        }

        for (group_index, group) in score.fill_groups.iter().enumerate() {
            let owner = SavedScoreResourceOwner::FillGroup {
                fill_group_index: group_index,
                owner: group.owner.clone(),
            };
            let synthetic = matches!(
                (&group.owner, group.members.as_slice()),
                (
                    FillGroupOwner::Instruction { .. },
                    [PlacementMember {
                        symbolic: Some(symbolic),
                        ..
                    }]
                ) if symbolic.kind == SymbolicMemberKind::Primitive
            );
            if synthetic {
                let member = &group.members[0];
                let symbolic = member.symbolic.as_ref().unwrap();
                let FillGroupOwner::Instruction {
                    source_instruction_index,
                } = group.owner
                else {
                    unreachable!()
                };
                let source = source_index(&symbolic.owner);
                if source != source_instruction_index
                    || member.end - member.start != 1
                    || !member.anchor_indices.is_empty()
                    || !member.transform_group_indices.is_empty()
                    || symbolic.instance_count != group.logical_count
                {
                    return Err(invalid(owner, "synthetic fill ownership is inconsistent"));
                }
                let instruction_owner = &score.instructions[member.start]
                    .arrangement
                    .as_ref()
                    .unwrap()
                    .resolved
                    .as_ref()
                    .unwrap()
                    .owner;
                if instruction_owner != &symbolic.owner
                    || self.direct_fills[member.start]
                        .replace(DirectFill {
                            group_index,
                            source,
                            count: symbolic.instance_count,
                        })
                        .is_some()
                {
                    return Err(invalid(
                        owner,
                        "synthetic fill must uniquely match its instruction template",
                    ));
                }
                self.add_source(source);
                self.fill_sources.push(source);
                continue;
            }

            let mut member_sources = Vec::new();
            for member in &group.members {
                let symbolic = member
                    .symbolic
                    .as_ref()
                    .ok_or_else(|| invalid(owner.clone(), "fill member is not symbolic"))?;
                member_sources.extend(symbolic_sources(symbolic));
            }
            if let FillGroupOwner::Instruction {
                source_instruction_index,
            } = group.owner
                && (member_sources.as_slice() != [source_instruction_index]
                    || group.members[0].symbolic.as_ref().unwrap().kind
                        != SymbolicMemberKind::Macro)
            {
                return Err(invalid(
                    owner,
                    "instruction-owned authored fill must own one complete Macro",
                ));
            }
            if let FillGroupOwner::CoordinatedGroup { group_index } = group.owner
                && !coordinated_group_ids.insert(group_index)
            {
                return Err(invalid(owner, "coordinated group identity is duplicated"));
            }
            let unit = self.register_group(
                &member_sources,
                group.cycle_members.is_some(),
                owner.clone(),
            )?;
            self.fill_sources.push(unit);
            for (ordinal, member) in group.members.iter().enumerate() {
                let symbolic = member.symbolic.as_ref().unwrap();
                self.register_outer_member(
                    score,
                    member,
                    cycle_repetitions(
                        group.cycle_members.as_ref(),
                        u64::try_from(ordinal).expect("member ordinal fits u64"),
                        group.members.len(),
                        symbolic.instance_count,
                    ),
                    group.cycle_members.is_some(),
                    owner.clone(),
                )?;
            }
            self.contributions.push(Contribution {
                source: unit,
                owner,
                demand: ResourceDemand {
                    template_nodes: 1,
                    fill_instances: 1,
                    ..ResourceDemand::default()
                },
            });
        }

        for (group_index, group) in score.repetition_groups.iter().enumerate() {
            let symbolic = group.member.symbolic.as_ref().unwrap();
            let source = source_index(&symbolic.owner);
            let owner = SavedScoreResourceOwner::RepetitionGroup {
                repetition_group_index: group_index,
                source_instruction_index: source,
            };
            self.add_source(source);
            self.set_unit_owner(source, owner.clone())?;
            self.register_outer_member(
                score,
                &group.member,
                symbolic.instance_count,
                false,
                owner,
            )?;
            self.repetition_sources.push(source);
        }

        for fill in self.direct_fills.iter().flatten() {
            let unit = self.source_units[&fill.source];
            if !self.unit_owners.contains_key(&unit) {
                self.unit_owners.insert(
                    unit,
                    SavedScoreResourceOwner::FillGroup {
                        fill_group_index: fill.group_index,
                        owner: score.fill_groups[fill.group_index].owner.clone(),
                    },
                );
            }
        }
        Ok(())
    }

    fn validate_ownership(&self, score: &Score) -> Result<(), SavedScoreResourceError> {
        let mut direct_template_cycles = BTreeMap::<usize, bool>::new();
        for (instruction_index, instruction) in score.instructions.iter().enumerate() {
            let resolved = instruction
                .arrangement
                .as_ref()
                .unwrap()
                .resolved
                .as_ref()
                .unwrap();
            let claim = self.instruction_claims[instruction_index];
            match (&resolved.owner, claim) {
                (ScoreSourceOwner::MacroEmit { .. }, None) => {
                    return Err(invalid(
                        SavedScoreResourceOwner::Instruction {
                            instruction_index,
                            owner: resolved.owner.clone(),
                        },
                        "Macro emitted instruction has no complete outer owner",
                    ));
                }
                (ScoreSourceOwner::MacroEmit { .. }, Some(claim))
                    if !matches!(
                        claim.kind,
                        SymbolicMemberKind::Macro | SymbolicMemberKind::OrdinaryGroup
                    ) =>
                {
                    return Err(invalid(
                        SavedScoreResourceOwner::Instruction {
                            instruction_index,
                            owner: resolved.owner.clone(),
                        },
                        "Macro emitted instruction has a non-Macro outer owner",
                    ));
                }
                (ScoreSourceOwner::SourceInstruction { .. }, Some(claim))
                    if !matches!(
                        claim.kind,
                        SymbolicMemberKind::Primitive | SymbolicMemberKind::OrdinaryGroup
                    ) =>
                {
                    return Err(invalid(
                        SavedScoreResourceOwner::Instruction {
                            instruction_index,
                            owner: resolved.owner.clone(),
                        },
                        "source primitive has an incompatible outer owner",
                    ));
                }
                _ => {}
            }
            if let Some(claim) = claim
                && self.unit(claim.source) != self.unit(self.instruction_sources[instruction_index])
            {
                return Err(invalid(
                    SavedScoreResourceOwner::Instruction {
                        instruction_index,
                        owner: resolved.owner.clone(),
                    },
                    "instruction source differs from its outer owner",
                ));
            }
            if let ScoreSourceOwner::SourceInstruction {
                instruction_index: source_instruction_index,
            } = resolved.owner
            {
                let cycle = claim.is_some_and(|claim| claim.cycle);
                if direct_template_cycles
                    .insert(source_instruction_index, cycle)
                    .is_some_and(|prior_cycle| !prior_cycle || !cycle)
                {
                    return Err(invalid(
                        SavedScoreResourceOwner::Instruction {
                            instruction_index,
                            owner: resolved.owner.clone(),
                        },
                        "source instruction owns multiple templates outside one cycle group",
                    ));
                }
            }
            if (claim.is_some_and(|claim| claim.kind == SymbolicMemberKind::Primitive)
                || self.direct_fills[instruction_index].is_some())
                && (instruction.arrangement.as_ref().unwrap().count != 1
                    || !matches!(resolved.count_origin, crate::CountOrigin::TemplateSingle))
            {
                return Err(invalid(
                    SavedScoreResourceOwner::Instruction {
                        instruction_index,
                        owner: resolved.owner.clone(),
                    },
                    "externally counted primitive must be stored as one template instance",
                ));
            }
        }
        for (anchor_index, claim) in self.anchor_claims.iter().enumerate() {
            if claim.is_none() {
                return Err(invalid(
                    SavedScoreResourceOwner::Score,
                    "saved anchor has no source owner",
                ));
            }
            if !matches!(
                claim.unwrap().kind,
                SymbolicMemberKind::Macro | SymbolicMemberKind::OrdinaryGroup
            ) {
                return Err(invalid(
                    SavedScoreResourceOwner::Anchor {
                        anchor_index,
                        source_instruction_index: claim.unwrap().source,
                    },
                    "saved anchor must belong to a complete Macro",
                ));
            }
        }
        for (transform_group_index, claim) in self.transform_claims.iter().enumerate() {
            if claim.is_none() {
                return Err(invalid(
                    SavedScoreResourceOwner::Score,
                    "saved transform has no source owner",
                ));
            }
            if !matches!(
                claim.unwrap().kind,
                SymbolicMemberKind::Macro | SymbolicMemberKind::OrdinaryGroup
            ) {
                return Err(invalid(
                    SavedScoreResourceOwner::TransformGroup {
                        transform_group_index,
                        source_instruction_index: claim.unwrap().source,
                    },
                    "saved transform must belong to a complete Macro",
                ));
            }
        }
        for (instruction_index, instruction) in score.instructions.iter().enumerate() {
            if let Some(relation) = &instruction.relation {
                if relation
                    .target_instruction_index
                    .is_some_and(|index| index >= score.instructions.len())
                    || relation
                        .target_anchor_index
                        .is_some_and(|index| index >= score.anchors.len())
                {
                    let owner = instruction
                        .arrangement
                        .as_ref()
                        .unwrap()
                        .resolved
                        .as_ref()
                        .unwrap()
                        .owner
                        .clone();
                    return Err(invalid(
                        SavedScoreResourceOwner::Instruction {
                            instruction_index,
                            owner,
                        },
                        "relation target index exceeds the saved Score",
                    ));
                }
            }
        }
        Ok(())
    }

    fn account(&mut self, score: &Score) {
        for (instruction_index, instruction) in score.instructions.iter().enumerate() {
            let source = self.instruction_sources[instruction_index];
            let arrangement = instruction.arrangement.as_ref().unwrap();
            let intrinsic = self.direct_fills[instruction_index]
                .as_ref()
                .map_or(u64::from(arrangement.count), |fill| fill.count);
            let outer =
                self.instruction_claims[instruction_index].map_or(1, |claim| claim.repetitions);
            let owner = SavedScoreResourceOwner::Instruction {
                instruction_index,
                owner: arrangement.resolved.as_ref().unwrap().owner.clone(),
            };
            let Some(primitive_marks) = intrinsic.checked_mul(outer) else {
                self.pending_failures.push(PendingFailure {
                    source,
                    owner,
                    dimension: ResourceDimension::PrimitiveMarks,
                });
                continue;
            };
            let unclaimed_logical =
                u64::from(self.instruction_claims[instruction_index].is_none()) * intrinsic;
            self.contributions.push(Contribution {
                source,
                owner,
                demand: ResourceDemand {
                    logical_objects: unclaimed_logical,
                    primitive_marks,
                    object_templates: 1,
                    maximum_per_template_primitive_marks: primitive_marks,
                    maximum_resolved_count: intrinsic,
                    template_nodes: 1,
                    ..ResourceDemand::default()
                },
            });
        }
        for (anchor_index, claim) in self.anchor_claims.iter().enumerate() {
            let claim = claim.unwrap();
            self.contributions.push(Contribution {
                source: claim.source,
                owner: SavedScoreResourceOwner::Anchor {
                    anchor_index,
                    source_instruction_index: claim.source,
                },
                demand: ResourceDemand {
                    template_nodes: 1,
                    anchor_instances: claim.repetitions,
                    ..ResourceDemand::default()
                },
            });
        }
        for (transform_group_index, claim) in self.transform_claims.iter().enumerate() {
            let claim = claim.unwrap();
            self.contributions.push(Contribution {
                source: claim.source,
                owner: SavedScoreResourceOwner::TransformGroup {
                    transform_group_index,
                    source_instruction_index: claim.source,
                },
                demand: ResourceDemand {
                    template_nodes: 1,
                    transform_instances: claim.repetitions,
                    ..ResourceDemand::default()
                },
            });
        }
        for fill in self.direct_fills.iter().flatten() {
            let outer = self.instruction_claims[score.fill_groups[fill.group_index].start]
                .map_or(1, |claim| claim.repetitions);
            self.contributions.push(Contribution {
                source: fill.source,
                owner: SavedScoreResourceOwner::FillGroup {
                    fill_group_index: fill.group_index,
                    owner: score.fill_groups[fill.group_index].owner.clone(),
                },
                demand: ResourceDemand {
                    fill_instances: outer,
                    ..ResourceDemand::default()
                },
            });
        }
    }

    fn unit(&self, source: usize) -> usize {
        self.source_units[&source]
    }
}

struct UnitDemand {
    demand: ResourceDemand,
    cause: Option<(SavedScoreResourceOwner, ResourceDimension)>,
    dimension_owners: [Option<SavedScoreResourceOwner>; 10],
}

impl UnitDemand {
    fn new() -> Self {
        Self {
            demand: ResourceDemand::default(),
            cause: None,
            dimension_owners: std::array::from_fn(|_| None),
        }
    }
}

struct IndexMap {
    values: Vec<Option<usize>>,
    boundaries: Vec<usize>,
}

impl IndexMap {
    fn new(retained: &[bool]) -> Self {
        let mut values = vec![None; retained.len()];
        let mut boundaries = Vec::with_capacity(retained.len() + 1);
        boundaries.push(0);
        let mut next = 0;
        for (index, &keep) in retained.iter().enumerate() {
            if keep {
                values[index] = Some(next);
                next += 1;
            }
            boundaries.push(next);
        }
        Self { values, boundaries }
    }

    fn required(
        &self,
        old: usize,
        owner: SavedScoreResourceOwner,
    ) -> Result<usize, SavedScoreResourceError> {
        self.values
            .get(old)
            .copied()
            .flatten()
            .ok_or_else(|| invalid(owner, "retained descriptor references an omitted index"))
    }

    fn required_indices(
        &self,
        old: &[usize],
        owner: SavedScoreResourceOwner,
    ) -> Result<Vec<usize>, SavedScoreResourceError> {
        old.iter()
            .map(|&index| self.required(index, owner.clone()))
            .collect()
    }
}

fn remap_member(
    member: &PlacementMember,
    instructions: &IndexMap,
    anchors: &IndexMap,
    transforms: &IndexMap,
    owner: SavedScoreResourceOwner,
) -> Result<PlacementMember, SavedScoreResourceError> {
    Ok(PlacementMember {
        start: instructions.boundaries[member.start],
        end: instructions.boundaries[member.end],
        anchor_indices: anchors.required_indices(&member.anchor_indices, owner.clone())?,
        transform_group_indices: transforms
            .required_indices(&member.transform_group_indices, owner)?,
        symbolic: member.symbolic.clone(),
    })
}

fn remap_mirror_body_ref(
    score: &Score,
    body: &crate::MirrorBodyRef,
    instructions: &IndexMap,
    placements: &IndexMap,
    repetitions: &IndexMap,
) -> Option<crate::MirrorBodyRef> {
    match body {
        crate::MirrorBodyRef::Instruction { instruction_index } => instructions
            .values
            .get(*instruction_index)?
            .map(|instruction_index| crate::MirrorBodyRef::Instruction { instruction_index }),
        crate::MirrorBodyRef::RepetitionGroup {
            repetition_group_index,
        } => repetitions
            .values
            .get(*repetition_group_index)?
            .map(
                |repetition_group_index| crate::MirrorBodyRef::RepetitionGroup {
                    repetition_group_index,
                },
            ),
        crate::MirrorBodyRef::PlacementMember {
            placement_group_index,
            member_index,
        } => {
            score
                .placement_groups
                .get(*placement_group_index)?
                .members
                .get(*member_index)?;
            placements
                .values
                .get(*placement_group_index)?
                .map(
                    |placement_group_index| crate::MirrorBodyRef::PlacementMember {
                        placement_group_index,
                        member_index: *member_index,
                    },
                )
        }
        crate::MirrorBodyRef::PlacementGroup {
            placement_group_index,
        } => placements
            .values
            .get(*placement_group_index)?
            .map(
                |placement_group_index| crate::MirrorBodyRef::PlacementGroup {
                    placement_group_index,
                },
            ),
    }
}

// Original instruction provenance for the existing relation-only diagnostic.
// This is not a replacement target: missing references are never rebound.
fn mirror_body_instruction_index(score: &Score, body: &crate::MirrorBodyRef) -> Option<usize> {
    match body {
        crate::MirrorBodyRef::Instruction { instruction_index } => Some(*instruction_index),
        crate::MirrorBodyRef::RepetitionGroup {
            repetition_group_index,
        } => score
            .repetition_groups
            .get(*repetition_group_index)
            .map(|group| group.member.start),
        crate::MirrorBodyRef::PlacementMember {
            placement_group_index,
            member_index,
        } => score
            .placement_groups
            .get(*placement_group_index)?
            .members
            .get(*member_index)
            .map(|member| member.start),
        crate::MirrorBodyRef::PlacementGroup {
            placement_group_index,
        } => score
            .placement_groups
            .get(*placement_group_index)
            .map(|group| group.start),
    }
}

/// Demand of a legacy-edition Score, counted the way its hosts limited it.
///
/// Legacy editions predate accounting v1 and carry no resource policy. The
/// Python host capped two totals when it coerced them: the instruction count,
/// and the sum over composite units of the head's count (rows x cols for an
/// explicit grid) times the group size. This counts the same two totals, so
/// saved legacy works stay within the limits they were drawn under.
///
/// Stored groups are counted once each, and anchors once plus once for every
/// group that moves them: scheduling compares every pair of groups and their
/// anchor lists (100 groups sharing 1,000 anchors took 0.55 s), so both need a
/// bound before execution starts.
pub fn legacy_resource_demand(score: &Score) -> Result<ResourceDemand, ResourceDimension> {
    let mut primitive_marks = 0_u64;
    let mut index = 0;
    while let Some(head) = score.instructions.get(index) {
        let (marks, group_size) = head.arrangement.as_ref().map_or((1, 1), |arrangement| {
            let marks = match (arrangement.layout, arrangement.rows, arrangement.cols) {
                (crate::Layout::Grid, Some(rows), Some(cols)) => u64::from(rows) * u64::from(cols),
                _ => u64::from(arrangement.count),
            };
            (marks.max(1), arrangement.group_size.max(1))
        });
        primitive_marks = marks
            .checked_mul(u64::from(group_size))
            .and_then(|unit| primitive_marks.checked_add(unit))
            .ok_or(ResourceDimension::PrimitiveMarks)?;
        index = index.saturating_add(usize::try_from(group_size).unwrap_or(usize::MAX));
    }
    let count = |length: usize, dimension| u64::try_from(length).map_err(|_| dimension);
    let anchor_moves = score
        .transform_groups
        .iter()
        .map(|group| group.anchor_indices.len())
        .chain(
            score
                .placement_groups
                .iter()
                .flat_map(|group| &group.members)
                .map(|member| member.anchor_indices.len()),
        )
        .try_fold(score.anchors.len(), usize::checked_add)
        .ok_or(ResourceDimension::AnchorInstances)?;
    Ok(ResourceDemand {
        primitive_marks,
        object_templates: count(score.instructions.len(), ResourceDimension::ObjectTemplates)?,
        anchor_instances: count(anchor_moves, ResourceDimension::AnchorInstances)?,
        transform_instances: count(
            score.transform_groups.len(),
            ResourceDimension::TransformInstances,
        )?,
        placement_instances: count(
            score.placement_groups.len(),
            ResourceDimension::PlacementInstances,
        )?,
        fill_instances: count(score.fill_groups.len(), ResourceDimension::FillInstances)?,
        ..ResourceDemand::default()
    })
}

/// Refuse a legacy-edition Score whose demand exceeds either authority.
///
/// A compact Score is finalized by [`finalize_saved_score`] instead. Without
/// this check an explicit budget did not limit a legacy Score at all, and an
/// arrangement count of 100,000 took 50 s and 95 MB of SVG to render.
pub fn check_legacy_resource_demand(
    score: &Score,
    authorized_hard_policy: &HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
) -> Result<ResourceDemand, SavedScoreResourceError> {
    let demand = legacy_resource_demand(score).map_err(|dimension| {
        error(
            SavedScoreResourceOwner::Score,
            SavedScoreResourceFailure::ArithmeticOverflow(dimension),
        )
    })?;
    authorized_hard_policy
        .budget
        .check(demand, ResourceAuthority::HardPolicy)
        .and_then(|()| {
            operational_budget
                .0
                .check(demand, ResourceAuthority::OperationalBudget)
        })
        .map_err(|exceeded| {
            error(
                SavedScoreResourceOwner::Score,
                SavedScoreResourceFailure::BudgetExceeded(exceeded),
            )
        })?;
    Ok(demand)
}

/// Recompute demand from an untrusted compact Score, omit only offending atomic
/// source units, and return a schema-valid Score with every retained index remapped.
pub fn finalize_saved_score(
    score: &Score,
    authorized_hard_policy: &HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
) -> Result<FinalizedScore, SavedScoreResourceError> {
    finalize_saved_score_with_omitted_instructions(
        score,
        authorized_hard_policy,
        operational_budget,
        &[],
    )
}

/// Apply the normal saved-Score finalization while excluding every complete
/// atomic source unit that contains a caller-omitted original instruction.
pub fn finalize_saved_score_with_omitted_instructions(
    score: &Score,
    authorized_hard_policy: &HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
    omitted_original_instruction_indices: &[usize],
) -> Result<FinalizedScore, SavedScoreResourceError> {
    if !matches!(
        score.version.as_str(),
        "0.10.0" | "0.11.0" | "0.12.0" | "0.13.0" | "0.14.0" | "0.15.0"
    ) {
        return Err(invalid(
            SavedScoreResourceOwner::Score,
            "saved resource finalization requires compact Score 0.10 or later",
        ));
    }
    if authorized_hard_policy.identity.trim().is_empty() {
        return Err(invalid(
            SavedScoreResourceOwner::Score,
            "authorized hard policy identity is required",
        ));
    }
    let snapshot = score.resource_policy.as_ref().ok_or_else(|| {
        error(
            SavedScoreResourceOwner::Score,
            SavedScoreResourceFailure::MissingResourcePolicy,
        )
    })?;
    if snapshot.accounting_id != RESOURCE_ACCOUNTING_ID {
        return Err(error(
            SavedScoreResourceOwner::Score,
            SavedScoreResourceFailure::AccountingIdMismatch {
                saved: snapshot.accounting_id.clone(),
            },
        ));
    }
    if snapshot.hard_policy != *authorized_hard_policy {
        return Err(error(
            SavedScoreResourceOwner::Score,
            SavedScoreResourceFailure::HardPolicyMismatch {
                saved: snapshot.hard_policy.clone(),
                authorized: authorized_hard_policy.clone(),
            },
        ));
    }
    // Schema validation compares placement groups with every earlier placement
    // group and every transform group, before any accounting. A stored group
    // or anchor is performed at least once unless it belongs to a cycle member
    // that never occurs, so compiled Scores store far fewer than the hard
    // policy's instance maxima. Refusing larger stored counts here keeps that
    // validation bounded for an untrusted Score.
    let maximum = authorized_hard_policy.budget.maximum;
    for (stored, dimension) in [
        (score.anchors.len(), ResourceDimension::AnchorInstances),
        (
            score.transform_groups.len(),
            ResourceDimension::TransformInstances,
        ),
        (
            score.placement_groups.len(),
            ResourceDimension::PlacementInstances,
        ),
        (score.fill_groups.len(), ResourceDimension::FillInstances),
    ] {
        let stored = u64::try_from(stored).unwrap_or(u64::MAX);
        if stored > maximum.get(dimension) {
            return Err(error(
                SavedScoreResourceOwner::Score,
                SavedScoreResourceFailure::BudgetExceeded(ResourceBudgetExceeded {
                    authority: ResourceAuthority::HardPolicy,
                    dimension,
                    required: stored,
                    maximum: maximum.get(dimension),
                }),
            ));
        }
    }
    score
        .validate_schema_edition()
        .map_err(|reason| invalid(SavedScoreResourceOwner::Score, reason))?;

    for &instruction_index in omitted_original_instruction_indices {
        if instruction_index >= score.instructions.len() {
            return Err(error(
                SavedScoreResourceOwner::Score,
                SavedScoreResourceFailure::InvalidOmittedInstructionIndex {
                    instruction_index,
                    instruction_count: score.instructions.len(),
                },
            ));
        }
    }

    let mut analysis = Analysis::new(score)?;
    analysis.analyze_groups(score)?;
    analysis.validate_ownership(score)?;
    analysis.account(score);
    let omitted_units = omitted_original_instruction_indices
        .iter()
        .map(|&instruction_index| analysis.unit(analysis.instruction_sources[instruction_index]))
        .collect::<HashSet<_>>();

    let mut units: BTreeMap<usize, UnitDemand> = analysis
        .source_units
        .values()
        .copied()
        .map(|unit| (unit, UnitDemand::new()))
        .collect();
    for contribution in &analysis.contributions {
        let unit = analysis.unit(contribution.source);
        let entry = units.get_mut(&unit).unwrap();
        for (dimension_index, dimension) in ResourceDimension::ALL.into_iter().enumerate() {
            let value = contribution.demand.get(dimension);
            let peak = matches!(
                dimension,
                ResourceDimension::MaximumPerTemplatePrimitiveMarks
                    | ResourceDimension::MaximumResolvedCount
            );
            if value > 0 && (!peak || value >= entry.demand.get(dimension)) {
                entry.dimension_owners[dimension_index] = Some(contribution.owner.clone());
            }
        }
        if entry.cause.is_none() {
            match entry.demand.checked_add(contribution.demand) {
                Ok(demand) => entry.demand = demand,
                Err(dimension) => entry.cause = Some((contribution.owner.clone(), dimension)),
            }
        }
    }
    for failure in &analysis.pending_failures {
        let unit = analysis.unit(failure.source);
        let entry = units.get_mut(&unit).unwrap();
        if entry.cause.is_none() {
            entry.cause = Some((failure.owner.clone(), failure.dimension));
        }
    }

    let mut demand = ResourceDemand::default();
    let mut admitted_units = HashSet::new();
    let mut resource_diagnostics = Vec::new();
    for (&unit, entry) in &units {
        if omitted_units.contains(&unit) {
            continue;
        }
        let unit_owner = analysis.unit_owners.get(&unit).cloned().unwrap_or(
            SavedScoreResourceOwner::SourceInstruction {
                source_instruction_index: unit,
            },
        );
        let candidate = demand.checked_add(entry.demand);
        let failure = entry
            .cause
            .as_ref()
            .map(|(owner, dimension)| {
                (
                    owner.clone(),
                    SavedScoreResourceFailure::ArithmeticOverflow(*dimension),
                )
            })
            .or_else(|| match candidate {
                Err(dimension) => {
                    let index = ResourceDimension::ALL
                        .iter()
                        .position(|candidate| *candidate == dimension)
                        .unwrap();
                    Some((
                        entry.dimension_owners[index]
                            .clone()
                            .unwrap_or_else(|| unit_owner.clone()),
                        SavedScoreResourceFailure::ArithmeticOverflow(dimension),
                    ))
                }
                Ok(candidate) => authorized_hard_policy
                    .budget
                    .check(candidate, ResourceAuthority::HardPolicy)
                    .and_then(|()| {
                        operational_budget
                            .0
                            .check(candidate, ResourceAuthority::OperationalBudget)
                    })
                    .err()
                    .map(|exceeded| {
                        let index = ResourceDimension::ALL
                            .iter()
                            .position(|dimension| *dimension == exceeded.dimension)
                            .unwrap();
                        (
                            entry.dimension_owners[index]
                                .clone()
                                .unwrap_or_else(|| unit_owner.clone()),
                            SavedScoreResourceFailure::BudgetExceeded(exceeded),
                        )
                    }),
            });
        if let Some((cause_owner, failure)) = failure {
            resource_diagnostics.push(SavedScoreResourceDiagnostic {
                owner: unit_owner,
                cause_owner,
                failure,
                disposition: SavedScoreResourceDisposition::Omitted,
            });
        } else {
            demand = candidate.unwrap();
            admitted_units.insert(unit);
        }
    }

    let source_admitted = |source: usize| admitted_units.contains(&analysis.unit(source));
    let retained_instructions = analysis
        .instruction_sources
        .iter()
        .map(|&source| source_admitted(source))
        .collect::<Vec<_>>();
    let retained_anchors = analysis
        .anchor_claims
        .iter()
        .map(|claim| source_admitted(claim.unwrap().source))
        .collect::<Vec<_>>();
    let retained_transforms = analysis
        .transform_claims
        .iter()
        .map(|claim| source_admitted(claim.unwrap().source))
        .collect::<Vec<_>>();
    let retained_placements = analysis
        .placement_sources
        .iter()
        .map(|&source| source_admitted(source))
        .collect::<Vec<_>>();
    let retained_fills = analysis
        .fill_sources
        .iter()
        .map(|&source| source_admitted(source))
        .collect::<Vec<_>>();
    let retained_repetitions = analysis
        .repetition_sources
        .iter()
        .map(|&source| source_admitted(source))
        .collect::<Vec<_>>();

    let instruction_map = IndexMap::new(&retained_instructions);
    let anchor_map = IndexMap::new(&retained_anchors);
    let transform_map = IndexMap::new(&retained_transforms);
    let placement_map = IndexMap::new(&retained_placements);
    let fill_map = IndexMap::new(&retained_fills);
    let repetition_map = IndexMap::new(&retained_repetitions);
    let mut relation_diagnostics = Vec::new();
    let mut instructions = Vec::with_capacity(instruction_map.values.iter().flatten().count());
    for (instruction_index, instruction) in score.instructions.iter().enumerate() {
        if !retained_instructions[instruction_index] {
            continue;
        }
        let mut instruction = instruction.clone();
        if let Some(relation) = instruction.relation.as_mut() {
            let missing = relation
                .target_instruction_index
                .is_some_and(|index| instruction_map.values[index].is_none())
                || relation
                    .target_anchor_index
                    .is_some_and(|index| anchor_map.values[index].is_none());
            if missing {
                let owner = instruction
                    .arrangement
                    .as_ref()
                    .unwrap()
                    .resolved
                    .as_ref()
                    .unwrap()
                    .owner
                    .clone();
                relation_diagnostics.push(SavedScoreRelationDiagnostic {
                    instruction_index,
                    owner,
                    target_instruction_index: relation.target_instruction_index,
                    target_anchor_index: relation.target_anchor_index,
                    disposition: SavedScoreRelationDisposition::Omitted,
                });
                instruction.relation = None;
            } else {
                if let Some(index) = relation.target_instruction_index.as_mut() {
                    *index = instruction_map.values[*index].unwrap();
                }
                if let Some(index) = relation.target_anchor_index.as_mut() {
                    *index = anchor_map.values[*index].unwrap();
                }
            }
        }
        instructions.push(instruction);
    }

    let anchors = score
        .anchors
        .iter()
        .enumerate()
        .filter(|(index, _)| retained_anchors[*index])
        .map(|(_, anchor)| anchor.clone())
        .collect();
    let transform_groups = score
        .transform_groups
        .iter()
        .enumerate()
        .filter(|(index, _)| retained_transforms[*index])
        .map(|(index, group)| {
            let owner = SavedScoreResourceOwner::TransformGroup {
                transform_group_index: index,
                source_instruction_index: analysis.transform_claims[index].unwrap().source,
            };
            let mut group = group.clone();
            group.start = instruction_map.boundaries[group.start];
            group.end = instruction_map.boundaries[group.end];
            group.fixed_position_indices =
                instruction_map.required_indices(&group.fixed_position_indices, owner.clone())?;
            group.anchor_indices = anchor_map.required_indices(&group.anchor_indices, owner)?;
            Ok(group)
        })
        .collect::<Result<Vec<_>, SavedScoreResourceError>>()?;
    let placement_groups = score
        .placement_groups
        .iter()
        .enumerate()
        .filter(|(index, _)| retained_placements[*index])
        .map(|(index, group)| {
            let owner = SavedScoreResourceOwner::PlacementGroup {
                placement_group_index: index,
                owner: group.resolved.as_ref().unwrap().owner.clone(),
            };
            let mut group = group.clone();
            group.start = instruction_map.boundaries[group.start];
            group.end = instruction_map.boundaries[group.end];
            group.members = group
                .members
                .iter()
                .map(|member| {
                    remap_member(
                        member,
                        &instruction_map,
                        &anchor_map,
                        &transform_map,
                        owner.clone(),
                    )
                })
                .collect::<Result<Vec<_>, _>>()?;
            Ok(group)
        })
        .collect::<Result<Vec<_>, SavedScoreResourceError>>()?;
    let fill_groups = score
        .fill_groups
        .iter()
        .enumerate()
        .filter(|(index, _)| retained_fills[*index])
        .map(|(index, group)| {
            let owner = SavedScoreResourceOwner::FillGroup {
                fill_group_index: index,
                owner: group.owner.clone(),
            };
            let mut group = group.clone();
            group.start = instruction_map.boundaries[group.start];
            group.end = instruction_map.boundaries[group.end];
            group.members = group
                .members
                .iter()
                .map(|member| {
                    remap_member(
                        member,
                        &instruction_map,
                        &anchor_map,
                        &transform_map,
                        owner.clone(),
                    )
                })
                .collect::<Result<Vec<_>, _>>()?;
            Ok(group)
        })
        .collect::<Result<Vec<_>, SavedScoreResourceError>>()?;
    let repetition_groups = score
        .repetition_groups
        .iter()
        .enumerate()
        .filter(|(index, _)| retained_repetitions[*index])
        .map(|(index, group)| {
            let owner = SavedScoreResourceOwner::RepetitionGroup {
                repetition_group_index: index,
                source_instruction_index: analysis.repetition_sources[index],
            };
            let mut group = group.clone();
            group.member = remap_member(
                &group.member,
                &instruction_map,
                &anchor_map,
                &transform_map,
                owner,
            )?;
            Ok(group)
        })
        .collect::<Result<Vec<_>, SavedScoreResourceError>>()?;

    let mut finalized = score.clone();
    finalized.instructions = instructions;
    finalized.anchors = anchors;
    finalized.transform_groups = transform_groups;
    finalized.placement_groups = placement_groups;
    finalized.fill_groups = fill_groups;
    finalized.repetition_groups = repetition_groups;
    finalized.mirror_relations = score
        .mirror_relations
        .iter()
        .filter_map(|relation| {
            let target = remap_mirror_body_ref(
                score,
                &relation.target,
                &instruction_map,
                &placement_map,
                &repetition_map,
            );
            let follower = remap_mirror_body_ref(
                score,
                &relation.follower,
                &instruction_map,
                &placement_map,
                &repetition_map,
            );
            let (Some(target), Some(follower)) = (target, follower) else {
                let target_instruction_index =
                    mirror_body_instruction_index(score, &relation.target);
                let instruction_index = mirror_body_instruction_index(score, &relation.follower)
                    .or(target_instruction_index)
                    .unwrap_or(0);
                let owner = score
                    .instructions
                    .get(instruction_index)
                    .and_then(|instruction| instruction.arrangement.as_ref())
                    .and_then(|arrangement| arrangement.resolved.as_ref())
                    .map(|resolved| resolved.owner.clone())
                    .unwrap_or(ScoreSourceOwner::SourceInstruction { instruction_index });
                relation_diagnostics.push(SavedScoreRelationDiagnostic {
                    instruction_index,
                    owner,
                    target_instruction_index,
                    target_anchor_index: None,
                    disposition: SavedScoreRelationDisposition::Omitted,
                });
                return None;
            };
            Some(crate::MirrorRelationV1 {
                target,
                follower,
                follower_facts: relation.follower_facts.clone(),
            })
        })
        .collect();
    finalized
        .resource_policy
        .as_mut()
        .unwrap()
        .operational_budget = operational_budget;
    finalized
        .validate_schema_edition()
        .map_err(|reason| invalid(SavedScoreResourceOwner::Score, reason))?;

    Ok(FinalizedScore {
        score: finalized,
        demand,
        index_maps: SavedScoreIndexMaps {
            instructions: instruction_map.values,
            anchors: anchor_map.values,
            transform_groups: transform_map.values,
            placement_groups: placement_map.values,
            fill_groups: fill_map.values,
            repetition_groups: repetition_map.values,
        },
        resource_diagnostics,
        relation_diagnostics,
    })
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::{Color, ScoreResourcePolicy};

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
            identity: "test.saved-score-policy.v1".into(),
            budget: budget(maximum),
        }
    }

    fn instruction(owner: serde_json::Value, template_single: bool) -> crate::Instruction {
        serde_json::from_value(json!({
            "primitive": "circle",
            "center": [0.5, 0.5],
            "radius": 0.1,
            "arrangement": {
                "count": 1,
                "resolved": {
                    "owner": owner,
                    "first_instance_ordinal": 0,
                    "count_origin": {"kind": if template_single {"template_single"} else {"explicit"}},
                    "domain": [1.0, 1.0],
                    "anchor": {"kind": if template_single {"enclosing_group"} else {"numeric"}, "point": if template_single {serde_json::Value::Null} else {json!([0.5, 0.5])}},
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
        source: usize,
        kind: &str,
        ordinal: u64,
        first: u64,
        count: u64,
    ) -> PlacementMember {
        serde_json::from_value(json!({
            "start": start,
            "end": end,
            "symbolic": {
                "owner": {"kind": "source_instruction", "instruction_index": source},
                "kind": kind,
                "member_ordinal": ordinal,
                "first_instance_ordinal": first,
                "instance_count": count,
                "count_origin": {"kind": "explicit"}
            }
        }))
        .unwrap()
    }

    fn representative_score(policy: HardResourcePolicy) -> Score {
        let mut instructions = vec![
            instruction(
                json!({
                    "kind": "macro_emit",
                    "source_instruction_index": 0,
                    "invocation_ordinal": 0,
                    "generated_ordinal": 0
                }),
                true,
            ),
            instruction(
                json!({"kind": "source_instruction", "instruction_index": 1}),
                true,
            ),
            instruction(
                json!({"kind": "source_instruction", "instruction_index": 2}),
                true,
            ),
            instruction(
                json!({"kind": "source_instruction", "instruction_index": 3}),
                false,
            ),
        ];
        instructions[3].relation = serde_json::from_value(json!({
            "type": "connected",
            "target_instruction_index": 2
        }))
        .unwrap();
        let macro_fill_member: PlacementMember = serde_json::from_value(json!({
            "start": 0,
            "end": 1,
            "symbolic": {
                "owner": {
                    "kind": "macro_emit",
                    "source_instruction_index": 0,
                    "invocation_ordinal": 0,
                    "generated_ordinal": 0
                },
                "kind": "primitive",
                "member_ordinal": 0,
                "first_instance_ordinal": 0,
                "instance_count": 2,
                "count_origin": {"kind": "explicit"}
            }
        }))
        .unwrap();
        Score {
            version: "0.10.0".into(),
            mirror_relations: Vec::new(),
            canvas: crate::Canvas::Id("square".into()),
            background: Color::Black,
            presence: None,
            instructions,
            anchors: Vec::new(),
            transform_groups: Vec::new(),
            placement_groups: vec![
                serde_json::from_value(json!({
                    "start": 1,
                    "end": 3,
                    "layout": "overlap",
                    "at": {"region": [0.0, 0.0, 1.0, 1.0]},
                    "members": [
                        symbolic_member(1, 2, 1, "primitive", 0, 0, 1),
                        symbolic_member(2, 3, 2, "primitive", 1, 1, 1)
                    ],
                    "resolved": {
                        "owner": {"kind": "coordinated_group", "group_index": 7},
                        "logical_count": 2,
                        "domain": [1.0, 1.0],
                        "anchor": {"kind": "named", "region": [0.0, 0.0, 1.0, 1.0]},
                        "recipe": {"kind": "place"},
                        "ordinal_scheme": "source_member_then_instance_v1"
                    }
                }))
                .unwrap(),
            ],
            repetition_groups: vec![crate::RepetitionGroup {
                member: symbolic_member(0, 1, 0, "macro", 0, 0, 3),
                ordinal_scheme: crate::InstanceOrdinalScheme::SourceMemberThenInstanceV1,
            }],
            fill_groups: vec![
                serde_json::from_value(json!({
                    "start": 0,
                    "end": 1,
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
                    "members": [macro_fill_member]
                }))
                .unwrap(),
            ],
            resource_policy: Some(ScoreResourcePolicy {
                accounting_id: RESOURCE_ACCOUNTING_ID.into(),
                hard_policy: policy,
                operational_budget: OperationalResourceBudget(budget(100)),
            }),
        }
    }

    #[test]
    fn nested_fill_parity_and_atomic_later_admission_remap_every_index() {
        let policy = hard(100);
        let score = representative_score(policy.clone());
        assert!(score.validate_schema_edition().is_ok());
        let mut nested_fill = score.clone();
        nested_fill.repetition_groups.clear();
        nested_fill.fill_groups.insert(
            0,
            serde_json::from_value(json!({
                "start": 0,
                "end": 1,
                "owner": {"kind": "instruction", "source_instruction_index": 0},
                "logical_count": 3,
                "recipe": "uniform_in_region",
                "target": {
                    "owner": {"kind": "omitted_canvas"},
                    "geometry": {"kind": "rectangle", "bounds": [0.0, 0.0, 1.0, 1.0]},
                    "reference_area": 1.0
                },
                "boundary": "clip_to_target",
                "ordinal_scheme": "source_member_then_instance_v1",
                "members": [symbolic_member(0, 1, 0, "macro", 0, 0, 3)]
            }))
            .unwrap(),
        );
        let finalized_nested = finalize_saved_score(
            &nested_fill,
            &policy,
            OperationalResourceBudget(budget(100)),
        )
        .unwrap();
        assert_eq!(
            (
                finalized_nested.index_maps.fill_groups,
                finalized_nested.demand.fill_instances,
            ),
            (vec![Some(0), Some(1)], 4)
        );
        let mut operational = budget(100);
        operational.maximum.primitive_marks = 7;

        let finalized =
            finalize_saved_score(&score, &policy, OperationalResourceBudget(operational)).unwrap();

        assert_eq!(finalized.score.background, Color::Black);
        assert_eq!(finalized.score.instructions.len(), 2);
        assert_eq!(
            finalized.index_maps.instructions,
            vec![Some(0), None, None, Some(1)]
        );
        assert_eq!(finalized.index_maps.placement_groups, vec![None]);
        assert_eq!(finalized.index_maps.fill_groups, vec![Some(0)]);
        assert_eq!(finalized.index_maps.repetition_groups, vec![Some(0)]);
        assert!(finalized.score.instructions[1].relation.is_none());
        assert_eq!(finalized.relation_diagnostics.len(), 1);
        assert_eq!(
            finalized.demand,
            ResourceDemand {
                logical_objects: 4,
                primitive_marks: 7,
                object_templates: 2,
                maximum_per_template_primitive_marks: 6,
                maximum_resolved_count: 3,
                template_nodes: 2,
                anchor_instances: 0,
                transform_instances: 0,
                placement_instances: 0,
                fill_instances: 3,
            }
        );
        assert_eq!(finalized.resource_diagnostics.len(), 1);
        assert!(matches!(
            finalized.resource_diagnostics[0],
            SavedScoreResourceDiagnostic {
                owner: SavedScoreResourceOwner::PlacementGroup { .. },
                failure: SavedScoreResourceFailure::BudgetExceeded(ResourceBudgetExceeded {
                    authority: ResourceAuthority::OperationalBudget,
                    dimension: ResourceDimension::PrimitiveMarks,
                    required: 8,
                    maximum: 7,
                }),
                disposition: SavedScoreResourceDisposition::Omitted,
                ..
            }
        ));
        assert!(finalized.score.validate_schema_edition().is_ok());

        let explicitly_omitted = finalize_saved_score_with_omitted_instructions(
            &score,
            &policy,
            OperationalResourceBudget(budget(100)),
            &[2],
        )
        .unwrap();
        assert_eq!(
            (
                explicitly_omitted.index_maps.instructions,
                explicitly_omitted.resource_diagnostics.len(),
                explicitly_omitted.relation_diagnostics.len(),
            ),
            (vec![Some(0), None, None, Some(1)], 0, 1)
        );
    }

    #[test]
    fn compact_mirror_missing_references_diagnose_only_relation_and_preserve_later_pair() {
        let policy = hard(100);
        let mut score = representative_score(policy.clone());
        score.version = "0.15.0".into();
        score.instructions[3].relation = None;
        let instruction_ref =
            |instruction_index| crate::MirrorBodyRef::Instruction { instruction_index };
        let relation = |target, follower| crate::MirrorRelationV1 {
            target,
            follower,
            follower_facts: crate::MirrorFollowerFactsV1 {
                dimensions_fixed: true,
                direction_degrees: None,
            },
        };
        score.mirror_relations = vec![
            relation(instruction_ref(0), instruction_ref(3)),
            relation(
                crate::MirrorBodyRef::PlacementMember {
                    placement_group_index: 0,
                    member_index: usize::MAX,
                },
                instruction_ref(3),
            ),
            relation(instruction_ref(1), instruction_ref(2)),
        ];
        // Missing relation references are recoverable, not schema failures.
        assert_eq!(score.validate_schema_edition(), Ok(()));
        let finalized = finalize_saved_score_with_omitted_instructions(
            &score,
            &policy,
            OperationalResourceBudget(budget(100)),
            &[0],
        )
        .unwrap();
        assert_eq!(finalized.score.instructions, score.instructions[1..]);
        assert_eq!(
            finalized.index_maps.instructions,
            vec![None, Some(0), Some(1), Some(2)]
        );
        assert_eq!(finalized.relation_diagnostics.len(), 2);
        assert!(finalized.relation_diagnostics.iter().all(|diagnostic| {
            diagnostic.instruction_index == 3
                && diagnostic.owner
                    == ScoreSourceOwner::SourceInstruction {
                        instruction_index: 3,
                    }
                && diagnostic.disposition == SavedScoreRelationDisposition::Omitted
        }));
        assert_eq!(
            finalized.relation_diagnostics[0].target_instruction_index,
            Some(0)
        );
        assert_eq!(
            finalized.relation_diagnostics[1].target_instruction_index,
            None
        );
        assert_eq!(
            finalized.score.mirror_relations,
            vec![relation(instruction_ref(0), instruction_ref(1))]
        );
        assert!(finalized.resource_diagnostics.is_empty());
    }

    #[test]
    fn compact_0_13_remap_preserves_a_retained_path_position() {
        let policy = hard(100);
        let mut score = representative_score(policy.clone());
        score.version = "0.13.0".into();
        let mut target = serde_json::to_value(&score.instructions[2]).unwrap();
        let target = target.as_object_mut().unwrap();
        target.insert("primitive".into(), json!("line"));
        target.insert("from".into(), json!([0.1, 0.5]));
        target.insert("to".into(), json!([0.9, 0.5]));
        target.remove("center");
        target.remove("radius");
        score.instructions[2] = serde_json::from_value(serde_json::Value::Object(target.clone()))
            .expect("compact path target line");
        score.instructions[3].relation = serde_json::from_value(json!({
            "type": "connected",
            "target_instruction_index": 2,
            "target_path_position": 0.625
        }))
        .unwrap();
        assert!(score.validate_schema_edition().is_ok());

        let finalized = finalize_saved_score_with_omitted_instructions(
            &score,
            &policy,
            OperationalResourceBudget(budget(100)),
            &[0],
        )
        .unwrap();
        assert_eq!(
            finalized.index_maps.instructions,
            vec![None, Some(0), Some(1), Some(2)]
        );
        let relation = finalized.score.instructions[2]
            .relation
            .as_ref()
            .expect("retained relation");
        assert_eq!(relation.target_instruction_index, Some(1));
        assert_eq!(
            relation.target_path_position,
            Some(crate::TargetPathPosition::Exact(0.625))
        );
    }

    #[test]
    fn legacy_demand_counts_marks_like_the_python_host_and_every_anchor_move() {
        let score: Score = serde_json::from_value(json!({
            "version": "0.9.0",
            "instructions": [
                {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1,
                 "arrangement": {"count": 3, "group_size": 2}},
                {"primitive": "point", "center": [0.2, 0.2], "radius": 0.01},
                {"primitive": "square", "position": [0.1, 0.1], "size": [0.1, 0.1],
                 "arrangement": {"count": 1, "layout": "grid", "rows": 4, "cols": 5}}
            ],
            "anchors": [{"position": [0.5, 0.5]}, {"position": [0.1, 0.9]}],
            "transform_groups": [
                {"start": 0, "end": 0, "rotation_degrees": 5.0, "anchor_indices": [0, 1]},
                {"start": 0, "end": 2, "rotation_degrees": 5.0, "anchor_indices": [0, 1]}
            ]
        }))
        .unwrap();
        let demand = legacy_resource_demand(&score).unwrap();
        // A composite head of 3 with its member, then a 4 x 5 grid.
        assert_eq!(demand.primitive_marks, 3 * 2 + 4 * 5);
        assert_eq!(demand.object_templates, 3);
        // Two anchors, each moved by two groups.
        assert_eq!(demand.anchor_instances, 2 + 2 + 2);
        assert_eq!(demand.transform_instances, 2);
    }

    #[test]
    fn stored_groups_beyond_the_hard_maximum_are_refused_before_validation() {
        let policy = hard(100);
        let mut score = representative_score(policy.clone());
        let stored = score.transform_groups.len() as u64 + 101;
        // Groups that validation would reject; the count is refused first.
        score
            .transform_groups
            .extend((0..101).map(|_| crate::TransformGroup {
                start: 1,
                end: 0,
                rotation_degrees: 0.0,
                scale_x: 1.0,
                scale_y: 1.0,
                translate_x: 0.0,
                translate_y: 0.0,
                fixed_position_indices: Vec::new(),
                anchor_indices: Vec::new(),
            }));
        let error = finalize_saved_score(&score, &policy, OperationalResourceBudget(budget(100)))
            .unwrap_err();
        assert_eq!(
            error.reason,
            SavedScoreResourceFailure::BudgetExceeded(ResourceBudgetExceeded {
                authority: ResourceAuthority::HardPolicy,
                dimension: ResourceDimension::TransformInstances,
                required: stored,
                maximum: 100,
            })
        );
    }

    #[test]
    fn caller_policy_is_authoritative_and_legacy_adapter_needs_all_other_limits() {
        let saved_policy = hard(100);
        let score = representative_score(saved_policy.clone());
        let mut authorized = saved_policy.clone();
        authorized.budget.maximum.primitive_marks = 101;
        assert!(matches!(
            finalize_saved_score(&score, &authorized, OperationalResourceBudget(budget(100)))
                .unwrap_err()
                .reason,
            SavedScoreResourceFailure::HardPolicyMismatch { .. }
        ));

        assert_eq!(
            resource_budget_from_legacy_four_limits(
                LegacyFourResourceLimits {
                    primitive_marks: 400,
                    maximum_per_template_primitive_marks: 240,
                    maximum_resolved_count: 2000,
                    object_templates: 64,
                },
                AdditionalResourceLimits {
                    logical_objects: 401,
                    template_nodes: 65,
                    anchor_instances: 402,
                    transform_instances: 403,
                    placement_instances: 404,
                    fill_instances: 405,
                },
            )
            .maximum,
            ResourceDemand {
                logical_objects: 401,
                primitive_marks: 400,
                object_templates: 64,
                maximum_per_template_primitive_marks: 240,
                maximum_resolved_count: 2000,
                template_nodes: 65,
                anchor_instances: 402,
                transform_instances: 403,
                placement_instances: 404,
                fill_instances: 405,
            }
        );
    }
}
