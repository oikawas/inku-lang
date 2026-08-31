//! Visible macro invocation resolution against document locks and explicit definitions.

use crate::{
    ClauseAtom, ClauseStreamError, MacroDefinition, MacroDefinitionIdentity, MacroInvocation,
    MacroLock, NeutralDiagnosticKind, NormalizedDdlDocument, RelationReferenceEvidenceResult,
    SourceSpan, collect_relation_reference_evidence,
    parser::{QualifiedMacroMatch, qualified_macro_match},
};

/// Stable identity for the runtime-disconnected macro lock resolution overlay.
pub const MACRO_INVOCATION_LOCK_RESOLUTION_SCHEMA_ID: &str =
    "inku.macro-invocation-lock-resolution.v1";

/// One exact sidecar lock identity retained without transforming any field.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroLockResolutionIdentity {
    pub qualified_name: String,
    pub version: String,
    pub digest: String,
}

impl From<&MacroLock> for MacroLockResolutionIdentity {
    fn from(macro_lock: &MacroLock) -> Self {
        Self {
            qualified_name: macro_lock.qualified_name().to_owned(),
            version: macro_lock.version().to_owned(),
            digest: macro_lock.digest().to_owned(),
        }
    }
}

/// One unexpanded visible invocation resolved to an exact definition identity.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResolvedMacroInvocation {
    pub invocation: MacroInvocation,
    pub span: SourceSpan,
    pub clause_index: usize,
    pub atom_index: usize,
    pub lock: MacroLockResolutionIdentity,
    pub definition_identity: MacroDefinitionIdentity,
}

/// Stable failure classes for one source-ordered visible macro occurrence.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MacroInvocationResolutionDiagnosticKind {
    MissingLock,
    AmbiguousLockPrefix,
    MissingDefinition,
    DuplicateMatchingDefinition,
    InvalidDefinition,
    QualifiedNameMismatch,
    VersionMismatch,
    DigestMismatch,
    SourceClauseAtomMismatch,
}

/// One occurrence withheld from the resolved set, retaining its exact evidence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroInvocationResolutionDiagnostic {
    pub kind: MacroInvocationResolutionDiagnosticKind,
    pub ordinal: u64,
    pub invocation: Option<MacroInvocation>,
    pub surface: String,
    pub span: SourceSpan,
    pub clause_index: Option<usize>,
    pub atom_index: Option<usize>,
    pub matching_locks: Vec<MacroLockResolutionIdentity>,
    pub definition_identity: Option<MacroDefinitionIdentity>,
    pub definition_index: Option<usize>,
    pub invalid_definition_codes: Vec<&'static str>,
}

/// The complete accepted I-579 result plus an unexpanded macro-resolution overlay.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroInvocationLockResolutionResult {
    pub relation_reference_evidence: RelationReferenceEvidenceResult,
    pub resolved: Vec<ResolvedMacroInvocation>,
    pub diagnostics: Vec<MacroInvocationResolutionDiagnostic>,
    pub recognized_occurrence_count: usize,
}

/// Resolve visible qualified occurrences using only sidecar locks and caller-owned definitions.
///
/// The accepted I-579 collector is invoked exactly once. Its complete result and source-owning
/// ClauseStream are retained unchanged; this overlay never expands a definition body.
pub fn resolve_macro_invocations(
    document: &NormalizedDdlDocument,
    definitions: &[MacroDefinition],
) -> Result<MacroInvocationLockResolutionResult, ClauseStreamError> {
    let relation_reference_evidence = collect_relation_reference_evidence(document)?;
    let definition_records = definitions
        .iter()
        .enumerate()
        .map(|(index, definition)| DefinitionRecord {
            index,
            qualified_name: definition.qualified_name(),
            identity: definition.identity().map_err(|validation| {
                validation
                    .diagnostics()
                    .iter()
                    .map(|diagnostic| diagnostic.code())
                    .collect()
            }),
        })
        .collect::<Vec<_>>();
    Ok(build_resolution(
        document,
        relation_reference_evidence,
        &definition_records,
    ))
}

#[derive(Clone)]
struct DefinitionRecord {
    index: usize,
    qualified_name: Option<String>,
    identity: Result<MacroDefinitionIdentity, Vec<&'static str>>,
}

fn build_resolution(
    document: &NormalizedDdlDocument,
    relation_reference_evidence: RelationReferenceEvidenceResult,
    definitions: &[DefinitionRecord],
) -> MacroInvocationLockResolutionResult {
    let stream = &relation_reference_evidence
        .attachment_evidence
        .noun_phrase
        .clause_stream;
    let mut resolved = Vec::new();
    let mut diagnostics = Vec::new();
    let mut ordinal = 0_u64;

    for (clause_index, clause) in stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let start_byte = atom.span().start_byte;
            let Some(macro_match) = qualified_macro_match(document, start_byte) else {
                continue;
            };
            let occurrence = occurrence(
                document,
                macro_match,
                start_byte,
                ordinal,
                clause_index,
                atom_index,
            );
            ordinal += 1;

            if !occurrence_matches_atom(document.source(), atom, &occurrence) {
                diagnostics.push(occurrence.diagnostic(
                    MacroInvocationResolutionDiagnosticKind::SourceClauseAtomMismatch,
                    None,
                    None,
                    Vec::new(),
                ));
                continue;
            }

            match occurrence.lock_indices.as_slice() {
                [] => diagnostics.push(occurrence.diagnostic(
                    MacroInvocationResolutionDiagnosticKind::MissingLock,
                    None,
                    None,
                    Vec::new(),
                )),
                [lock_index] => {
                    let macro_lock = &document.macro_locks()[*lock_index];
                    match resolve_definition(macro_lock, definitions) {
                        DefinitionResolution::Resolved(identity) => {
                            resolved.push(ResolvedMacroInvocation {
                                invocation: occurrence
                                    .invocation
                                    .expect("an exact validated lock has an invocation"),
                                span: occurrence.span,
                                clause_index,
                                atom_index,
                                lock: macro_lock.into(),
                                definition_identity: identity,
                            });
                        }
                        DefinitionResolution::Diagnostic {
                            kind,
                            identity,
                            definition_index,
                            invalid_codes,
                        } => diagnostics.push(occurrence.diagnostic(
                            kind,
                            identity,
                            definition_index,
                            invalid_codes,
                        )),
                    }
                }
                _ => diagnostics.push(occurrence.diagnostic(
                    MacroInvocationResolutionDiagnosticKind::AmbiguousLockPrefix,
                    None,
                    None,
                    Vec::new(),
                )),
            }
        }
    }

    MacroInvocationLockResolutionResult {
        relation_reference_evidence,
        recognized_occurrence_count: resolved.len() + diagnostics.len(),
        resolved,
        diagnostics,
    }
}

struct PendingOccurrence {
    ordinal: u64,
    invocation: Option<MacroInvocation>,
    surface: String,
    span: SourceSpan,
    clause_index: usize,
    atom_index: usize,
    lock_indices: Vec<usize>,
    matching_locks: Vec<MacroLockResolutionIdentity>,
    expected_recognized: bool,
    expected_kind: NeutralDiagnosticKind,
}

impl PendingOccurrence {
    fn diagnostic(
        self,
        kind: MacroInvocationResolutionDiagnosticKind,
        definition_identity: Option<MacroDefinitionIdentity>,
        definition_index: Option<usize>,
        invalid_definition_codes: Vec<&'static str>,
    ) -> MacroInvocationResolutionDiagnostic {
        MacroInvocationResolutionDiagnostic {
            kind,
            ordinal: self.ordinal,
            invocation: self.invocation,
            surface: self.surface,
            span: self.span,
            clause_index: Some(self.clause_index),
            atom_index: Some(self.atom_index),
            matching_locks: self.matching_locks,
            definition_identity,
            definition_index,
            invalid_definition_codes,
        }
    }
}

fn occurrence(
    document: &NormalizedDdlDocument,
    macro_match: QualifiedMacroMatch,
    start_byte: usize,
    ordinal: u64,
    clause_index: usize,
    atom_index: usize,
) -> PendingOccurrence {
    let (end_byte, lock_indices, expected_kind, expected_recognized) = match macro_match {
        QualifiedMacroMatch::Unlocked { end_byte } => {
            (end_byte, Vec::new(), NeutralDiagnosticKind::Unknown, false)
        }
        QualifiedMacroMatch::ExactLock {
            end_byte,
            lock_index,
        } => (
            end_byte,
            vec![lock_index],
            NeutralDiagnosticKind::Unknown,
            false,
        ),
        QualifiedMacroMatch::AmbiguousLocks {
            end_byte,
            lock_indices,
        } => (
            end_byte,
            lock_indices,
            NeutralDiagnosticKind::Conflict,
            true,
        ),
    };
    let span = SourceSpan {
        start_byte,
        end_byte,
    };
    let surface = document.source()[span.start_byte..span.end_byte].to_owned();
    let invocation = invocation(&surface, ordinal);
    let matching_locks = lock_indices
        .iter()
        .map(|&index| (&document.macro_locks()[index]).into())
        .collect();
    PendingOccurrence {
        ordinal,
        invocation,
        surface,
        span,
        clause_index,
        atom_index,
        lock_indices,
        matching_locks,
        expected_recognized,
        expected_kind,
    }
}

fn invocation(surface: &str, ordinal: u64) -> Option<MacroInvocation> {
    let (namespace, heading) = surface.split_once('.')?;
    MacroInvocation::new(namespace, heading, ordinal).ok()
}

fn occurrence_matches_atom(
    source: &str,
    atom: &ClauseAtom,
    occurrence: &PendingOccurrence,
) -> bool {
    let ClauseAtom::UnresolvedDiagnostic(diagnostic) = atom else {
        return false;
    };
    atom.span() == occurrence.span
        && source.get(occurrence.span.start_byte..occurrence.span.end_byte)
            == Some(occurrence.surface.as_str())
        && diagnostic.surface == occurrence.surface
        && diagnostic.kind == occurrence.expected_kind
        && diagnostic.recognized == occurrence.expected_recognized
}

enum DefinitionResolution {
    Resolved(MacroDefinitionIdentity),
    Diagnostic {
        kind: MacroInvocationResolutionDiagnosticKind,
        identity: Option<MacroDefinitionIdentity>,
        definition_index: Option<usize>,
        invalid_codes: Vec<&'static str>,
    },
}

fn resolve_definition(
    macro_lock: &MacroLock,
    definitions: &[DefinitionRecord],
) -> DefinitionResolution {
    let matching_name = definitions
        .iter()
        .filter(|definition| {
            definition.qualified_name.as_deref() == Some(macro_lock.qualified_name())
        })
        .collect::<Vec<_>>();
    let invalid = matching_name
        .iter()
        .filter_map(|definition| {
            definition
                .identity
                .as_ref()
                .err()
                .map(|codes| (*definition, codes))
        })
        .collect::<Vec<_>>();
    if !invalid.is_empty() {
        return DefinitionResolution::Diagnostic {
            kind: MacroInvocationResolutionDiagnosticKind::InvalidDefinition,
            identity: None,
            definition_index: (invalid.len() == 1).then_some(invalid[0].0.index),
            invalid_codes: invalid
                .iter()
                .flat_map(|(_, codes)| codes.iter().copied())
                .collect(),
        };
    }

    let valid = definitions
        .iter()
        .filter_map(|definition| {
            definition
                .identity
                .as_ref()
                .ok()
                .map(|identity| (definition.index, identity))
        })
        .collect::<Vec<_>>();
    let same_name = valid
        .iter()
        .copied()
        .filter(|(_, identity)| identity.qualified_name() == macro_lock.qualified_name())
        .collect::<Vec<_>>();
    if same_name.is_empty() {
        if let [(index, identity)] = valid.as_slice() {
            return mismatch(
                MacroInvocationResolutionDiagnosticKind::QualifiedNameMismatch,
                *index,
                (*identity).clone(),
            );
        }
        return simple_diagnostic(MacroInvocationResolutionDiagnosticKind::MissingDefinition);
    }

    let same_version = same_name
        .iter()
        .copied()
        .filter(|(_, identity)| identity.version() == macro_lock.version())
        .collect::<Vec<_>>();
    if same_version.is_empty() {
        return match same_name.as_slice() {
            [(index, identity)] => mismatch(
                MacroInvocationResolutionDiagnosticKind::VersionMismatch,
                *index,
                (*identity).clone(),
            ),
            _ => simple_diagnostic(MacroInvocationResolutionDiagnosticKind::VersionMismatch),
        };
    }

    let expected_digest = macro_lock
        .digest()
        .strip_prefix("sha256:")
        .expect("MacroLock validates its digest prefix");
    let same_digest = same_version
        .iter()
        .copied()
        .filter(|(_, identity)| identity.full_digest_hex() == expected_digest)
        .collect::<Vec<_>>();
    match same_digest.as_slice() {
        [] => match same_version.as_slice() {
            [(index, identity)] => mismatch(
                MacroInvocationResolutionDiagnosticKind::DigestMismatch,
                *index,
                (*identity).clone(),
            ),
            _ => simple_diagnostic(MacroInvocationResolutionDiagnosticKind::DigestMismatch),
        },
        [(_, identity)] => DefinitionResolution::Resolved((*identity).clone()),
        _ => {
            simple_diagnostic(MacroInvocationResolutionDiagnosticKind::DuplicateMatchingDefinition)
        }
    }
}

fn mismatch(
    kind: MacroInvocationResolutionDiagnosticKind,
    definition_index: usize,
    identity: MacroDefinitionIdentity,
) -> DefinitionResolution {
    DefinitionResolution::Diagnostic {
        kind,
        identity: Some(identity),
        definition_index: Some(definition_index),
        invalid_codes: Vec::new(),
    }
}

fn simple_diagnostic(kind: MacroInvocationResolutionDiagnosticKind) -> DefinitionResolution {
    DefinitionResolution::Diagnostic {
        kind,
        identity: None,
        definition_index: None,
        invalid_codes: Vec::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ResolvedInstructionLanguage;

    #[test]
    fn corrupted_owned_atom_is_a_typed_mismatch_not_a_partial_resolution() {
        let definition = MacroDefinition::from_json(
            r#"{"schema":"inku.macro-definition.v1","namespace":"Nature","heading":"若葉","version":"1.0.0","parameters":{},"components":{},"body":[]}"#,
        )
        .unwrap();
        let identity = definition.identity().unwrap();
        let document = NormalizedDdlDocument::new(
            "Nature.若葉 を置く",
            ResolvedInstructionLanguage::Ja,
            vec![
                MacroLock::new(
                    identity.qualified_name(),
                    identity.version(),
                    format!("sha256:{}", identity.full_digest_hex()),
                )
                .unwrap(),
            ],
        )
        .unwrap();
        let mut relation = collect_relation_reference_evidence(&document).unwrap();
        let ClauseAtom::UnresolvedDiagnostic(diagnostic) = &mut relation
            .attachment_evidence
            .noun_phrase
            .clause_stream
            .clauses[0]
            .atoms[0]
        else {
            panic!("macro occurrence must remain an opaque diagnostic atom");
        };
        diagnostic.surface = "corrupt".to_owned();
        let definitions = vec![DefinitionRecord {
            index: 0,
            qualified_name: definition.qualified_name(),
            identity: Ok(identity),
        }];

        let result = build_resolution(&document, relation, &definitions);
        assert!(result.resolved.is_empty());
        assert_eq!(result.recognized_occurrence_count, 1);
        assert_eq!(result.diagnostics.len(), 1);
        assert_eq!(
            result.diagnostics[0].kind,
            MacroInvocationResolutionDiagnosticKind::SourceClauseAtomMismatch
        );
    }
}
