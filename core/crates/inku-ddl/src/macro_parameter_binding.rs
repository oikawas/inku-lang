//! Unique typed macro parameter binding over the accepted clause and lock-resolution results.

use std::collections::BTreeMap;

use crate::{
    ClauseAtom, ClauseStreamError, MacroDefinition, MacroDefinitionIdentity,
    MacroInvocationLockResolutionResult, NormalizedDdlDocument, ParameterSchema,
    ResolvedMacroInvocation, SourceSpan, project_macro_semantic_ref, resolve_macro_invocations,
};

/// Stable identity for the runtime-disconnected typed macro parameter binding overlay.
pub const MACRO_PARAMETER_BINDING_SCHEMA_ID: &str = "inku.macro-parameter-binding.v1";

/// One source-owned value accepted by the closed I-534 parameter schema.
#[derive(Clone, Debug, PartialEq)]
pub enum BoundMacroParameterValue {
    Integer {
        value: i64,
        source_span: SourceSpan,
    },
    Number {
        value: f64,
        source_span: SourceSpan,
    },
    SemanticRef {
        category: String,
        canonical_id: String,
        source_asset_id: String,
        canonical_surface_ja: String,
        source_span: SourceSpan,
    },
}

impl BoundMacroParameterValue {
    pub const fn source_span(&self) -> SourceSpan {
        match self {
            Self::Integer { source_span, .. }
            | Self::Number { source_span, .. }
            | Self::SemanticRef { source_span, .. } => *source_span,
        }
    }
}

/// One parameter slot and its uniquely owned same-clause source fact.
#[derive(Clone, Debug, PartialEq)]
pub struct MacroParameterBinding {
    pub invocation_index: usize,
    pub invocation_ordinal: u64,
    pub invocation_clause_index: usize,
    pub invocation_atom_index: usize,
    pub definition_identity: MacroDefinitionIdentity,
    pub parameter_name: String,
    pub parameter_schema: ParameterSchema,
    pub source_fact_clause_index: usize,
    pub source_fact_atom_index: usize,
    pub source_span: SourceSpan,
    pub source_surface: String,
    pub value: BoundMacroParameterValue,
}

/// One complete binding envelope for exactly one resolved invocation.
#[derive(Clone, Debug, PartialEq)]
pub struct CompleteMacroParameterBinding {
    pub invocation_index: usize,
    pub invocation_ordinal: u64,
    pub clause_index: usize,
    pub atom_index: usize,
    pub definition_identity: MacroDefinitionIdentity,
    pub parameters: Vec<MacroParameterBinding>,
}

/// Stable typed incomplete outcomes; none permits a partial binding envelope.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MacroParameterBindingDiagnosticKind {
    MissingCompatibleFact,
    AmbiguousCompleteAssignment,
    SharedFact,
    UnsupportedSchema,
    NumericRange,
    NumericPrecision,
    DefinitionIdentityOwnershipMismatch,
    SourceClauseAtomOwnershipMismatch,
}

/// One resolved invocation withheld from the complete binding set.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MacroParameterBindingDiagnostic {
    pub kind: MacroParameterBindingDiagnosticKind,
    pub invocation_index: usize,
    pub invocation_ordinal: u64,
    pub clause_index: usize,
    pub atom_index: usize,
    pub definition_identity: MacroDefinitionIdentity,
    pub parameter_names: Vec<String>,
}

/// The complete accepted I-580 result plus unique typed binding outcomes.
#[derive(Clone, Debug, PartialEq)]
pub struct MacroParameterBindingResult {
    pub macro_resolution: MacroInvocationLockResolutionResult,
    pub complete: Vec<CompleteMacroParameterBinding>,
    pub diagnostics: Vec<MacroParameterBindingDiagnostic>,
}

/// Resolve visible invocations exactly once, then bind only unique complete clause assignments.
pub fn bind_macro_parameters(
    document: &NormalizedDdlDocument,
    definitions: &[MacroDefinition],
) -> Result<MacroParameterBindingResult, ClauseStreamError> {
    let macro_resolution = resolve_macro_invocations(document, definitions)?;
    Ok(build_parameter_bindings(
        document,
        definitions,
        macro_resolution,
    ))
}

#[derive(Clone)]
struct PreparedInvocation<'a> {
    invocation_index: usize,
    resolved: &'a ResolvedMacroInvocation,
    definition: &'a MacroDefinition,
}

#[derive(Clone)]
struct Slot<'a> {
    invocation_index: usize,
    resolved: &'a ResolvedMacroInvocation,
    parameter_name: &'a str,
    parameter_schema: &'a ParameterSchema,
}

#[derive(Clone)]
struct Fact {
    clause_index: usize,
    atom_index: usize,
    span: SourceSpan,
    source_surface: String,
    kind: FactKind,
}

#[derive(Clone)]
enum FactKind {
    ExactNumber(u64),
    Semantic {
        category: String,
        canonical_id: String,
        source_asset_id: String,
        canonical_surface_ja: String,
    },
}

fn build_parameter_bindings(
    document: &NormalizedDdlDocument,
    definitions: &[MacroDefinition],
    macro_resolution: MacroInvocationLockResolutionResult,
) -> MacroParameterBindingResult {
    let mut complete = Vec::new();
    let mut diagnostics = Vec::new();
    let mut by_clause = BTreeMap::<usize, Vec<PreparedInvocation<'_>>>::new();
    let mut ownership_failures = BTreeMap::<usize, MacroParameterBindingDiagnosticKind>::new();
    let mut failed_clauses = BTreeMap::<usize, MacroParameterBindingDiagnosticKind>::new();

    for (invocation_index, resolved) in macro_resolution.resolved.iter().enumerate() {
        let matching_definitions = definitions
            .iter()
            .filter(|definition| {
                definition
                    .identity()
                    .is_ok_and(|identity| identity == resolved.definition_identity)
            })
            .collect::<Vec<_>>();
        if matching_definitions.len() != 1 {
            ownership_failures.insert(
                invocation_index,
                MacroParameterBindingDiagnosticKind::DefinitionIdentityOwnershipMismatch,
            );
            failed_clauses.entry(resolved.clause_index).or_insert(
                MacroParameterBindingDiagnosticKind::DefinitionIdentityOwnershipMismatch,
            );
            continue;
        }
        if !invocation_atom_matches(document, &macro_resolution, resolved) {
            ownership_failures.insert(
                invocation_index,
                MacroParameterBindingDiagnosticKind::SourceClauseAtomOwnershipMismatch,
            );
            failed_clauses
                .entry(resolved.clause_index)
                .or_insert(MacroParameterBindingDiagnosticKind::SourceClauseAtomOwnershipMismatch);
            continue;
        }
        by_clause
            .entry(resolved.clause_index)
            .or_default()
            .push(PreparedInvocation {
                invocation_index,
                resolved,
                definition: matching_definitions[0],
            });
    }

    for (&invocation_index, &kind) in &ownership_failures {
        let resolved = &macro_resolution.resolved[invocation_index];
        diagnostics.push(diagnostic(resolved, invocation_index, kind, Vec::new()));
    }

    for (clause_index, mut invocations) in by_clause {
        invocations.sort_by_key(|invocation| invocation.resolved.invocation.ordinal());
        if let Some(&kind) = failed_clauses.get(&clause_index) {
            for invocation in invocations {
                diagnostics.push(diagnostic(
                    invocation.resolved,
                    invocation.invocation_index,
                    kind,
                    invocation.definition.parameters.keys().cloned().collect(),
                ));
            }
            continue;
        }
        let facts = match clause_facts(document, &macro_resolution, clause_index) {
            Some(facts) => facts,
            None => {
                for invocation in invocations {
                    diagnostics.push(diagnostic(
                        invocation.resolved,
                        invocation.invocation_index,
                        MacroParameterBindingDiagnosticKind::SourceClauseAtomOwnershipMismatch,
                        invocation.definition.parameters.keys().cloned().collect(),
                    ));
                }
                continue;
            }
        };

        let mut slots = Vec::new();
        for invocation in &invocations {
            if invocation.definition.parameters.is_empty() {
                complete.push(CompleteMacroParameterBinding {
                    invocation_index: invocation.invocation_index,
                    invocation_ordinal: invocation.resolved.invocation.ordinal(),
                    clause_index: invocation.resolved.clause_index,
                    atom_index: invocation.resolved.atom_index,
                    definition_identity: invocation.resolved.definition_identity.clone(),
                    parameters: Vec::new(),
                });
                continue;
            }
            for (parameter_name, parameter_schema) in invocation.definition.parameters.iter() {
                slots.push(Slot {
                    invocation_index: invocation.invocation_index,
                    resolved: invocation.resolved,
                    parameter_name,
                    parameter_schema,
                });
            }
        }
        if slots.is_empty() {
            continue;
        }

        if slots.iter().any(|slot| {
            matches!(
                slot.parameter_schema,
                ParameterSchema::Boolean | ParameterSchema::List { .. }
            )
        }) {
            diagnose_clause(
                &mut diagnostics,
                &invocations,
                MacroParameterBindingDiagnosticKind::UnsupportedSchema,
            );
            continue;
        }

        let values = slots
            .iter()
            .map(|slot| {
                facts
                    .iter()
                    .map(|fact| compatible_value(slot.parameter_schema, fact))
                    .collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();
        let adjacency = values
            .iter()
            .map(|row| {
                row.iter()
                    .enumerate()
                    .filter_map(|(fact_index, value)| value.as_ref().map(|_| fact_index))
                    .collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();

        let Some(matching) = perfect_matching(&adjacency, facts.len(), None) else {
            let kind = incomplete_kind(&slots, &facts, &adjacency);
            diagnose_clause(&mut diagnostics, &invocations, kind);
            continue;
        };
        if matching.iter().enumerate().any(|(slot_index, fact_index)| {
            perfect_matching(&adjacency, facts.len(), Some((slot_index, *fact_index))).is_some()
        }) {
            diagnose_clause(
                &mut diagnostics,
                &invocations,
                MacroParameterBindingDiagnosticKind::AmbiguousCompleteAssignment,
            );
            continue;
        }

        let mut parameters_by_invocation = BTreeMap::<usize, Vec<MacroParameterBinding>>::new();
        for (slot_index, fact_index) in matching.into_iter().enumerate() {
            let slot = &slots[slot_index];
            let fact = &facts[fact_index];
            let value = values[slot_index][fact_index]
                .clone()
                .expect("a matched edge must retain its typed value");
            parameters_by_invocation
                .entry(slot.invocation_index)
                .or_default()
                .push(MacroParameterBinding {
                    invocation_index: slot.invocation_index,
                    invocation_ordinal: slot.resolved.invocation.ordinal(),
                    invocation_clause_index: slot.resolved.clause_index,
                    invocation_atom_index: slot.resolved.atom_index,
                    definition_identity: slot.resolved.definition_identity.clone(),
                    parameter_name: slot.parameter_name.to_owned(),
                    parameter_schema: slot.parameter_schema.clone(),
                    source_fact_clause_index: fact.clause_index,
                    source_fact_atom_index: fact.atom_index,
                    source_span: fact.span,
                    source_surface: fact.source_surface.clone(),
                    value,
                });
        }
        for invocation in invocations {
            if invocation.definition.parameters.is_empty() {
                continue;
            }
            complete.push(CompleteMacroParameterBinding {
                invocation_index: invocation.invocation_index,
                invocation_ordinal: invocation.resolved.invocation.ordinal(),
                clause_index: invocation.resolved.clause_index,
                atom_index: invocation.resolved.atom_index,
                definition_identity: invocation.resolved.definition_identity.clone(),
                parameters: parameters_by_invocation
                    .remove(&invocation.invocation_index)
                    .expect("every complete invocation must own all of its parameters"),
            });
        }
    }

    complete.sort_by_key(|binding| binding.invocation_index);
    diagnostics.sort_by_key(|diagnostic| diagnostic.invocation_index);
    MacroParameterBindingResult {
        macro_resolution,
        complete,
        diagnostics,
    }
}

fn invocation_atom_matches(
    document: &NormalizedDdlDocument,
    macro_resolution: &MacroInvocationLockResolutionResult,
    resolved: &ResolvedMacroInvocation,
) -> bool {
    let Some(clause) = macro_resolution
        .relation_reference_evidence
        .attachment_evidence
        .noun_phrase
        .clause_stream
        .clauses
        .get(resolved.clause_index)
    else {
        return false;
    };
    let Some(atom) = clause.atoms.get(resolved.atom_index) else {
        return false;
    };
    matches!(atom, ClauseAtom::UnresolvedDiagnostic(_))
        && atom.span() == resolved.span
        && document
            .source()
            .get(resolved.span.start_byte..resolved.span.end_byte)
            == Some(resolved.invocation.qualified_name().as_str())
}

fn clause_facts(
    document: &NormalizedDdlDocument,
    macro_resolution: &MacroInvocationLockResolutionResult,
    clause_index: usize,
) -> Option<Vec<Fact>> {
    let clause = macro_resolution
        .relation_reference_evidence
        .attachment_evidence
        .noun_phrase
        .clause_stream
        .clauses
        .get(clause_index)?;
    let mut facts = Vec::new();
    for (atom_index, atom) in clause.atoms.iter().enumerate() {
        let span = atom.span();
        if !(clause.span.start_byte <= span.start_byte && span.end_byte <= clause.span.end_byte) {
            return None;
        }
        let source_surface = document
            .source()
            .get(span.start_byte..span.end_byte)?
            .to_owned();
        let kind = match atom {
            ClauseAtom::CoreRole(term) => semantic_fact(
                &term.asset_id,
                &term.category_key,
                &term.canonical_surface_ja,
            )?,
            ClauseAtom::RemainingRole(term) => semantic_fact(
                &term.asset_id,
                &term.category_key,
                &term.canonical_surface_ja,
            )?,
            ClauseAtom::UnattachedExactNumber(number) => FactKind::ExactNumber(number.value),
            ClauseAtom::FunctionWord { .. }
            | ClauseAtom::SaijikiRelation { .. }
            | ClauseAtom::UnresolvedDiagnostic(_) => continue,
        };
        facts.push(Fact {
            clause_index,
            atom_index,
            span,
            source_surface,
            kind,
        });
    }
    Some(facts)
}

fn semantic_fact(
    source_asset_id: &str,
    category_key: &str,
    canonical_surface_ja: &str,
) -> Option<FactKind> {
    let projection = project_macro_semantic_ref(category_key, canonical_surface_ja)?;
    Some(FactKind::Semantic {
        category: projection.category,
        canonical_id: projection.canonical_id,
        source_asset_id: source_asset_id.to_owned(),
        canonical_surface_ja: canonical_surface_ja.to_owned(),
    })
}

fn compatible_value(schema: &ParameterSchema, fact: &Fact) -> Option<BoundMacroParameterValue> {
    match (schema, &fact.kind) {
        (ParameterSchema::Integer, FactKind::ExactNumber(value)) => {
            i64::try_from(*value)
                .ok()
                .map(|value| BoundMacroParameterValue::Integer {
                    value,
                    source_span: fact.span,
                })
        }
        (ParameterSchema::Number, FactKind::ExactNumber(value)) => {
            exact_u64_as_f64(*value).map(|value| BoundMacroParameterValue::Number {
                value,
                source_span: fact.span,
            })
        }
        (
            ParameterSchema::SemanticRef { category },
            FactKind::Semantic {
                category: fact_category,
                canonical_id,
                source_asset_id,
                canonical_surface_ja,
            },
        ) if category == fact_category => Some(BoundMacroParameterValue::SemanticRef {
            category: fact_category.clone(),
            canonical_id: canonical_id.clone(),
            source_asset_id: source_asset_id.clone(),
            canonical_surface_ja: canonical_surface_ja.clone(),
            source_span: fact.span,
        }),
        (ParameterSchema::Boolean | ParameterSchema::List { .. }, _)
        | (ParameterSchema::Integer | ParameterSchema::Number, FactKind::Semantic { .. })
        | (ParameterSchema::SemanticRef { .. }, FactKind::ExactNumber(_))
        | (ParameterSchema::SemanticRef { .. }, FactKind::Semantic { .. }) => None,
    }
}

fn exact_u64_as_f64(value: u64) -> Option<f64> {
    if value == 0 {
        return Some(0.0);
    }
    let significant_bits =
        (u64::BITS - value.leading_zeros()).saturating_sub(value.trailing_zeros());
    (significant_bits <= f64::MANTISSA_DIGITS).then_some(value as f64)
}

fn incomplete_kind(
    slots: &[Slot<'_>],
    facts: &[Fact],
    adjacency: &[Vec<usize>],
) -> MacroParameterBindingDiagnosticKind {
    for (slot, candidates) in slots.iter().zip(adjacency) {
        if !candidates.is_empty() {
            continue;
        }
        if matches!(slot.parameter_schema, ParameterSchema::Integer)
            && facts.iter().any(|fact| {
                matches!(fact.kind, FactKind::ExactNumber(value) if i64::try_from(value).is_err())
            })
        {
            return MacroParameterBindingDiagnosticKind::NumericRange;
        }
        if matches!(slot.parameter_schema, ParameterSchema::Number)
            && facts.iter().any(|fact| {
                matches!(fact.kind, FactKind::ExactNumber(value) if exact_u64_as_f64(value).is_none())
            })
        {
            return MacroParameterBindingDiagnosticKind::NumericPrecision;
        }
    }
    if adjacency.iter().any(Vec::is_empty) {
        MacroParameterBindingDiagnosticKind::MissingCompatibleFact
    } else {
        MacroParameterBindingDiagnosticKind::SharedFact
    }
}

fn perfect_matching(
    adjacency: &[Vec<usize>],
    fact_count: usize,
    excluded: Option<(usize, usize)>,
) -> Option<Vec<usize>> {
    let mut fact_to_slot = vec![None; fact_count];
    for slot_index in 0..adjacency.len() {
        let mut visited = vec![false; fact_count];
        if !augment(
            slot_index,
            adjacency,
            excluded,
            &mut visited,
            &mut fact_to_slot,
        ) {
            return None;
        }
    }
    let mut slot_to_fact = vec![usize::MAX; adjacency.len()];
    for (fact_index, slot_index) in fact_to_slot.into_iter().enumerate() {
        if let Some(slot_index) = slot_index {
            slot_to_fact[slot_index] = fact_index;
        }
    }
    slot_to_fact
        .iter()
        .all(|fact_index| *fact_index != usize::MAX)
        .then_some(slot_to_fact)
}

fn augment(
    slot_index: usize,
    adjacency: &[Vec<usize>],
    excluded: Option<(usize, usize)>,
    visited: &mut [bool],
    fact_to_slot: &mut [Option<usize>],
) -> bool {
    for &fact_index in &adjacency[slot_index] {
        if excluded == Some((slot_index, fact_index)) || visited[fact_index] {
            continue;
        }
        visited[fact_index] = true;
        if fact_to_slot[fact_index]
            .is_none_or(|owner| augment(owner, adjacency, excluded, visited, fact_to_slot))
        {
            fact_to_slot[fact_index] = Some(slot_index);
            return true;
        }
    }
    false
}

fn diagnose_clause(
    diagnostics: &mut Vec<MacroParameterBindingDiagnostic>,
    invocations: &[PreparedInvocation<'_>],
    kind: MacroParameterBindingDiagnosticKind,
) {
    for invocation in invocations {
        if invocation.definition.parameters.is_empty() {
            continue;
        }
        diagnostics.push(diagnostic(
            invocation.resolved,
            invocation.invocation_index,
            kind,
            invocation.definition.parameters.keys().cloned().collect(),
        ));
    }
}

fn diagnostic(
    resolved: &ResolvedMacroInvocation,
    invocation_index: usize,
    kind: MacroParameterBindingDiagnosticKind,
    parameter_names: Vec<String>,
) -> MacroParameterBindingDiagnostic {
    MacroParameterBindingDiagnostic {
        kind,
        invocation_index,
        invocation_ordinal: resolved.invocation.ordinal(),
        clause_index: resolved.clause_index,
        atom_index: resolved.atom_index,
        definition_identity: resolved.definition_identity.clone(),
        parameter_names,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{MacroLock, ResolvedInstructionLanguage};

    fn definition() -> MacroDefinition {
        MacroDefinition::from_json(
            r#"{"schema":"inku.macro-definition.v1","namespace":"Bind","heading":"Owned","version":"1.0.0","parameters":{},"components":{},"body":[]}"#,
        )
        .unwrap()
    }

    fn document(definition: &MacroDefinition) -> NormalizedDdlDocument {
        let identity = definition.identity().unwrap();
        NormalizedDdlDocument::new(
            "Bind.Owned",
            ResolvedInstructionLanguage::En,
            vec![
                MacroLock::new(
                    identity.qualified_name(),
                    identity.version(),
                    format!("sha256:{}", identity.full_digest_hex()),
                )
                .unwrap(),
            ],
        )
        .unwrap()
    }

    #[test]
    fn defensive_definition_and_source_ownership_diagnostics_are_stable() {
        let definition = definition();
        let document = document(&definition);
        let resolution =
            resolve_macro_invocations(&document, std::slice::from_ref(&definition)).unwrap();
        let missing_definition = build_parameter_bindings(&document, &[], resolution.clone());
        assert_eq!(missing_definition.complete.len(), 0);
        assert_eq!(
            missing_definition.diagnostics[0].kind,
            MacroParameterBindingDiagnosticKind::DefinitionIdentityOwnershipMismatch
        );

        let mut wrong_source_owner = resolution;
        wrong_source_owner.resolved[0].atom_index = usize::MAX;
        let wrong_source = build_parameter_bindings(
            &document,
            std::slice::from_ref(&definition),
            wrong_source_owner,
        );
        assert_eq!(wrong_source.complete.len(), 0);
        assert_eq!(
            wrong_source.diagnostics[0].kind,
            MacroParameterBindingDiagnosticKind::SourceClauseAtomOwnershipMismatch
        );
    }
}
