//! Explicit Action, Position, and previous-reference association over the accepted entity result.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use crate::{
    AttachmentMarkerKind, ClauseAtom, ClauseStreamError, CoreRoleKind, EnglishAttachmentMarkerKind,
    ExplicitPreviousReferenceOccurrence, JapaneseAttachmentMarkerKind, MacroParameterBindingResult,
    NormalizedDdlDocument, RemainingRoleKind, SemanticAssociationResult, SemanticEntity,
    SemanticPreviousReference, SemanticRelationKind, SemanticTerm, SourceOccurrence,
    associate_semantic_entities, associate_semantic_entities_with_macro_binding,
    semantic_association::{
        project_semantic_term, semantic_entity_value, semantic_identity_value,
        sentence_region_index,
    },
};

/// Stable identity for the runtime-disconnected explicit instruction association AST.
pub const SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID: &str =
    "inku.semantic-instruction-association.v13";

/// One explicit relation from the current instruction to prior source-ordered instruction(s).
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticRelation {
    pub kind: SemanticRelationKind,
    pub reference: SemanticPreviousReference,
    pub provenance: SourceOccurrence,
}

/// One single-head entity and its independently optional explicit Action and Position.
///
/// A missing field is unspecified; neither field receives a default.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticInstruction {
    pub entity: SemanticEntity,
    pub action: Option<SemanticTerm>,
    pub position: Option<SemanticTerm>,
    pub relation: Option<SemanticRelation>,
}

/// Partial or complete semantic instruction sequence in entity source order.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticInstructionAssociationAst {
    pub instructions: Vec<SemanticInstruction>,
    pub complete: bool,
}

/// The two roles owned by this instruction slice.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticInstructionOccurrenceRole {
    Action,
    Position,
}

impl SemanticInstructionOccurrenceRole {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Action => "action",
            Self::Position => "position",
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
        }
    }
}

/// One typed instruction issue with every owned occurrence delivered exactly once.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstructionIssue {
    pub kind: SemanticInstructionIssueKind,
    pub region_index: usize,
    pub occurrences: Vec<SemanticInstructionOccurrence>,
}

/// Stable relation-association issue classes without fallback target selection.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticRelationIssueKind {
    AmbiguousCurrentInstructionOwnership,
    ConflictingRelations,
    MissingCurrentInstruction,
    MissingPreviousOne,
    MissingPreviousTwo,
}

impl SemanticRelationIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::AmbiguousCurrentInstructionOwnership => "ambiguous_current_relation_ownership",
            Self::ConflictingRelations => "conflicting_relations",
            Self::MissingCurrentInstruction => "missing_current_instruction",
            Self::MissingPreviousOne => "missing_previous_one",
            Self::MissingPreviousTwo => "missing_previous_two",
        }
    }
}

/// One typed relation issue owning every undelivered full-literal occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticRelationIssue {
    pub kind: SemanticRelationIssueKind,
    pub region_index: usize,
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
    pub canonical_bytes: Option<Vec<u8>>,
    pub owned_instruction_occurrence_count: usize,
    pub delivered_instruction_occurrence_count: usize,
    pub relation_issues: Vec<SemanticRelationIssue>,
    pub owned_relation_occurrence_count: usize,
    pub delivered_relation_occurrence_count: usize,
}

#[derive(Default)]
struct InstructionOwnership {
    action_starts_by_head: BTreeMap<usize, BTreeSet<usize>>,
    position_starts_by_head: BTreeMap<usize, BTreeSet<usize>>,
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

fn build_semantic_instructions(
    document: &NormalizedDdlDocument,
    association: SemanticAssociationResult,
) -> SemanticInstructionAssociationResult {
    let mut actions = Vec::new();
    let mut positions = Vec::new();
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
                | RemainingRoleKind::Continuity
                | RemainingRoleKind::Fluctuation
                | RemainingRoleKind::Proportion => continue,
            };
            let region_index = sentence_region_index(&association.clause_stream, term.span);
            let projected =
                project_instruction_term(document, term, region_index, clause_index, atom_index);
            match role {
                SemanticInstructionOccurrenceRole::Action => actions.push(projected),
                SemanticInstructionOccurrenceRole::Position => positions.push(projected),
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

    let ownership = collect_instruction_ownership(&association, &actions, &positions);

    let mut instructions = Vec::new();
    let mut issues = Vec::new();
    let mut relation_issues = Vec::new();
    let mut entity_counts_by_region = BTreeMap::<usize, usize>::new();
    for entity in &association.ast.entities {
        *entity_counts_by_region
            .entry(entity.head.source().region_index)
            .or_default() += 1;
    }
    for (&region_index, &entity_count) in &entity_counts_by_region {
        if entity_count > 1
            && let Some(relations) = relations_by_region.remove(&region_index)
        {
            relation_issues.push(SemanticRelationIssue {
                kind: SemanticRelationIssueKind::AmbiguousCurrentInstructionOwnership,
                region_index,
                occurrences: relations,
            });
        }
    }
    for entity in &association.ast.entities {
        let region_index = entity.head.source().region_index;
        let head_start = entity.head.source().span.start_byte;
        let action = select_one(
            take_owned_instruction_terms(
                &mut actions,
                ownership.action_starts_by_head.get(&head_start),
            ),
            SemanticInstructionOccurrenceRole::Action,
            SemanticInstructionIssueKind::ConflictingActions,
            region_index,
            &mut issues,
        );
        let position = select_one(
            take_owned_instruction_terms(
                &mut positions,
                ownership.position_starts_by_head.get(&head_start),
            ),
            SemanticInstructionOccurrenceRole::Position,
            SemanticInstructionIssueKind::ConflictingPositions,
            region_index,
            &mut issues,
        );
        let relation = if entity_counts_by_region[&region_index] == 1 {
            select_relation(
                relations_by_region
                    .remove(&region_index)
                    .unwrap_or_default(),
                instructions.len(),
                region_index,
                &mut relation_issues,
            )
        } else {
            None
        };
        instructions.push(SemanticInstruction {
            entity: entity.clone(),
            action,
            position,
            relation,
        });
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
            occurrences: relations,
        });
    }
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
            usize::from(instruction.action.is_some()) + usize::from(instruction.position.is_some())
        })
        .sum::<usize>()
        + issues
            .iter()
            .map(|issue| issue.occurrences.len())
            .sum::<usize>();
    assert_eq!(
        delivered_instruction_occurrence_count, owned_instruction_occurrence_count,
        "semantic instruction association must deliver every Action / Position occurrence exactly once"
    );
    let delivered_relation_occurrence_count = instructions
        .iter()
        .filter(|instruction| instruction.relation.is_some())
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
        complete: association.ast.complete && issues.is_empty() && relation_issues.is_empty(),
    };
    let canonical_bytes = ast.complete.then(|| canonical_ast_bytes(&ast));

    SemanticInstructionAssociationResult {
        schema_id: SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
        association,
        ast,
        issues,
        canonical_bytes,
        owned_instruction_occurrence_count,
        delivered_instruction_occurrence_count,
        relation_issues,
        owned_relation_occurrence_count,
        delivered_relation_occurrence_count,
    }
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

fn collect_instruction_ownership(
    association: &SemanticAssociationResult,
    actions: &[SemanticTerm],
    positions: &[SemanticTerm],
) -> InstructionOwnership {
    let mut ownership = InstructionOwnership::default();
    collect_japanese_instruction_ownership(association, actions, positions, &mut ownership);
    collect_english_instruction_ownership(association, actions, positions, &mut ownership);
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
            ClauseAtom::RemainingRole(term) => term.role != RemainingRoleKind::Motion,
            ClauseAtom::FunctionWord { span, .. } => matches!(
                attachment_marker_at(association, clause_index, span.start_byte),
                Some(AttachmentMarkerKind::Japanese(
                    JapaneseAttachmentMarkerKind::No
                        | JapaneseAttachmentMarkerKind::Ni
                        | JapaneseAttachmentMarkerKind::De
                        | JapaneseAttachmentMarkerKind::He
                ))
            ),
            ClauseAtom::SaijikiRelation { .. } | ClauseAtom::UnresolvedDiagnostic(_) => false,
        })
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
            ClauseAtom::CoreModifier(_) | ClauseAtom::UnattachedExactNumber(_) => true,
            ClauseAtom::RemainingRole(term) => {
                matches!(
                    term.role,
                    RemainingRoleKind::Motion | RemainingRoleKind::Place
                )
            }
            ClauseAtom::FunctionWord { span, .. } => matches!(
                attachment_marker_at(association, clause_index, span.start_byte),
                Some(AttachmentMarkerKind::Japanese(
                    JapaneseAttachmentMarkerKind::Ni
                        | JapaneseAttachmentMarkerKind::De
                        | JapaneseAttachmentMarkerKind::He
                ))
            ),
            ClauseAtom::CoreRole(_)
            | ClauseAtom::SaijikiRelation { .. }
            | ClauseAtom::UnresolvedDiagnostic(_) => false,
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
            ClauseAtom::RemainingRole(term) => matches!(
                term.role,
                RemainingRoleKind::Angle
                    | RemainingRoleKind::Continuity
                    | RemainingRoleKind::Fluctuation
                    | RemainingRoleKind::Proportion
            ),
            ClauseAtom::FunctionWord { span, .. } => {
                association
                    .clause_topology
                    .determiner_starts
                    .contains(&span.start_byte)
                    || attachment_marker_at(association, clause_index, span.start_byte)
                        == Some(AttachmentMarkerKind::English(
                            EnglishAttachmentMarkerKind::Of,
                        ))
            }
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
            ClauseAtom::RemainingRole(term) => term.role == RemainingRoleKind::Place,
            ClauseAtom::FunctionWord { span, .. } => {
                association
                    .clause_topology
                    .determiner_starts
                    .contains(&span.start_byte)
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
            ClauseAtom::FunctionWord { span, .. } => association
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
    previous_instruction_count: usize,
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
            occurrences,
        });
        return None;
    }

    let occurrence = occurrences.pop().expect("one relation occurrence");
    if previous_instruction_count < occurrence.reference.required_previous_count() {
        let kind = match occurrence.reference {
            SemanticPreviousReference::PreviousOne => SemanticRelationIssueKind::MissingPreviousOne,
            SemanticPreviousReference::PreviousTwo => SemanticRelationIssueKind::MissingPreviousTwo,
        };
        issues.push(SemanticRelationIssue {
            kind,
            region_index,
            occurrences: vec![occurrence],
        });
        return None;
    }

    Some(SemanticRelation {
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
    });
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
    root.insert("instructions".to_owned(), Value::Array(instructions));
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID.to_owned()),
    );
    serde_json::to_vec(&root).expect("closed semantic instruction AST serializes")
}

pub(crate) fn semantic_instruction_value(instruction: &SemanticInstruction) -> Value {
    let mut record = BTreeMap::new();
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
    Value::Object(record.into_iter().collect())
}

fn semantic_relation_value(relation: &SemanticRelation) -> Value {
    let mut record = BTreeMap::new();
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
