//! Source-sized validation and admission of a sealed symbolic composition plan.
//!
//! No geometry, count or appearance is changed. Admission covers structural
//! resources only; it neither materializes Score nor certifies renderer capacity.

use std::collections::{HashMap, HashSet};

use serde::Serialize;

use inku_score::{
    HardResourcePolicy, OperationalResourceBudget, RESOURCE_ACCOUNTING_ID, ResourceAuthority,
    ResourceBudgetExceeded, ResourceDemand, ResourceDimension,
};

use crate::{
    CompositionPlanOutcome, CompositionPlanResult, FillPlanOwner, PlacementMemberKind,
    PlacementMemberPlan, PlacementRecipe, ScoreAnchorOrigin, ScoreInstructionOrigin,
};

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum PlanResourceOwner {
    Plan,
    Object(ScoreInstructionOrigin),
    Anchor(ScoreAnchorOrigin),
    SourceInstruction { source_instruction_index: usize },
    PlacementGroup { group_index: usize },
    FillGroup(FillPlanOwner),
    Transform(crate::GeneratedNodeProvenance),
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum PlanResourceFailure {
    StoppedPlan,
    InvalidContract(&'static str),
    ArithmeticOverflow(ResourceDimension),
    BudgetExceeded(ResourceBudgetExceeded),
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct PlanResourceError {
    pub owner: PlanResourceOwner,
    pub reason: PlanResourceFailure,
}

/// Only preflight can construct this borrowing admission token. The immutable
/// borrow prevents mutation of the plan after its demand has been checked.
pub struct AdmittedCompositionPlan<'plan, 'source> {
    plan: &'plan CompositionPlanResult<'source>,
    demand: ResourceDemand,
    hard_policy: HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
}

impl<'plan, 'source> AdmittedCompositionPlan<'plan, 'source> {
    pub fn plan(&self) -> &'plan CompositionPlanResult<'source> {
        self.plan
    }
    pub const fn demand(&self) -> ResourceDemand {
        self.demand
    }
    pub const fn hard_policy(&self) -> &HardResourcePolicy {
        &self.hard_policy
    }
    pub const fn operational_budget(&self) -> OperationalResourceBudget {
        self.operational_budget
    }
    pub const fn accounting_id(&self) -> &'static str {
        RESOURCE_ACCOUNTING_ID
    }
}

fn invalid(owner: &PlanResourceOwner, reason: &'static str) -> PlanResourceError {
    PlanResourceError {
        owner: owner.clone(),
        reason: PlanResourceFailure::InvalidContract(reason),
    }
}

struct Accounting {
    demand: ResourceDemand,
    hard: HardResourcePolicy,
    operational: OperationalResourceBudget,
    contributions: Option<Vec<(ResourceDemand, PlanResourceOwner)>>,
}

impl Accounting {
    fn add(
        &mut self,
        demand: ResourceDemand,
        owner: &PlanResourceOwner,
    ) -> Result<(), PlanResourceError> {
        if let Some(contributions) = &mut self.contributions {
            contributions.push((demand, owner.clone()));
            return Ok(());
        }
        self.demand = self
            .demand
            .checked_add(demand)
            .map_err(|dimension| PlanResourceError {
                owner: owner.clone(),
                reason: PlanResourceFailure::ArithmeticOverflow(dimension),
            })?;
        self.hard
            .budget
            .check(self.demand, ResourceAuthority::HardPolicy)
            .and_then(|()| {
                self.operational
                    .0
                    .check(self.demand, ResourceAuthority::OperationalBudget)
            })
            .map_err(|exceeded| PlanResourceError {
                owner: owner.clone(),
                reason: PlanResourceFailure::BudgetExceeded(exceeded),
            })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct MemberClaim {
    source: usize,
    repetitions: u32,
}

struct Claims {
    objects: Vec<Option<MemberClaim>>,
    anchors: Vec<Option<MemberClaim>>,
    transforms: Vec<Option<MemberClaim>>,
    sources: HashSet<usize>,
}

fn object_source(origin: &ScoreInstructionOrigin) -> usize {
    match origin {
        ScoreInstructionOrigin::SourceInstruction { instruction_index } => *instruction_index,
        ScoreInstructionOrigin::MacroEmit {
            source_instruction_index,
            ..
        } => *source_instruction_index,
    }
}

fn anchor_source(origin: &ScoreAnchorOrigin) -> usize {
    let ScoreAnchorOrigin::MacroAnchor {
        source_instruction_index,
        ..
    } = origin;
    *source_instruction_index
}

fn claim(
    slot: &mut Option<MemberClaim>,
    value: MemberClaim,
    owner: &PlanResourceOwner,
) -> Result<(), PlanResourceError> {
    if slot.replace(value).is_some() {
        return Err(invalid(owner, "overlapping member ownership"));
    }
    Ok(())
}

fn register_member(
    plan: &CompositionPlanResult<'_>,
    member: &PlacementMemberPlan,
    claims: &mut Claims,
    accounting: &mut Accounting,
) -> Result<(), PlanResourceError> {
    let source = member.source_instruction_index();
    let owner = PlanResourceOwner::SourceInstruction {
        source_instruction_index: source,
    };
    let body = member.member();
    if member.logical_count() == 0
        || body.start > body.end
        || body.end > plan.objects.len()
        || (body.start == body.end && body.anchor_indices.is_empty())
    {
        return Err(invalid(&owner, "invalid member range or count"));
    }
    if !claims.sources.insert(source) {
        return Err(invalid(&owner, "duplicate member source"));
    }
    if member.kind() == PlacementMemberKind::Primitive
        && (body.end - body.start != 1
            || !body.anchor_indices.is_empty()
            || !body.transform_group_indices.is_empty())
    {
        return Err(invalid(
            &owner,
            "primitive member must own exactly one object",
        ));
    }
    let value = MemberClaim {
        source,
        repetitions: member.body_repeat_count(),
    };
    for index in body.start..body.end {
        let object = &plan.objects[index];
        let kind_matches = matches!(
            (member.kind(), object.origin()),
            (
                PlacementMemberKind::Primitive,
                ScoreInstructionOrigin::SourceInstruction { .. }
            ) | (
                PlacementMemberKind::Macro,
                ScoreInstructionOrigin::MacroEmit { .. }
            )
        );
        if object_source(object.origin()) != source
            || !kind_matches
            || (member.kind() == PlacementMemberKind::Primitive
                && object.count() != member.logical_count())
        {
            return Err(invalid(
                &owner,
                "member source, kind or primitive count mismatch",
            ));
        }
        claim(&mut claims.objects[index], value, &owner)?;
    }
    for &index in &body.anchor_indices {
        if index >= plan.anchors.len() || anchor_source(&plan.anchor_origins[index]) != source {
            return Err(invalid(&owner, "invalid member anchor owner"));
        }
        claim(&mut claims.anchors[index], value, &owner)?;
    }
    for &index in &body.transform_group_indices {
        let Some(group) = plan.transform_groups.get(index) else {
            return Err(invalid(&owner, "invalid member transform index"));
        };
        if group.start() < body.start || group.end() > body.end {
            return Err(invalid(&owner, "member transform escapes body"));
        }
        claim(&mut claims.transforms[index], value, &owner)?;
    }
    accounting.add(
        ResourceDemand {
            logical_objects: u64::from(member.logical_count()),
            maximum_resolved_count: u64::from(member.logical_count()),
            ..ResourceDemand::default()
        },
        &owner,
    )
}

fn validate_recipe(
    recipe: &PlacementRecipe,
    count: u64,
    owner: &PlanResourceOwner,
) -> Result<(), PlanResourceError> {
    if let PlacementRecipe::Grid {
        columns,
        rows,
        filled_count,
        ..
    } = recipe
    {
        let capacity = columns
            .checked_mul(*rows)
            .ok_or_else(|| invalid(owner, "grid capacity overflow"))?;
        if *columns == 0 || *rows == 0 || *filled_count != count || capacity < count {
            return Err(invalid(owner, "grid count contract mismatch"));
        }
    }
    Ok(())
}

fn register_group(
    plan: &CompositionPlanResult<'_>,
    members: &[PlacementMemberPlan],
    logical_count: u64,
    owner: &PlanResourceOwner,
    claims: &mut Claims,
    accounting: &mut Accounting,
) -> Result<(), PlanResourceError> {
    if members.is_empty() {
        return Err(invalid(owner, "empty placement or fill group"));
    }
    let mut count = 0u64;
    let mut end = members[0].member().start;
    for member in members {
        if member.member().start != end {
            return Err(invalid(owner, "noncontiguous group members"));
        }
        end = member.member().end;
        count = count
            .checked_add(u64::from(member.logical_count()))
            .ok_or_else(|| PlanResourceError {
                owner: owner.clone(),
                reason: PlanResourceFailure::ArithmeticOverflow(ResourceDimension::LogicalObjects),
            })?;
        register_member(plan, member, claims, accounting)?;
    }
    if count != logical_count {
        return Err(invalid(owner, "group logical count mismatch"));
    }
    Ok(())
}

/// Validate source ownership and charge exact symbolic demand against both
/// independently supplied authorities. Work and allocation depend on source
/// templates and their stored index lists, never on a resolved repetition count.
fn account_composition_plan(
    plan: &CompositionPlanResult<'_>,
    hard_policy: HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
    collect: bool,
) -> Result<Accounting, PlanResourceError> {
    if plan.outcome() == CompositionPlanOutcome::Stopped {
        return Err(PlanResourceError {
            owner: PlanResourceOwner::Plan,
            reason: PlanResourceFailure::StoppedPlan,
        });
    }
    if hard_policy.identity.trim().is_empty() {
        return Err(invalid(
            &PlanResourceOwner::Plan,
            "hard policy identity required",
        ));
    }
    if plan.anchors.len() != plan.anchor_origins.len() {
        return Err(invalid(
            &PlanResourceOwner::Plan,
            "anchor origin length mismatch",
        ));
    }
    let mut accounting = Accounting {
        demand: ResourceDemand::default(),
        hard: hard_policy.clone(),
        operational: operational_budget,
        contributions: collect.then(Vec::new),
    };
    // Check source node capacity before allocating ownership vectors.
    for object in &plan.objects {
        accounting.add(
            ResourceDemand {
                object_templates: 1,
                template_nodes: 1,
                ..ResourceDemand::default()
            },
            &PlanResourceOwner::Object(object.origin().clone()),
        )?;
    }
    for owner in plan
        .anchor_origins
        .iter()
        .cloned()
        .map(PlanResourceOwner::Anchor)
        .chain(
            plan.transform_groups
                .iter()
                .map(|group| PlanResourceOwner::Transform(group.provenance().clone())),
        )
        .chain(
            plan.placement_groups
                .iter()
                .map(|group| PlanResourceOwner::PlacementGroup {
                    group_index: group.group_index(),
                }),
        )
        .chain(
            plan.fill_groups
                .iter()
                .map(|group| PlanResourceOwner::FillGroup(group.owner)),
        )
    {
        accounting.add(
            ResourceDemand {
                template_nodes: 1,
                ..ResourceDemand::default()
            },
            &owner,
        )?;
    }
    let mut claims = Claims {
        objects: vec![None; plan.objects.len()],
        anchors: vec![None; plan.anchors.len()],
        transforms: vec![None; plan.transform_groups.len()],
        sources: HashSet::new(),
    };
    for group in plan.placement_groups() {
        let owner = PlanResourceOwner::PlacementGroup {
            group_index: group.group_index(),
        };
        register_group(
            plan,
            group.members(),
            group.logical_count(),
            &owner,
            &mut claims,
            &mut accounting,
        )?;
        let placement = group.placement();
        if placement.start != group.members()[0].member().start
            || placement.end != group.members().last().unwrap().member().end
            || if placement.members.is_empty() {
                // The old Score projection elides trivial primitive member spans.
                // The sealed Plan keeps those spans and remains authoritative.
                group
                    .members()
                    .iter()
                    .any(|member| member.kind() != PlacementMemberKind::Primitive)
            } else {
                placement.members.len() != group.members().len()
                    || placement
                        .members
                        .iter()
                        .zip(group.members())
                        .any(|(wire, member)| wire != member.member())
            }
        {
            return Err(invalid(&owner, "placement range or members mismatch"));
        }
        validate_recipe(group.recipe(), group.logical_count(), &owner)?;
        accounting.add(
            ResourceDemand {
                placement_instances: 1,
                ..ResourceDemand::default()
            },
            &owner,
        )?;
    }
    for group in plan.fill_groups() {
        let owner = PlanResourceOwner::FillGroup(group.owner);
        if !matches!(
            group.recipe,
            PlacementRecipe::FillUniformInRegionAndClip { .. }
        ) {
            return Err(invalid(&owner, "fill recipe required"));
        }
        register_group(
            plan,
            &group.members,
            group.logical_count,
            &owner,
            &mut claims,
            &mut accounting,
        )?;
        if let FillPlanOwner::Instruction {
            source_instruction_index,
        } = group.owner
            && (group.members.len() != 1
                || group.members[0].source_instruction_index() != source_instruction_index)
        {
            return Err(invalid(&owner, "standalone fill owner mismatch"));
        }
        accounting.add(
            ResourceDemand {
                fill_instances: 1,
                ..ResourceDemand::default()
            },
            &owner,
        )?;
    }
    for member in plan.standalone_macro_repetitions() {
        if member.kind() != PlacementMemberKind::Macro {
            return Err(invalid(
                &PlanResourceOwner::SourceInstruction {
                    source_instruction_index: member.source_instruction_index(),
                },
                "standalone repetition must be Macro",
            ));
        }
        register_member(plan, member, &mut claims, &mut accounting)?;
    }
    let mut ungrouped_macros = HashSet::new();
    for (index, object) in plan.objects.iter().enumerate() {
        let owner = PlanResourceOwner::Object(object.origin().clone());
        if object.count() == 0 {
            return Err(invalid(&owner, "zero object count"));
        }
        validate_recipe(object.recipe(), u64::from(object.count()), &owner)?;
        let source = object_source(object.origin());
        if claims.objects[index].is_none() && claims.sources.contains(&source) {
            return Err(invalid(&owner, "member omitted source object"));
        }
        let repetitions = claims.objects[index].map_or(1, |claim| claim.repetitions);
        let primitive_marks = u64::from(object.count())
            .checked_mul(u64::from(repetitions))
            .ok_or_else(|| PlanResourceError {
                owner: owner.clone(),
                reason: PlanResourceFailure::ArithmeticOverflow(ResourceDimension::PrimitiveMarks),
            })?;
        let logical_objects = if claims.objects[index].is_some() {
            0
        } else {
            match object.origin() {
                ScoreInstructionOrigin::SourceInstruction { .. } => u64::from(object.count()),
                ScoreInstructionOrigin::MacroEmit { .. } => {
                    u64::from(ungrouped_macros.insert(source))
                }
            }
        };
        let fill_instances = if matches!(
            object.recipe(),
            PlacementRecipe::FillUniformInRegionAndClip { .. }
        ) {
            u64::from(repetitions)
        } else {
            0
        };
        accounting.add(
            ResourceDemand {
                logical_objects,
                primitive_marks,
                maximum_per_template_primitive_marks: primitive_marks,
                maximum_resolved_count: u64::from(object.count()),
                fill_instances,
                ..ResourceDemand::default()
            },
            &owner,
        )?;
    }
    for (index, origin) in plan.anchor_origins.iter().enumerate() {
        let owner = PlanResourceOwner::Anchor(origin.clone());
        let source = anchor_source(origin);
        if claims.anchors[index].is_none() && claims.sources.contains(&source) {
            return Err(invalid(&owner, "member omitted source anchor"));
        }
        accounting.add(
            ResourceDemand {
                logical_objects: u64::from(
                    claims.anchors[index].is_none() && ungrouped_macros.insert(source),
                ),
                anchor_instances: u64::from(
                    claims.anchors[index].map_or(1, |claim| claim.repetitions),
                ),
                ..ResourceDemand::default()
            },
            &owner,
        )?;
    }
    // Range checks stay linear even for deeply nested Transform ranges.
    let mut run_end = vec![plan.objects.len(); plan.objects.len()];
    for index in (0..plan.objects.len().saturating_sub(1)).rev() {
        run_end[index] = if claims.objects[index] == claims.objects[index + 1] {
            run_end[index + 1]
        } else {
            index + 1
        };
    }
    for (index, group) in plan.transform_groups.iter().enumerate() {
        let owner = PlanResourceOwner::Transform(group.provenance().clone());
        if group.start() > group.end()
            || group.end() > plan.objects.len()
            || group
                .fixed_position_indices()
                .iter()
                .any(|&i| i < group.start() || i >= group.end())
            || group
                .anchor_indices()
                .iter()
                .any(|&i| i >= plan.anchors.len())
        {
            return Err(invalid(&owner, "invalid transform range or indices"));
        }
        if (group.start() < group.end()
            && (claims.objects[group.start()] != claims.transforms[index]
                || run_end[group.start()] < group.end()))
            || group
                .anchor_indices()
                .iter()
                .any(|&i| claims.anchors[i] != claims.transforms[index])
        {
            return Err(invalid(&owner, "transform repetition ownership mismatch"));
        }
        accounting.add(
            ResourceDemand {
                transform_instances: u64::from(
                    claims.transforms[index].map_or(1, |claim| claim.repetitions),
                ),
                ..ResourceDemand::default()
            },
            &owner,
        )?;
    }
    Ok(accounting)
}

/// Strict admission for callers that require every unit in this plan. Runtime
/// callers that continue after local resource failures use selection instead.
pub fn preflight_composition_plan<'plan, 'source>(
    plan: &'plan CompositionPlanResult<'source>,
    hard_policy: HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
) -> Result<AdmittedCompositionPlan<'plan, 'source>, PlanResourceError> {
    let accounting =
        account_composition_plan(plan, hard_policy.clone(), operational_budget, false)?;
    Ok(AdmittedCompositionPlan {
        plan,
        demand: accounting.demand,
        hard_policy,
        operational_budget,
    })
}

/// Original-plan indices, never indices into a silently rewritten plan.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct CompositionPlanSelection {
    pub source_instruction_indices: Vec<usize>,
    pub object_indices: Vec<usize>,
    pub anchor_indices: Vec<usize>,
    pub transform_group_indices: Vec<usize>,
    pub placement_group_indices: Vec<usize>,
    pub fill_group_indices: Vec<usize>,
    pub standalone_macro_repetition_indices: Vec<usize>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct PlanResourceOmission {
    /// Atomic placement or complete source head omitted, without reducing count.
    pub owner: PlanResourceOwner,
    /// Exact source/generated owner that caused arithmetic or budget refusal.
    pub cause: PlanResourceError,
}

/// Admission applies only to `selection`, not to every object in `plan`.
pub struct SelectedCompositionPlan<'plan, 'source> {
    plan: &'plan CompositionPlanResult<'source>,
    selection: CompositionPlanSelection,
    demand: ResourceDemand,
    omissions: Vec<PlanResourceOmission>,
    hard_policy: HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
}

impl<'plan, 'source> SelectedCompositionPlan<'plan, 'source> {
    pub fn plan(&self) -> &'plan CompositionPlanResult<'source> {
        self.plan
    }
    pub fn selection(&self) -> &CompositionPlanSelection {
        &self.selection
    }
    pub fn source_instruction_indices(&self) -> &[usize] {
        &self.selection.source_instruction_indices
    }
    pub fn object_indices(&self) -> &[usize] {
        &self.selection.object_indices
    }
    pub fn anchor_indices(&self) -> &[usize] {
        &self.selection.anchor_indices
    }
    pub fn transform_indices(&self) -> &[usize] {
        &self.selection.transform_group_indices
    }
    pub fn placement_group_indices(&self) -> &[usize] {
        &self.selection.placement_group_indices
    }
    pub fn fill_group_indices(&self) -> &[usize] {
        &self.selection.fill_group_indices
    }
    pub fn standalone_macro_indices(&self) -> &[usize] {
        &self.selection.standalone_macro_repetition_indices
    }
    pub const fn demand(&self) -> ResourceDemand {
        self.demand
    }
    pub fn omissions(&self) -> &[PlanResourceOmission] {
        &self.omissions
    }
    pub const fn hard_policy(&self) -> &HardResourcePolicy {
        &self.hard_policy
    }
    pub const fn operational_budget(&self) -> OperationalResourceBudget {
        self.operational_budget
    }
    pub const fn accounting_id(&self) -> &'static str {
        RESOURCE_ACCOUNTING_ID
    }
}

struct UnitMapping {
    source_units: Vec<usize>,
    owners: Vec<Option<PlanResourceOwner>>,
    placement_units: HashMap<usize, usize>,
    fill_units: HashMap<FillPlanOwner, usize>,
    macro_sources: HashMap<u64, usize>,
}

impl UnitMapping {
    fn new(plan: &CompositionPlanResult<'_>) -> Result<Self, PlanResourceError> {
        let retained_count = plan
            .verified_effective_view()
            .original_semantic_document()
            .instructions
            .len();
        let highest_retained_source = plan
            .objects
            .iter()
            .map(|object| object_source(object.origin()))
            .chain(plan.anchor_origins.iter().map(anchor_source))
            .max()
            .map_or(0, |index| index + 1);
        let count = retained_count.max(highest_retained_source);
        let mut result = Self {
            source_units: (0..count).collect(),
            owners: vec![None; count],
            placement_units: HashMap::new(),
            fill_units: HashMap::new(),
            macro_sources: HashMap::new(),
        };
        for object in &plan.objects {
            if let ScoreInstructionOrigin::MacroEmit {
                source_instruction_index,
                provenance,
                ..
            } = object.origin()
            {
                result.macro_sources.insert(
                    provenance.invocation.invocation_ordinal,
                    *source_instruction_index,
                );
            }
        }
        for origin in &plan.anchor_origins {
            let ScoreAnchorOrigin::MacroAnchor {
                source_instruction_index,
                provenance,
                ..
            } = origin;
            result.macro_sources.insert(
                provenance.invocation.invocation_ordinal,
                *source_instruction_index,
            );
        }
        for group in plan.placement_groups() {
            let owner = PlanResourceOwner::PlacementGroup {
                group_index: group.group_index(),
            };
            let unit = result.group(group.members(), owner)?;
            if result
                .placement_units
                .insert(group.group_index(), unit)
                .is_some()
            {
                return Err(invalid(
                    &PlanResourceOwner::Plan,
                    "duplicate placement group identity",
                ));
            }
        }
        for group in plan.fill_groups() {
            let unit = result.group(&group.members, PlanResourceOwner::FillGroup(group.owner))?;
            if result.fill_units.insert(group.owner, unit).is_some() {
                return Err(invalid(
                    &PlanResourceOwner::Plan,
                    "duplicate fill group identity",
                ));
            }
        }
        Ok(result)
    }

    fn group(
        &mut self,
        members: &[PlacementMemberPlan],
        owner: PlanResourceOwner,
    ) -> Result<usize, PlanResourceError> {
        let first = members
            .first()
            .ok_or_else(|| invalid(&owner, "empty resource unit"))?
            .source_instruction_index();
        let mut previous = None;
        for member in members {
            let source = member.source_instruction_index();
            if source >= self.source_units.len()
                || previous.is_some_and(|previous| source <= previous)
                || self.owners[source].is_some()
                || self.source_units[source] != source
            {
                return Err(invalid(
                    &owner,
                    "invalid or overlapping resource unit source",
                ));
            }
            self.source_units[source] = first;
            previous = Some(source);
        }
        self.owners[first] = Some(owner);
        Ok(first)
    }

    fn source_unit(
        &self,
        source: usize,
        owner: &PlanResourceOwner,
    ) -> Result<usize, PlanResourceError> {
        self.source_units
            .get(source)
            .copied()
            .ok_or_else(|| invalid(owner, "resource owner outside source document"))
    }

    fn unit(&self, owner: &PlanResourceOwner) -> Result<usize, PlanResourceError> {
        let source = match owner {
            PlanResourceOwner::Object(origin) => object_source(origin),
            PlanResourceOwner::Anchor(origin) => anchor_source(origin),
            PlanResourceOwner::SourceInstruction {
                source_instruction_index,
            } => *source_instruction_index,
            PlanResourceOwner::PlacementGroup { group_index } => {
                return self
                    .placement_units
                    .get(group_index)
                    .copied()
                    .ok_or_else(|| invalid(owner, "missing placement resource unit"));
            }
            PlanResourceOwner::FillGroup(fill_owner) => {
                return self
                    .fill_units
                    .get(fill_owner)
                    .copied()
                    .ok_or_else(|| invalid(owner, "missing fill resource unit"));
            }
            PlanResourceOwner::Transform(provenance) => *self
                .macro_sources
                .get(&provenance.invocation.invocation_ordinal)
                .ok_or_else(|| invalid(owner, "missing transform source"))?,
            PlanResourceOwner::Plan => {
                return Err(invalid(
                    owner,
                    "resource contribution requires source owner",
                ));
            }
        };
        self.source_unit(source, owner)
    }
}

/// Admit atomic source/placement units in source order. Resource refusal omits
/// only that complete unit; later units are tried against the remaining budget.
/// Malformed plan contracts remain errors. No repetition is partially admitted.
pub fn select_composition_plan_resources<'plan, 'source>(
    plan: &'plan CompositionPlanResult<'source>,
    hard_policy: HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
) -> Result<SelectedCompositionPlan<'plan, 'source>, PlanResourceError> {
    let accounting = account_composition_plan(plan, hard_policy.clone(), operational_budget, true)?;
    let mapping = UnitMapping::new(plan)?;
    let count = mapping.source_units.len();
    let mut demands = vec![ResourceDemand::default(); count];
    let mut causes = vec![None; count];
    let mut present = vec![false; count];
    let mut dimension_owners: Vec<[Option<PlanResourceOwner>; 10]> =
        vec![std::array::from_fn(|_| None); count];
    for (demand, owner) in accounting.contributions.unwrap() {
        let unit = mapping.unit(&owner)?;
        present[unit] = true;
        for (index, dimension) in ResourceDimension::ALL.into_iter().enumerate() {
            let value = demand.get(dimension);
            let is_peak = matches!(
                dimension,
                ResourceDimension::MaximumPerTemplatePrimitiveMarks
                    | ResourceDimension::MaximumResolvedCount
            );
            if value > 0 && (!is_peak || value >= demands[unit].get(dimension)) {
                dimension_owners[unit][index] = Some(owner.clone());
            }
        }
        if causes[unit].is_none() {
            match demands[unit].checked_add(demand) {
                Ok(total) => demands[unit] = total,
                Err(dimension) => {
                    causes[unit] = Some(PlanResourceError {
                        owner: owner.clone(),
                        reason: PlanResourceFailure::ArithmeticOverflow(dimension),
                    })
                }
            }
        }
    }
    let mut demand = ResourceDemand::default();
    let mut admitted = vec![false; count];
    let mut omissions = Vec::new();
    for unit in 0..count {
        if !present[unit] {
            continue;
        }
        let owner = mapping.owners[unit]
            .clone()
            .unwrap_or(PlanResourceOwner::SourceInstruction {
                source_instruction_index: unit,
            });
        let cause_owner = |dimension| {
            ResourceDimension::ALL
                .iter()
                .position(|candidate| *candidate == dimension)
                .and_then(|index| dimension_owners[unit][index].clone())
                .unwrap_or_else(|| owner.clone())
        };
        let candidate = demand.checked_add(demands[unit]);
        let failure = causes[unit].take().or_else(|| match candidate {
            Err(dimension) => Some(PlanResourceError {
                owner: cause_owner(dimension),
                reason: PlanResourceFailure::ArithmeticOverflow(dimension),
            }),
            Ok(candidate) => hard_policy
                .budget
                .check(candidate, ResourceAuthority::HardPolicy)
                .and_then(|()| {
                    operational_budget
                        .0
                        .check(candidate, ResourceAuthority::OperationalBudget)
                })
                .err()
                .map(|exceeded| PlanResourceError {
                    owner: cause_owner(exceeded.dimension),
                    reason: PlanResourceFailure::BudgetExceeded(exceeded),
                }),
        });
        if let Some(cause) = failure {
            omissions.push(PlanResourceOmission { owner, cause });
        } else {
            demand = candidate.unwrap();
            admitted[unit] = true;
        }
    }
    let mut selection = CompositionPlanSelection::default();
    for source in 0..count {
        if admitted[mapping.source_units[source]] {
            selection.source_instruction_indices.push(source);
        }
    }
    for (index, object) in plan.objects.iter().enumerate() {
        if admitted[mapping.unit(&PlanResourceOwner::Object(object.origin().clone()))?] {
            selection.object_indices.push(index);
        }
    }
    for (index, origin) in plan.anchor_origins.iter().enumerate() {
        if admitted[mapping.unit(&PlanResourceOwner::Anchor(origin.clone()))?] {
            selection.anchor_indices.push(index);
        }
    }
    for (index, group) in plan.transform_groups.iter().enumerate() {
        if admitted[mapping.unit(&PlanResourceOwner::Transform(group.provenance().clone()))?] {
            selection.transform_group_indices.push(index);
        }
    }
    for (index, group) in plan.placement_groups.iter().enumerate() {
        if admitted[mapping.placement_units[&group.group_index()]] {
            selection.placement_group_indices.push(index);
        }
    }
    for (index, group) in plan.fill_groups.iter().enumerate() {
        if admitted[mapping.fill_units[&group.owner]] {
            selection.fill_group_indices.push(index);
        }
    }
    for (index, member) in plan.standalone_macro_repetitions.iter().enumerate() {
        if admitted[mapping.source_unit(
            member.source_instruction_index(),
            &PlanResourceOwner::SourceInstruction {
                source_instruction_index: member.source_instruction_index(),
            },
        )?] {
            selection.standalone_macro_repetition_indices.push(index);
        }
    }
    Ok(SelectedCompositionPlan {
        plan,
        selection,
        demand,
        omissions,
        hard_policy,
        operational_budget,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::*;
    use inku_score::{Color, ResourceBudget};
    use serde_json::json;

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
            identity: "test.structural-policy.v1".into(),
            budget: budget(maximum),
        }
    }

    fn stage(source: &str, definitions: &[MacroDefinition]) -> Stage15TransformationResult {
        let locks = definitions
            .iter()
            .map(|definition| {
                let identity = definition.identity().unwrap();
                MacroLock::new(
                    identity.qualified_name(),
                    identity.version(),
                    format!("sha256:{}", identity.full_digest_hex()),
                )
                .unwrap()
            })
            .collect();
        let compiled = compile_typed_ddl(
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, locks).unwrap(),
            definitions,
            Some(19),
            MacroExpansionLimits {
                max_invocations: 8,
                max_depth: 8,
                max_evaluation_steps: 128,
                max_nodes_per_invocation: 32,
                max_total_nodes: 64,
            },
        );
        transform_stage15(stage15_transformation_input(&compiled).unwrap(), None).unwrap()
    }

    fn plan(stage: &Stage15TransformationResult) -> CompositionPlanResult<'_> {
        plan_verified_stage15(
            stage.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        )
    }

    fn motif(count: u32) -> MacroDefinition {
        let emit = |shape| {
            json!({"op":"emit","binding":null,"fields":{
                "shape":{"expr":"semantic_ref","category":"shape","id":shape},
                "movement":{"expr":"semantic_ref","category":"movement","id":"scatter"},
                "color":{"expr":"semantic_ref","category":"color","id":"red"},
                "count":{"expr":"integer","value":count}
            }})
        };
        MacroDefinition::from_json(&json!({
            "schema":"inku.macro-definition.v1", "namespace":"Test", "heading":"Pair", "version":"1.0.0",
            "parameters":{}, "components":{}, "body":[{
                "op":"transform", "transform":{"rotate_degrees":{"expr":"number","value":10.0}},
                "body":[emit("circle"), emit("square")]
            }]
        }).to_string()).unwrap()
    }

    fn demand(plan: &CompositionPlanResult<'_>) -> ResourceDemand {
        preflight_composition_plan(
            plan,
            hard(u64::MAX),
            OperationalResourceBudget(budget(u64::MAX)),
        )
        .unwrap_or_else(|error| panic!("{error:?}; diagnostics: {:?}", plan.diagnostics()))
        .demand()
    }

    #[test]
    fn primitive_maximum_is_rejected_symbolically_without_changing_plan() {
        let stage = stage("fill 4294967295 red circle.", &[]);
        let plan = plan(&stage);
        let before = plan.objects.clone();
        let error = preflight_composition_plan(
            &plan,
            hard(100),
            OperationalResourceBudget(budget(u64::MAX)),
        )
        .err()
        .unwrap();
        assert!(matches!(
            error.owner,
            PlanResourceOwner::Object(ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 0
            })
        ));
        assert!(matches!(
            error.reason,
            PlanResourceFailure::BudgetExceeded(ResourceBudgetExceeded {
                authority: ResourceAuthority::HardPolicy,
                required: 4_294_967_295,
                ..
            })
        ));
        assert_eq!(plan.objects, before);
        let exact = demand(&plan);
        assert_eq!(exact.logical_objects, u64::from(u32::MAX));
        assert_eq!(exact.primitive_marks, u64::from(u32::MAX));
        assert_eq!(exact.template_nodes, 1);
        assert_eq!(exact.fill_instances, 1);
    }

    #[test]
    fn operational_budget_cannot_raise_hard_policy_and_has_distinct_authority() {
        let stage = stage("scatter ten red circles.", &[]);
        let plan = plan(&stage);
        for (hard_max, operational_max, authority) in [
            (9, 100, ResourceAuthority::HardPolicy),
            (100, 9, ResourceAuthority::OperationalBudget),
        ] {
            let error = preflight_composition_plan(
                &plan,
                hard(hard_max),
                OperationalResourceBudget(budget(operational_max)),
            )
            .err()
            .unwrap();
            assert!(
                matches!(error.reason, PlanResourceFailure::BudgetExceeded(ResourceBudgetExceeded { authority: actual, .. }) if actual == authority)
            );
        }
        let admitted =
            preflight_composition_plan(&plan, hard(10), OperationalResourceBudget(budget(10)))
                .unwrap();
        assert_eq!(admitted.demand().primitive_marks, 10);
        assert!(std::ptr::eq(admitted.plan(), &plan));
        assert_eq!(admitted.hard_policy().identity, "test.structural-policy.v1");
    }

    #[test]
    fn macro_internal_counts_and_outer_occurrences_are_separate() {
        let definition = motif(2);
        for (source, logical, marks, placement, fill) in [
            ("Test.Pair", 1, 4, 0, 0),
            ("three Test.Pair", 3, 12, 0, 0),
            (
                "scatter three Test.Pair and five blue circles at center.",
                8,
                17,
                1,
                0,
            ),
            (
                "fill with three Test.Pair and five blue circles.",
                8,
                17,
                0,
                1,
            ),
        ] {
            let stage = stage(source, std::slice::from_ref(&definition));
            let plan = plan(&stage);
            let exact = demand(&plan);
            assert_eq!(
                (exact.logical_objects, exact.primitive_marks),
                (logical, marks),
                "{source}"
            );
            assert_eq!(
                exact.transform_instances,
                if logical == 1 { 1 } else { 3 },
                "{source}"
            );
            assert_eq!(
                (exact.placement_instances, exact.fill_instances),
                (placement, fill)
            );
            assert_eq!(exact.template_nodes, if logical <= 3 { 3 } else { 5 });
        }
    }

    #[test]
    fn maximum_macro_products_overflow_without_expansion() {
        let stage = stage("4294967295 Test.Pair", &[motif(u32::MAX)]);
        let plan = plan(&stage);
        assert_eq!(plan.objects.len(), 2);
        let error = preflight_composition_plan(
            &plan,
            hard(u64::MAX),
            OperationalResourceBudget(budget(u64::MAX)),
        )
        .err()
        .unwrap();
        assert!(matches!(
            error.reason,
            PlanResourceFailure::ArithmeticOverflow(ResourceDimension::PrimitiveMarks)
        ));
        assert!(matches!(
            error.owner,
            PlanResourceOwner::Object(ScoreInstructionOrigin::MacroEmit {
                source_instruction_index: 0,
                ..
            })
        ));
    }

    #[test]
    fn malformed_private_group_contracts_are_rejected_with_owner() {
        let stage = stage(
            "fill with three Test.Pair and five blue circles.",
            &[motif(2)],
        );
        let mut plan = plan(&stage);
        assert_eq!(demand(&plan).primitive_marks, 17);
        let original = plan.fill_groups[0].clone();
        plan.fill_groups[0].logical_count += 1;
        let error =
            preflight_composition_plan(&plan, hard(100), OperationalResourceBudget(budget(100)))
                .err()
                .unwrap();
        assert!(matches!(error.owner, PlanResourceOwner::FillGroup(_)));
        assert_eq!(
            error.reason,
            PlanResourceFailure::InvalidContract("group logical count mismatch")
        );
        plan.fill_groups[0] = original.clone();
        plan.fill_groups[0].members[1].source_count = 6;
        let error =
            preflight_composition_plan(&plan, hard(100), OperationalResourceBudget(budget(100)))
                .err()
                .unwrap();
        assert_eq!(
            error.owner,
            PlanResourceOwner::SourceInstruction {
                source_instruction_index: 1
            }
        );
        plan.fill_groups[0] = original;
        plan.fill_groups[0].members[0].member.end = usize::MAX;
        assert!(
            preflight_composition_plan(&plan, hard(100), OperationalResourceBudget(budget(100)))
                .is_err()
        );
    }

    #[test]
    fn stopped_plan_and_template_budget_are_rejected() {
        let stage = stage("scatter ten red circles.", &[]);
        let mut plan = plan(&stage);
        let mut policy = hard(100);
        policy.budget.maximum.template_nodes = 0;
        let error =
            preflight_composition_plan(&plan, policy, OperationalResourceBudget(budget(100)))
                .err()
                .unwrap();
        assert!(matches!(
            error.reason,
            PlanResourceFailure::BudgetExceeded(ResourceBudgetExceeded {
                dimension: ResourceDimension::TemplateNodes,
                ..
            })
        ));
        plan.outcome = CompositionPlanOutcome::Stopped;
        assert_eq!(
            preflight_composition_plan(&plan, hard(100), OperationalResourceBudget(budget(100)))
                .err()
                .unwrap()
                .reason,
            PlanResourceFailure::StoppedPlan
        );
    }

    #[test]
    fn shipping_limit_units_keep_macro_emits_separate_and_do_not_clamp_fill() {
        let definition = motif(1);
        let stage = stage("125 Test.Pair", &[definition]);
        let plan = plan(&stage);
        let mut policy = hard(u64::MAX);
        policy.budget.maximum.primitive_marks = 400;
        policy.budget.maximum.maximum_per_template_primitive_marks = 240;
        policy.budget.maximum.maximum_resolved_count = 2000;
        policy.budget.maximum.object_templates = 64;
        let admitted = preflight_composition_plan(
            &plan,
            policy.clone(),
            OperationalResourceBudget(budget(u64::MAX)),
        )
        .unwrap();
        assert_eq!(admitted.demand().primitive_marks, 250);
        assert_eq!(admitted.demand().maximum_per_template_primitive_marks, 125);
        assert_eq!(admitted.demand().object_templates, 2);
        assert_eq!(admitted.demand().maximum_resolved_count, 125);
        let point_stage = self::stage("fill red point.", &[]);
        let point_plan = self::plan(&point_stage);
        assert_eq!(point_plan.objects[0].count(), 6945);
        let error = preflight_composition_plan(
            &point_plan,
            policy,
            OperationalResourceBudget(budget(u64::MAX)),
        )
        .err()
        .unwrap();
        assert!(matches!(
            error.reason,
            PlanResourceFailure::BudgetExceeded(ResourceBudgetExceeded {
                dimension: ResourceDimension::PrimitiveMarks,
                required: 6945,
                maximum: 400,
                ..
            })
        ));
        assert_eq!(point_plan.objects[0].count(), 6945);
    }

    #[test]
    fn each_distinct_limit_dimension_rejects_at_its_exact_boundary() {
        for (source, definition, dimension, maximum) in [
            (
                "241 Test.Pair",
                Some(motif(1)),
                ResourceDimension::MaximumPerTemplatePrimitiveMarks,
                240,
            ),
            (
                "scatter 2001 red circles.",
                None,
                ResourceDimension::MaximumResolvedCount,
                2000,
            ),
            (
                "Test.Pair",
                Some(motif(1)),
                ResourceDimension::ObjectTemplates,
                1,
            ),
        ] {
            let stage = stage(source, &definition.into_iter().collect::<Vec<_>>());
            let plan = plan(&stage);
            let mut policy = hard(u64::MAX);
            match dimension {
                ResourceDimension::MaximumPerTemplatePrimitiveMarks => {
                    policy.budget.maximum.maximum_per_template_primitive_marks = maximum
                }
                ResourceDimension::MaximumResolvedCount => {
                    policy.budget.maximum.maximum_resolved_count = maximum
                }
                ResourceDimension::ObjectTemplates => {
                    policy.budget.maximum.object_templates = maximum
                }
                _ => unreachable!(),
            }
            let error = preflight_composition_plan(
                &plan,
                policy,
                OperationalResourceBudget(budget(u64::MAX)),
            )
            .err()
            .unwrap();
            assert!(
                matches!(error.reason, PlanResourceFailure::BudgetExceeded(ResourceBudgetExceeded { dimension: actual, required, .. }) if actual == dimension && required == maximum + 1),
                "{source}: {error:?}"
            );
            assert!(matches!(error.owner, PlanResourceOwner::Object(_)));
        }
    }

    #[test]
    fn anchor_only_repetitions_are_charged_and_bad_indices_do_not_panic() {
        let definition = MacroDefinition::from_json(&json!({
            "schema":"inku.macro-definition.v1", "namespace":"Test", "heading":"Anchor", "version":"1.0.0",
            "parameters":{}, "components":{}, "body":[{"op":"anchor","name":"pivot","fields":{
                "position_x":{"expr":"exact_decimal","value":"0.2"},
                "position_y":{"expr":"exact_decimal","value":"0.5"}
            }}]
        }).to_string()).unwrap();
        let stage = stage("three Test.Anchor", &[definition]);
        let mut plan = plan(&stage);
        let exact = demand(&plan);
        assert_eq!(
            (
                exact.logical_objects,
                exact.primitive_marks,
                exact.anchor_instances,
                exact.template_nodes
            ),
            (3, 0, 3, 1)
        );
        plan.standalone_macro_repetitions[0].member.anchor_indices[0] = usize::MAX;
        let error =
            preflight_composition_plan(&plan, hard(100), OperationalResourceBudget(budget(100)))
                .err()
                .unwrap();
        assert_eq!(
            error.owner,
            PlanResourceOwner::SourceInstruction {
                source_instruction_index: 0
            }
        );
        assert_eq!(
            error.reason,
            PlanResourceFailure::InvalidContract("invalid member anchor owner")
        );
    }

    #[test]
    fn selection_omits_excessive_fill_and_keeps_later_drawing_exact() {
        let stage = stage("fill red point. place one blue circle.", &[]);
        let plan = plan(&stage);
        let selected = select_composition_plan_resources(
            &plan,
            hard(400),
            OperationalResourceBudget(budget(400)),
        )
        .unwrap();
        assert_eq!(selected.object_indices(), [1]);
        assert_eq!(selected.source_instruction_indices(), [1]);
        assert_eq!(selected.demand().primitive_marks, 1);
        assert_eq!(selected.omissions().len(), 1);
        assert_eq!(
            selected.omissions()[0].owner,
            PlanResourceOwner::SourceInstruction {
                source_instruction_index: 0
            }
        );
        assert_eq!(plan.objects[0].count(), 6945);
        assert_eq!(plan.objects[1].count(), 1);
        assert!(std::ptr::eq(selected.plan(), &plan));
    }

    #[test]
    fn selection_tests_later_units_against_remaining_budget() {
        let stage = stage(
            "scatter 240 red circles. scatter 200 blue squares. scatter 100 green triangles.",
            &[],
        );
        let plan = plan(&stage);
        let selected = select_composition_plan_resources(
            &plan,
            hard(400),
            OperationalResourceBudget(budget(400)),
        )
        .unwrap();
        assert_eq!(selected.object_indices(), [0, 2]);
        assert_eq!(selected.demand().primitive_marks, 340);
        assert_eq!(selected.demand().maximum_per_template_primitive_marks, 240);
        assert_eq!(selected.demand().object_templates, 2);
        assert_eq!(selected.omissions().len(), 1);
        assert_eq!(
            selected.omissions()[0].owner,
            PlanResourceOwner::SourceInstruction {
                source_instruction_index: 1
            }
        );
        assert!(matches!(
            selected.omissions()[0].cause.reason,
            PlanResourceFailure::BudgetExceeded(ResourceBudgetExceeded {
                required: 440,
                maximum: 400,
                ..
            })
        ));
    }

    #[test]
    fn selection_never_splits_group_members_or_macro_bodies() {
        for (source, first_kept_index, is_fill) in [
            (
                "fill with three Test.Pair and five blue circles. place one green square.",
                3,
                true,
            ),
            (
                "scatter three Test.Pair and five blue circles at center. place one green square.",
                3,
                false,
            ),
            ("three Test.Pair. place one green square.", 2, false),
        ] {
            let stage = stage(source, &[motif(2)]);
            let plan = plan(&stage);
            let selected = select_composition_plan_resources(
                &plan,
                hard(10),
                OperationalResourceBudget(budget(10)),
            )
            .unwrap();
            assert_eq!(selected.object_indices(), [first_kept_index], "{source}");
            assert_eq!(selected.demand().primitive_marks, 1);
            assert!(selected.transform_indices().is_empty());
            assert!(selected.fill_group_indices().is_empty());
            assert!(selected.placement_group_indices().is_empty());
            assert!(selected.standalone_macro_indices().is_empty());
            assert_eq!(selected.omissions().len(), 1);
            if is_fill {
                assert!(matches!(
                    selected.omissions()[0].owner,
                    PlanResourceOwner::FillGroup(_)
                ));
            }
        }
    }

    #[test]
    fn selection_recovers_from_one_unit_overflow_but_not_invalid_contracts() {
        let stage = stage(
            "4294967295 Test.Pair. place one blue circle.",
            &[motif(u32::MAX)],
        );
        let mut plan = plan(&stage);
        let selected = select_composition_plan_resources(
            &plan,
            hard(u64::MAX),
            OperationalResourceBudget(budget(u64::MAX)),
        )
        .unwrap();
        assert_eq!(selected.object_indices(), [2]);
        assert_eq!(selected.demand().primitive_marks, 1);
        assert!(matches!(
            selected.omissions()[0].cause.reason,
            PlanResourceFailure::ArithmeticOverflow(ResourceDimension::PrimitiveMarks)
        ));
        plan.standalone_macro_repetitions[0].member.end = usize::MAX;
        let error =
            select_composition_plan_resources(&plan, hard(0), OperationalResourceBudget(budget(0)))
                .err()
                .unwrap();
        assert!(matches!(
            error.reason,
            PlanResourceFailure::InvalidContract(_)
        ));
    }

    #[test]
    fn selection_can_be_empty_and_preserves_operational_refusal_authority() {
        let stage = stage("scatter ten red circles.", &[]);
        let plan = plan(&stage);
        let selected = select_composition_plan_resources(
            &plan,
            hard(100),
            OperationalResourceBudget(budget(9)),
        )
        .unwrap();
        assert!(selected.object_indices().is_empty());
        assert_eq!(selected.demand(), ResourceDemand::default());
        assert!(matches!(
            selected.omissions()[0].cause.reason,
            PlanResourceFailure::BudgetExceeded(ResourceBudgetExceeded {
                authority: ResourceAuthority::OperationalBudget,
                ..
            })
        ));
    }
}
