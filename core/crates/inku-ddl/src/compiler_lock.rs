//! Runtime-disconnected typed delivery, canonical compiler identity, and lock construction.

use std::collections::BTreeMap;

use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};

use crate::{
    AttachmentMarkerKind, BoundMacroParameterValue, ClauseAtom, CompleteMacroParameterBinding,
    EnglishAttachmentMarkerKind, ExpandedMacroNode, ExpandedMacroValue, ExpansionPathSegment,
    JapaneseAttachmentMarkerKind, MacroDefinition, MacroExpansionDiagnosticKind,
    MacroExpansionLimits, MacroExpansionResult, MacroInvocationResolutionDiagnosticKind,
    MacroParameterBindingDiagnosticKind, MacroParameterBindingResult, MacroSeed,
    NeutralDiagnosticKind, NormalizedDdlDocument, RelationReferenceEvidenceAvailability,
    RelationReferenceOccurrenceKind, SourceSpan, bind_macro_parameters, derive_macro_seed,
    expand_macros, project_macro_semantic_ref,
};

/// Stable identity for the compilation envelope.
pub const TYPED_DDL_COMPILATION_SCHEMA_ID: &str = "inku.typed-ddl-compilation.v1";
/// Stable identity for source-independent pre-expansion semantic bytes.
pub const CANONICAL_SEMANTIC_DDL_SCHEMA_ID: &str = "inku.canonical-semantic-ddl.v1";
/// Stable identity for compiler locks.
pub const TYPED_DDL_COMPILER_LOCK_SCHEMA_ID: &str = "inku.typed-ddl-compiler-lock.v1";
/// ASCII domain prefix for the fully framed compiler lock digest.
pub const COMPILER_LOCK_DIGEST_DOMAIN: &[u8] = b"inku.typed-ddl-compiler-lock.v1";

/// Closed compiler state. This is not a Score-readiness decision.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CompilerLockState {
    CanonicalReady,
    IncompleteKnownHole,
    BlockedConflict,
    BlockedDiagnostic,
}

impl CompilerLockState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::CanonicalReady => "canonical_ready",
            Self::IncompleteKnownHole => "incomplete_known_hole",
            Self::BlockedConflict => "blocked_conflict",
            Self::BlockedDiagnostic => "blocked_diagnostic",
        }
    }
}

/// Exhaustive delivery buckets for recognized and syntax-only occurrences.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticDeliveryKind {
    Explicit,
    Unspecified,
    Defaulted,
    Hole,
    Conflict,
    BlockingDiagnostic,
    SyntaxOnly,
}

impl SemanticDeliveryKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Explicit => "explicit",
            Self::Unspecified => "unspecified",
            Self::Defaulted => "defaulted",
            Self::Hole => "hole",
            Self::Conflict => "conflict",
            Self::BlockingDiagnostic => "blocking_diagnostic",
            Self::SyntaxOnly => "syntax_only",
        }
    }
}

/// One exactly-once classified source or expansion occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticDelivery {
    pub id: String,
    pub kind: SemanticDeliveryKind,
    pub descriptor: String,
    pub span: Option<SourceSpan>,
    pub source_independent: bool,
}

/// Counts kept separately so syntax consumption cannot inflate semantic delivery.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct DeliverySummary {
    pub explicit: usize,
    pub unspecified: usize,
    pub defaulted: usize,
    pub holes: usize,
    pub conflicts: usize,
    pub blocking_diagnostics: usize,
    pub syntax_only: usize,
    pub recognized_but_ignored: usize,
}

impl DeliverySummary {
    fn add(&mut self, kind: SemanticDeliveryKind) {
        match kind {
            SemanticDeliveryKind::Explicit => self.explicit += 1,
            SemanticDeliveryKind::Unspecified => self.unspecified += 1,
            SemanticDeliveryKind::Defaulted => self.defaulted += 1,
            SemanticDeliveryKind::Hole => self.holes += 1,
            SemanticDeliveryKind::Conflict => self.conflicts += 1,
            SemanticDeliveryKind::BlockingDiagnostic => self.blocking_diagnostics += 1,
            SemanticDeliveryKind::SyntaxOnly => self.syntax_only += 1,
        }
    }
}

/// A patchable known hole locked to one exact source range.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedHole {
    pub id: String,
    pub kind: String,
    pub span: SourceSpan,
    pub allowed_span: SourceSpan,
    pub expected_range_digest: String,
    pub candidate_identity: String,
    pub upstream_diagnostic_identity: String,
}

/// A non-patchable incompatible or multiple-candidate outcome.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompilerConflict {
    pub id: String,
    pub kind: String,
    pub span: Option<SourceSpan>,
    pub candidate_identities: Vec<String>,
}

/// A non-patchable unknown or integrity/ownership failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompilerBlockingDiagnostic {
    pub id: String,
    pub kind: String,
    pub span: Option<SourceSpan>,
}

/// Sidecar and resolved definition identity retained separately from semantic meaning.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompilerDefinitionIdentity {
    pub qualified_name: String,
    pub version: String,
    pub sidecar_digest: String,
    pub resolved_definition_digest: Option<String>,
}

/// One exact I-533 seed identity.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompilerSeedIdentity {
    pub qualified_name: String,
    pub ordinal: u64,
    pub scheme_id: &'static str,
    pub full_digest: String,
    pub resolved_seed: u64,
}

/// Complete deterministic identity for one integrity-valid compilation attempt.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedDdlCompilerLock {
    pub schema_id: &'static str,
    pub state: CompilerLockState,
    pub visible_source_digest: String,
    pub explicit_fact_digest: String,
    pub canonical_pre_expansion_digest: Option<String>,
    pub composition_seed: Option<u64>,
    pub definition_identities: Vec<CompilerDefinitionIdentity>,
    pub macro_seeds: Vec<CompilerSeedIdentity>,
    pub expanded_meaning_digest: Option<String>,
    pub hole_identities: Vec<String>,
    pub conflict_identities: Vec<String>,
    pub blocking_diagnostic_identities: Vec<String>,
    pub full_digest: String,
}

/// One source-preserving compilation result. Exactly one accepted binding result is owned,
/// either directly or through the I-582 result that consumed it.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedDdlCompilation {
    pub schema_id: &'static str,
    pub document: NormalizedDdlDocument,
    pub deliveries: Vec<SemanticDelivery>,
    pub delivery_summary: DeliverySummary,
    pub holes: Vec<TypedHole>,
    pub conflicts: Vec<CompilerConflict>,
    pub blocking_diagnostics: Vec<CompilerBlockingDiagnostic>,
    pub canonical_semantic_bytes: Option<Vec<u8>>,
    pub derived_seeds: Vec<MacroSeed>,
    pub parameter_binding: Option<MacroParameterBindingResult>,
    pub macro_expansion: Option<MacroExpansionResult>,
    pub compiler_lock: Option<TypedDdlCompilerLock>,
}

impl TypedDdlCompilation {
    /// The exact accepted I-581 result, regardless of whether I-582 was reached.
    pub fn accepted_parameter_binding(&self) -> Option<&MacroParameterBindingResult> {
        self.parameter_binding.as_ref().or_else(|| {
            self.macro_expansion
                .as_ref()
                .map(|expansion| &expansion.parameter_binding)
        })
    }

    /// Source-independent fingerprints used by constrained patch validation.
    pub fn explicit_fingerprints(&self) -> Vec<(SourceSpan, String)> {
        self.deliveries
            .iter()
            .filter_map(|delivery| {
                (delivery.kind == SemanticDeliveryKind::Explicit)
                    .then_some(
                        delivery
                            .span
                            .map(|span| (span, delivery.descriptor.clone())),
                    )
                    .flatten()
            })
            .collect()
    }
}

#[derive(Default)]
struct Projection {
    deliveries: Vec<SemanticDelivery>,
    holes: Vec<TypedHole>,
    conflicts: Vec<CompilerConflict>,
    blocking: Vec<CompilerBlockingDiagnostic>,
    facts: Vec<Value>,
    source_independent: bool,
}

/// Compile one source-preserving document without selecting defaults, targets, Score, or runtime
/// behavior. I-581 and, when eligible, I-582 are each invoked exactly once.
pub fn compile_typed_ddl(
    document: NormalizedDdlDocument,
    definitions: &[MacroDefinition],
    composition_seed: Option<u64>,
    limits: MacroExpansionLimits,
) -> TypedDdlCompilation {
    if !valid_limits(limits) {
        return integrity_failure(document, "invalid_expansion_limits");
    }

    let parameter_binding = match bind_macro_parameters(&document, definitions) {
        Ok(binding) => binding,
        Err(_) => return integrity_failure(document, "clause_stream_integrity"),
    };
    let mut projection = project_deliveries(&document, &parameter_binding);
    sort_projection(&mut projection);

    let explicit_bytes = canonical_bytes(CANONICAL_SEMANTIC_DDL_SCHEMA_ID, &projection.facts, &[]);
    let explicit_fact_digest = sha256_hex(&explicit_bytes);
    let canonical_semantic_bytes = if projection.source_independent
        && projection.conflicts.is_empty()
        && projection.blocking.is_empty()
    {
        let holes = projection
            .holes
            .iter()
            .map(|hole| {
                string_record(&[
                    ("candidate", hole.candidate_identity.as_str()),
                    ("kind", hole.kind.as_str()),
                ])
            })
            .collect::<Vec<_>>();
        Some(canonical_bytes(
            CANONICAL_SEMANTIC_DDL_SCHEMA_ID,
            &projection.facts,
            &holes,
        ))
    } else {
        None
    };

    let source_independent_projection = projection.conflicts.is_empty()
        && projection.blocking.is_empty()
        && canonical_semantic_bytes.is_some();
    let mut seeds = Vec::new();
    let mut expansion = None;
    let mut retained_binding = Some(parameter_binding);

    if source_independent_projection {
        let canonical = String::from_utf8(
            canonical_semantic_bytes
                .as_ref()
                .expect("ready projection has canonical UTF-8")
                .clone(),
        )
        .expect("serde_json emits UTF-8");
        let binding = retained_binding
            .take()
            .expect("binding is owned exactly once");
        for complete in &binding.complete {
            let resolved = &binding.macro_resolution.resolved[complete.invocation_index];
            seeds.push(derive_macro_seed(
                &canonical,
                &resolved.invocation,
                composition_seed,
            ));
        }
        let expanded = expand_macros(binding, definitions, &seeds, limits);
        project_expansion_diagnostics(&document, &expanded, &mut projection);
        project_expanded_deliveries(&expanded, &mut projection);
        expansion = Some(expanded);
        sort_projection(&mut projection);
    }

    let state = compiler_state(&projection);
    let expanded_digest = if state == CompilerLockState::CanonicalReady {
        expansion
            .as_ref()
            .map(|value| sha256_hex(&expanded_meaning_canonical_bytes(value)))
    } else {
        None
    };
    let lock = build_lock(
        &document,
        definitions,
        composition_seed,
        &projection,
        explicit_fact_digest,
        canonical_semantic_bytes.as_deref(),
        &seeds,
        expanded_digest,
        state,
    );
    let summary = summarize(&projection.deliveries);

    TypedDdlCompilation {
        schema_id: TYPED_DDL_COMPILATION_SCHEMA_ID,
        document,
        deliveries: projection.deliveries,
        delivery_summary: summary,
        holes: projection.holes,
        conflicts: projection.conflicts,
        blocking_diagnostics: projection.blocking,
        canonical_semantic_bytes,
        derived_seeds: seeds,
        parameter_binding: retained_binding,
        macro_expansion: expansion,
        compiler_lock: Some(lock),
    }
}

fn integrity_failure(document: NormalizedDdlDocument, kind: &str) -> TypedDdlCompilation {
    let diagnostic = CompilerBlockingDiagnostic {
        id: identity("blocking", kind.as_bytes()),
        kind: kind.to_owned(),
        span: None,
    };
    let delivery = SemanticDelivery {
        id: diagnostic.id.clone(),
        kind: SemanticDeliveryKind::BlockingDiagnostic,
        descriptor: kind.to_owned(),
        span: None,
        source_independent: false,
    };
    TypedDdlCompilation {
        schema_id: TYPED_DDL_COMPILATION_SCHEMA_ID,
        document,
        deliveries: vec![delivery],
        delivery_summary: DeliverySummary {
            blocking_diagnostics: 1,
            ..DeliverySummary::default()
        },
        holes: Vec::new(),
        conflicts: Vec::new(),
        blocking_diagnostics: vec![diagnostic],
        canonical_semantic_bytes: None,
        derived_seeds: Vec::new(),
        parameter_binding: None,
        macro_expansion: None,
        compiler_lock: None,
    }
}

fn project_deliveries(
    document: &NormalizedDdlDocument,
    binding: &MacroParameterBindingResult,
) -> Projection {
    let mut projection = Projection {
        source_independent: true,
        ..Projection::default()
    };
    let relation = &binding.macro_resolution.relation_reference_evidence;
    let stream = &relation.attachment_evidence.noun_phrase.clause_stream;
    let relation_spans = relation
        .evidence
        .iter()
        .map(|item| item.occurrence.span)
        .chain(relation.diagnostics.iter().map(|item| item.occurrence.span))
        .collect::<Vec<_>>();
    let macro_spans = binding
        .macro_resolution
        .resolved
        .iter()
        .map(|item| item.span)
        .chain(
            binding
                .macro_resolution
                .diagnostics
                .iter()
                .map(|item| item.span),
        )
        .collect::<Vec<_>>();

    for evidence in &relation.evidence {
        let occurrence = relation_occurrence_descriptor(&evidence.occurrence.kind);
        let candidates = evidence
            .candidate_atom_indices
            .iter()
            .map(|index| atom_descriptor(&stream.clauses[evidence.clause_index].atoms[*index]))
            .collect::<Vec<_>>();
        let descriptor = format!(
            "relation|clause={}|occurrence={}|candidates={}",
            evidence.clause_index,
            occurrence,
            candidates.join(",")
        );
        match evidence.availability {
            RelationReferenceEvidenceAvailability::Zero => add_hole(
                document,
                &mut projection,
                "missing_relation_target",
                evidence.occurrence.span,
                format!("{occurrence}:missing-target"),
                "i579:zero".to_owned(),
            ),
            RelationReferenceEvidenceAvailability::ExactOne => {
                add_explicit(
                    &mut projection,
                    evidence.occurrence.span,
                    descriptor.clone(),
                );
                projection.facts.push(string_record(&[
                    ("association", candidates[0].as_str()),
                    ("clause", &evidence.clause_index.to_string()),
                    ("kind", "relation"),
                    ("occurrence", occurrence.as_str()),
                ]));
            }
            RelationReferenceEvidenceAvailability::Multiple => add_conflict(
                &mut projection,
                "multiple_relation_targets",
                Some(evidence.occurrence.span),
                candidates,
            ),
        }
    }
    for diagnostic in &relation.diagnostics {
        add_blocking(
            &mut projection,
            "relation_evidence_integrity",
            Some(diagnostic.occurrence.span),
        );
    }

    for (clause_index, clause) in stream.clauses.iter().enumerate() {
        for atom in &clause.atoms {
            let span = atom.span();
            if relation_spans.contains(&span) || macro_spans.contains(&span) {
                continue;
            }
            match atom {
                ClauseAtom::CoreRole(term) => {
                    let descriptor = format!(
                        "role|clause={clause_index}|role={}|id={}",
                        core_role_name(term.role),
                        canonical_asset_id(&term.category_key, &term.canonical_surface_ja)
                    );
                    add_explicit(&mut projection, span, descriptor);
                    projection.facts.push(string_record(&[
                        ("clause", &clause_index.to_string()),
                        (
                            "id",
                            canonical_asset_id(&term.category_key, &term.canonical_surface_ja)
                                .as_str(),
                        ),
                        ("kind", "role"),
                        ("role", core_role_name(term.role)),
                    ]));
                }
                ClauseAtom::RemainingRole(term) => {
                    let descriptor = format!(
                        "role|clause={clause_index}|role={}|id={}",
                        remaining_role_name(term.role),
                        canonical_asset_id(&term.category_key, &term.canonical_surface_ja)
                    );
                    add_explicit(&mut projection, span, descriptor);
                    projection.facts.push(string_record(&[
                        ("clause", &clause_index.to_string()),
                        (
                            "id",
                            canonical_asset_id(&term.category_key, &term.canonical_surface_ja)
                                .as_str(),
                        ),
                        ("kind", "role"),
                        ("role", remaining_role_name(term.role)),
                    ]));
                }
                ClauseAtom::UnattachedExactNumber(number) => {
                    let descriptor = format!("number|clause={clause_index}|value={}", number.value);
                    add_explicit(&mut projection, span, descriptor);
                    projection
                        .facts
                        .push(number_record(clause_index, number.value));
                }
                ClauseAtom::FunctionWord { .. } => {
                    add_syntax(&mut projection, span, "function_word")
                }
                ClauseAtom::SaijikiRelation { .. } => {
                    add_blocking(&mut projection, "unaccounted_relation", Some(span));
                }
                ClauseAtom::UnresolvedDiagnostic(diagnostic) => match diagnostic.kind {
                    NeutralDiagnosticKind::Hole if diagnostic.recognized => add_hole(
                        document,
                        &mut projection,
                        "unresolved_value",
                        span,
                        "known-value".to_owned(),
                        "parser:hole".to_owned(),
                    ),
                    NeutralDiagnosticKind::Conflict if diagnostic.recognized => {
                        add_conflict(&mut projection, "parser_conflict", Some(span), Vec::new())
                    }
                    _ => add_blocking(&mut projection, "unknown_source", Some(span)),
                },
            }
        }
    }

    for resolved in &binding.macro_resolution.resolved {
        let complete = binding.complete.iter().find(|item| {
            item.invocation_index < binding.macro_resolution.resolved.len()
                && binding.macro_resolution.resolved[item.invocation_index]
                    .invocation
                    .ordinal()
                    == resolved.invocation.ordinal()
        });
        if let Some(complete) = complete {
            let descriptor = binding_descriptor(complete);
            add_explicit(&mut projection, resolved.span, descriptor.clone());
            projection.facts.push(binding_record(complete));
        }
    }

    for diagnostic in &binding.macro_resolution.diagnostics {
        let kind = macro_resolution_kind(diagnostic.kind);
        match diagnostic.kind {
            MacroInvocationResolutionDiagnosticKind::MissingLock
            | MacroInvocationResolutionDiagnosticKind::MissingDefinition
            | MacroInvocationResolutionDiagnosticKind::InvalidDefinition => add_hole(
                document,
                &mut projection,
                kind,
                diagnostic.span,
                diagnostic
                    .invocation
                    .as_ref()
                    .map(|value| value.qualified_name())
                    .unwrap_or_else(|| "unresolved-macro".to_owned()),
                format!("i580:{kind}"),
            ),
            MacroInvocationResolutionDiagnosticKind::AmbiguousLockPrefix
            | MacroInvocationResolutionDiagnosticKind::DuplicateMatchingDefinition => add_conflict(
                &mut projection,
                kind,
                Some(diagnostic.span),
                diagnostic
                    .matching_locks
                    .iter()
                    .map(|item| format!("{}@{}#{}", item.qualified_name, item.version, item.digest))
                    .collect(),
            ),
            MacroInvocationResolutionDiagnosticKind::QualifiedNameMismatch
            | MacroInvocationResolutionDiagnosticKind::VersionMismatch
            | MacroInvocationResolutionDiagnosticKind::DigestMismatch
            | MacroInvocationResolutionDiagnosticKind::SourceClauseAtomMismatch => {
                add_blocking(&mut projection, kind, Some(diagnostic.span));
            }
        }
    }

    for diagnostic in &binding.diagnostics {
        let resolved = binding
            .macro_resolution
            .resolved
            .get(diagnostic.invocation_index);
        let span = resolved.map(|item| item.span);
        let kind = macro_binding_kind(diagnostic.kind);
        match diagnostic.kind {
            MacroParameterBindingDiagnosticKind::MissingCompatibleFact
            | MacroParameterBindingDiagnosticKind::UnsupportedSchema
            | MacroParameterBindingDiagnosticKind::NumericRange
            | MacroParameterBindingDiagnosticKind::NumericPrecision => {
                if let Some(span) = span {
                    add_hole(
                        document,
                        &mut projection,
                        kind,
                        span,
                        format!(
                            "{}:{}",
                            diagnostic.definition_identity.qualified_name(),
                            diagnostic.parameter_names.join(",")
                        ),
                        format!("i581:{kind}"),
                    );
                } else {
                    add_blocking(&mut projection, "binding_missing_invocation", None);
                }
            }
            MacroParameterBindingDiagnosticKind::AmbiguousCompleteAssignment
            | MacroParameterBindingDiagnosticKind::SharedFact => add_conflict(
                &mut projection,
                kind,
                span,
                diagnostic.parameter_names.clone(),
            ),
            MacroParameterBindingDiagnosticKind::DefinitionIdentityOwnershipMismatch
            | MacroParameterBindingDiagnosticKind::SourceClauseAtomOwnershipMismatch => {
                add_blocking(&mut projection, kind, span);
            }
        }
    }

    projection
}

fn project_expansion_diagnostics(
    document: &NormalizedDdlDocument,
    expansion: &MacroExpansionResult,
    projection: &mut Projection,
) {
    for diagnostic in &expansion.diagnostics {
        let span = diagnostic.invocation_index.and_then(|index| {
            expansion
                .parameter_binding
                .macro_resolution
                .resolved
                .get(index)
                .map(|item| item.span)
        });
        let kind = macro_expansion_kind(diagnostic.kind);
        match diagnostic.kind {
            MacroExpansionDiagnosticKind::ExpressionMismatch
            | MacroExpansionDiagnosticKind::ComponentMismatch
            | MacroExpansionDiagnosticKind::RepeatCountInvalid
            | MacroExpansionDiagnosticKind::RepeatMaximumExceeded
            | MacroExpansionDiagnosticKind::NumericRange
            | MacroExpansionDiagnosticKind::DepthBudget
            | MacroExpansionDiagnosticKind::EvaluationStepBudget
            | MacroExpansionDiagnosticKind::NodeBudget
            | MacroExpansionDiagnosticKind::InvocationBudget
            | MacroExpansionDiagnosticKind::TotalNodeBudget => {
                if let Some(span) = span {
                    add_hole(
                        document,
                        projection,
                        kind,
                        span,
                        format!(
                            "expansion:{}",
                            compact_json(&Value::Array(
                                diagnostic.expansion_path.iter().map(path_value).collect()
                            ))
                        ),
                        format!("i582:{kind}"),
                    );
                } else {
                    add_blocking(projection, kind, None);
                }
            }
            MacroExpansionDiagnosticKind::InvalidLimits
            | MacroExpansionDiagnosticKind::MissingSeed
            | MacroExpansionDiagnosticKind::DuplicateSeed
            | MacroExpansionDiagnosticKind::MismatchedSeed
            | MacroExpansionDiagnosticKind::DefinitionOwnershipMismatch
            | MacroExpansionDiagnosticKind::BindingOwnershipMismatch
            | MacroExpansionDiagnosticKind::TargetOwnershipMismatch
            | MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch => {
                add_blocking(projection, kind, span);
            }
        }
    }
}

fn project_expanded_deliveries(expansion: &MacroExpansionResult, projection: &mut Projection) {
    for invocation in &expansion.expanded {
        for node in flatten_nodes(&invocation.nodes) {
            let descriptor = compact_json(&node_value(node));
            let provenance = node.provenance();
            let mut identity_bytes = Vec::new();
            append_field(
                &mut identity_bytes,
                &provenance.invocation.invocation_ordinal.to_be_bytes(),
            );
            append_field(
                &mut identity_bytes,
                &provenance.generated_ordinal.to_be_bytes(),
            );
            append_field(
                &mut identity_bytes,
                compact_json(&Value::Array(
                    provenance.expansion_path.iter().map(path_value).collect(),
                ))
                .as_bytes(),
            );
            append_field(&mut identity_bytes, descriptor.as_bytes());
            projection.deliveries.push(SemanticDelivery {
                id: identity("expanded", &identity_bytes),
                kind: SemanticDeliveryKind::Explicit,
                descriptor,
                span: Some(provenance.invocation.source_span),
                source_independent: true,
            });
        }
    }
}

fn flatten_nodes(nodes: &[ExpandedMacroNode]) -> Vec<&ExpandedMacroNode> {
    let mut flattened = Vec::new();
    for node in nodes {
        flattened.push(node);
        match node {
            ExpandedMacroNode::Group { body, .. } | ExpandedMacroNode::Transform { body, .. } => {
                flattened.extend(flatten_nodes(body))
            }
            ExpandedMacroNode::Emit { .. }
            | ExpandedMacroNode::Anchor { .. }
            | ExpandedMacroNode::Relation { .. } => {}
        }
    }
    flattened
}

fn add_explicit(projection: &mut Projection, span: SourceSpan, descriptor: String) {
    projection.deliveries.push(SemanticDelivery {
        id: ranged_identity("explicit", &descriptor, span, ""),
        kind: SemanticDeliveryKind::Explicit,
        descriptor,
        span: Some(span),
        source_independent: true,
    });
}

fn add_syntax(projection: &mut Projection, span: SourceSpan, descriptor: &str) {
    projection.deliveries.push(SemanticDelivery {
        id: ranged_identity("syntax", descriptor, span, ""),
        kind: SemanticDeliveryKind::SyntaxOnly,
        descriptor: descriptor.to_owned(),
        span: Some(span),
        source_independent: false,
    });
}

fn add_hole(
    document: &NormalizedDdlDocument,
    projection: &mut Projection,
    kind: &str,
    span: SourceSpan,
    candidate_identity: String,
    upstream: String,
) {
    let range = document
        .source()
        .get(span.start_byte..span.end_byte)
        .unwrap_or_default();
    let range_digest = sha256_hex(range.as_bytes());
    let id = ranged_identity("hole", kind, span, &range_digest);
    projection.holes.push(TypedHole {
        id: id.clone(),
        kind: kind.to_owned(),
        span,
        allowed_span: span,
        expected_range_digest: range_digest,
        candidate_identity: candidate_identity.clone(),
        upstream_diagnostic_identity: upstream,
    });
    projection.deliveries.push(SemanticDelivery {
        id,
        kind: SemanticDeliveryKind::Hole,
        descriptor: format!("{kind}|candidate={candidate_identity}"),
        span: Some(span),
        source_independent: true,
    });
}

fn add_conflict(
    projection: &mut Projection,
    kind: &str,
    span: Option<SourceSpan>,
    mut candidates: Vec<String>,
) {
    candidates.sort();
    let payload = format!("{kind}|{}", candidates.join(","));
    let id = span.map_or_else(
        || identity("conflict", payload.as_bytes()),
        |span| ranged_identity("conflict", kind, span, &payload),
    );
    projection.conflicts.push(CompilerConflict {
        id: id.clone(),
        kind: kind.to_owned(),
        span,
        candidate_identities: candidates,
    });
    projection.deliveries.push(SemanticDelivery {
        id,
        kind: SemanticDeliveryKind::Conflict,
        descriptor: payload,
        span,
        source_independent: true,
    });
}

fn add_blocking(projection: &mut Projection, kind: &str, span: Option<SourceSpan>) {
    let id = span.map_or_else(
        || identity("blocking", kind.as_bytes()),
        |span| ranged_identity("blocking", kind, span, ""),
    );
    projection.blocking.push(CompilerBlockingDiagnostic {
        id: id.clone(),
        kind: kind.to_owned(),
        span,
    });
    projection.deliveries.push(SemanticDelivery {
        id,
        kind: SemanticDeliveryKind::BlockingDiagnostic,
        descriptor: kind.to_owned(),
        span,
        source_independent: false,
    });
    projection.source_independent = false;
}

fn sort_projection(projection: &mut Projection) {
    projection.deliveries.sort_by_key(|item| {
        let span = item.span.unwrap_or(SourceSpan {
            start_byte: usize::MAX,
            end_byte: usize::MAX,
        });
        (
            span.start_byte,
            span.end_byte,
            item.kind.as_str(),
            item.id.clone(),
        )
    });
    projection
        .holes
        .sort_by(|left, right| left.id.cmp(&right.id));
    projection
        .conflicts
        .sort_by(|left, right| left.id.cmp(&right.id));
    projection
        .blocking
        .sort_by(|left, right| left.id.cmp(&right.id));
    projection.facts.sort_by_key(compact_json);
}

fn summarize(deliveries: &[SemanticDelivery]) -> DeliverySummary {
    let mut summary = DeliverySummary::default();
    for delivery in deliveries {
        summary.add(delivery.kind);
    }
    summary
}

fn compiler_state(projection: &Projection) -> CompilerLockState {
    if !projection.blocking.is_empty() {
        CompilerLockState::BlockedDiagnostic
    } else if !projection.conflicts.is_empty() {
        CompilerLockState::BlockedConflict
    } else if !projection.holes.is_empty() {
        CompilerLockState::IncompleteKnownHole
    } else {
        CompilerLockState::CanonicalReady
    }
}

#[allow(clippy::too_many_arguments)]
fn build_lock(
    document: &NormalizedDdlDocument,
    definitions: &[MacroDefinition],
    composition_seed: Option<u64>,
    projection: &Projection,
    explicit_fact_digest: String,
    canonical_bytes: Option<&[u8]>,
    seeds: &[MacroSeed],
    expanded_meaning_digest: Option<String>,
    state: CompilerLockState,
) -> TypedDdlCompilerLock {
    let ready = state == CompilerLockState::CanonicalReady;
    let canonical_pre_expansion_digest =
        ready.then(|| sha256_hex(canonical_bytes.expect("ready lock has canonical bytes")));
    let definition_identities = if ready {
        definition_identities(document, definitions)
    } else {
        Vec::new()
    };
    let macro_seeds = if ready {
        seeds
            .iter()
            .map(|seed| CompilerSeedIdentity {
                qualified_name: seed.qualified_macro_name().to_owned(),
                ordinal: seed.ordinal(),
                scheme_id: seed.scheme_id(),
                full_digest: seed.full_digest_hex().to_owned(),
                resolved_seed: seed.resolved_seed(),
            })
            .collect()
    } else {
        Vec::new()
    };
    let mut lock = TypedDdlCompilerLock {
        schema_id: TYPED_DDL_COMPILER_LOCK_SCHEMA_ID,
        state,
        visible_source_digest: sha256_hex(document.source().as_bytes()),
        explicit_fact_digest,
        canonical_pre_expansion_digest,
        composition_seed: ready.then_some(composition_seed.unwrap_or(0)),
        definition_identities,
        macro_seeds,
        expanded_meaning_digest: ready.then_some(expanded_meaning_digest).flatten(),
        hole_identities: projection
            .holes
            .iter()
            .map(|item| item.id.clone())
            .collect(),
        conflict_identities: projection
            .conflicts
            .iter()
            .map(|item| item.id.clone())
            .collect(),
        blocking_diagnostic_identities: projection
            .blocking
            .iter()
            .map(|item| item.id.clone())
            .collect(),
        full_digest: String::new(),
    };
    lock.full_digest = sha256_hex(&compiler_lock_hash_input(&lock));
    lock
}

/// Exact fixed-order, length-framed bytes hashed for the full compiler lock.
pub fn compiler_lock_hash_input(lock: &TypedDdlCompilerLock) -> Vec<u8> {
    let mut bytes = COMPILER_LOCK_DIGEST_DOMAIN.to_vec();
    append_field(&mut bytes, lock.schema_id.as_bytes());
    append_field(&mut bytes, lock.state.as_str().as_bytes());
    append_field(&mut bytes, lock.visible_source_digest.as_bytes());
    append_field(&mut bytes, lock.explicit_fact_digest.as_bytes());
    append_optional(&mut bytes, lock.canonical_pre_expansion_digest.as_deref());
    match lock.composition_seed {
        Some(seed) => {
            append_field(&mut bytes, b"present");
            append_field(&mut bytes, &seed.to_be_bytes());
        }
        None => append_field(&mut bytes, b"absent"),
    }
    append_field(
        &mut bytes,
        &definition_identity_bytes(&lock.definition_identities),
    );
    append_field(&mut bytes, &seed_identity_bytes(&lock.macro_seeds));
    append_optional(&mut bytes, lock.expanded_meaning_digest.as_deref());
    append_strings(&mut bytes, &lock.hole_identities);
    append_strings(&mut bytes, &lock.conflict_identities);
    append_strings(&mut bytes, &lock.blocking_diagnostic_identities);
    bytes
}

fn definition_identities(
    document: &NormalizedDdlDocument,
    definitions: &[MacroDefinition],
) -> Vec<CompilerDefinitionIdentity> {
    document
        .macro_locks()
        .iter()
        .map(|sidecar| CompilerDefinitionIdentity {
            qualified_name: sidecar.qualified_name().to_owned(),
            version: sidecar.version().to_owned(),
            sidecar_digest: sidecar.digest().to_owned(),
            resolved_definition_digest: definitions
                .iter()
                .filter_map(|definition| definition.identity().ok())
                .find(|identity| {
                    identity.qualified_name() == sidecar.qualified_name()
                        && identity.version() == sidecar.version()
                        && format!("sha256:{}", identity.full_digest_hex()) == sidecar.digest()
                })
                .map(|identity| identity.full_digest_hex().to_owned()),
        })
        .collect()
}

fn canonical_bytes(schema: &str, facts: &[Value], holes: &[Value]) -> Vec<u8> {
    let mut root = BTreeMap::new();
    root.insert("facts".to_owned(), Value::Array(facts.to_vec()));
    root.insert("holes".to_owned(), Value::Array(holes.to_vec()));
    root.insert("schema".to_owned(), Value::String(schema.to_owned()));
    serde_json::to_vec(&root).expect("closed canonical semantic values serialize")
}

/// Canonical expanded meaning bytes with all display and provenance fields excluded.
pub fn expanded_meaning_canonical_bytes(expansion: &MacroExpansionResult) -> Vec<u8> {
    let mut invocations = expansion
        .expanded
        .iter()
        .map(|invocation| {
            let mut record = BTreeMap::new();
            record.insert(
                "invocation_ordinal".to_owned(),
                Value::Number(Number::from(invocation.provenance.invocation_ordinal)),
            );
            record.insert(
                "nodes".to_owned(),
                Value::Array(invocation.nodes.iter().map(node_value).collect()),
            );
            Value::Object(record.into_iter().collect())
        })
        .collect::<Vec<_>>();
    invocations.sort_by_key(compact_json);
    let mut root = BTreeMap::new();
    root.insert("invocations".to_owned(), Value::Array(invocations));
    root.insert(
        "schema".to_owned(),
        Value::String("inku.expanded-macro-meaning.v1".to_owned()),
    );
    serde_json::to_vec(&root).expect("closed expanded values serialize")
}

fn node_value(node: &ExpandedMacroNode) -> Value {
    let mut record = BTreeMap::new();
    match node {
        ExpandedMacroNode::Emit {
            binding, fields, ..
        } => {
            record.insert("kind".to_owned(), Value::String("emit".to_owned()));
            record.insert(
                "binding".to_owned(),
                binding.as_ref().map(target_value).unwrap_or(Value::Null),
            );
            record.insert(
                "fields".to_owned(),
                Value::Object(
                    fields
                        .iter()
                        .map(|(key, value)| (key.clone(), expanded_value(value)))
                        .collect(),
                ),
            );
        }
        ExpandedMacroNode::Group { body, .. } => {
            record.insert("kind".to_owned(), Value::String("group".to_owned()));
            record.insert(
                "body".to_owned(),
                Value::Array(body.iter().map(node_value).collect()),
            );
        }
        ExpandedMacroNode::Anchor { target, .. } => {
            record.insert("kind".to_owned(), Value::String("anchor".to_owned()));
            record.insert("target".to_owned(), target_value(target));
        }
        ExpandedMacroNode::Relation { kind, from, to, .. } => {
            record.insert("kind".to_owned(), Value::String("relation".to_owned()));
            record.insert("relation".to_owned(), Value::String(kind.clone()));
            record.insert("from".to_owned(), target_value(from));
            record.insert("to".to_owned(), target_value(to));
        }
        ExpandedMacroNode::Transform {
            transform, body, ..
        } => {
            record.insert("kind".to_owned(), Value::String("transform".to_owned()));
            let mut axes = BTreeMap::new();
            axes.insert(
                "rotate_degrees".to_owned(),
                optional_f64(transform.rotate_degrees),
            );
            axes.insert("scale_x".to_owned(), optional_f64(transform.scale_x));
            axes.insert("scale_y".to_owned(), optional_f64(transform.scale_y));
            axes.insert(
                "translate_x".to_owned(),
                optional_f64(transform.translate_x),
            );
            axes.insert(
                "translate_y".to_owned(),
                optional_f64(transform.translate_y),
            );
            record.insert(
                "transform".to_owned(),
                Value::Object(axes.into_iter().collect()),
            );
            record.insert(
                "body".to_owned(),
                Value::Array(body.iter().map(node_value).collect()),
            );
        }
    }
    Value::Object(record.into_iter().collect())
}

fn expanded_value(value: &ExpandedMacroValue) -> Value {
    let mut record = BTreeMap::new();
    match value {
        ExpandedMacroValue::Number(value) => {
            record.insert("kind".to_owned(), Value::String("number".to_owned()));
            record.insert("value".to_owned(), finite_number(*value));
        }
        ExpandedMacroValue::Integer(value) => {
            record.insert("kind".to_owned(), Value::String("integer".to_owned()));
            record.insert("value".to_owned(), Value::Number(Number::from(*value)));
        }
        ExpandedMacroValue::Boolean(value) => {
            record.insert("kind".to_owned(), Value::String("boolean".to_owned()));
            record.insert("value".to_owned(), Value::Bool(*value));
        }
        ExpandedMacroValue::List(values) => {
            record.insert("kind".to_owned(), Value::String("list".to_owned()));
            record.insert(
                "value".to_owned(),
                Value::Array(values.iter().map(expanded_value).collect()),
            );
        }
        ExpandedMacroValue::SemanticRef { category, id } => {
            record.insert("kind".to_owned(), Value::String("semantic_ref".to_owned()));
            record.insert("category".to_owned(), Value::String(category.clone()));
            record.insert("id".to_owned(), Value::String(id.clone()));
        }
    }
    Value::Object(record.into_iter().collect())
}

fn target_value(target: &crate::GeneratedTargetId) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "invocation_ordinal".to_owned(),
        Value::Number(Number::from(target.invocation_ordinal)),
    );
    record.insert(
        "local_name".to_owned(),
        Value::String(target.local_name.clone()),
    );
    record.insert(
        "path".to_owned(),
        Value::Array(target.expansion_path.iter().map(path_value).collect()),
    );
    Value::Object(record.into_iter().collect())
}

fn path_value(segment: &ExpansionPathSegment) -> Value {
    let mut record = BTreeMap::new();
    match segment {
        ExpansionPathSegment::RootStatement { statement_index } => {
            record.insert(
                "kind".to_owned(),
                Value::String("root_statement".to_owned()),
            );
            record.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
        }
        ExpansionPathSegment::ComponentUse {
            statement_index,
            component_id,
        } => {
            record.insert("kind".to_owned(), Value::String("component_use".to_owned()));
            record.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
            record.insert(
                "component_id".to_owned(),
                Value::String(component_id.clone()),
            );
        }
        ExpansionPathSegment::Group { statement_index } => {
            record.insert("kind".to_owned(), Value::String("group".to_owned()));
            record.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
        }
        ExpansionPathSegment::Repeat {
            statement_index,
            iteration,
        } => {
            record.insert("kind".to_owned(), Value::String("repeat".to_owned()));
            record.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
            record.insert(
                "iteration".to_owned(),
                Value::Number(Number::from(*iteration)),
            );
        }
        ExpansionPathSegment::Transform { statement_index } => {
            record.insert("kind".to_owned(), Value::String("transform".to_owned()));
            record.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
        }
        ExpansionPathSegment::Vary {
            statement_index,
            selected_index,
        } => {
            record.insert("kind".to_owned(), Value::String("vary".to_owned()));
            record.insert(
                "statement_index".to_owned(),
                Value::Number(Number::from(*statement_index)),
            );
            record.insert(
                "selected_index".to_owned(),
                Value::Number(Number::from(*selected_index)),
            );
        }
    }
    Value::Object(record.into_iter().collect())
}

fn binding_record(binding: &CompleteMacroParameterBinding) -> Value {
    let mut parameters = binding
        .parameters
        .iter()
        .map(|parameter| {
            let mut record = BTreeMap::new();
            record.insert(
                "name".to_owned(),
                Value::String(parameter.parameter_name.clone()),
            );
            record.insert("value".to_owned(), bound_value(&parameter.value));
            Value::Object(record.into_iter().collect())
        })
        .collect::<Vec<_>>();
    parameters.sort_by_key(compact_json);
    let mut record = BTreeMap::new();
    record.insert(
        "clause".to_owned(),
        Value::Number(Number::from(binding.clause_index as u64)),
    );
    record.insert(
        "invocation".to_owned(),
        Value::String(binding.definition_identity.qualified_name().to_owned()),
    );
    record.insert("kind".to_owned(), Value::String("macro_binding".to_owned()));
    record.insert(
        "ordinal".to_owned(),
        Value::Number(Number::from(binding.invocation_ordinal)),
    );
    record.insert("parameters".to_owned(), Value::Array(parameters));
    Value::Object(record.into_iter().collect())
}

fn binding_descriptor(binding: &CompleteMacroParameterBinding) -> String {
    compact_json(&binding_record(binding))
}

fn bound_value(value: &BoundMacroParameterValue) -> Value {
    let mut record = BTreeMap::new();
    match value {
        BoundMacroParameterValue::Integer { value, .. } => {
            record.insert("kind".to_owned(), Value::String("integer".to_owned()));
            record.insert("value".to_owned(), Value::Number(Number::from(*value)));
        }
        BoundMacroParameterValue::Number { value, .. } => {
            record.insert("kind".to_owned(), Value::String("number".to_owned()));
            record.insert("value".to_owned(), finite_number(*value));
        }
        BoundMacroParameterValue::SemanticRef {
            category,
            canonical_id,
            ..
        } => {
            record.insert("kind".to_owned(), Value::String("semantic_ref".to_owned()));
            record.insert("category".to_owned(), Value::String(category.clone()));
            record.insert("id".to_owned(), Value::String(canonical_id.clone()));
        }
    }
    Value::Object(record.into_iter().collect())
}

fn number_record(clause: usize, value: u64) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "clause".to_owned(),
        Value::Number(Number::from(clause as u64)),
    );
    record.insert("kind".to_owned(), Value::String("exact_number".to_owned()));
    record.insert("value".to_owned(), Value::Number(Number::from(value)));
    Value::Object(record.into_iter().collect())
}

fn string_record(fields: &[(&str, &str)]) -> Value {
    Value::Object(
        fields
            .iter()
            .map(|(key, value)| ((*key).to_owned(), Value::String((*value).to_owned())))
            .collect::<Map<_, _>>(),
    )
}

fn relation_occurrence_descriptor(kind: &RelationReferenceOccurrenceKind) -> String {
    match kind {
        RelationReferenceOccurrenceKind::SaijikiRelation { relation_type, .. } => {
            format!("relation:{relation_type}")
        }
        RelationReferenceOccurrenceKind::AttachmentMarker { marker, .. } => {
            format!("attachment:{}", attachment_marker_id(*marker))
        }
    }
}

const fn attachment_marker_id(marker: AttachmentMarkerKind) -> &'static str {
    match marker {
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wo) => "ja:wo",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Ni) => "ja:ni",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::De) => "ja:de",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::No) => "ja:no",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wa) => "ja:wa",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Ga) => "ja:ga",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::He) => "ja:he",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::To) => "ja:to",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::With) => "en:with",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::In) => "en:in",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::At) => "en:at",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::On) => "en:on",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::To) => "en:to",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::Of) => "en:of",
    }
}

fn atom_descriptor(atom: &ClauseAtom) -> String {
    match atom {
        ClauseAtom::CoreRole(term) => format!(
            "{}:{}",
            core_role_name(term.role),
            canonical_asset_id(&term.category_key, &term.canonical_surface_ja)
        ),
        ClauseAtom::RemainingRole(term) => format!(
            "{}:{}",
            remaining_role_name(term.role),
            canonical_asset_id(&term.category_key, &term.canonical_surface_ja)
        ),
        ClauseAtom::UnattachedExactNumber(number) => format!("number:{}", number.value),
        ClauseAtom::UnresolvedDiagnostic(_) => "unknown".to_owned(),
        ClauseAtom::FunctionWord { .. } => "syntax".to_owned(),
        ClauseAtom::SaijikiRelation { relation_type, .. } => format!("relation:{relation_type}"),
    }
}

fn canonical_asset_id(category: &str, canonical_surface_ja: &str) -> String {
    let projected = project_macro_semantic_ref(category, canonical_surface_ja)
        .expect("accepted typed roles have a canonical semantic projection");
    format!("{}:{}", projected.category, projected.canonical_id)
}

const fn core_role_name(role: crate::CoreRoleKind) -> &'static str {
    match role {
        crate::CoreRoleKind::Primitive => "primitive",
        crate::CoreRoleKind::Touch => "touch",
        crate::CoreRoleKind::Color => "color",
        crate::CoreRoleKind::Surface => "surface",
        crate::CoreRoleKind::Ground => "ground",
    }
}

const fn remaining_role_name(role: crate::RemainingRoleKind) -> &'static str {
    match role {
        crate::RemainingRoleKind::Angle => "angle",
        crate::RemainingRoleKind::Continuity => "continuity",
        crate::RemainingRoleKind::Fluctuation => "fluctuation",
        crate::RemainingRoleKind::Place => "place",
        crate::RemainingRoleKind::Motion => "motion",
        crate::RemainingRoleKind::Proportion => "proportion",
    }
}

fn macro_resolution_kind(kind: MacroInvocationResolutionDiagnosticKind) -> &'static str {
    match kind {
        MacroInvocationResolutionDiagnosticKind::MissingLock => "missing_macro_lock",
        MacroInvocationResolutionDiagnosticKind::AmbiguousLockPrefix => "ambiguous_macro_lock",
        MacroInvocationResolutionDiagnosticKind::MissingDefinition => "missing_macro_definition",
        MacroInvocationResolutionDiagnosticKind::DuplicateMatchingDefinition => {
            "duplicate_macro_definition"
        }
        MacroInvocationResolutionDiagnosticKind::InvalidDefinition => "invalid_macro_definition",
        MacroInvocationResolutionDiagnosticKind::QualifiedNameMismatch => {
            "macro_qualified_name_mismatch"
        }
        MacroInvocationResolutionDiagnosticKind::VersionMismatch => "macro_version_mismatch",
        MacroInvocationResolutionDiagnosticKind::DigestMismatch => "macro_digest_mismatch",
        MacroInvocationResolutionDiagnosticKind::SourceClauseAtomMismatch => {
            "macro_source_ownership"
        }
    }
}

fn macro_binding_kind(kind: MacroParameterBindingDiagnosticKind) -> &'static str {
    match kind {
        MacroParameterBindingDiagnosticKind::MissingCompatibleFact => "missing_macro_parameter",
        MacroParameterBindingDiagnosticKind::AmbiguousCompleteAssignment => {
            "ambiguous_macro_assignment"
        }
        MacroParameterBindingDiagnosticKind::SharedFact => "shared_macro_fact",
        MacroParameterBindingDiagnosticKind::UnsupportedSchema => "unsupported_macro_parameter",
        MacroParameterBindingDiagnosticKind::NumericRange => "macro_parameter_numeric_range",
        MacroParameterBindingDiagnosticKind::NumericPrecision => {
            "macro_parameter_numeric_precision"
        }
        MacroParameterBindingDiagnosticKind::DefinitionIdentityOwnershipMismatch => {
            "macro_definition_ownership"
        }
        MacroParameterBindingDiagnosticKind::SourceClauseAtomOwnershipMismatch => {
            "macro_source_ownership"
        }
    }
}

fn macro_expansion_kind(kind: MacroExpansionDiagnosticKind) -> &'static str {
    match kind {
        MacroExpansionDiagnosticKind::InvalidLimits => "invalid_expansion_limits",
        MacroExpansionDiagnosticKind::InvocationBudget => "expansion_invocation_budget",
        MacroExpansionDiagnosticKind::TotalNodeBudget => "expansion_total_node_budget",
        MacroExpansionDiagnosticKind::MissingSeed => "missing_derived_seed",
        MacroExpansionDiagnosticKind::DuplicateSeed => "duplicate_derived_seed",
        MacroExpansionDiagnosticKind::MismatchedSeed => "mismatched_derived_seed",
        MacroExpansionDiagnosticKind::DefinitionOwnershipMismatch => {
            "expansion_definition_ownership"
        }
        MacroExpansionDiagnosticKind::BindingOwnershipMismatch => "expansion_binding_ownership",
        MacroExpansionDiagnosticKind::ExpressionMismatch => "expansion_expression",
        MacroExpansionDiagnosticKind::ComponentMismatch => "expansion_component",
        MacroExpansionDiagnosticKind::RepeatCountInvalid => "expansion_repeat_count",
        MacroExpansionDiagnosticKind::RepeatMaximumExceeded => "expansion_repeat_maximum",
        MacroExpansionDiagnosticKind::NumericRange => "expansion_numeric_range",
        MacroExpansionDiagnosticKind::DepthBudget => "expansion_depth_budget",
        MacroExpansionDiagnosticKind::EvaluationStepBudget => "expansion_step_budget",
        MacroExpansionDiagnosticKind::NodeBudget => "expansion_node_budget",
        MacroExpansionDiagnosticKind::TargetOwnershipMismatch => "expansion_target_ownership",
        MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch => {
            "expansion_provenance_ownership"
        }
    }
}

fn valid_limits(limits: MacroExpansionLimits) -> bool {
    limits.max_invocations != 0
        && limits.max_depth != 0
        && limits.max_evaluation_steps != 0
        && limits.max_nodes_per_invocation != 0
        && limits.max_total_nodes != 0
}

fn finite_number(value: f64) -> Value {
    let normalized = if value == 0.0 { 0.0 } else { value };
    Value::Number(Number::from_f64(normalized).expect("accepted values are finite"))
}

fn optional_f64(value: Option<f64>) -> Value {
    value.map(finite_number).unwrap_or(Value::Null)
}

fn compact_json(value: &Value) -> String {
    serde_json::to_string(value).expect("closed value serializes")
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn identity(domain: &str, payload: &[u8]) -> String {
    let mut bytes = Vec::new();
    append_field(&mut bytes, domain.as_bytes());
    append_field(&mut bytes, payload);
    format!("{domain}:{}", sha256_hex(&bytes))
}

fn ranged_identity(domain: &str, kind: &str, span: SourceSpan, extra: &str) -> String {
    let mut bytes = Vec::new();
    append_field(&mut bytes, kind.as_bytes());
    append_field(&mut bytes, &(span.start_byte as u64).to_be_bytes());
    append_field(&mut bytes, &(span.end_byte as u64).to_be_bytes());
    append_field(&mut bytes, extra.as_bytes());
    identity(domain, &bytes)
}

fn append_field(output: &mut Vec<u8>, value: &[u8]) {
    output.extend_from_slice(&(value.len() as u64).to_be_bytes());
    output.extend_from_slice(value);
}

fn append_optional(output: &mut Vec<u8>, value: Option<&str>) {
    match value {
        Some(value) => {
            append_field(output, b"present");
            append_field(output, value.as_bytes());
        }
        None => append_field(output, b"absent"),
    }
}

fn append_strings(output: &mut Vec<u8>, values: &[String]) {
    append_field(output, &(values.len() as u64).to_be_bytes());
    for value in values {
        append_field(output, value.as_bytes());
    }
}

fn definition_identity_bytes(values: &[CompilerDefinitionIdentity]) -> Vec<u8> {
    let mut bytes = Vec::new();
    append_field(&mut bytes, &(values.len() as u64).to_be_bytes());
    for value in values {
        append_field(&mut bytes, value.qualified_name.as_bytes());
        append_field(&mut bytes, value.version.as_bytes());
        append_field(&mut bytes, value.sidecar_digest.as_bytes());
        append_optional(&mut bytes, value.resolved_definition_digest.as_deref());
    }
    bytes
}

fn seed_identity_bytes(values: &[CompilerSeedIdentity]) -> Vec<u8> {
    let mut bytes = Vec::new();
    append_field(&mut bytes, &(values.len() as u64).to_be_bytes());
    for value in values {
        append_field(&mut bytes, value.qualified_name.as_bytes());
        append_field(&mut bytes, &value.ordinal.to_be_bytes());
        append_field(&mut bytes, value.scheme_id.as_bytes());
        append_field(&mut bytes, value.full_digest.as_bytes());
        append_field(&mut bytes, &value.resolved_seed.to_be_bytes());
    }
    bytes
}
