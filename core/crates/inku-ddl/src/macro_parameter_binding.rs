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
    ExactDecimal {
        value: crate::ExactDecimal,
        geometry: Option<crate::SemanticGeometryValue>,
        source_span: SourceSpan,
    },
    /// A finite core value with source provenance and no Saijiki asset origin.
    CoreModifier {
        value: crate::CoreModifierValue,
        source_span: SourceSpan,
    },
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
            Self::ExactDecimal { source_span, .. } => *source_span,
            Self::Integer { source_span, .. }
            | Self::CoreModifier { source_span, .. }
            | Self::Number { source_span, .. }
            | Self::SemanticRef { source_span, .. } => *source_span,
        }
    }
}

impl MacroParameterBinding {
    pub(crate) fn owns_span(&self, span: SourceSpan) -> bool {
        if let BoundMacroParameterValue::ExactDecimal {
            geometry: Some(value),
            ..
        } = &self.value
        {
            span == value.keyword_provenance.span
                || span == value.decimal.provenance.span
                || span == self.source_span
        } else {
            span == self.source_span
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
    ExactDecimal {
        value: crate::ExactDecimal,
        geometry: Option<crate::SemanticGeometryValue>,
        siblings: Vec<SourceSpan>,
    },
    CoreModifier(crate::CoreModifierValue),
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
        let exact_enabled = invocations.iter().any(|invocation| {
            invocation
                .definition
                .parameters
                .iter()
                .any(|(_, schema)| matches!(schema, ParameterSchema::ExactDecimal { .. }))
        });
        // Numeric geometry has no multi-head phrase owner in the accepted grammar.
        // A matching parameter type must not take a primitive's explicit source fact.
        if exact_enabled && macro_resolution.relation_reference_evidence.attachment_evidence.noun_phrase.clause_stream
            .clauses[clause_index].atoms.iter().any(|atom| matches!(atom, ClauseAtom::CoreRole(term) if term.role == crate::CoreRoleKind::Primitive)) {
            diagnose_clause(&mut diagnostics, &invocations, MacroParameterBindingDiagnosticKind::AmbiguousCompleteAssignment);
            continue;
        }
        let facts = match clause_facts(document, &macro_resolution, clause_index, exact_enabled) {
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

        // A compound source fact is transferred only when all of its dimensions belong
        // to one invocation. Never split width/height or X/Y between callers.
        let complete_compounds = matching.iter().enumerate().all(|(slot_index, fact_index)| {
            let FactKind::ExactDecimal { siblings, .. } = &facts[*fact_index].kind else {
                return true;
            };
            siblings.iter().all(|span| {
                matching.iter().enumerate().any(|(other_slot, other_fact)| {
                    slots[other_slot].invocation_index == slots[slot_index].invocation_index
                        && facts[*other_fact].span == *span
                })
            })
        });
        if !complete_compounds {
            diagnose_clause(
                &mut diagnostics,
                &invocations,
                MacroParameterBindingDiagnosticKind::MissingCompatibleFact,
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
    let written = document
        .source()
        .get(resolved.span.start_byte..resolved.span.end_byte);
    let invoked = resolved.invocation.qualified_name();
    matches!(atom, ClauseAtom::UnresolvedDiagnostic(_))
        && atom.span() == resolved.span
        && written.is_some_and(|written| {
            // The visible name is the canonical name or an alias of its lock.
            written == invoked
                || document.macro_locks().iter().any(|macro_lock| {
                    macro_lock.qualified_name() == invoked
                        && macro_lock.aliases().iter().any(|alias| alias == written)
                })
        })
}

fn clause_facts(
    document: &NormalizedDdlDocument,
    macro_resolution: &MacroInvocationLockResolutionResult,
    clause_index: usize,
    exact_enabled: bool,
) -> Option<Vec<Fact>> {
    let attachment = &macro_resolution
        .relation_reference_evidence
        .attachment_evidence;
    let topology = crate::semantic_association::ClauseTopologyEvidence::from_attachment(attachment);
    let clause = macro_resolution
        .relation_reference_evidence
        .attachment_evidence
        .noun_phrase
        .clause_stream
        .clauses
        .get(clause_index)?;
    let mut facts = Vec::new();
    let region_index = crate::semantic_association::sentence_region_index(
        &attachment.noun_phrase.clause_stream,
        clause.span,
    );
    let geometry =
        crate::geometry::analyze_clause_geometry(document, clause, clause_index, region_index);
    let mut geometry_groups = geometry
        .geometries
        .iter()
        .map(|value| match value {
            crate::SemanticExplicitGeometry::Radius(value)
            | crate::SemanticExplicitGeometry::Diameter(value)
            | crate::SemanticExplicitGeometry::Length(value)
            | crate::SemanticExplicitGeometry::Side(value) => vec![value],
            crate::SemanticExplicitGeometry::WidthHeight { width, height } => vec![width, height],
            crate::SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => {
                vec![chord, sagitta]
            }
        })
        .collect::<Vec<_>>();
    geometry_groups.extend(
        geometry
            .positions
            .iter()
            .map(|position| vec![&position.x, &position.y]),
    );
    for values in geometry_groups {
        if !exact_enabled {
            break;
        }
        let siblings = values
            .iter()
            .map(|value| SourceSpan {
                start_byte: value.keyword_provenance.span.start_byte,
                end_byte: value.decimal.provenance.span.end_byte,
            })
            .collect::<Vec<_>>();
        for (value, span) in values.into_iter().zip(&siblings) {
            facts.push(Fact {
                clause_index,
                atom_index: value.keyword_provenance.atom_index,
                span: *span,
                source_surface: document
                    .source()
                    .get(span.start_byte..span.end_byte)?
                    .to_owned(),
                kind: FactKind::ExactDecimal {
                    value: value.decimal.value,
                    geometry: Some(value.clone()),
                    siblings: siblings.clone(),
                },
            });
        }
    }
    let primitive_owned = crate::semantic_association::primitive_phrase_modifier_starts(
        &macro_resolution
            .relation_reference_evidence
            .attachment_evidence,
    );
    for (atom_index, atom) in clause.atoms.iter().enumerate() {
        let span = atom.span();
        if exact_enabled
            && geometry
                .consumed_numeric_spans
                .contains(&(span.start_byte, span.end_byte))
        {
            continue;
        }
        if !(clause.span.start_byte <= span.start_byte && span.end_byte <= clause.span.end_byte) {
            return None;
        }
        let source_surface = document
            .source()
            .get(span.start_byte..span.end_byte)?
            .to_owned();
        let kind = match atom {
            ClauseAtom::FunctionWord {
                exact_decimal: Some(value),
                ..
            } if exact_enabled => FactKind::ExactDecimal {
                value: *value,
                geometry: None,
                siblings: Vec::new(),
            },
            // One constrained head cannot be consumed as an unconstrained shape ref.
            // Callers bind the independently declared form/sides facts explicitly.
            ClauseAtom::CoreRole(term) if term.shape_constraint.is_some() => continue,
            ClauseAtom::CoreRole(term) => semantic_fact(
                &term.asset_id,
                &term.category_key,
                &term.canonical_surface_ja,
            )?,
            ClauseAtom::RemainingRole(term)
                if crate::semantic_association::is_layout_direction(
                    document,
                    &attachment.noun_phrase.clause_stream,
                    &topology,
                    term,
                ) =>
            {
                continue;
            }
            ClauseAtom::RemainingRole(term) => semantic_fact(
                &term.asset_id,
                &term.category_key,
                &term.canonical_surface_ja,
            )?,
            ClauseAtom::UnattachedExactNumber(number) => FactKind::ExactNumber(number.value),
            ClauseAtom::CoreModifier(modifier) => {
                if primitive_owned.contains(&span.start_byte) {
                    continue;
                }
                if modifier.identity.dimension != modifier.identity.value.dimension() {
                    return None;
                }
                FactKind::CoreModifier(modifier.identity.value)
            }
            ClauseAtom::GrammarMarker { .. }
            | ClauseAtom::FunctionWord { .. }
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
        (
            ParameterSchema::ExactDecimal { dimension },
            FactKind::ExactDecimal {
                value, geometry, ..
            },
        ) if *dimension
            == geometry
                .as_ref()
                .and_then(|value| crate::ExactDecimalDimension::from_keyword(value.keyword)) =>
        {
            Some(BoundMacroParameterValue::ExactDecimal {
                value: *value,
                geometry: geometry.clone(),
                source_span: fact.span,
            })
        }
        (ParameterSchema::ExactDecimal { dimension: None }, FactKind::ExactNumber(value)) => {
            Some(BoundMacroParameterValue::ExactDecimal {
                value: crate::ExactDecimal::from_u64(*value),
                geometry: None,
                source_span: fact.span,
            })
        }
        (
            ParameterSchema::Integer,
            FactKind::CoreModifier(crate::CoreModifierValue::Sides(value)),
        ) => i64::try_from(*value)
            .ok()
            .map(|value| BoundMacroParameterValue::Integer {
                value,
                source_span: fact.span,
            }),
        (
            ParameterSchema::SemanticRef {
                category,
                dimension: None,
            },
            FactKind::CoreModifier(value),
        ) if category == value.dimension().as_str() => {
            Some(BoundMacroParameterValue::CoreModifier {
                value: *value,
                source_span: fact.span,
            })
        }
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
            ParameterSchema::SemanticRef {
                category,
                dimension,
            },
            FactKind::Semantic {
                category: fact_category,
                canonical_id,
                source_asset_id,
                canonical_surface_ja,
            },
        ) if category == fact_category
            && crate::fluctuation::matches_dimension(category, canonical_id, *dimension) =>
        {
            Some(BoundMacroParameterValue::SemanticRef {
                category: fact_category.clone(),
                canonical_id: canonical_id.clone(),
                source_asset_id: source_asset_id.clone(),
                canonical_surface_ja: canonical_surface_ja.clone(),
                source_span: fact.span,
            })
        }
        _ => None,
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
