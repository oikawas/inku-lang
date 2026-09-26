//! Explicit Action, Position, and previous-reference association over the accepted entity result.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use crate::{
    AttachmentMarkerKind, ClauseAtom, ClauseStreamError, CoordinationMarkerEvidence,
    CoordinationMarkerKind, CoreRoleKind, EnglishAttachmentMarkerKind,
    ExplicitPreviousReferenceOccurrence, JapaneseAttachmentMarkerKind, MacroParameterBindingResult,
    MarkerId, NormalizedDdlDocument, RemainingRoleKind, SemanticAssociationResult, SemanticEntity,
    SemanticIssueCausalProvenance, SemanticPreviousReference, SemanticRelationKind, SemanticTerm,
    SemanticUpstreamCausalRelation, SourceOccurrence, SourceSpan, associate_semantic_entities,
    associate_semantic_entities_with_macro_binding,
    attachment::collect_coordination_marker_evidence,
    semantic_association::{
        causal_provenance, diagnostic_causes_between, project_semantic_term, semantic_entity_value,
        semantic_identity_value, sentence_region_index,
    },
};

/// Stable identity for the explicit instruction association AST.
pub const SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID: &str =
    "inku.semantic-instruction-association.v24";

/// An explicit fill domain. Inline operands retain their original instruction owner
/// and are consumed as geometry by the fill, rather than drawn independently.
#[derive(Clone, Debug, PartialEq)]
pub enum SemanticFillTarget {
    Canvas {
        source: SourceOccurrence,
        markers: Vec<SourceOccurrence>,
    },
    InlineShape {
        target_instruction_index: usize,
        markers: Vec<SourceOccurrence>,
    },
}

impl SemanticFillTarget {
    pub(crate) fn sources(&self) -> Vec<&SourceOccurrence> {
        match self {
            Self::Canvas { source, markers } => std::iter::once(source).chain(markers).collect(),
            Self::InlineShape { markers, .. } => markers.iter().collect(),
        }
    }
}

/// One explicit relation from the current instruction to prior source-ordered instruction(s).
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticRelation {
    pub target_endpoint: Option<inku_score::Endpoint>,
    pub target_path_selection: Option<inku_score::TargetPathSelection>,
    pub kind: SemanticRelationKind,
    pub reference: SemanticPreviousReference,
    pub provenance: SourceOccurrence,
}

/// One single-head entity and its independently optional action-side predicates.
///
/// Missing fields are unspecified and receive no semantic default.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticInstruction {
    pub entity: SemanticEntity,
    pub sequence: Option<crate::SemanticSequence>,
    pub action: Option<SemanticTerm>,
    pub position: Option<SemanticTerm>,
    pub layout_direction: Option<SemanticTerm>,
    pub relation: Option<SemanticRelation>,
    pub fill_target: Option<SemanticFillTarget>,
}

/// A source-ordered reference to existing instructions joined by explicit coordination.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticCoordinatedHeadGroup {
    pub member_instruction_indices: Vec<usize>,
    pub markers: Vec<SourceOccurrence>,
}

/// One Action / Position owner shared by a coordinated head group.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticGroupPredicateEdge {
    pub group_index: usize,
    pub action: Option<SemanticTerm>,
    pub position: Option<SemanticTerm>,
    pub relation: Option<SemanticRelation>,
    pub layout: GroupLayout,
    pub fill_target: Option<SemanticFillTarget>,
}

/// Closed coordinated-placement layout, separate from member actions and positions.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GroupLayout {
    Overlap,
    HorizontalSourceOrder,
}

impl GroupLayout {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Overlap => "overlap",
            Self::HorizontalSourceOrder => "horizontal_source_order",
        }
    }
}

/// Stable fail-closed coordination ownership issue classes.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticCoordinationIssueKind {
    MissingLeftHead,
    MissingRightHead,
    MissingBothHeads,
    BlockedBoundary,
    OverlappingChain,
    PredicateOwnershipConflict,
    ContinuationOwnershipConflict,
    ConflictingGroupActions,
    ConflictingGroupPositions,
}

impl SemanticCoordinationIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MissingLeftHead => "missing_left_coordination_head",
            Self::MissingRightHead => "missing_right_coordination_head",
            Self::MissingBothHeads => "missing_both_coordination_heads",
            Self::BlockedBoundary => "blocked_coordination_boundary",
            Self::OverlappingChain => "overlapping_coordination_chain",
            Self::PredicateOwnershipConflict => "conflicting_coordination_predicate_ownership",
            Self::ContinuationOwnershipConflict => "coordination_continuation_ownership_conflict",
            Self::ConflictingGroupActions => "conflicting_group_actions",
            Self::ConflictingGroupPositions => "conflicting_group_positions",
        }
    }
}

/// All source evidence retained when a coordinated predicate owner is not unique.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticCoordinationIssue {
    pub kind: SemanticCoordinationIssueKind,
    pub member_instruction_indices: Vec<usize>,
    pub candidate_instruction_indices: Vec<usize>,
    pub markers: Vec<SourceOccurrence>,
    pub continuation_markers: Vec<SourceOccurrence>,
    pub predicates: Vec<SemanticInstructionOccurrence>,
    pub claim_spans: Vec<SourceSpan>,
    pub causal_provenance: SemanticIssueCausalProvenance,
}

/// Partial or complete semantic instruction sequence in entity source order.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticInstructionAssociationAst {
    pub instructions: Vec<SemanticInstruction>,
    pub coordinated_head_groups: Vec<SemanticCoordinatedHeadGroup>,
    pub group_predicates: Vec<SemanticGroupPredicateEdge>,
    pub complete: bool,
}

/// Roles owned by the instruction independently from entity modifiers.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticInstructionOccurrenceRole {
    Action,
    Position,
    LayoutDirection,
}

impl SemanticInstructionOccurrenceRole {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Action => "action",
            Self::Position => "position",
            Self::LayoutDirection => "layout_direction",
        }
    }
}

/// One role-tagged occurrence delivered to an instruction issue.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstructionOccurrence {
    pub role: SemanticInstructionOccurrenceRole,
    pub term: SemanticTerm,
}

/// Stable, expected instruction-association issue classes.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticInstructionIssueKind {
    AmbiguousActionOwnership,
    AmbiguousPositionOwnership,
    ConflictingActions,
    MissingActionEntity,
    ConflictingPositions,
    MissingPositionEntity,
    AmbiguousLayoutDirectionOwnership,
    ConflictingLayoutDirections,
    MissingLayoutDirectionEntity,
}

impl SemanticInstructionIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::AmbiguousActionOwnership => "ambiguous_action_ownership",
            Self::AmbiguousPositionOwnership => "ambiguous_position_ownership",
            Self::ConflictingActions => "conflicting_actions",
            Self::MissingActionEntity => "missing_action_entity",
            Self::ConflictingPositions => "conflicting_positions",
            Self::MissingPositionEntity => "missing_position_entity",
            Self::AmbiguousLayoutDirectionOwnership => "ambiguous_layout_direction_ownership",
            Self::ConflictingLayoutDirections => "conflicting_layout_directions",
            Self::MissingLayoutDirectionEntity => "missing_layout_direction_entity",
        }
    }
}

/// One typed instruction issue with every owned occurrence delivered exactly once.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstructionIssue {
    pub kind: SemanticInstructionIssueKind,
    pub region_index: usize,
    pub occurrences: Vec<SemanticInstructionOccurrence>,
    pub causal_provenance: SemanticIssueCausalProvenance,
}

/// Stable relation-association issue classes without fallback target selection.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticRelationIssueKind {
    TargetPrimitiveMismatch,
    AmbiguousCurrentInstructionOwnership,
    ConflictingRelations,
    MissingCurrentInstruction,
    MissingPreviousOne,
    MissingPreviousTwo,
}

impl SemanticRelationIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::TargetPrimitiveMismatch => "relation_target_primitive_mismatch",
            Self::AmbiguousCurrentInstructionOwnership => "ambiguous_current_relation_ownership",
            Self::ConflictingRelations => "conflicting_relations",
            Self::MissingCurrentInstruction => "missing_current_instruction",
            Self::MissingPreviousOne => "missing_previous_one",
            Self::MissingPreviousTwo => "missing_previous_two",
        }
    }
}

/// Exact current owner established by relation association.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticRelationIssueOwner {
    Instruction { instruction_index: usize },
    CoordinatedGroup { group_index: usize },
}

/// One typed relation issue owning every undelivered full-literal occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticRelationIssue {
    pub kind: SemanticRelationIssueKind,
    pub region_index: usize,
    pub current_owner: Option<SemanticRelationIssueOwner>,
    pub occurrences: Vec<ExplicitPreviousReferenceOccurrence>,
}

/// Source-preserving explicit Action / Position / previous-reference association result.
///
/// The accepted entity association is owned unchanged. Action / Position counts and relation
/// counts are separate; accepted entity occurrences are not recounted.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticInstructionAssociationResult {
    pub schema_id: &'static str,
    pub association: SemanticAssociationResult,
    pub ast: SemanticInstructionAssociationAst,
    pub issues: Vec<SemanticInstructionIssue>,
    pub coordination_issues: Vec<SemanticCoordinationIssue>,
    pub canonical_bytes: Option<Vec<u8>>,
    pub owned_instruction_occurrence_count: usize,
    pub delivered_instruction_occurrence_count: usize,
    pub owned_coordination_marker_count: usize,
    pub delivered_coordination_marker_count: usize,
    pub relation_issues: Vec<SemanticRelationIssue>,
    pub owned_relation_occurrence_count: usize,
    pub delivered_relation_occurrence_count: usize,
}

#[derive(Default)]
struct InstructionOwnership {
    action_starts_by_head: BTreeMap<usize, BTreeSet<usize>>,
    position_starts_by_head: BTreeMap<usize, BTreeSet<usize>>,
    action_starts_by_group: BTreeMap<usize, BTreeSet<usize>>,
    position_starts_by_group: BTreeMap<usize, BTreeSet<usize>>,
}

impl InstructionOwnership {
    fn insert_action(&mut self, head_start: usize, action_start: usize) {
        self.action_starts_by_head
            .entry(head_start)
            .or_default()
            .insert(action_start);
    }

    fn insert_position(&mut self, head_start: usize, position_start: usize) {
        self.position_starts_by_head
            .entry(head_start)
            .or_default()
            .insert(position_start);
    }

    fn insert_group_action(&mut self, group_index: usize, action_start: usize) {
        self.action_starts_by_group
            .entry(group_index)
            .or_default()
            .insert(action_start);
    }

    fn insert_group_position(&mut self, group_index: usize, position_start: usize) {
        self.position_starts_by_group
            .entry(group_index)
            .or_default()
            .insert(position_start);
    }
}

/// Associate explicit Saijiki Motion, Place, and full-literal relation terms with single-head entities.
///
/// Entity association is called exactly once. Its `ClauseStream`, entities, state, and issues are
/// reused directly; no parser, role composition, or sentence-region splitter is rerun.
pub fn associate_semantic_instructions(
    document: &NormalizedDdlDocument,
) -> Result<SemanticInstructionAssociationResult, ClauseStreamError> {
    let association = associate_semantic_entities(document)?;
    Ok(build_semantic_instructions(document, association))
}

/// Associate instructions from one caller-owned accepted I-581 result without rerunning it.
pub fn associate_semantic_instructions_with_macro_binding(
    document: &NormalizedDdlDocument,
    macro_parameter_binding: MacroParameterBindingResult,
) -> SemanticInstructionAssociationResult {
    let association =
        associate_semantic_entities_with_macro_binding(document, macro_parameter_binding);
    build_semantic_instructions(document, association)
}

pub(crate) fn fill_phrase_ranges(
    language: crate::ResolvedInstructionLanguage,
    clause: &crate::ClauseSegment,
    action_span: SourceSpan,
) -> Option<(SourceSpan, SourceSpan, Vec<usize>)> {
    let marker = |expected: MarkerId| {
        clause
            .atoms
            .iter()
            .enumerate()
            .filter_map(|(index, atom)| {
                matches!(atom, ClauseAtom::GrammarMarker { marker_id, .. }
                    if *marker_id == expected)
                .then_some(index)
            })
            .collect::<Vec<_>>()
    };
    let ranges = match language {
        crate::ResolvedInstructionLanguage::Ja => {
            let object = marker(MarkerId::JaWo);
            let material = marker(MarkerId::JaDe);
            let [material] = material.as_slice() else {
                return None;
            };
            let object = match object.as_slice() {
                [] => None,
                [object] => Some(*object),
                _ => return None,
            };
            if object.is_some_and(|object| object >= *material)
                || clause.atoms[*material].span().end_byte > action_span.start_byte
                || clause.atoms.last().map(ClauseAtom::span) != Some(action_span)
            {
                return None;
            }
            (
                SourceSpan {
                    start_byte: clause.span.start_byte,
                    end_byte: object.map_or(clause.span.start_byte, |index| {
                        clause.atoms[index].span().start_byte
                    }),
                },
                SourceSpan {
                    start_byte: object.map_or(clause.span.start_byte, |index| {
                        clause.atoms[index].span().end_byte
                    }),
                    end_byte: clause.atoms[*material].span().start_byte,
                },
                object
                    .into_iter()
                    .chain(std::iter::once(*material))
                    .collect(),
            )
        }
        crate::ResolvedInstructionLanguage::En => {
            let with = marker(MarkerId::EnWith);
            let [with] = with.as_slice() else {
                return None;
            };
            if clause.atoms.first().map(ClauseAtom::span) != Some(action_span)
                || action_span.end_byte > clause.atoms[*with].span().start_byte
            {
                return None;
            }
            (
                SourceSpan {
                    start_byte: action_span.end_byte,
                    end_byte: clause.atoms[*with].span().start_byte,
                },
                SourceSpan {
                    start_byte: clause.atoms[*with].span().end_byte,
                    end_byte: clause.span.end_byte,
                },
                vec![*with],
            )
        }
    };
    Some(ranges)
}

fn associate_fill_targets(
    document: &NormalizedDdlDocument,
    association: &SemanticAssociationResult,
    actions: &[SemanticTerm],
    positions: &[SemanticTerm],
    groups: &[SemanticCoordinatedHeadGroup],
    ownership: &mut InstructionOwnership,
    group_targets: &mut BTreeMap<usize, SemanticFillTarget>,
) -> BTreeMap<usize, SemanticFillTarget> {
    let mut targets = BTreeMap::new();
    for (clause_index, clause) in association.clause_stream.clauses.iter().enumerate() {
        let clause_actions = actions
            .iter()
            .filter(|term| term.provenance.source.clause_index == clause_index)
            .collect::<Vec<_>>();
        let [action] = clause_actions.as_slice() else {
            continue;
        };
        if action.identity.category != "movement"
            || action.identity.id != "fill"
            || clause.atoms.iter().any(|atom| {
                matches!(atom, ClauseAtom::UnresolvedDiagnostic(diagnostic)
                    if !association.ast.entities.iter().any(|entity|
                        matches!(entity.head, crate::SemanticHead::MacroInvocation(_))
                            && entity.head.source().span == diagnostic.span))
            })
        {
            continue;
        }
        let Some((target_range, motif_range, marker_indices)) =
            fill_phrase_ranges(document.language(), clause, action.provenance.source.span)
        else {
            continue;
        };
        let heads = |range: SourceSpan| {
            association
                .ast
                .entities
                .iter()
                .enumerate()
                .filter_map(|(index, entity)| {
                    let span = entity.head.source().span;
                    (range.start_byte <= span.start_byte && span.end_byte <= range.end_byte)
                        .then_some(index)
                })
                .collect::<Vec<_>>()
        };
        let motif_heads = heads(motif_range);
        let Some(motif_index) = motif_heads.first() else {
            continue;
        };
        let motif_group = if motif_heads.len() > 1 {
            let Some(group_index) = groups
                .iter()
                .position(|group| group.member_instruction_indices == motif_heads)
            else {
                continue;
            };
            Some(group_index)
        } else {
            None
        };
        let source = |atom_index: usize| {
            let span = clause.atoms[atom_index].span();
            SourceOccurrence {
                span,
                surface: document.source()[span.start_byte..span.end_byte].to_owned(),
                language: document.language(),
                region_index: sentence_region_index(&association.clause_stream, span),
                clause_index,
                atom_index,
            }
        };
        let markers = marker_indices.into_iter().map(source).collect::<Vec<_>>();
        let target_heads = heads(target_range);
        let target = if let [target_index] = target_heads.as_slice() {
            if !matches!(
                &association.ast.entities[*target_index].head,
                crate::SemanticHead::Primitive(_)
            ) {
                continue;
            }
            Some(SemanticFillTarget::InlineShape {
                target_instruction_index: *target_index,
                markers,
            })
        } else if target_heads.is_empty() {
            let background = clause
                .atoms
                .iter()
                .enumerate()
                .filter_map(|(index, atom)| {
                    (target_range.start_byte <= atom.span().start_byte
                        && atom.span().end_byte <= target_range.end_byte
                        && matches!(atom, ClauseAtom::GrammarMarker {marker_id, ..}
                        if matches!(marker_id, MarkerId::JaBackground | MarkerId::EnBackground)))
                    .then_some(index)
                })
                .collect::<Vec<_>>();
            let named = positions
                .iter()
                .filter(|position| {
                    let span = position.provenance.source.span;
                    target_range.start_byte <= span.start_byte
                        && span.end_byte <= target_range.end_byte
                })
                .count();
            if document.source()[target_range.start_byte..target_range.end_byte]
                .trim()
                .is_empty()
                || (background.is_empty() && named == 1)
            {
                None
            } else {
                let [background] = background.as_slice() else {
                    continue;
                };
                Some(SemanticFillTarget::Canvas {
                    source: source(*background),
                    markers,
                })
            }
        } else {
            continue;
        };
        if groups.iter().any(|group| {
            (motif_group.is_none() && group.member_instruction_indices.contains(motif_index))
                || target_heads
                    .iter()
                    .any(|index| group.member_instruction_indices.contains(index))
        }) {
            continue;
        }
        let action_start = action.provenance.source.span.start_byte;
        for starts in ownership.action_starts_by_head.values_mut() {
            starts.remove(&action_start);
        }
        for starts in ownership.action_starts_by_group.values_mut() {
            starts.remove(&action_start);
        }
        let motif_start = association.ast.entities[*motif_index]
            .head
            .source()
            .span
            .start_byte;
        if let Some(group_index) = motif_group {
            ownership.insert_group_action(group_index, action_start);
        } else {
            ownership.insert_action(motif_start, action_start);
        }
        // Positions written inside the target phrase retain the target's owner.
        // A Canvas target uses the motif's position as its named fill domain.
        for position in positions {
            let span = position.provenance.source.span;
            if target_range.start_byte <= span.start_byte && span.end_byte <= target_range.end_byte
            {
                for starts in ownership.position_starts_by_head.values_mut() {
                    starts.remove(&span.start_byte);
                }
                for starts in ownership.position_starts_by_group.values_mut() {
                    starts.remove(&span.start_byte);
                }
                if let Some(target_index) = target_heads.first() {
                    ownership.insert_position(
                        association.ast.entities[*target_index]
                            .head
                            .source()
                            .span
                            .start_byte,
                        span.start_byte,
                    );
                } else if let Some(group_index) = motif_group {
                    ownership.insert_group_position(group_index, span.start_byte);
                } else {
                    ownership.insert_position(motif_start, span.start_byte);
                }
            }
        }
        if let Some(target) = target {
            if let Some(group_index) = motif_group {
                group_targets.insert(group_index, target);
            } else {
                targets.insert(motif_start, target);
            }
        }
    }
    targets
}

fn build_semantic_instructions(
    document: &NormalizedDdlDocument,
    association: SemanticAssociationResult,
) -> SemanticInstructionAssociationResult {
    let mut actions = Vec::new();
    let mut positions = Vec::new();
    let mut directions = Vec::new();
    let mut owned_instruction_occurrence_count = 0;

    for (clause_index, clause) in association.clause_stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let ClauseAtom::RemainingRole(term) = atom else {
                continue;
            };
            if association.macro_parameter_owns_span(term.span) {
                continue;
            }
            let role = match term.role {
                RemainingRoleKind::Motion => SemanticInstructionOccurrenceRole::Action,
                RemainingRoleKind::Place => SemanticInstructionOccurrenceRole::Position,
                RemainingRoleKind::Angle
                    if crate::semantic_association::is_layout_direction(
                        document,
                        &association.clause_stream,
                        &association.clause_topology,
                        term,
                    ) =>
                {
                    SemanticInstructionOccurrenceRole::LayoutDirection
                }
                RemainingRoleKind::Angle
                | RemainingRoleKind::Continuity
                | RemainingRoleKind::Fluctuation
                | RemainingRoleKind::Proportion
                | RemainingRoleKind::Sequence => continue,
            };
            let region_index = sentence_region_index(&association.clause_stream, term.span);
            let projected =
                project_instruction_term(document, term, region_index, clause_index, atom_index);
            match role {
                SemanticInstructionOccurrenceRole::Action => actions.push(projected),
                SemanticInstructionOccurrenceRole::Position => positions.push(projected),
                SemanticInstructionOccurrenceRole::LayoutDirection => directions.push(projected),
            }
            owned_instruction_occurrence_count += 1;
        }
    }
    let owned_relation_occurrence_count = association.explicit_previous_references.len();
    let mut relations_by_region =
        BTreeMap::<usize, Vec<ExplicitPreviousReferenceOccurrence>>::new();
    for occurrence in &association.explicit_previous_references {
        relations_by_region
            .entry(occurrence.provenance.region_index)
            .or_default()
            .push(occurrence.clone());
    }

    let mut sequence_predicates = BTreeMap::new();
    for sequence in &association.ast.sequences {
        if !matches!(sequence.sequence.kind, crate::SemanticSequenceKind::Units) {
            continue;
        }
        let region_index = sequence.sequence.operator.provenance.source.region_index;
        let action = take_unique_region_term(&mut actions, region_index);
        let position = take_unique_region_term(&mut positions, region_index);
        sequence_predicates.insert(sequence.target_entity_index, (action, position));
    }

    let sequence_marker_spans = association
        .ast
        .sequences
        .iter()
        .flat_map(|sequence| &sequence.sequence.markers)
        .chain(
            association
                .sequence_issues
                .iter()
                .flat_map(|issue| &issue.markers),
        )
        .map(|marker| (marker.span.start_byte, marker.span.end_byte))
        .collect::<BTreeSet<_>>();
    let coordination_evidence =
        collect_coordination_marker_evidence(document, &association.clause_stream)
            .into_iter()
            .filter(|marker| marker.kind == CoordinationMarkerKind::HeadConjunction)
            .filter(|marker| {
                !sequence_marker_spans.contains(&(marker.source.start_byte, marker.source.end_byte))
            })
            .collect::<Vec<_>>();
    let owned_coordination_identities = coordination_evidence
        .iter()
        .map(|marker| {
            (
                marker.clause_index,
                marker.source.start_byte,
                marker.source.end_byte,
            )
        })
        .collect::<BTreeSet<_>>();
    assert_eq!(
        owned_coordination_identities.len(),
        coordination_evidence.len(),
        "accepted coordination evidence identities must be unique"
    );
    let owned_coordination_marker_count = coordination_evidence.len();
    let (coordinated_head_groups, mut coordination_issues) =
        collect_coordinated_head_groups(document, &association, &coordination_evidence);
    assign_ambiguous_boundary_predicates(&mut actions, &mut positions, &mut coordination_issues);
    let mut ownership =
        collect_instruction_ownership(&association, &actions, &positions, &coordinated_head_groups);
    let mut group_fill_targets = BTreeMap::new();
    let fill_targets = associate_fill_targets(
        document,
        &association,
        &actions,
        &positions,
        &coordinated_head_groups,
        &mut ownership,
        &mut group_fill_targets,
    );
    let (mut group_predicates, mut predicate_coordination_issues) = extract_group_predicates(
        &mut actions,
        &mut positions,
        &ownership,
        &coordinated_head_groups,
        &association,
    );
    coordination_issues.append(&mut predicate_coordination_issues);
    for edge in &mut group_predicates {
        edge.fill_target = group_fill_targets.remove(&edge.group_index);
    }

    let mut instructions = Vec::new();
    let mut issues = Vec::new();
    let mut relation_issues = Vec::new();
    let mut entity_counts_by_region = BTreeMap::<usize, usize>::new();
    for entity in &association.ast.entities {
        *entity_counts_by_region
            .entry(entity.head.source().region_index)
            .or_default() += 1;
    }
    claim_group_mirrored_relations(
        &association,
        &coordinated_head_groups,
        &mut group_predicates,
        &mut relations_by_region,
        &mut relation_issues,
    );
    for (&region_index, &entity_count) in &entity_counts_by_region {
        if entity_count > 1
            && let Some(relations) = relations_by_region.remove(&region_index)
        {
            relation_issues.push(SemanticRelationIssue {
                kind: SemanticRelationIssueKind::AmbiguousCurrentInstructionOwnership,
                region_index,
                current_owner: None,
                occurrences: relations,
            });
        }
    }
    for (entity_index, entity) in association.ast.entities.iter().enumerate() {
        let region_index = entity.head.source().region_index;
        let head_start = entity.head.source().span.start_byte;
        let mut action = select_one(
            take_owned_instruction_terms(
                &mut actions,
                ownership.action_starts_by_head.get(&head_start),
            ),
            SemanticInstructionOccurrenceRole::Action,
            SemanticInstructionIssueKind::ConflictingActions,
            region_index,
            &mut issues,
        );
        let mut position = select_one(
            take_owned_instruction_terms(
                &mut positions,
                ownership.position_starts_by_head.get(&head_start),
            ),
            SemanticInstructionOccurrenceRole::Position,
            SemanticInstructionIssueKind::ConflictingPositions,
            region_index,
            &mut issues,
        );
        if let Some((sequence_action, sequence_position)) =
            sequence_predicates.remove(&entity_index)
        {
            action = sequence_action.or(action);
            position = sequence_position.or(position);
        }
        let relation = if entity_counts_by_region[&region_index] == 1 {
            select_relation(
                relations_by_region
                    .remove(&region_index)
                    .unwrap_or_default(),
                &instructions,
                region_index,
                &mut relation_issues,
            )
        } else {
            None
        };
        instructions.push(SemanticInstruction {
            entity: entity.clone(),
            sequence: association
                .ast
                .sequences
                .iter()
                .find(|sequence| sequence.target_entity_index == entity_index)
                .map(|sequence| sequence.sequence.clone()),
            action,
            position,
            layout_direction: None,
            relation,
            fill_target: fill_targets.get(&head_start).cloned(),
        });
    }
    for direction in directions {
        let source = &direction.provenance.source;
        let candidates = instructions
            .iter()
            .enumerate()
            .filter(|(_, instruction)| {
                let head = instruction.entity.head.source();
                if head.region_index != source.region_index {
                    return false;
                }
                if let Some(action) = &instruction.action {
                    let action = &action.provenance.source;
                    if action.clause_index != source.clause_index {
                        return false;
                    }
                    match source.language {
                        crate::ResolvedInstructionLanguage::Ja => {
                            head.span.end_byte <= source.span.start_byte
                                && source.span.end_byte <= action.span.start_byte
                        }
                        crate::ResolvedInstructionLanguage::En => {
                            action.span.end_byte <= head.span.start_byte
                                && head.span.end_byte <= source.span.start_byte
                                && instructions
                                    .iter()
                                    .filter_map(|candidate| candidate.action.as_ref())
                                    .filter(|candidate| {
                                        candidate.provenance.source.clause_index
                                            == source.clause_index
                                            && action.span.end_byte
                                                <= candidate.provenance.source.span.start_byte
                                    })
                                    .all(|candidate| {
                                        source.span.end_byte
                                            <= candidate.provenance.source.span.start_byte
                                    })
                        }
                    }
                } else {
                    entity_counts_by_region[&source.region_index] == 1
                }
            })
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        let group_owned = coordinated_head_groups.iter().any(|group| {
            group
                .member_instruction_indices
                .iter()
                .any(|index| candidates.contains(index))
        });
        if candidates.len() == 1 && !group_owned {
            let instruction = &mut instructions[candidates[0]];
            if let Some(previous) = instruction.layout_direction.take() {
                issues.push(SemanticInstructionIssue {
                    kind: SemanticInstructionIssueKind::ConflictingLayoutDirections,
                    region_index: source.region_index,
                    occurrences: vec![previous, direction]
                        .into_iter()
                        .map(|term| SemanticInstructionOccurrence {
                            role: SemanticInstructionOccurrenceRole::LayoutDirection,
                            term,
                        })
                        .collect(),
                    causal_provenance: SemanticIssueCausalProvenance::Unattributed,
                });
            } else {
                instruction.layout_direction = Some(direction);
            }
        } else {
            append_orphan_issue(
                vec![direction.clone()],
                SemanticInstructionOccurrenceRole::LayoutDirection,
                if entity_counts_by_region.contains_key(&source.region_index) {
                    SemanticInstructionIssueKind::AmbiguousLayoutDirectionOwnership
                } else {
                    SemanticInstructionIssueKind::MissingLayoutDirectionEntity
                },
                source.region_index,
                &mut issues,
            );
        }
    }
    let mut remaining_by_region = BTreeMap::<usize, (Vec<SemanticTerm>, Vec<SemanticTerm>)>::new();
    for action in actions {
        remaining_by_region
            .entry(action.provenance.source.region_index)
            .or_default()
            .0
            .push(action);
    }
    for position in positions {
        remaining_by_region
            .entry(position.provenance.source.region_index)
            .or_default()
            .1
            .push(position);
    }
    for (region_index, (actions, positions)) in remaining_by_region {
        let has_entity = entity_counts_by_region
            .get(&region_index)
            .copied()
            .unwrap_or(0)
            > 0;
        append_orphan_issue(
            actions,
            SemanticInstructionOccurrenceRole::Action,
            if has_entity {
                SemanticInstructionIssueKind::AmbiguousActionOwnership
            } else {
                SemanticInstructionIssueKind::MissingActionEntity
            },
            region_index,
            &mut issues,
        );
        append_orphan_issue(
            positions,
            SemanticInstructionOccurrenceRole::Position,
            if has_entity {
                SemanticInstructionIssueKind::AmbiguousPositionOwnership
            } else {
                SemanticInstructionIssueKind::MissingPositionEntity
            },
            region_index,
            &mut issues,
        );
    }
    for (region_index, relations) in relations_by_region {
        relation_issues.push(SemanticRelationIssue {
            kind: SemanticRelationIssueKind::MissingCurrentInstruction,
            region_index,
            current_owner: None,
            occurrences: relations,
        });
    }
    attach_instruction_causal_provenance(&association, &mut issues);
    issues.sort_by_key(|issue| {
        issue
            .occurrences
            .first()
            .map(|occurrence| occurrence.term.provenance.source.span.start_byte)
            .unwrap_or(usize::MAX)
    });

    let delivered_instruction_occurrence_count = instructions
        .iter()
        .map(|instruction| {
            usize::from(instruction.action.is_some())
                + usize::from(instruction.position.is_some())
                + usize::from(instruction.layout_direction.is_some())
        })
        .sum::<usize>()
        + group_predicates
            .iter()
            .map(|edge| usize::from(edge.action.is_some()) + usize::from(edge.position.is_some()))
            .sum::<usize>()
        + coordination_issues
            .iter()
            .map(|issue| issue.predicates.len())
            .sum::<usize>()
        + issues
            .iter()
            .map(|issue| issue.occurrences.len())
            .sum::<usize>();
    assert_eq!(
        delivered_instruction_occurrence_count, owned_instruction_occurrence_count,
        "semantic instruction association must deliver every Action / Position occurrence exactly once"
    );
    let delivered_coordination_identities = coordinated_head_groups
        .iter()
        .flat_map(|group| &group.markers)
        .chain(coordination_issues.iter().flat_map(|issue| &issue.markers))
        .map(|marker| {
            (
                marker.clause_index,
                marker.span.start_byte,
                marker.span.end_byte,
            )
        })
        .collect::<Vec<_>>();
    let delivered_coordination_marker_count = delivered_coordination_identities.len();
    assert_eq!(
        delivered_coordination_identities
            .iter()
            .copied()
            .collect::<BTreeSet<_>>()
            .len(),
        delivered_coordination_marker_count,
        "semantic instruction association must not duplicate a coordination marker owner"
    );
    assert_eq!(
        delivered_coordination_marker_count, owned_coordination_marker_count,
        "semantic instruction association must deliver every coordinated-head marker exactly once"
    );
    let delivered_relation_occurrence_count = instructions
        .iter()
        .filter(|instruction| instruction.relation.is_some())
        .count()
        + group_predicates
            .iter()
            .filter(|predicate| predicate.relation.is_some())
            .count()
        + relation_issues
            .iter()
            .map(|issue| issue.occurrences.len())
            .sum::<usize>();
    assert_eq!(
        delivered_relation_occurrence_count, owned_relation_occurrence_count,
        "semantic instruction association must deliver every full-literal relation exactly once"
    );

    let ast = SemanticInstructionAssociationAst {
        instructions,
        coordinated_head_groups,
        group_predicates,
        complete: association.ast.complete
            && issues.is_empty()
            && relation_issues.is_empty()
            && coordination_issues.is_empty(),
    };
    let canonical_bytes = ast.complete.then(|| canonical_ast_bytes(&ast));

    SemanticInstructionAssociationResult {
        schema_id: SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
        association,
        ast,
        issues,
        coordination_issues,
        canonical_bytes,
        owned_instruction_occurrence_count,
        delivered_instruction_occurrence_count,
        owned_coordination_marker_count,
        delivered_coordination_marker_count,
        relation_issues,
        owned_relation_occurrence_count,
        delivered_relation_occurrence_count,
    }
}

fn take_unique_region_term(
    terms: &mut Vec<SemanticTerm>,
    region_index: usize,
) -> Option<SemanticTerm> {
    let indices = terms
        .iter()
        .enumerate()
        .filter_map(|(index, term)| {
            (term.provenance.source.region_index == region_index).then_some(index)
        })
        .collect::<Vec<_>>();
    if indices.len() != 1 {
        return None;
    }
    Some(terms.remove(indices[0]))
}

fn take_owned_instruction_terms(
    terms: &mut Vec<SemanticTerm>,
    owned_starts: Option<&BTreeSet<usize>>,
) -> Vec<SemanticTerm> {
    let Some(owned_starts) = owned_starts else {
        return Vec::new();
    };
    let (owned, remaining) = std::mem::take(terms)
        .into_iter()
        .partition(|term| owned_starts.contains(&term.provenance.source.span.start_byte));
    *terms = remaining;
    owned
}

fn collect_coordinated_head_groups(
    document: &NormalizedDdlDocument,
    association: &SemanticAssociationResult,
    coordination_evidence: &[CoordinationMarkerEvidence],
) -> (
    Vec<SemanticCoordinatedHeadGroup>,
    Vec<SemanticCoordinationIssue>,
) {
    let entities = &association.ast.entities;
    let mut candidate_links = Vec::<(usize, usize, SourceOccurrence)>::new();
    let mut issues = Vec::new();
    let mut repeated_endpoint_markers =
        BTreeMap::<(usize, usize), Vec<&CoordinationMarkerEvidence>>::new();
    for marker in coordination_evidence {
        let left = entities
            .iter()
            .enumerate()
            .filter(|(_, entity)| {
                let source = entity.head.source();
                source.clause_index == marker.clause_index
                    && source.span.end_byte <= marker.source.start_byte
            })
            .max_by_key(|(_, entity)| entity.head.source().span.end_byte)
            .map(|(index, _)| index);
        let right = entities
            .iter()
            .enumerate()
            .filter(|(_, entity)| {
                let source = entity.head.source();
                source.clause_index == marker.clause_index
                    && marker.source.end_byte <= source.span.start_byte
            })
            .min_by_key(|(_, entity)| entity.head.source().span.start_byte)
            .map(|(index, _)| index);
        if let (Some(left), Some(right)) = (left, right) {
            repeated_endpoint_markers
                .entry((left, right))
                .or_default()
                .push(marker);
        }
    }

    for marker in coordination_evidence {
        let left = entities
            .iter()
            .enumerate()
            .filter(|(_, entity)| {
                let source = entity.head.source();
                source.clause_index == marker.clause_index
                    && source.span.end_byte <= marker.source.start_byte
            })
            .max_by_key(|(_, entity)| entity.head.source().span.end_byte);
        let right = entities
            .iter()
            .enumerate()
            .filter(|(_, entity)| {
                let source = entity.head.source();
                source.clause_index == marker.clause_index
                    && marker.source.end_byte <= source.span.start_byte
            })
            .min_by_key(|(_, entity)| entity.head.source().span.start_byte);
        let occurrence = coordination_marker_occurrence(document, association, marker);
        let member_instruction_indices = left
            .iter()
            .map(|(index, _)| *index)
            .chain(right.iter().map(|(index, _)| *index))
            .collect::<Vec<_>>();
        let missing_kind = match (left.is_some(), right.is_some()) {
            (false, false) => Some(SemanticCoordinationIssueKind::MissingBothHeads),
            (false, true) => Some(SemanticCoordinationIssueKind::MissingLeftHead),
            (true, false) => Some(SemanticCoordinationIssueKind::MissingRightHead),
            (true, true) => None,
        };
        if let Some(kind) = missing_kind {
            issues.push(SemanticCoordinationIssue {
                kind,
                member_instruction_indices,
                candidate_instruction_indices: Vec::new(),
                markers: vec![occurrence],
                continuation_markers: Vec::new(),
                predicates: Vec::new(),
                claim_spans: Vec::new(),
                causal_provenance: coordination_issue_causal_provenance(
                    association,
                    marker,
                    left.map(|(_, entity)| entity),
                    right.map(|(_, entity)| entity),
                ),
            });
            continue;
        }
        let (Some((left_index, left)), Some((right_index, right))) = (left, right) else {
            unreachable!("missing coordination side handled above")
        };
        let member_instruction_indices = vec![left_index, right_index];
        if let Some(repeated) = repeated_endpoint_markers.get(&(left_index, right_index))
            && repeated.len() > 1
        {
            if repeated[0].source != marker.source {
                continue;
            }
            issues.push(SemanticCoordinationIssue {
                kind: SemanticCoordinationIssueKind::OverlappingChain,
                member_instruction_indices,
                candidate_instruction_indices: Vec::new(),
                markers: repeated
                    .iter()
                    .map(|marker| coordination_marker_occurrence(document, association, marker))
                    .collect(),
                continuation_markers: Vec::new(),
                predicates: Vec::new(),
                claim_spans: Vec::new(),
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            });
            continue;
        }
        let clear = right_index == left_index + 1
            && left.head.source().region_index == right.head.source().region_index
            && coordination_gap_is_clear(association, left, right, marker.source);
        if !clear {
            issues.push(SemanticCoordinationIssue {
                kind: SemanticCoordinationIssueKind::BlockedBoundary,
                member_instruction_indices,
                candidate_instruction_indices: Vec::new(),
                markers: vec![occurrence],
                continuation_markers: Vec::new(),
                predicates: Vec::new(),
                claim_spans: Vec::new(),
                causal_provenance: coordination_issue_causal_provenance(
                    association,
                    marker,
                    Some(left),
                    Some(right),
                ),
            });
            continue;
        }
        candidate_links.push((left_index, right_index, occurrence));
    }

    let mut overlapping = BTreeSet::new();
    for (index, (left, right, _)) in candidate_links.iter().enumerate() {
        if candidate_links
            .iter()
            .enumerate()
            .any(|(other_index, (other_left, other_right, _))| {
                index != other_index && (left == other_left || right == other_right)
            })
        {
            overlapping.insert(index);
        }
    }
    while let Some(first) = overlapping.iter().next().copied() {
        let mut component = BTreeSet::from([first]);
        loop {
            let previous_len = component.len();
            for candidate in overlapping.iter().copied() {
                if component.iter().any(|member| {
                    let (left, right, _) = &candidate_links[*member];
                    let (candidate_left, candidate_right, _) = &candidate_links[candidate];
                    left == candidate_left || right == candidate_right
                }) {
                    component.insert(candidate);
                }
            }
            if component.len() == previous_len {
                break;
            }
        }
        let mut members = component
            .iter()
            .flat_map(|index| {
                let (left, right, _) = candidate_links[*index];
                [left, right]
            })
            .collect::<Vec<_>>();
        members.sort_unstable();
        members.dedup();
        let markers = component
            .iter()
            .map(|index| candidate_links[*index].2.clone())
            .collect::<Vec<_>>();
        issues.push(SemanticCoordinationIssue {
            kind: SemanticCoordinationIssueKind::OverlappingChain,
            member_instruction_indices: members,
            candidate_instruction_indices: Vec::new(),
            markers,
            continuation_markers: Vec::new(),
            predicates: Vec::new(),
            claim_spans: Vec::new(),
            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
        });
        for index in component {
            overlapping.remove(&index);
        }
    }

    let mut links = BTreeMap::<usize, (usize, SourceOccurrence)>::new();
    for (index, (left, right, marker)) in candidate_links.into_iter().enumerate() {
        if !issues.iter().any(|issue| {
            issue.kind == SemanticCoordinationIssueKind::OverlappingChain
                && issue
                    .markers
                    .iter()
                    .any(|candidate| candidate.span == marker.span)
        }) {
            debug_assert!(!overlapping.contains(&index));
            links.insert(left, (right, marker));
        }
    }

    let mut groups = Vec::new();
    let mut left_index = 0;
    while left_index < entities.len() {
        let Some((right_index, marker)) = links.get(&left_index).cloned() else {
            left_index += 1;
            continue;
        };
        let mut members = vec![left_index, right_index];
        let mut markers = vec![marker];
        let mut tail = right_index;
        while let Some((next_index, next_marker)) = links.get(&tail).cloned() {
            members.push(next_index);
            markers.push(next_marker);
            tail = next_index;
        }
        groups.push(SemanticCoordinatedHeadGroup {
            member_instruction_indices: members,
            markers,
        });
        left_index = tail + 1;
    }
    (groups, issues)
}

fn coordination_issue_causal_provenance(
    association: &SemanticAssociationResult,
    marker: &CoordinationMarkerEvidence,
    left: Option<&SemanticEntity>,
    right: Option<&SemanticEntity>,
) -> SemanticIssueCausalProvenance {
    let clause = &association.clause_stream.clauses[marker.clause_index];
    let marker_atom_index = clause
        .atoms
        .iter()
        .position(|atom| atom.span() == marker.source)
        .expect("coordination evidence belongs to its accepted clause");
    let left_atom_index = left.map(|entity| entity.head.source().atom_index);
    let right_atom_index = right.map(|entity| entity.head.source().atom_index);
    let (start_atom_index, end_atom_index) = match (left_atom_index, right_atom_index) {
        (Some(left), Some(right)) => (left, right),
        (Some(left), None) => (left, marker_atom_index),
        (None, Some(right)) => (marker_atom_index, right),
        (None, None) => return SemanticIssueCausalProvenance::Unattributed,
    };
    causal_provenance(diagnostic_causes_between(
        &association.clause_stream,
        marker.clause_index,
        start_atom_index,
        end_atom_index,
        SemanticUpstreamCausalRelation::InstructionOwnershipPath,
    ))
}

fn assign_ambiguous_boundary_predicates(
    actions: &mut Vec<SemanticTerm>,
    positions: &mut Vec<SemanticTerm>,
    issues: &mut [SemanticCoordinationIssue],
) {
    for (role, terms) in [
        (SemanticInstructionOccurrenceRole::Action, actions),
        (SemanticInstructionOccurrenceRole::Position, positions),
    ] {
        let mut remaining = Vec::new();
        for term in std::mem::take(terms) {
            let candidate_issues = issues
                .iter()
                .enumerate()
                .filter(|(_, issue)| {
                    matches!(
                        issue.kind,
                        SemanticCoordinationIssueKind::MissingLeftHead
                            | SemanticCoordinationIssueKind::MissingRightHead
                            | SemanticCoordinationIssueKind::MissingBothHeads
                            | SemanticCoordinationIssueKind::BlockedBoundary
                            | SemanticCoordinationIssueKind::OverlappingChain
                    ) && issue.markers.iter().any(|marker| {
                        marker.clause_index == term.provenance.source.clause_index
                            && marker.region_index == term.provenance.source.region_index
                    })
                })
                .map(|(index, _)| index)
                .collect::<Vec<_>>();
            if candidate_issues.len() == 1 {
                issues[candidate_issues[0]]
                    .predicates
                    .push(SemanticInstructionOccurrence { role, term });
            } else {
                remaining.push(term);
            }
        }
        *terms = remaining;
    }
}

fn coordination_marker_occurrence(
    document: &NormalizedDdlDocument,
    association: &SemanticAssociationResult,
    marker: &CoordinationMarkerEvidence,
) -> SourceOccurrence {
    let atom_index = association.clause_stream.clauses[marker.clause_index]
        .atoms
        .iter()
        .position(|atom| atom.span() == marker.source)
        .expect("attachment marker belongs to its accepted clause");
    SourceOccurrence {
        span: marker.source,
        surface: document.source()[marker.source.start_byte..marker.source.end_byte].to_owned(),
        language: document.language(),
        region_index: sentence_region_index(&association.clause_stream, marker.source),
        clause_index: marker.clause_index,
        atom_index,
    }
}

fn coordination_gap_is_clear(
    association: &SemanticAssociationResult,
    left: &SemanticEntity,
    right: &SemanticEntity,
    marker_span: SourceSpan,
) -> bool {
    let left_source = left.head.source();
    let right_source = right.head.source();
    let right_owned = semantic_entity_owned_spans(right);
    let right_heads = BTreeSet::from([(right_source.span.start_byte, right_source.span.end_byte)]);
    association.clause_stream.clauses[left_source.clause_index]
        .atoms
        .iter()
        .filter(|atom| {
            left_source.span.end_byte <= atom.span().start_byte
                && atom.span().end_byte <= right_source.span.start_byte
        })
        .all(|atom| {
            atom.span() == marker_span
                || right_owned.contains(&(atom.span().start_byte, atom.span().end_byte))
                // An accepted right modifier keeps its genitive bridge to that
                // entity head, e.g. `circle と vertical の line`; it is part of
                // the right noun phrase, not a coordination boundary.
                || japanese_owned_genitive_bridge(
                    association,
                    left_source.clause_index,
                    atom.span(),
                    &right_owned,
                    &right_heads,
                )
                || matches!(atom, ClauseAtom::GrammarMarker { span, .. }
                    if association.clause_topology.determiner_starts.contains(&span.start_byte))
        })
}

fn japanese_owned_genitive_bridge(
    association: &SemanticAssociationResult,
    clause_index: usize,
    span: SourceSpan,
    owned_spans: &BTreeSet<(usize, usize)>,
    head_spans: &BTreeSet<(usize, usize)>,
) -> bool {
    association
        .clause_topology
        .attachment_markers
        .iter()
        .filter(|marker| marker.clause_index == clause_index)
        .any(|marker| {
            marker.span == span
                && marker.marker == AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::No)
                && marker
                    .left_atom_spans
                    .last()
                    .is_some_and(|left| owned_spans.contains(&(left.start_byte, left.end_byte)))
                // The bridge stays inside one noun phrase when its right side is
                // that phrase's head or another of its accepted modifiers, e.g.
                // `四つ の 青い 点`.
                && marker.right_atom_spans.first().is_some_and(|right| {
                    let key = (right.start_byte, right.end_byte);
                    head_spans.contains(&key) || owned_spans.contains(&key)
                })
        })
}

fn semantic_entity_owned_spans(entity: &SemanticEntity) -> BTreeSet<(usize, usize)> {
    let mut spans = BTreeSet::new();
    if let crate::SemanticHead::MacroInvocation(head) = &entity.head {
        spans.extend(head.parameters.iter().map(|parameter| {
            (
                parameter.provenance.span.start_byte,
                parameter.provenance.span.end_byte,
            )
        }));
    }
    let mut insert_term = |term: &SemanticTerm| {
        spans.insert((
            term.provenance.source.span.start_byte,
            term.provenance.source.span.end_byte,
        ));
    };
    for term in [
        entity.color.as_ref(),
        entity.touch.as_ref(),
        entity.continuity.as_ref(),
        entity.angle.as_ref(),
        entity.surface.quality.as_ref(),
        entity.surface.intensity.as_ref(),
        entity.fluctuation.amplitude.as_ref(),
        entity.fluctuation.frequency.as_ref(),
        entity.fluctuation.quality.as_ref(),
        entity.fluctuation.spread.as_ref(),
        entity.proportion.aspect.as_ref(),
        entity.proportion.width_extent.as_ref(),
        entity.proportion.arc_form.as_ref(),
    ]
    .into_iter()
    .flatten()
    .chain(&entity.additional_width_extents)
    {
        insert_term(term);
    }
    if let Some(constraint) = &entity.shape_constraint {
        for source in
            std::iter::once(&constraint.provenance).chain(&constraint.additional_provenance)
        {
            spans.insert((source.span.start_byte, source.span.end_byte));
        }
    }
    if let Some(quantity) = &entity.quantity {
        spans.insert((
            quantity.provenance.span.start_byte,
            quantity.provenance.span.end_byte,
        ));
    }
    if let Some(thinness) = &entity.thinness {
        spans.insert((
            thinness.provenance.span.start_byte,
            thinness.provenance.span.end_byte,
        ));
    }
    for relative_scale in entity
        .relative_scale
        .iter()
        .chain(&entity.additional_relative_scales)
    {
        spans.insert((
            relative_scale.provenance.span.start_byte,
            relative_scale.provenance.span.end_byte,
        ));
    }
    for geometry in entity
        .explicit_geometry
        .iter()
        .chain(&entity.additional_explicit_geometries)
    {
        let span = geometry.source().span;
        spans.insert((span.start_byte, span.end_byte));
    }

    spans
}

fn extract_group_predicates(
    actions: &mut Vec<SemanticTerm>,
    positions: &mut Vec<SemanticTerm>,
    ownership: &InstructionOwnership,
    groups: &[SemanticCoordinatedHeadGroup],
    association: &SemanticAssociationResult,
) -> (
    Vec<SemanticGroupPredicateEdge>,
    Vec<SemanticCoordinationIssue>,
) {
    let head_indices_by_start = association
        .ast
        .entities
        .iter()
        .enumerate()
        .map(|(index, entity)| (entity.head.source().span.start_byte, index))
        .collect::<BTreeMap<_, _>>();
    let (actions_by_group, mut issues) = extract_group_role(
        actions,
        SemanticInstructionOccurrenceRole::Action,
        &ownership.action_starts_by_head,
        &ownership.action_starts_by_group,
        groups,
        &head_indices_by_start,
    );
    let (positions_by_group, mut position_issues) = extract_group_role(
        positions,
        SemanticInstructionOccurrenceRole::Position,
        &ownership.position_starts_by_head,
        &ownership.position_starts_by_group,
        groups,
        &head_indices_by_start,
    );
    issues.append(&mut position_issues);

    let mut edges = Vec::new();
    for group_index in 0..groups.len() {
        let action = select_group_role(
            group_index,
            SemanticInstructionOccurrenceRole::Action,
            SemanticCoordinationIssueKind::ConflictingGroupActions,
            actions_by_group
                .get(&group_index)
                .cloned()
                .unwrap_or_default(),
            groups,
            &mut issues,
        );
        let position = select_group_role(
            group_index,
            SemanticInstructionOccurrenceRole::Position,
            SemanticCoordinationIssueKind::ConflictingGroupPositions,
            positions_by_group
                .get(&group_index)
                .cloned()
                .unwrap_or_default(),
            groups,
            &mut issues,
        );
        if action.is_some() || position.is_some() {
            edges.push(SemanticGroupPredicateEdge {
                group_index,
                fill_target: None,
                relation: None,
                layout: group_layout(
                    group_index,
                    groups,
                    association,
                    action.as_ref(),
                    position.as_ref(),
                ),
                action,
                position,
            });
        }
    }
    (edges, issues)
}

fn claim_group_mirrored_relations(
    association: &SemanticAssociationResult,
    groups: &[SemanticCoordinatedHeadGroup],
    edges: &mut Vec<SemanticGroupPredicateEdge>,
    relations_by_region: &mut BTreeMap<usize, Vec<ExplicitPreviousReferenceOccurrence>>,
    issues: &mut Vec<SemanticRelationIssue>,
) {
    for (group_index, group) in groups.iter().enumerate() {
        let Some(&first_member) = group.member_instruction_indices.first() else {
            continue;
        };
        let Some(region_index) = group
            .member_instruction_indices
            .iter()
            .map(|&index| association.ast.entities[index].head.source().region_index)
            .reduce(|left, right| if left == right { left } else { usize::MAX })
            .filter(|region| *region != usize::MAX)
        else {
            continue;
        };
        let region_members = association
            .ast
            .entities
            .iter()
            .enumerate()
            .filter(|(_, entity)| entity.head.source().region_index == region_index)
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        if region_members != group.member_instruction_indices {
            continue;
        }
        let Some(occurrences) = relations_by_region.get(&region_index) else {
            continue;
        };
        if occurrences.is_empty()
            || !occurrences
                .iter()
                .all(|occurrence| occurrence.kind == SemanticRelationKind::Mirrored)
        {
            continue;
        }
        let last_head_end = group
            .member_instruction_indices
            .iter()
            .map(|&index| association.ast.entities[index].head.source().span.end_byte)
            .max()
            .unwrap_or(0);
        if occurrences
            .iter()
            .any(|occurrence| occurrence.provenance.span.start_byte < last_head_end)
        {
            continue;
        }
        let mut occurrences = relations_by_region
            .remove(&region_index)
            .expect("checked group relation occurrences");
        if occurrences.len() > 1 {
            issues.push(SemanticRelationIssue {
                kind: SemanticRelationIssueKind::ConflictingRelations,
                region_index,
                current_owner: Some(SemanticRelationIssueOwner::CoordinatedGroup { group_index }),
                occurrences,
            });
            continue;
        }
        let occurrence = occurrences.pop().expect("nonempty group relation");
        if first_member == 0 {
            issues.push(SemanticRelationIssue {
                kind: SemanticRelationIssueKind::MissingPreviousOne,
                region_index,
                current_owner: Some(SemanticRelationIssueOwner::CoordinatedGroup { group_index }),
                occurrences: vec![occurrence],
            });
            continue;
        }
        let relation = SemanticRelation {
            target_endpoint: occurrence.target_endpoint,
            target_path_selection: occurrence.target_path_selection,
            kind: occurrence.kind,
            reference: occurrence.reference,
            provenance: occurrence.provenance,
        };
        if let Some(edge) = edges
            .iter_mut()
            .find(|edge| edge.group_index == group_index)
        {
            edge.relation = Some(relation);
        } else {
            edges.push(SemanticGroupPredicateEdge {
                group_index,
                action: None,
                position: None,
                relation: Some(relation),
                layout: group_layout(group_index, groups, association, None, None),
                fill_target: None,
            });
        }
    }
    edges.sort_by_key(|edge| edge.group_index);
}

fn group_layout(
    group_index: usize,
    groups: &[SemanticCoordinatedHeadGroup],
    association: &SemanticAssociationResult,
    action: Option<&SemanticTerm>,
    position: Option<&SemanticTerm>,
) -> GroupLayout {
    let Some(action) = action else {
        return GroupLayout::Overlap;
    };
    if action.identity.id != "place" {
        return GroupLayout::Overlap;
    }
    let group = &groups[group_index];
    let first = &association.ast.entities[group.member_instruction_indices[0]];
    let last = &association.ast.entities[*group
        .member_instruction_indices
        .last()
        .expect("coordinated group has members")];
    let clause_index = first.head.source().clause_index;
    if action.provenance.source.clause_index != clause_index
        || position.is_some_and(|term| term.provenance.source.clause_index != clause_index)
    {
        return GroupLayout::Overlap;
    }
    let start_byte = first
        .head
        .source()
        .span
        .start_byte
        .min(action.provenance.source.span.start_byte);
    let end_byte = last
        .head
        .source()
        .span
        .end_byte
        .max(action.provenance.source.span.end_byte)
        .max(position.map_or(0, |term| term.provenance.source.span.end_byte));
    association.clause_stream.clauses[clause_index]
        .atoms
        .iter()
        .filter_map(|atom| match atom {
            ClauseAtom::FunctionWord { surface, span, .. }
                if start_byte <= span.start_byte
                    && span.end_byte <= end_byte
                    && crate::parser::is_group_layout_function_word(surface) =>
            {
                match surface.as_str() {
                    "並べて" => Some(GroupLayout::HorizontalSourceOrder),
                    "重ねて" => Some(GroupLayout::Overlap),
                    value if value.eq_ignore_ascii_case("side by side") => {
                        Some(GroupLayout::HorizontalSourceOrder)
                    }
                    value if value.eq_ignore_ascii_case("overlapping") => {
                        Some(GroupLayout::Overlap)
                    }
                    _ => None,
                }
            }
            _ => None,
        })
        .next()
        .unwrap_or(GroupLayout::Overlap)
}

fn extract_group_role(
    terms: &mut Vec<SemanticTerm>,
    role: SemanticInstructionOccurrenceRole,
    individual_claims: &BTreeMap<usize, BTreeSet<usize>>,
    group_claims: &BTreeMap<usize, BTreeSet<usize>>,
    groups: &[SemanticCoordinatedHeadGroup],
    head_indices_by_start: &BTreeMap<usize, usize>,
) -> (
    BTreeMap<usize, Vec<SemanticTerm>>,
    Vec<SemanticCoordinationIssue>,
) {
    let mut assigned = BTreeMap::<usize, Vec<SemanticTerm>>::new();
    let mut issues = Vec::new();
    let mut remaining = Vec::new();
    for term in std::mem::take(terms) {
        let start = term.provenance.source.span.start_byte;
        let group_owners = group_claims
            .iter()
            .filter(|(_, starts)| starts.contains(&start))
            .map(|(group_index, _)| *group_index)
            .collect::<Vec<_>>();
        let head_owners = individual_claims
            .iter()
            .filter(|(_, starts)| starts.contains(&start))
            .map(|(head_start, _)| *head_start)
            .collect::<Vec<_>>();
        let head_owner_indices = head_owners
            .iter()
            .filter_map(|head_start| head_indices_by_start.get(head_start).copied())
            .collect::<Vec<_>>();
        if group_owners.is_empty() {
            let member_groups = groups
                .iter()
                .enumerate()
                .filter(|(_, group)| {
                    head_owner_indices
                        .iter()
                        .any(|index| group.member_instruction_indices.contains(index))
                })
                .map(|(group_index, _)| group_index)
                .collect::<Vec<_>>();
            if member_groups.is_empty() {
                remaining.push(term);
                continue;
            }
            let mut members = head_owner_indices;
            members.extend(member_groups.iter().flat_map(|group_index| {
                groups[*group_index]
                    .member_instruction_indices
                    .iter()
                    .copied()
            }));
            members.sort_unstable();
            members.dedup();
            let mut claim_spans = member_groups
                .iter()
                .flat_map(|group_index| {
                    groups[*group_index]
                        .markers
                        .iter()
                        .map(|marker| marker.span)
                })
                .collect::<Vec<_>>();
            claim_spans.push(term.provenance.source.span);
            issues.push(SemanticCoordinationIssue {
                kind: SemanticCoordinationIssueKind::PredicateOwnershipConflict,
                member_instruction_indices: members,
                candidate_instruction_indices: Vec::new(),
                markers: Vec::new(),
                continuation_markers: Vec::new(),
                predicates: vec![SemanticInstructionOccurrence { role, term }],
                claim_spans,
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            });
            continue;
        }
        if group_owners.len() == 1
            && head_owner_indices.iter().all(|index| {
                groups[group_owners[0]]
                    .member_instruction_indices
                    .contains(index)
            })
        {
            assigned.entry(group_owners[0]).or_default().push(term);
            continue;
        }
        let mut members = group_owners
            .iter()
            .flat_map(|group_index| {
                groups[*group_index]
                    .member_instruction_indices
                    .iter()
                    .copied()
            })
            .collect::<Vec<_>>();
        members.extend(head_owner_indices);
        members.sort_unstable();
        members.dedup();
        let mut claim_spans = group_owners
            .iter()
            .flat_map(|group_index| {
                groups[*group_index]
                    .markers
                    .iter()
                    .map(|marker| marker.span)
            })
            .collect::<Vec<_>>();
        claim_spans.push(term.provenance.source.span);
        issues.push(SemanticCoordinationIssue {
            kind: SemanticCoordinationIssueKind::PredicateOwnershipConflict,
            member_instruction_indices: members,
            candidate_instruction_indices: Vec::new(),
            markers: Vec::new(),
            continuation_markers: Vec::new(),
            predicates: vec![SemanticInstructionOccurrence { role, term }],
            claim_spans,
            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
        });
    }
    *terms = remaining;
    (assigned, issues)
}

fn select_group_role(
    group_index: usize,
    role: SemanticInstructionOccurrenceRole,
    conflict_kind: SemanticCoordinationIssueKind,
    mut terms: Vec<SemanticTerm>,
    groups: &[SemanticCoordinatedHeadGroup],
    issues: &mut Vec<SemanticCoordinationIssue>,
) -> Option<SemanticTerm> {
    match terms.len() {
        0 => None,
        1 => terms.pop(),
        _ => {
            let mut claim_spans = groups[group_index]
                .markers
                .iter()
                .map(|marker| marker.span)
                .collect::<Vec<_>>();
            claim_spans.extend(terms.iter().map(|term| term.provenance.source.span));
            issues.push(SemanticCoordinationIssue {
                kind: conflict_kind,
                member_instruction_indices: groups[group_index].member_instruction_indices.clone(),
                candidate_instruction_indices: Vec::new(),
                markers: Vec::new(),
                continuation_markers: Vec::new(),
                predicates: terms
                    .into_iter()
                    .map(|term| SemanticInstructionOccurrence { role, term })
                    .collect(),
                claim_spans,
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            });
            None
        }
    }
}

fn collect_instruction_ownership(
    association: &SemanticAssociationResult,
    actions: &[SemanticTerm],
    positions: &[SemanticTerm],
    groups: &[SemanticCoordinatedHeadGroup],
) -> InstructionOwnership {
    let mut ownership = InstructionOwnership::default();
    collect_japanese_instruction_ownership(association, actions, positions, &mut ownership);
    collect_english_instruction_ownership(association, actions, positions, &mut ownership);
    collect_japanese_group_ownership(association, actions, positions, groups, &mut ownership);
    collect_english_group_ownership(association, actions, positions, groups, &mut ownership);
    ownership
}

fn collect_japanese_instruction_ownership(
    association: &SemanticAssociationResult,
    actions: &[SemanticTerm],
    positions: &[SemanticTerm],
    ownership: &mut InstructionOwnership,
) {
    for marker in association
        .clause_topology
        .attachment_markers
        .iter()
        .filter(|marker| {
            marker.marker == AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wo)
        })
    {
        let clause = &association.clause_stream.clauses[marker.clause_index];
        let previous_action_end = actions
            .iter()
            .filter(|action| {
                action.provenance.source.clause_index == marker.clause_index
                    && action.provenance.source.span.end_byte <= marker.span.start_byte
            })
            .map(|action| action.provenance.source.span.end_byte)
            .max()
            .unwrap_or(clause.span.start_byte);
        let candidate_entities = association
            .ast
            .entities
            .iter()
            .filter(|entity| {
                let source = entity.head.source();
                source.clause_index == marker.clause_index
                    && previous_action_end <= source.span.start_byte
                    && source.span.end_byte <= marker.span.start_byte
            })
            .collect::<Vec<_>>();
        if candidate_entities.len() != 1
            || !japanese_entity_segment_is_clear(
                association,
                marker.clause_index,
                previous_action_end,
                marker.span.start_byte,
            )
        {
            continue;
        }
        let entity = candidate_entities[0];
        let head_start = entity.head.source().span.start_byte;
        let next_head_start = association
            .ast
            .entities
            .iter()
            .filter(|candidate| {
                let source = candidate.head.source();
                source.clause_index == marker.clause_index
                    && marker.span.end_byte <= source.span.start_byte
            })
            .map(|candidate| candidate.head.source().span.start_byte)
            .min()
            .unwrap_or(clause.span.end_byte);
        if !japanese_predicate_segment_is_clear(
            association,
            marker.clause_index,
            marker.span.end_byte,
            next_head_start,
        ) {
            continue;
        }
        let candidate_actions = actions
            .iter()
            .filter(|action| {
                action.provenance.source.clause_index == marker.clause_index
                    && marker.span.end_byte <= action.provenance.source.span.start_byte
                    && action.provenance.source.span.end_byte <= next_head_start
            })
            .collect::<Vec<_>>();
        if candidate_actions.is_empty() {
            continue;
        }
        for action in &candidate_actions {
            ownership.insert_action(head_start, action.provenance.source.span.start_byte);
        }
        let predicate_start = candidate_actions
            .iter()
            .map(|action| action.provenance.source.span.start_byte)
            .min()
            .expect("non-empty action candidates");
        for position in positions.iter().filter(|position| {
            position.provenance.source.clause_index == marker.clause_index
                && previous_action_end <= position.provenance.source.span.start_byte
                && position.provenance.source.span.end_byte <= predicate_start
        }) {
            let has_direct_marker = association
                .clause_topology
                .attachment_markers
                .iter()
                .filter(|candidate| candidate.clause_index == marker.clause_index)
                .filter(|candidate| {
                    matches!(
                        candidate.marker,
                        AttachmentMarkerKind::Japanese(
                            JapaneseAttachmentMarkerKind::Ni
                                | JapaneseAttachmentMarkerKind::De
                                | JapaneseAttachmentMarkerKind::He
                        )
                    )
                })
                .any(|candidate| {
                    position.provenance.source.span.end_byte <= candidate.span.start_byte
                        && candidate.span.end_byte <= predicate_start
                        && clause.atoms.iter().all(|atom| {
                            atom.span().end_byte <= position.provenance.source.span.end_byte
                                || candidate.span.start_byte <= atom.span().start_byte
                        })
                });
            if has_direct_marker {
                ownership.insert_position(head_start, position.provenance.source.span.start_byte);
            }
        }
    }
}

fn collect_english_instruction_ownership(
    association: &SemanticAssociationResult,
    actions: &[SemanticTerm],
    positions: &[SemanticTerm],
    ownership: &mut InstructionOwnership,
) {
    for action in actions {
        let clause_index = action.provenance.source.clause_index;
        let clause = &association.clause_stream.clauses[clause_index];
        let upper_bound = actions
            .iter()
            .filter(|candidate| {
                candidate.provenance.source.clause_index == clause_index
                    && action.provenance.source.span.end_byte
                        <= candidate.provenance.source.span.start_byte
            })
            .map(|candidate| candidate.provenance.source.span.start_byte)
            .min()
            .unwrap_or(clause.span.end_byte);
        let candidate_entities = association
            .ast
            .entities
            .iter()
            .filter(|entity| {
                let source = entity.head.source();
                source.clause_index == clause_index
                    && action.provenance.source.span.end_byte <= source.span.start_byte
                    && source.span.end_byte <= upper_bound
                    && english_entity_prefix_is_clear(
                        association,
                        clause_index,
                        action.provenance.source.span.end_byte,
                        source.span.start_byte,
                    )
            })
            .collect::<Vec<_>>();
        if candidate_entities.len() != 1 {
            continue;
        }
        let entity = candidate_entities[0];
        let head_start = entity.head.source().span.start_byte;
        ownership.insert_action(head_start, action.provenance.source.span.start_byte);

        for marker in association
            .clause_topology
            .attachment_markers
            .iter()
            .filter(|marker| marker.clause_index == clause_index)
            .filter(|marker| {
                matches!(
                    marker.marker,
                    AttachmentMarkerKind::English(
                        EnglishAttachmentMarkerKind::At
                            | EnglishAttachmentMarkerKind::In
                            | EnglishAttachmentMarkerKind::On
                            | EnglishAttachmentMarkerKind::To
                    )
                )
            })
            .filter(|marker| {
                entity.head.source().span.end_byte <= marker.span.start_byte
                    && marker.span.end_byte <= upper_bound
            })
            .filter(|marker| {
                english_entity_to_marker_gap_is_clear(
                    association,
                    clause_index,
                    entity.head.source().span.end_byte,
                    marker.span.start_byte,
                )
            })
        {
            for position in positions.iter().filter(|position| {
                position.provenance.source.clause_index == clause_index
                    && marker.span.end_byte <= position.provenance.source.span.start_byte
                    && position.provenance.source.span.end_byte <= upper_bound
            }) {
                if english_position_gap_is_clear(
                    association,
                    clause_index,
                    marker.span.end_byte,
                    position.provenance.source.span.start_byte,
                ) {
                    ownership
                        .insert_position(head_start, position.provenance.source.span.start_byte);
                }
            }
        }
    }
}

fn collect_japanese_group_ownership(
    association: &SemanticAssociationResult,
    actions: &[SemanticTerm],
    positions: &[SemanticTerm],
    groups: &[SemanticCoordinatedHeadGroup],
    ownership: &mut InstructionOwnership,
) {
    for marker in association
        .clause_topology
        .attachment_markers
        .iter()
        .filter(|marker| {
            marker.marker == AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wo)
        })
    {
        let clause = &association.clause_stream.clauses[marker.clause_index];
        let previous_action_end = actions
            .iter()
            .filter(|action| {
                action.provenance.source.clause_index == marker.clause_index
                    && action.provenance.source.span.end_byte <= marker.span.start_byte
            })
            .map(|action| action.provenance.source.span.end_byte)
            .max()
            .unwrap_or(clause.span.start_byte);
        let candidate_groups = groups
            .iter()
            .enumerate()
            .filter(|(_, group)| {
                let first = &association.ast.entities[group.member_instruction_indices[0]];
                let last = &association.ast.entities[*group
                    .member_instruction_indices
                    .last()
                    .expect("coordinated group has members")];
                first.head.source().clause_index == marker.clause_index
                    && previous_action_end <= first.head.source().span.start_byte
                    && last.head.source().span.end_byte <= marker.span.start_byte
                    && association
                        .ast
                        .entities
                        .iter()
                        .enumerate()
                        .all(|(index, entity)| {
                            let source = entity.head.source();
                            source.clause_index != marker.clause_index
                                || source.span.end_byte <= previous_action_end
                                || marker.span.start_byte <= source.span.start_byte
                                || group.member_instruction_indices.contains(&index)
                        })
                    && japanese_group_segment_is_clear(
                        association,
                        group,
                        previous_action_end,
                        marker.span.start_byte,
                    )
            })
            .map(|(group_index, _)| group_index)
            .collect::<Vec<_>>();
        if candidate_groups.len() != 1 {
            continue;
        }
        let group_index = candidate_groups[0];
        let next_head_start = association
            .ast
            .entities
            .iter()
            .filter(|candidate| {
                let source = candidate.head.source();
                source.clause_index == marker.clause_index
                    && marker.span.end_byte <= source.span.start_byte
            })
            .map(|candidate| candidate.head.source().span.start_byte)
            .min()
            .unwrap_or(clause.span.end_byte);
        if !japanese_predicate_segment_is_clear(
            association,
            marker.clause_index,
            marker.span.end_byte,
            next_head_start,
        ) {
            continue;
        }
        let candidate_actions = actions
            .iter()
            .filter(|action| {
                action.provenance.source.clause_index == marker.clause_index
                    && marker.span.end_byte <= action.provenance.source.span.start_byte
                    && action.provenance.source.span.end_byte <= next_head_start
            })
            .collect::<Vec<_>>();
        for action in &candidate_actions {
            ownership.insert_group_action(group_index, action.provenance.source.span.start_byte);
        }
        let Some(predicate_start) = candidate_actions
            .iter()
            .map(|action| action.provenance.source.span.start_byte)
            .min()
        else {
            continue;
        };
        for position in positions.iter().filter(|position| {
            position.provenance.source.clause_index == marker.clause_index
                && previous_action_end <= position.provenance.source.span.start_byte
                && position.provenance.source.span.end_byte <= predicate_start
        }) {
            let has_direct_marker = association
                .clause_topology
                .attachment_markers
                .iter()
                .filter(|candidate| candidate.clause_index == marker.clause_index)
                .filter(|candidate| {
                    matches!(
                        candidate.marker,
                        AttachmentMarkerKind::Japanese(
                            JapaneseAttachmentMarkerKind::Ni
                                | JapaneseAttachmentMarkerKind::De
                                | JapaneseAttachmentMarkerKind::He
                        )
                    )
                })
                .any(|candidate| {
                    position.provenance.source.span.end_byte <= candidate.span.start_byte
                        && candidate.span.end_byte <= predicate_start
                        && clause.atoms.iter().all(|atom| {
                            atom.span().end_byte <= position.provenance.source.span.end_byte
                                || candidate.span.start_byte <= atom.span().start_byte
                        })
                });
            if has_direct_marker {
                ownership
                    .insert_group_position(group_index, position.provenance.source.span.start_byte);
            }
        }
    }
}

fn collect_english_group_ownership(
    association: &SemanticAssociationResult,
    actions: &[SemanticTerm],
    positions: &[SemanticTerm],
    groups: &[SemanticCoordinatedHeadGroup],
    ownership: &mut InstructionOwnership,
) {
    for action in actions {
        let clause_index = action.provenance.source.clause_index;
        let clause = &association.clause_stream.clauses[clause_index];
        let upper_bound = actions
            .iter()
            .filter(|candidate| {
                candidate.provenance.source.clause_index == clause_index
                    && action.provenance.source.span.end_byte
                        <= candidate.provenance.source.span.start_byte
            })
            .map(|candidate| candidate.provenance.source.span.start_byte)
            .min()
            .unwrap_or(clause.span.end_byte);
        let candidate_groups = groups
            .iter()
            .enumerate()
            .filter(|(_, group)| {
                let first = &association.ast.entities[group.member_instruction_indices[0]];
                let last = &association.ast.entities[*group
                    .member_instruction_indices
                    .last()
                    .expect("coordinated group has members")];
                first.head.source().clause_index == clause_index
                    && action.provenance.source.span.end_byte <= first.head.source().span.start_byte
                    && last.head.source().span.end_byte <= upper_bound
                    && english_entity_prefix_is_clear(
                        association,
                        clause_index,
                        action.provenance.source.span.end_byte,
                        first.head.source().span.start_byte,
                    )
                    && association
                        .ast
                        .entities
                        .iter()
                        .enumerate()
                        .all(|(index, entity)| {
                            let source = entity.head.source();
                            source.clause_index != clause_index
                                || source.span.end_byte <= action.provenance.source.span.end_byte
                                || upper_bound <= source.span.start_byte
                                || group.member_instruction_indices.contains(&index)
                        })
            })
            .map(|(group_index, _)| group_index)
            .collect::<Vec<_>>();
        if candidate_groups.len() != 1 {
            continue;
        }
        let group_index = candidate_groups[0];
        let group = &groups[group_index];
        let last = &association.ast.entities[*group
            .member_instruction_indices
            .last()
            .expect("coordinated group has members")];
        ownership.insert_group_action(group_index, action.provenance.source.span.start_byte);

        for marker in association
            .clause_topology
            .attachment_markers
            .iter()
            .filter(|marker| marker.clause_index == clause_index)
            .filter(|marker| {
                matches!(
                    marker.marker,
                    AttachmentMarkerKind::English(
                        EnglishAttachmentMarkerKind::At
                            | EnglishAttachmentMarkerKind::In
                            | EnglishAttachmentMarkerKind::On
                            | EnglishAttachmentMarkerKind::To
                    )
                )
            })
            .filter(|marker| {
                last.head.source().span.end_byte <= marker.span.start_byte
                    && marker.span.end_byte <= upper_bound
            })
            .filter(|marker| {
                english_entity_to_marker_gap_is_clear(
                    association,
                    clause_index,
                    last.head.source().span.end_byte,
                    marker.span.start_byte,
                )
            })
        {
            for position in positions.iter().filter(|position| {
                position.provenance.source.clause_index == clause_index
                    && marker.span.end_byte <= position.provenance.source.span.start_byte
                    && position.provenance.source.span.end_byte <= upper_bound
            }) {
                if english_position_gap_is_clear(
                    association,
                    clause_index,
                    marker.span.end_byte,
                    position.provenance.source.span.start_byte,
                ) {
                    ownership.insert_group_position(
                        group_index,
                        position.provenance.source.span.start_byte,
                    );
                }
            }
        }
    }
}

fn japanese_group_segment_is_clear(
    association: &SemanticAssociationResult,
    group: &SemanticCoordinatedHeadGroup,
    start_byte: usize,
    end_byte: usize,
) -> bool {
    let clause_index = association.ast.entities[group.member_instruction_indices[0]]
        .head
        .source()
        .clause_index;
    let owned_spans = group
        .member_instruction_indices
        .iter()
        .flat_map(|index| {
            let entity = &association.ast.entities[*index];
            let mut spans = semantic_entity_owned_spans(entity);
            spans.insert((
                entity.head.source().span.start_byte,
                entity.head.source().span.end_byte,
            ));
            spans
        })
        .collect::<BTreeSet<_>>();
    let marker_spans = group
        .markers
        .iter()
        .map(|marker| (marker.span.start_byte, marker.span.end_byte))
        .collect::<BTreeSet<_>>();
    let head_spans = group
        .member_instruction_indices
        .iter()
        .map(|index| association.ast.entities[*index].head.source().span)
        .map(|span| (span.start_byte, span.end_byte))
        .collect::<BTreeSet<_>>();
    association.clause_stream.clauses[clause_index]
        .atoms
        .iter()
        .filter(|atom| start_byte <= atom.span().start_byte && atom.span().end_byte <= end_byte)
        .all(|atom| {
            let key = (atom.span().start_byte, atom.span().end_byte);
            owned_spans.contains(&key)
                || marker_spans.contains(&key)
                || japanese_owned_genitive_bridge(
                    association,
                    clause_index,
                    atom.span(),
                    &owned_spans,
                    &head_spans,
                )
                || matches!(
                    atom,
                    ClauseAtom::GrammarMarker {
                        marker_id: MarkerId::JaGroup,
                        ..
                    }
                )
                || matches!(atom, ClauseAtom::GrammarMarker { marker_id: MarkerId::JaNo, span }
                if association.clause_stream.clauses[clause_index].atoms.iter().any(
                    |candidate| matches!(candidate,
                        ClauseAtom::GrammarMarker { marker_id: MarkerId::JaGroup, span: group_span }
                            if span.end_byte == group_span.start_byte
                    )
                ))
                || matches!(atom, ClauseAtom::GrammarMarker { span, .. }
                    if association.clause_topology.determiner_starts.contains(&span.start_byte))
        })
}

fn japanese_entity_segment_is_clear(
    association: &SemanticAssociationResult,
    clause_index: usize,
    start_byte: usize,
    end_byte: usize,
) -> bool {
    association.clause_stream.clauses[clause_index]
        .atoms
        .iter()
        .filter(|atom| start_byte <= atom.span().start_byte && atom.span().end_byte <= end_byte)
        .all(|atom| match atom {
            ClauseAtom::CoreRole(term) => term.role != CoreRoleKind::Ground,
            ClauseAtom::CoreModifier(_) | ClauseAtom::UnattachedExactNumber(_) => true,
            // The counter of a count inside the entity phrase, e.g. `三 本 の 線`.
            ClauseAtom::FunctionWord { surface, span, .. }
                if crate::parser::is_japanese_counter_surface(surface)
                    && association.clause_stream.clauses[clause_index].atoms.iter().any(|candidate|
                        matches!(candidate, ClauseAtom::UnattachedExactNumber(number) if number.span.end_byte == span.start_byte)) => true,
            ClauseAtom::FunctionWord {
                geometry_keyword: Some(_),
                ..
            }
            | ClauseAtom::FunctionWord {
                exact_decimal: Some(_),
                ..
            } => true,
            ClauseAtom::RemainingRole(term) => term.role != RemainingRoleKind::Motion,
            ClauseAtom::GrammarMarker { span, .. } => {
                matches!(
                    attachment_marker_at(association, clause_index, span.start_byte),
                    Some(AttachmentMarkerKind::Japanese(
                        JapaneseAttachmentMarkerKind::No
                            | JapaneseAttachmentMarkerKind::Ni
                            | JapaneseAttachmentMarkerKind::De
                            | JapaneseAttachmentMarkerKind::He
                    ))
                ) || semantic_sequence_marker_owns_span(association, *span)
            }
            ClauseAtom::FunctionWord { span, .. } => {
                semantic_sequence_marker_owns_span(association, *span)
            }
            ClauseAtom::SaijikiRelation { span, .. } => association
                .explicit_previous_references
                .iter()
                .any(|reference| reference.provenance.span == *span),
            // The exact Japanese object marker and a single typed head still
            // delimit the entity phrase. Keep an unresolved modifier as its own
            // diagnostic without taking the typed head away from the predicate.
            ClauseAtom::UnresolvedDiagnostic(_) => true,
        })
}

fn semantic_sequence_marker_owns_span(
    association: &SemanticAssociationResult,
    span: SourceSpan,
) -> bool {
    association
        .ast
        .sequences
        .iter()
        .flat_map(|sequence| &sequence.sequence.markers)
        .chain(
            association
                .sequence_issues
                .iter()
                .flat_map(|issue| &issue.markers),
        )
        .any(|marker| marker.span == span)
}

fn japanese_predicate_segment_is_clear(
    association: &SemanticAssociationResult,
    clause_index: usize,
    start_byte: usize,
    end_byte: usize,
) -> bool {
    association.clause_stream.clauses[clause_index]
        .atoms
        .iter()
        .filter(|atom| start_byte <= atom.span().start_byte && atom.span().end_byte <= end_byte)
        .all(|atom| match atom {
            ClauseAtom::FunctionWord { surface, span, .. }
                if crate::parser::is_japanese_counter_surface(surface)
                    && association.clause_stream.clauses[clause_index].atoms.iter().any(|candidate|
                        matches!(candidate, ClauseAtom::UnattachedExactNumber(number) if number.span.end_byte == span.start_byte)) => true,
            ClauseAtom::CoreModifier(_) | ClauseAtom::UnattachedExactNumber(_) => true,
            ClauseAtom::FunctionWord {
                geometry_keyword: Some(_),
                ..
            }
            | ClauseAtom::FunctionWord {
                exact_decimal: Some(_),
                ..
            } => true,
            // A typed but unowned modifier is delivered by its own semantic
            // issue. It does not erase the exact single head/action ownership
            // established by the object marker.
            ClauseAtom::RemainingRole(_) => true,
            ClauseAtom::FunctionWord { surface, .. } => {
                crate::parser::is_group_layout_function_word(surface)
            }
            ClauseAtom::GrammarMarker { span, .. } => matches!(
                attachment_marker_at(association, clause_index, span.start_byte),
                Some(AttachmentMarkerKind::Japanese(
                    JapaneseAttachmentMarkerKind::No
                        | JapaneseAttachmentMarkerKind::Ni
                        | JapaneseAttachmentMarkerKind::De
                        | JapaneseAttachmentMarkerKind::He
                ))
            ),
            ClauseAtom::CoreRole(_) => false,
            ClauseAtom::SaijikiRelation { span, .. } => association.explicit_previous_references.iter().any(|reference| reference.provenance.span == *span),
            // The exact Japanese object marker and the single typed head/action on
            // its two sides own the accepted predicate terms. An unresolved atom
            // remains a separately delivered diagnostic; it does not take those
            // already typed terms away from their exact owner.
            ClauseAtom::UnresolvedDiagnostic(_) => true,
        })
}

fn english_entity_prefix_is_clear(
    association: &SemanticAssociationResult,
    clause_index: usize,
    start_byte: usize,
    end_byte: usize,
) -> bool {
    association.clause_stream.clauses[clause_index]
        .atoms
        .iter()
        .filter(|atom| start_byte <= atom.span().start_byte && atom.span().end_byte <= end_byte)
        .all(|atom| match atom {
            ClauseAtom::CoreRole(term) => matches!(
                term.role,
                CoreRoleKind::Color | CoreRoleKind::Touch | CoreRoleKind::Surface
            ),
            ClauseAtom::CoreModifier(_) | ClauseAtom::UnattachedExactNumber(_) => true,
            ClauseAtom::FunctionWord {
                geometry_keyword: Some(_),
                ..
            }
            | ClauseAtom::FunctionWord {
                exact_decimal: Some(_),
                ..
            } => true,
            ClauseAtom::RemainingRole(term) => matches!(
                term.role,
                RemainingRoleKind::Angle
                    | RemainingRoleKind::Continuity
                    | RemainingRoleKind::Fluctuation
                    | RemainingRoleKind::Proportion
            ),
            ClauseAtom::GrammarMarker { marker_id, span } => {
                *marker_id == MarkerId::EnGroupOf
                    || association
                        .clause_topology
                        .determiner_starts
                        .contains(&span.start_byte)
                    || attachment_marker_at(association, clause_index, span.start_byte)
                        == Some(AttachmentMarkerKind::English(
                            EnglishAttachmentMarkerKind::Of,
                        ))
            }
            ClauseAtom::FunctionWord { .. } => false,
            ClauseAtom::SaijikiRelation { .. } | ClauseAtom::UnresolvedDiagnostic(_) => false,
        })
}

fn english_entity_to_marker_gap_is_clear(
    association: &SemanticAssociationResult,
    clause_index: usize,
    start_byte: usize,
    end_byte: usize,
) -> bool {
    association.clause_stream.clauses[clause_index]
        .atoms
        .iter()
        .filter(|atom| start_byte <= atom.span().start_byte && atom.span().end_byte <= end_byte)
        .all(|atom| match atom {
            ClauseAtom::RemainingRole(term) => matches!(
                term.role,
                RemainingRoleKind::Place | RemainingRoleKind::Angle
            ),
            ClauseAtom::FunctionWord {
                geometry_keyword: Some(_),
                ..
            }
            | ClauseAtom::FunctionWord {
                exact_decimal: Some(_),
                ..
            } => true,
            ClauseAtom::FunctionWord { surface, .. } => {
                crate::parser::is_group_layout_function_word(surface)
            }
            ClauseAtom::GrammarMarker { span, .. } => {
                association
                    .clause_topology
                    .determiner_starts
                    .contains(&span.start_byte)
                    || (attachment_marker_at(association, clause_index, span.start_byte)
                        == Some(AttachmentMarkerKind::English(
                            EnglishAttachmentMarkerKind::With,
                        ))
                        && association.ast.entities.iter().any(|entity| {
                            entity.head.source().clause_index == clause_index
                                && entity.head.source().span.end_byte == start_byte
                                && entity
                                    .explicit_geometry
                                    .iter()
                                    .chain(&entity.additional_explicit_geometries)
                                    .any(|geometry| {
                                        span.end_byte <= geometry.source().span.start_byte
                                            && geometry.source().span.end_byte <= end_byte
                                    })
                        }))
                    || matches!(
                        attachment_marker_at(association, clause_index, span.start_byte),
                        Some(AttachmentMarkerKind::English(
                            EnglishAttachmentMarkerKind::At
                                | EnglishAttachmentMarkerKind::In
                                | EnglishAttachmentMarkerKind::On
                                | EnglishAttachmentMarkerKind::To
                        ))
                    )
            }
            _ => false,
        })
}

fn english_position_gap_is_clear(
    association: &SemanticAssociationResult,
    clause_index: usize,
    start_byte: usize,
    end_byte: usize,
) -> bool {
    association.clause_stream.clauses[clause_index]
        .atoms
        .iter()
        .filter(|atom| start_byte <= atom.span().start_byte && atom.span().end_byte <= end_byte)
        .all(|atom| match atom {
            ClauseAtom::GrammarMarker { span, .. } => association
                .clause_topology
                .determiner_starts
                .contains(&span.start_byte),
            _ => false,
        })
}

fn attachment_marker_at(
    association: &SemanticAssociationResult,
    clause_index: usize,
    start_byte: usize,
) -> Option<AttachmentMarkerKind> {
    association
        .clause_topology
        .attachment_markers
        .iter()
        .find(|marker| marker.clause_index == clause_index && marker.span.start_byte == start_byte)
        .map(|marker| marker.marker)
}

fn select_relation(
    mut occurrences: Vec<ExplicitPreviousReferenceOccurrence>,
    previous_instructions: &[SemanticInstruction],
    region_index: usize,
    issues: &mut Vec<SemanticRelationIssue>,
) -> Option<SemanticRelation> {
    if occurrences.is_empty() {
        return None;
    }
    if occurrences.len() > 1 {
        issues.push(SemanticRelationIssue {
            kind: SemanticRelationIssueKind::ConflictingRelations,
            region_index,
            current_owner: Some(SemanticRelationIssueOwner::Instruction {
                instruction_index: previous_instructions.len(),
            }),
            occurrences,
        });
        return None;
    }

    let occurrence = occurrences.pop().expect("one relation occurrence");
    if previous_instructions.len() < occurrence.reference.required_previous_count() {
        let kind = match occurrence.reference {
            SemanticPreviousReference::PreviousOne => SemanticRelationIssueKind::MissingPreviousOne,
            SemanticPreviousReference::PreviousTwo => SemanticRelationIssueKind::MissingPreviousTwo,
        };
        issues.push(SemanticRelationIssue {
            kind,
            region_index,
            current_owner: Some(SemanticRelationIssueOwner::Instruction {
                instruction_index: previous_instructions.len(),
            }),
            occurrences: vec![occurrence],
        });
        return None;
    }

    if let Some(target) = occurrence.target
        && !previous_instructions.last().is_some_and(|prior| {
            matches!(
                &prior.entity.head,
                crate::SemanticHead::Primitive(term)
                    if term.identity.category == "shape" && term.identity.id == target.as_str()
            )
        })
    {
        issues.push(SemanticRelationIssue {
            kind: SemanticRelationIssueKind::TargetPrimitiveMismatch,
            region_index,
            current_owner: Some(SemanticRelationIssueOwner::Instruction {
                instruction_index: previous_instructions.len(),
            }),
            occurrences: vec![occurrence],
        });
        return None;
    }

    Some(SemanticRelation {
        target_endpoint: occurrence.target_endpoint,
        target_path_selection: occurrence.target_path_selection,
        kind: occurrence.kind,
        reference: occurrence.reference,
        provenance: occurrence.provenance,
    })
}

fn select_one(
    mut terms: Vec<SemanticTerm>,
    role: SemanticInstructionOccurrenceRole,
    conflict_kind: SemanticInstructionIssueKind,
    region_index: usize,
    issues: &mut Vec<SemanticInstructionIssue>,
) -> Option<SemanticTerm> {
    match terms.len() {
        0 => None,
        1 => terms.pop(),
        _ => {
            issues.push(SemanticInstructionIssue {
                kind: conflict_kind,
                region_index,
                occurrences: terms
                    .into_iter()
                    .map(|term| SemanticInstructionOccurrence { role, term })
                    .collect(),
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            });
            None
        }
    }
}

fn append_orphan_issue(
    terms: Vec<SemanticTerm>,
    role: SemanticInstructionOccurrenceRole,
    kind: SemanticInstructionIssueKind,
    region_index: usize,
    issues: &mut Vec<SemanticInstructionIssue>,
) {
    if terms.is_empty() {
        return;
    }
    issues.push(SemanticInstructionIssue {
        kind,
        region_index,
        occurrences: terms
            .into_iter()
            .map(|term| SemanticInstructionOccurrence { role, term })
            .collect(),
        causal_provenance: SemanticIssueCausalProvenance::Unattributed,
    });
}

fn attach_instruction_causal_provenance(
    association: &SemanticAssociationResult,
    issues: &mut [SemanticInstructionIssue],
) {
    let mut heads_by_region = BTreeMap::<usize, Vec<&SourceOccurrence>>::new();
    for entity in &association.ast.entities {
        heads_by_region
            .entry(entity.head.source().region_index)
            .or_default()
            .push(entity.head.source());
    }

    for issue in issues {
        let mut causes = Vec::new();
        if let Some(heads) = heads_by_region.get(&issue.region_index)
            && let [head] = heads.as_slice()
        {
            for occurrence in &issue.occurrences {
                let source = &occurrence.term.provenance.source;
                if source.clause_index == head.clause_index {
                    causes.extend(diagnostic_causes_between(
                        &association.clause_stream,
                        source.clause_index,
                        source.atom_index,
                        head.atom_index,
                        SemanticUpstreamCausalRelation::InstructionOwnershipPath,
                    ));
                }
            }
        }
        issue.causal_provenance = causal_provenance(causes);
    }
}

fn project_instruction_term(
    document: &NormalizedDdlDocument,
    term: &crate::RemainingRoleTerm,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> SemanticTerm {
    project_semantic_term(
        document,
        &term.asset_id,
        &term.category_key,
        &term.canonical_surface_ja,
        term.span,
        region_index,
        clause_index,
        atom_index,
    )
}

fn canonical_ast_bytes(ast: &SemanticInstructionAssociationAst) -> Vec<u8> {
    let instructions = ast
        .instructions
        .iter()
        .map(semantic_instruction_value)
        .collect::<Vec<_>>();
    let mut root = BTreeMap::new();
    root.insert(
        "coordinated_head_groups".to_owned(),
        Value::Array(
            ast.coordinated_head_groups
                .iter()
                .map(semantic_coordinated_head_group_value)
                .collect(),
        ),
    );
    root.insert(
        "group_predicates".to_owned(),
        Value::Array(
            ast.group_predicates
                .iter()
                .map(semantic_group_predicate_value)
                .collect(),
        ),
    );
    root.insert("instructions".to_owned(), Value::Array(instructions));
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID.to_owned()),
    );
    serde_json::to_vec(&root).expect("closed semantic instruction AST serializes")
}

pub(crate) fn semantic_coordinated_head_group_value(group: &SemanticCoordinatedHeadGroup) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "members".to_owned(),
        Value::Array(
            group
                .member_instruction_indices
                .iter()
                .map(|index| Value::from(*index as u64))
                .collect(),
        ),
    );
    Value::Object(record.into_iter().collect())
}

pub(crate) fn semantic_group_predicate_value(edge: &SemanticGroupPredicateEdge) -> Value {
    let mut record = BTreeMap::new();
    if let Some(target) = &edge.fill_target {
        record.insert("fill_target".to_owned(), semantic_fill_target_value(target));
    }
    record.insert(
        "action".to_owned(),
        edge.action
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    record.insert("group".to_owned(), Value::from(edge.group_index as u64));
    record.insert(
        "layout".to_owned(),
        Value::String(edge.layout.as_str().to_owned()),
    );
    record.insert(
        "position".to_owned(),
        edge.position
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    if let Some(relation) = &edge.relation {
        record.insert("relation".to_owned(), semantic_relation_value(relation));
    }
    Value::Object(record.into_iter().collect())
}

pub(crate) fn semantic_instruction_value(instruction: &SemanticInstruction) -> Value {
    let mut record = BTreeMap::new();
    if let Some(target) = &instruction.fill_target {
        record.insert("fill_target".to_owned(), semantic_fill_target_value(target));
    }
    if let Some(direction) = &instruction.layout_direction {
        record.insert(
            "layout_direction".to_owned(),
            semantic_identity_value(&direction.identity),
        );
    }
    record.insert(
        "action".to_owned(),
        instruction
            .action
            .as_ref()
            .map(|action| semantic_identity_value(&action.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "entity".to_owned(),
        semantic_entity_value(&instruction.entity),
    );
    record.insert(
        "position".to_owned(),
        instruction
            .position
            .as_ref()
            .map(|position| semantic_identity_value(&position.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "relation".to_owned(),
        instruction
            .relation
            .as_ref()
            .map(semantic_relation_value)
            .unwrap_or(Value::Null),
    );
    if let Some(sequence) = &instruction.sequence {
        let mut value = crate::semantic_association::semantic_sequence_value(0, sequence);
        value
            .as_object_mut()
            .expect("semantic sequence canonical value is an object")
            .remove("target_instruction_index");
        record.insert("sequence".to_owned(), value);
    }
    Value::Object(record.into_iter().collect())
}

pub(crate) fn semantic_fill_target_value(target: &SemanticFillTarget) -> Value {
    match target {
        SemanticFillTarget::Canvas { .. } => serde_json::json!({"kind":"canvas"}),
        SemanticFillTarget::InlineShape {
            target_instruction_index,
            ..
        } => {
            serde_json::json!({"kind":"inline_shape","target_instruction_index":target_instruction_index})
        }
    }
}

fn semantic_relation_value(relation: &SemanticRelation) -> Value {
    let mut record = BTreeMap::new();
    if let Some(endpoint) = relation.target_endpoint {
        record.insert(
            "target_endpoint".to_owned(),
            serde_json::to_value(endpoint).expect("closed endpoint"),
        );
    }
    if let Some(selection) = relation.target_path_selection {
        record.insert(
            "target_path_position".to_owned(),
            serde_json::to_value(selection).expect("closed target path selection"),
        );
    }
    record.insert(
        "kind".to_owned(),
        Value::String(relation.kind.as_str().to_owned()),
    );
    record.insert(
        "reference".to_owned(),
        Value::String(relation.reference.as_str().to_owned()),
    );
    Value::Object(record.into_iter().collect())
}
