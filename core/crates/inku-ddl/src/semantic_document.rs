//! Document-global semantic ownership over the accepted instruction association.

use std::collections::BTreeMap;

use serde_json::Value;

use crate::{
    ClauseAtom, ClauseStreamError, CoreRoleKind, NormalizedDdlDocument, SemanticInstruction,
    SemanticInstructionAssociationResult, SemanticTerm, associate_semantic_instructions,
    semantic_association::{project_semantic_term, semantic_identity_value, sentence_region_index},
    semantic_instruction::semantic_instruction_value,
};

/// Stable identity for the runtime-disconnected semantic document root.
pub const SEMANTIC_DOCUMENT_SCHEMA_ID: &str = "inku.semantic-document.v3";

/// Document-global semantic AST with accepted drawable instructions and optional support material.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticDocumentAst {
    pub ground: Option<SemanticTerm>,
    pub instructions: Vec<SemanticInstruction>,
    pub complete: bool,
}

/// Stable document-root issue classes.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticDocumentIssueKind {
    ConflictingGrounds,
}

impl SemanticDocumentIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ConflictingGrounds => "conflicting_grounds",
        }
    }
}

/// One document-root issue owning every conflicting Ground occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticDocumentIssue {
    pub kind: SemanticDocumentIssueKind,
    pub occurrences: Vec<SemanticTerm>,
}

/// Source-preserving document semantic result over the accepted instruction chain.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticDocumentResult {
    pub schema_id: &'static str,
    pub instruction_association: SemanticInstructionAssociationResult,
    pub ast: SemanticDocumentAst,
    pub issues: Vec<SemanticDocumentIssue>,
    pub canonical_bytes: Option<Vec<u8>>,
    pub owned_ground_occurrence_count: usize,
    pub delivered_ground_occurrence_count: usize,
}

/// Associate explicit Ground as document-global support material without reparsing instructions.
pub fn associate_semantic_document(
    document: &NormalizedDdlDocument,
) -> Result<SemanticDocumentResult, ClauseStreamError> {
    let instruction_association = associate_semantic_instructions(document)?;
    let mut grounds = Vec::new();

    for (clause_index, clause) in instruction_association
        .association
        .clause_stream
        .clauses
        .iter()
        .enumerate()
    {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let ClauseAtom::CoreRole(term) = atom else {
                continue;
            };
            if term.role != CoreRoleKind::Ground {
                continue;
            }
            let region_index = sentence_region_index(
                &instruction_association.association.clause_stream,
                term.span,
            );
            grounds.push(project_semantic_term(
                document,
                &term.asset_id,
                &term.category_key,
                &term.canonical_surface_ja,
                term.span,
                region_index,
                clause_index,
                atom_index,
            ));
        }
    }

    let owned_ground_occurrence_count = grounds.len();
    let (ground, issues) = match grounds.len() {
        0 => (None, Vec::new()),
        1 => (grounds.pop(), Vec::new()),
        _ => (
            None,
            vec![SemanticDocumentIssue {
                kind: SemanticDocumentIssueKind::ConflictingGrounds,
                occurrences: grounds,
            }],
        ),
    };
    let delivered_ground_occurrence_count = usize::from(ground.is_some())
        + issues
            .iter()
            .map(|issue| issue.occurrences.len())
            .sum::<usize>();
    assert_eq!(
        delivered_ground_occurrence_count, owned_ground_occurrence_count,
        "semantic document must deliver every Ground occurrence exactly once"
    );

    let ast = SemanticDocumentAst {
        ground,
        instructions: instruction_association.ast.instructions.clone(),
        complete: instruction_association.ast.complete && issues.is_empty(),
    };
    let canonical_bytes = ast.complete.then(|| canonical_ast_bytes(&ast));

    Ok(SemanticDocumentResult {
        schema_id: SEMANTIC_DOCUMENT_SCHEMA_ID,
        instruction_association,
        ast,
        issues,
        canonical_bytes,
        owned_ground_occurrence_count,
        delivered_ground_occurrence_count,
    })
}

fn canonical_ast_bytes(ast: &SemanticDocumentAst) -> Vec<u8> {
    let mut root = BTreeMap::new();
    root.insert(
        "ground".to_owned(),
        ast.ground
            .as_ref()
            .map(|ground| semantic_identity_value(&ground.identity))
            .unwrap_or(Value::Null),
    );
    root.insert(
        "instructions".to_owned(),
        Value::Array(
            ast.instructions
                .iter()
                .map(semantic_instruction_value)
                .collect(),
        ),
    );
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_DOCUMENT_SCHEMA_ID.to_owned()),
    );
    serde_json::to_vec(&root).expect("closed semantic document AST serializes")
}
