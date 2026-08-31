//! Explicit Action association over the accepted source-preserving I-584 result.

use std::collections::BTreeMap;

use serde_json::{Number, Value};

use crate::{
    ClauseAtom, ClauseSeparatorKind, ClauseStreamError, NormalizedDdlDocument, RemainingRoleKind,
    SemanticAssociationResult, SemanticEntity, SemanticIdentity, SemanticTerm,
    SemanticTermProvenance, SourceOccurrence, associate_semantic_entities,
    project_macro_semantic_ref,
};

/// Stable identity for the runtime-disconnected explicit Action association AST.
pub const SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID: &str =
    "inku.semantic-instruction-association.v1";

/// One single-head entity and its optional explicit Action.
///
/// A missing Action is unspecified; it is never a defaulted Action.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstruction {
    pub entity: SemanticEntity,
    pub action: Option<SemanticTerm>,
}

/// Partial or complete semantic instruction sequence in entity source order.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstructionAssociationAst {
    pub instructions: Vec<SemanticInstruction>,
    pub complete: bool,
}

/// Stable, expected Action-association issue classes.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticInstructionIssueKind {
    ConflictingActions,
    MissingActionEntity,
}

impl SemanticInstructionIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ConflictingActions => "conflicting_actions",
            Self::MissingActionEntity => "missing_action_entity",
        }
    }
}

/// One typed Action issue with every Action occurrence delivered exactly once.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstructionIssue {
    pub kind: SemanticInstructionIssueKind,
    pub region_index: usize,
    pub actions: Vec<SemanticTerm>,
}

/// Source-preserving explicit Action association result.
///
/// The accepted I-584 association is owned unchanged. Occurrence counts refer only to Motion
/// terms owned as Actions by this slice.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticInstructionAssociationResult {
    pub schema_id: &'static str,
    pub association: SemanticAssociationResult,
    pub ast: SemanticInstructionAssociationAst,
    pub issues: Vec<SemanticInstructionIssue>,
    pub canonical_bytes: Option<Vec<u8>>,
    pub owned_action_occurrence_count: usize,
    pub delivered_action_occurrence_count: usize,
}

/// Associate explicit Saijiki Motion terms as Actions with I-584 single-head entities.
///
/// I-584 is called exactly once. Its owned `ClauseStream`, entities, partial state, and issues are
/// reused directly; no parser, role composition, or sentence-region splitter is rerun.
pub fn associate_semantic_instructions(
    document: &NormalizedDdlDocument,
) -> Result<SemanticInstructionAssociationResult, ClauseStreamError> {
    let association = associate_semantic_entities(document)?;
    let mut actions_by_region = BTreeMap::<usize, Vec<SemanticTerm>>::new();
    let mut owned_action_occurrence_count = 0;

    for (clause_index, clause) in association.clause_stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let ClauseAtom::RemainingRole(term) = atom else {
                continue;
            };
            if term.role != RemainingRoleKind::Motion {
                continue;
            }
            let region_index = region_index_for_span(&association, term.span);
            actions_by_region
                .entry(region_index)
                .or_default()
                .push(project_action(
                    document,
                    term,
                    region_index,
                    clause_index,
                    atom_index,
                ));
            owned_action_occurrence_count += 1;
        }
    }

    let mut instructions = Vec::new();
    let mut issues = Vec::new();
    for entity in &association.ast.entities {
        let region_index = entity.head.provenance.source.region_index;
        let mut actions = actions_by_region.remove(&region_index).unwrap_or_default();
        let action = match actions.len() {
            0 => None,
            1 => actions.pop(),
            _ => {
                issues.push(SemanticInstructionIssue {
                    kind: SemanticInstructionIssueKind::ConflictingActions,
                    region_index,
                    actions,
                });
                None
            }
        };
        instructions.push(SemanticInstruction {
            entity: entity.clone(),
            action,
        });
    }
    issues.extend(
        actions_by_region
            .into_iter()
            .map(|(region_index, actions)| SemanticInstructionIssue {
                kind: SemanticInstructionIssueKind::MissingActionEntity,
                region_index,
                actions,
            }),
    );

    let delivered_action_occurrence_count = instructions
        .iter()
        .filter(|instruction| instruction.action.is_some())
        .count()
        + issues
            .iter()
            .map(|issue| issue.actions.len())
            .sum::<usize>();
    assert_eq!(
        delivered_action_occurrence_count, owned_action_occurrence_count,
        "semantic instruction association must deliver every Action occurrence exactly once"
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
        owned_action_occurrence_count,
        delivered_action_occurrence_count,
    })
}

fn region_index_for_span(
    association: &SemanticAssociationResult,
    span: crate::SourceSpan,
) -> usize {
    association
        .clause_stream
        .separators
        .iter()
        .filter(|separator| {
            separator.kind == ClauseSeparatorKind::SentenceEnd
                && separator.span.end_byte <= span.start_byte
        })
        .count()
}

fn project_action(
    document: &NormalizedDdlDocument,
    term: &crate::RemainingRoleTerm,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> SemanticTerm {
    let projected = project_macro_semantic_ref(&term.category_key, &term.canonical_surface_ja)
        .expect("accepted typed Motion term has a canonical semantic identity");
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
                    .map(|action| canonical_identity(&action.identity))
                    .unwrap_or(Value::Null),
            );
            record.insert("entity".to_owned(), canonical_entity(&instruction.entity));
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

fn canonical_entity(entity: &SemanticEntity) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "color".to_owned(),
        entity
            .color
            .as_ref()
            .map(|color| canonical_identity(&color.identity))
            .unwrap_or(Value::Null),
    );
    record.insert("head".to_owned(), canonical_identity(&entity.head.identity));
    record.insert(
        "quantity".to_owned(),
        entity
            .quantity
            .as_ref()
            .map(|quantity| Value::Number(Number::from(quantity.value)))
            .unwrap_or(Value::Null),
    );
    Value::Object(record.into_iter().collect())
}

fn canonical_identity(identity: &SemanticIdentity) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "category".to_owned(),
        Value::String(identity.category.clone()),
    );
    record.insert("id".to_owned(), Value::String(identity.id.clone()));
    Value::Object(record.into_iter().collect())
}
