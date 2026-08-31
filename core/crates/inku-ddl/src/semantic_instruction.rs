//! Explicit Action and Position association over the accepted source-preserving I-584 result.

use std::collections::BTreeMap;

use serde_json::Value;

use crate::{
    ClauseAtom, ClauseStreamError, NormalizedDdlDocument, RemainingRoleKind,
    SemanticAssociationResult, SemanticEntity, SemanticIdentity, SemanticTerm,
    SemanticTermProvenance, SourceOccurrence, associate_semantic_entities,
    project_macro_semantic_ref,
    semantic_association::{semantic_entity_value, semantic_identity_value, sentence_region_index},
};

/// Stable identity for the runtime-disconnected explicit instruction association AST.
pub const SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID: &str =
    "inku.semantic-instruction-association.v2";

/// One single-head entity and its independently optional explicit Action and Position.
///
/// A missing field is unspecified; neither field receives a default.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstruction {
    pub entity: SemanticEntity,
    pub action: Option<SemanticTerm>,
    pub position: Option<SemanticTerm>,
}

/// Partial or complete semantic instruction sequence in entity source order.
#[derive(Clone, Debug, Eq, PartialEq)]
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
    ConflictingActions,
    MissingActionEntity,
    ConflictingPositions,
    MissingPositionEntity,
}

impl SemanticInstructionIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
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

/// Source-preserving explicit Action / Position association result.
///
/// The accepted I-584 association is owned unchanged. Occurrence counts include only Motion and
/// Place terms newly owned by this slice; I-584 entity occurrences are not recounted.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstructionAssociationResult {
    pub schema_id: &'static str,
    pub association: SemanticAssociationResult,
    pub ast: SemanticInstructionAssociationAst,
    pub issues: Vec<SemanticInstructionIssue>,
    pub canonical_bytes: Option<Vec<u8>>,
    pub owned_instruction_occurrence_count: usize,
    pub delivered_instruction_occurrence_count: usize,
}

#[derive(Default)]
struct InstructionRegion {
    actions: Vec<SemanticTerm>,
    positions: Vec<SemanticTerm>,
}

/// Associate explicit Saijiki Motion and Place terms with I-584 single-head entities.
///
/// I-584 is called exactly once. Its owned `ClauseStream`, entities, partial state, and issues are
/// reused directly; no parser, role composition, or sentence-region splitter is rerun.
pub fn associate_semantic_instructions(
    document: &NormalizedDdlDocument,
) -> Result<SemanticInstructionAssociationResult, ClauseStreamError> {
    let association = associate_semantic_entities(document)?;
    let mut occurrences_by_region = BTreeMap::<usize, InstructionRegion>::new();
    let mut owned_instruction_occurrence_count = 0;

    for (clause_index, clause) in association.clause_stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let ClauseAtom::RemainingRole(term) = atom else {
                continue;
            };
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
            let region = occurrences_by_region.entry(region_index).or_default();
            match role {
                SemanticInstructionOccurrenceRole::Action => region.actions.push(projected),
                SemanticInstructionOccurrenceRole::Position => region.positions.push(projected),
            }
            owned_instruction_occurrence_count += 1;
        }
    }

    let mut instructions = Vec::new();
    let mut issues = Vec::new();
    for entity in &association.ast.entities {
        let region_index = entity.head.provenance.source.region_index;
        let region = occurrences_by_region
            .remove(&region_index)
            .unwrap_or_default();
        let action = select_one(
            region.actions,
            SemanticInstructionOccurrenceRole::Action,
            SemanticInstructionIssueKind::ConflictingActions,
            region_index,
            &mut issues,
        );
        let position = select_one(
            region.positions,
            SemanticInstructionOccurrenceRole::Position,
            SemanticInstructionIssueKind::ConflictingPositions,
            region_index,
            &mut issues,
        );
        instructions.push(SemanticInstruction {
            entity: entity.clone(),
            action,
            position,
        });
    }
    for (region_index, region) in occurrences_by_region {
        append_orphan_issue(
            region.actions,
            SemanticInstructionOccurrenceRole::Action,
            SemanticInstructionIssueKind::MissingActionEntity,
            region_index,
            &mut issues,
        );
        append_orphan_issue(
            region.positions,
            SemanticInstructionOccurrenceRole::Position,
            SemanticInstructionIssueKind::MissingPositionEntity,
            region_index,
            &mut issues,
        );
    }

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

    let ast = SemanticInstructionAssociationAst {
        instructions,
        complete: association.ast.complete && issues.is_empty(),
    };
    let canonical_bytes = ast.complete.then(|| canonical_ast_bytes(&ast));

    Ok(SemanticInstructionAssociationResult {
        schema_id: SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
        association,
        ast,
        issues,
        canonical_bytes,
        owned_instruction_occurrence_count,
        delivered_instruction_occurrence_count,
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
    let projected = project_macro_semantic_ref(&term.category_key, &term.canonical_surface_ja)
        .expect("accepted typed instruction term has a canonical semantic identity");
    SemanticTerm {
        identity: SemanticIdentity {
            category: projected.category,
            id: projected.canonical_id,
        },
        provenance: SemanticTermProvenance {
            source: SourceOccurrence {
                span: term.span,
                surface: document.source()[term.span.start_byte..term.span.end_byte].to_owned(),
                language: document.language(),
                region_index,
                clause_index,
                atom_index,
            },
            asset_id: term.asset_id.clone(),
            category_key: term.category_key.clone(),
            canonical_surface_ja: term.canonical_surface_ja.clone(),
        },
    }
}

fn canonical_ast_bytes(ast: &SemanticInstructionAssociationAst) -> Vec<u8> {
    let instructions = ast
        .instructions
        .iter()
        .map(|instruction| {
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
            Value::Object(record.into_iter().collect())
        })
        .collect::<Vec<_>>();
    let mut root = BTreeMap::new();
    root.insert("instructions".to_owned(), Value::Array(instructions));
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID.to_owned()),
    );
    serde_json::to_vec(&root).expect("closed semantic instruction AST serializes")
}
