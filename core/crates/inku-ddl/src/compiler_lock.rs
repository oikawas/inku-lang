//! Runtime-disconnected typed delivery, canonical compiler identity, and lock construction.

use std::collections::{BTreeMap, BTreeSet};

use serde::Serialize;
use serde_json::{Number, Value};
use sha2::{Digest, Sha256};

use crate::{
    ClauseAtom, CoreRoleKind, ExpandedMacroInvocation, ExpandedMacroNode, ExpandedMacroValue,
    ExpansionPathSegment, GEOMETRY_RESOLUTION_POLICY_ID, GeneratedNodeProvenance, MacroDefinition,
    MacroExpansionDiagnosticKind, MacroExpansionLimits, MacroExpansionResult, MacroInvocation,
    MacroInvocationResolutionDiagnosticKind, MacroParameterBindingDiagnosticKind,
    MacroParameterBindingResult, MacroSeed, NeutralDiagnosticKind, NormalizedDdlDocument,
    OwnedSemanticOccurrence, SemanticAssociationIssueKind, SemanticContinuationIssue,
    SemanticContinuationIssueKind, SemanticContinuationTarget, SemanticCoordinationIssueKind,
    SemanticDocumentAst, SemanticDocumentIssueKind, SemanticDocumentResult, SemanticHead,
    SemanticInstruction, SemanticInstructionIssueKind, SemanticInstructionOccurrenceRole,
    SemanticIssueCausalProvenance, SemanticMacroInvocationHead, SemanticMacroParameterValue,
    SemanticRelationIssueKind, SemanticTerm, SourceOccurrence, SourceSpan,
    associate_semantic_document_with_macro_binding, bind_macro_parameters, derive_macro_seed,
    geometry_resolution_policy_digest,
    macro_expansion::{
        MacroExpansionExecutionOwner, MacroExpansionSelection, expand_selected_macros,
    },
    project_macro_semantic_ref,
    semantic_association::{
        semantic_macro_parameters_have_same_meaning,
        semantic_macro_parameters_match_complete_binding,
    },
    semantic_document::{continuation_target_value, exclusive_continuation_issue_claim_spans},
};

const MISSING_CANONICAL_SEMANTIC_IDENTITY: &str = "missing_canonical_semantic_identity";

/// Stable identity for the compilation envelope.
pub const TYPED_DDL_COMPILATION_SCHEMA_ID: &str = "inku.typed-ddl-compilation.v17";
/// Stable identity for source-independent pre-expansion semantic bytes.
pub const CANONICAL_SEMANTIC_DDL_SCHEMA_ID: &str = crate::SEMANTIC_DOCUMENT_SCHEMA_ID;
/// Stable identity for compiler locks.
pub const TYPED_DDL_COMPILER_LOCK_SCHEMA_ID: &str = "inku.typed-ddl-compiler-lock.v18";
/// ASCII domain prefix for the fully framed compiler lock digest.
pub const COMPILER_LOCK_DIGEST_DOMAIN: &[u8] = b"inku.typed-ddl-compiler-lock.v17";
/// Stable identity for source-bearing semantic provenance bytes.
pub const SEMANTIC_SOURCE_PROVENANCE_SCHEMA_ID: &str = "inku.semantic-source-provenance.v6";
/// Stable identity for generated macro provenance bytes.
pub const EXPANDED_GENERATED_PROVENANCE_SCHEMA_ID: &str = "inku.expanded-generated-provenance.v1";
/// Stable identity for source-independent expanded macro meaning bytes.
pub const EXPANDED_MACRO_MEANING_SCHEMA_ID: &str = "inku.expanded-macro-meaning.v3";

/// Closed compiler state. This is not a Score-readiness decision.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
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

/// Closed owner identity for one structured semantic occurrence.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum SemanticDeliveryOwner {
    EntityHead,
    MacroParameter,
    Color,
    SequenceOperator,
    SequenceItem,
    Quantity,
    Thinness,
    RelativeScale,
    ExplicitGeometry,
    NumericPosition,
    Touch,
    Continuity,
    Angle,
    LayoutDirection,
    SurfaceQuality,
    SurfaceIntensity,
    FluctuationAmplitude,
    FluctuationFrequency,
    FluctuationQuality,
    InkSpread,
    ProportionAspect,
    ShapeConstraint,
    ProportionWidthExtent,
    ProportionArcForm,
    Action,
    Position,
    Relation,
    Ground,
    Background,
    FillTarget,
    ExpandedNode,
    TypedIssue,
    SyntaxOnly,
}

impl SemanticDeliveryOwner {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::EntityHead => "entity_head",
            Self::MacroParameter => "macro_parameter",
            Self::Color => "color",
            Self::SequenceOperator => "sequence_operator",
            Self::SequenceItem => "sequence_item",
            Self::Quantity => "quantity",
            Self::Thinness => "thinness",
            Self::RelativeScale => "relative_scale",
            Self::ExplicitGeometry => "explicit_geometry",
            Self::NumericPosition => "numeric_position",
            Self::Touch => "touch",
            Self::Continuity => "continuity",
            Self::Angle => "angle",
            Self::LayoutDirection => "layout_direction",
            Self::SurfaceQuality => "surface_quality",
            Self::SurfaceIntensity => "surface_intensity",
            Self::FluctuationAmplitude => "fluctuation_amplitude",
            Self::FluctuationFrequency => "fluctuation_frequency",
            Self::FluctuationQuality => "fluctuation_quality",
            Self::InkSpread => "ink_spread",
            Self::ProportionAspect => "proportion_aspect",
            Self::ShapeConstraint => "shape_constraint",
            Self::ProportionWidthExtent => "proportion_width_extent",
            Self::ProportionArcForm => "proportion_arc_form",
            Self::Action => "action",
            Self::Position => "position",
            Self::Relation => "relation",
            Self::Ground => "ground",
            Self::Background => "background",
            Self::FillTarget => "fill_target",
            Self::ExpandedNode => "expanded_node",
            Self::TypedIssue => "typed_issue",
            Self::SyntaxOnly => "syntax_only",
        }
    }
}

/// Source-independent, structured comparison key for one delivery.
#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct SemanticDeliveryIdentity {
    pub owner: SemanticDeliveryOwner,
    pub canonical_key: String,
}

/// One exactly-once classified source or expansion occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticDelivery {
    pub id: String,
    pub kind: SemanticDeliveryKind,
    pub identity: SemanticDeliveryIdentity,
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
    pub expected_owner: SemanticDeliveryOwner,
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

impl CompilerBlockingDiagnostic {
    /// Whether this diagnostic prevents every execution and any bounded hole patch.
    pub fn stops_all_execution(&self) -> bool {
        self.span.is_none()
            || matches!(
                self.kind.as_str(),
                "invalid_expansion_limits"
                    | "clause_stream_integrity"
                    | "missing_canonical_semantic_identity"
                    | "coordination_marker_delivery_integrity"
                    | "continuation_claim_owner_integrity"
                    | "missing_continuation_original_instruction"
                    | "expansion_invocation_budget"
                    | "expansion_total_node_budget"
                    | "missing_derived_seed"
                    | "duplicate_derived_seed"
                    | "mismatched_derived_seed"
                    | "expansion_definition_ownership"
                    | "expansion_binding_ownership"
                    | "expansion_target_ownership"
                    | "expansion_provenance_ownership"
            )
    }
}

/// Sidecar and resolved definition identity retained separately from semantic meaning.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct CompilerDefinitionIdentity {
    pub qualified_name: String,
    pub version: String,
    pub sidecar_digest: String,
    pub resolved_definition_digest: Option<String>,
}

/// One exact I-533 seed identity. `ordinal` is the post-resolution semantic execution ordinal
/// hashed by the compiler, distinct from the retained source occurrence ordinal.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct CompilerSeedIdentity {
    pub qualified_name: String,
    pub ordinal: u64,
    pub scheme_id: &'static str,
    pub full_digest: String,
    pub resolved_seed: u64,
}

/// One validated bridge between retained source ownership and meaning execution order.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct SemanticMacroExecutionOwner {
    pub(crate) binding_index: usize,
    pub(crate) source_invocation_index: usize,
    pub(crate) source_ordinal: u64,
    pub(crate) semantic_ordinal: u64,
}

/// The sole exact owner mapping reused by compiler seeds and meaning projections.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct SemanticMacroExecutionOwners {
    owners: Vec<SemanticMacroExecutionOwner>,
    explained_binding_indices: Vec<usize>,
}

impl SemanticMacroExecutionOwners {
    pub(crate) fn owners(&self) -> &[SemanticMacroExecutionOwner] {
        &self.owners
    }

    pub(crate) fn semantic_ordinal_for_source(&self, source_ordinal: u64) -> Option<u64> {
        let mut matches = self
            .owners
            .iter()
            .filter(|owner| owner.source_ordinal == source_ordinal)
            .map(|owner| owner.semantic_ordinal);
        let ordinal = matches.next()?;
        matches.next().is_none().then_some(ordinal)
    }

    pub(crate) fn expansion_selection(&self) -> MacroExpansionSelection {
        MacroExpansionSelection::exact(
            self.owners
                .iter()
                .map(|owner| MacroExpansionExecutionOwner {
                    binding_index: owner.binding_index,
                    seed_ordinal: owner.semantic_ordinal,
                })
                .collect(),
            self.explained_binding_indices.clone(),
        )
    }

    pub(crate) fn source_semantic_ordinals(&self) -> BTreeMap<u64, u64> {
        self.owners
            .iter()
            .map(|owner| (owner.source_ordinal, owner.semantic_ordinal))
            .collect()
    }

    pub(crate) fn validate_seed_identities(
        &self,
        canonical_bytes: &[u8],
        expansion: &MacroExpansionResult,
        seeds: &[CompilerSeedIdentity],
        composition_seed: Option<u64>,
    ) -> Result<(), MacroExpansionDiagnosticKind> {
        validate_expanded_execution_owners(self, expansion)?;
        let canonical = std::str::from_utf8(canonical_bytes)
            .map_err(|_| MacroExpansionDiagnosticKind::MismatchedSeed)?;
        if seeds.len() != self.owners.len() {
            return Err(MacroExpansionDiagnosticKind::MismatchedSeed);
        }
        for ((owner, invocation), seed) in self.owners.iter().zip(&expansion.expanded).zip(seeds) {
            let Some(binding) = expansion
                .parameter_binding
                .complete
                .get(owner.binding_index)
            else {
                return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
            };
            let Some(resolved) = expansion
                .parameter_binding
                .macro_resolution
                .resolved
                .get(binding.invocation_index)
            else {
                return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
            };
            let semantic_invocation = MacroInvocation::new(
                resolved.invocation.namespace(),
                resolved.invocation.heading(),
                owner.semantic_ordinal,
            )
            .map_err(|_| MacroExpansionDiagnosticKind::MismatchedSeed)?;
            let expected = derive_macro_seed(canonical, &semantic_invocation, composition_seed);
            let provenance = &invocation.provenance;
            if seed.qualified_name != binding.definition_identity.qualified_name()
                || seed.ordinal != owner.semantic_ordinal
                || seed.scheme_id != crate::MACRO_SEED_SCHEME_ID
                || seed.full_digest != expected.full_digest_hex()
                || seed.resolved_seed != expected.resolved_seed()
                || seed.scheme_id != provenance.seed_scheme_id
                || seed.full_digest != provenance.seed_full_digest
                || seed.resolved_seed != provenance.resolved_seed
                || provenance.effective_composition_seed != composition_seed.unwrap_or(0)
            {
                return Err(MacroExpansionDiagnosticKind::MismatchedSeed);
            }
        }
        Ok(())
    }
}

pub(crate) fn compiler_seed_identity(seed: &MacroSeed) -> CompilerSeedIdentity {
    CompilerSeedIdentity {
        qualified_name: seed.qualified_macro_name().to_owned(),
        ordinal: seed.ordinal(),
        scheme_id: seed.scheme_id(),
        full_digest: seed.full_digest_hex().to_owned(),
        resolved_seed: seed.resolved_seed(),
    }
}

/// Complete deterministic identity for one integrity-valid compilation attempt.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct TypedDdlCompilerLock {
    pub schema_id: &'static str,
    pub state: CompilerLockState,
    pub visible_source_digest: String,
    pub structured_semantic_occurrence_digest: String,
    pub canonical_pre_expansion_digest: Option<String>,
    pub semantic_source_provenance_digest: Option<String>,
    pub geometry_policy_id: &'static str,
    pub geometry_policy_digest: String,
    pub composition_seed: Option<u64>,
    pub definition_identities: Vec<CompilerDefinitionIdentity>,
    pub macro_seeds: Vec<CompilerSeedIdentity>,
    pub expanded_meaning_digest: Option<String>,
    pub expanded_generated_provenance_digest: Option<String>,
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
    pub semantic_document: Option<SemanticDocumentResult>,
    pub derived_seeds: Vec<MacroSeed>,
    pub macro_expansion: Option<MacroExpansionResult>,
    pub compiler_lock: Option<TypedDdlCompilerLock>,
}

impl TypedDdlCompilation {
    /// The exact accepted I-581 result, regardless of whether I-582 was reached.
    pub fn accepted_parameter_binding(&self) -> Option<&MacroParameterBindingResult> {
        self.semantic_document
            .as_ref()
            .and_then(|document| {
                document
                    .instruction_association
                    .association
                    .macro_parameter_binding
                    .as_ref()
            })
            .or_else(|| {
                self.macro_expansion
                    .as_ref()
                    .map(|expansion| &expansion.parameter_binding)
            })
    }

    /// Borrow the sole I-595 pre-expansion meaning authority when the document is complete.
    pub fn pre_expansion_canonical_bytes(&self) -> Option<&[u8]> {
        self.semantic_document
            .as_ref()
            .and_then(|document| document.canonical_bytes.as_deref())
    }

    /// Source-independent fingerprints used by constrained patch validation.
    pub fn explicit_fingerprints(&self) -> Vec<(SourceSpan, String)> {
        self.deliveries
            .iter()
            .filter_map(|delivery| {
                (delivery.kind == SemanticDeliveryKind::Explicit)
                    .then_some(delivery.span.map(|span| {
                        (
                            span,
                            format!(
                                "{}|{}",
                                delivery.identity.owner.as_str(),
                                delivery.identity.canonical_key
                            ),
                        )
                    }))
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
}

#[derive(Default)]
struct ContinuationIssueProjection {
    kinds: Vec<String>,
    members: Vec<String>,
    conflict: bool,
}

struct ExclusiveContinuationClaimProjection {
    claim_span: SourceSpan,
    issue_indices: Vec<usize>,
}

type ContinuationClaimKey = (usize, usize);

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
    let clause_stream = &parameter_binding
        .macro_resolution
        .relation_reference_evidence
        .attachment_evidence
        .noun_phrase
        .clause_stream;
    if let Some(kind) = projection_integrity_failure_kind(clause_stream) {
        return integrity_failure(document, kind);
    }
    let mut semantic_document =
        associate_semantic_document_with_macro_binding(&document, parameter_binding);
    let mut projection = project_deliveries(&document, &semantic_document);
    let canonical_ready = semantic_document.canonical_bytes.is_some();
    if !canonical_ready
        && projection.holes.is_empty()
        && projection.conflicts.is_empty()
        && projection.blocking.is_empty()
    {
        add_blocking(&mut projection, MISSING_CANONICAL_SEMANTIC_IDENTITY, None);
    }
    sort_projection(&mut projection);
    let structured_semantic_occurrence_digest = sha256_hex(&structured_semantic_occurrence_bytes(
        &projection.deliveries,
    ));
    let mut seeds = Vec::new();
    let mut expansion = None;
    let mut expanded_meaning_bytes = None;

    if canonical_ready {
        let binding = semantic_document
            .instruction_association
            .association
            .macro_parameter_binding
            .take()
            .expect("I-595 document owns the accepted binding exactly once");
        let canonical = std::str::from_utf8(
            semantic_document
                .canonical_bytes
                .as_deref()
                .expect("complete semantic document has canonical bytes"),
        )
        .expect("I-595 canonical JSON is UTF-8");
        let execution_owners = semantic_macro_execution_owners(&semantic_document.ast, &binding);
        let mut selection = execution_owners
            .as_ref()
            .map(SemanticMacroExecutionOwners::expansion_selection)
            .unwrap_or_else(|_| MacroExpansionSelection::invalid_owner_join());
        if let Ok(owners) = &execution_owners {
            for owner in owners.owners() {
                let Some(complete) = binding.complete.get(owner.binding_index) else {
                    selection = MacroExpansionSelection::invalid_owner_join();
                    seeds.clear();
                    break;
                };
                let Some(resolved) = binding
                    .macro_resolution
                    .resolved
                    .get(complete.invocation_index)
                else {
                    selection = MacroExpansionSelection::invalid_owner_join();
                    seeds.clear();
                    break;
                };
                let Ok(invocation) = MacroInvocation::new(
                    resolved.invocation.namespace(),
                    resolved.invocation.heading(),
                    owner.semantic_ordinal,
                ) else {
                    selection = MacroExpansionSelection::invalid_owner_join();
                    seeds.clear();
                    break;
                };
                seeds.push(derive_macro_seed(canonical, &invocation, composition_seed));
            }
        }
        let expanded = expand_selected_macros(binding, definitions, &seeds, limits, selection);
        project_expansion_diagnostics(&document, &expanded, &mut projection);
        if let Ok(owners) = &execution_owners {
            if expanded.diagnostics.is_empty() {
                match expanded_meaning_canonical_bytes_with_owners(owners, &expanded) {
                    Ok(bytes) => expanded_meaning_bytes = Some(bytes),
                    Err(kind) => add_blocking(&mut projection, macro_expansion_kind(kind), None),
                }
            }
            if let Err(kind) = project_expanded_deliveries(&expanded, owners, &mut projection) {
                add_blocking(&mut projection, macro_expansion_kind(kind), None);
            }
        }
        expansion = Some(expanded);
        sort_projection(&mut projection);
    }

    let state = compiler_state(&projection);
    let expanded_digest = if state == CompilerLockState::CanonicalReady {
        expanded_meaning_bytes.as_deref().map(sha256_hex)
    } else {
        None
    };
    let semantic_source_provenance_digest = canonical_ready.then(|| {
        sha256_hex(&semantic_source_provenance_canonical_bytes(
            &semantic_document.ast,
        ))
    });
    let expanded_generated_provenance_digest = if state == CompilerLockState::CanonicalReady {
        expansion
            .as_ref()
            .map(|value| sha256_hex(&expanded_generated_provenance_canonical_bytes(value)))
    } else {
        None
    };
    let lock = build_lock(
        &document,
        definitions,
        composition_seed,
        &projection,
        structured_semantic_occurrence_digest,
        semantic_document.canonical_bytes.as_deref(),
        semantic_source_provenance_digest,
        &seeds,
        expanded_digest,
        expanded_generated_provenance_digest,
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
        semantic_document: Some(semantic_document),
        derived_seeds: seeds,
        macro_expansion: expansion,
        compiler_lock: Some(lock),
    }
}

fn projection_integrity_failure_kind(stream: &crate::ClauseStream) -> Option<&'static str> {
    stream
        .clauses
        .iter()
        .flat_map(|clause| &clause.atoms)
        .find_map(|atom| {
            let (category_key, canonical_surface_ja) = match atom {
                ClauseAtom::CoreRole(term) => (
                    term.category_key.as_str(),
                    term.canonical_surface_ja.as_str(),
                ),
                ClauseAtom::RemainingRole(term) => (
                    term.category_key.as_str(),
                    term.canonical_surface_ja.as_str(),
                ),
                ClauseAtom::CoreModifier(_)
                | ClauseAtom::UnattachedExactNumber(_)
                | ClauseAtom::GrammarMarker { .. }
                | ClauseAtom::FunctionWord { .. }
                | ClauseAtom::SaijikiRelation { .. }
                | ClauseAtom::UnresolvedDiagnostic(_) => return None,
            };
            project_macro_semantic_ref(category_key, canonical_surface_ja)
                .is_none()
                .then_some(MISSING_CANONICAL_SEMANTIC_IDENTITY)
        })
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
        identity: SemanticDeliveryIdentity {
            owner: SemanticDeliveryOwner::TypedIssue,
            canonical_key: kind.to_owned(),
        },
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
        semantic_document: None,
        derived_seeds: Vec::new(),
        macro_expansion: None,
        compiler_lock: None,
    }
}

#[cfg(test)]
mod projection_integrity_tests {
    use super::*;
    use crate::{
        ClauseSegment, ClauseStream, CoreRoleKind, CoreRoleTerm, ResolvedInstructionLanguage,
    };

    #[test]
    fn unprojectable_typed_term_returns_stable_blocking_compilation() {
        let span = SourceSpan {
            start_byte: 0,
            end_byte: 1,
        };
        let stream = ClauseStream {
            clauses: vec![ClauseSegment {
                span,
                atoms: vec![ClauseAtom::CoreRole(CoreRoleTerm {
                    role: CoreRoleKind::Primitive,
                    asset_id: "synthetic.asset".to_owned(),
                    category_key: "synthetic.category".to_owned(),
                    canonical_surface_ja: "x".to_owned(),
                    shape_constraint: None,
                    span,
                })],
            }],
            separators: Vec::new(),
            delivery_conservation_count: 1,
        };

        let kind = projection_integrity_failure_kind(&stream)
            .expect("unprojectable typed term must fail closed");
        assert_eq!(kind, MISSING_CANONICAL_SEMANTIC_IDENTITY);

        let document =
            NormalizedDdlDocument::new("x", ResolvedInstructionLanguage::En, Vec::new()).unwrap();
        let result = integrity_failure(document, kind);
        assert_eq!(result.document.source(), "x");
        assert_eq!(result.delivery_summary.blocking_diagnostics, 1);
        assert_eq!(result.blocking_diagnostics[0].kind, kind);
        assert_eq!(
            result.deliveries[0].identity.owner,
            SemanticDeliveryOwner::TypedIssue
        );
        assert!(result.semantic_document.is_none());
        assert!(result.derived_seeds.is_empty());
        assert!(result.macro_expansion.is_none());
        assert!(result.compiler_lock.is_none());
    }
}

fn project_deliveries(
    document: &NormalizedDdlDocument,
    semantic_document: &SemanticDocumentResult,
) -> Projection {
    let mut projection = Projection::default();
    let unresolved_clause_spans = unresolved_clause_spans(semantic_document);
    let patchable_clause_spans =
        patchable_unresolved_clause_spans(semantic_document, &unresolved_clause_spans);
    let deferred_continuation_clause_spans =
        deferred_continuation_clause_spans(semantic_document, &patchable_clause_spans);
    let exclusive_continuation_claims =
        exclusive_continuation_claim_groups(&semantic_document.continuation_issues);

    if let Some(ground) = &semantic_document.ast.ground {
        add_term_explicit(&mut projection, SemanticDeliveryOwner::Ground, ground);
    }
    let background_spans = semantic_document
        .background_candidates
        .iter()
        .flat_map(crate::SemanticBackground::sources)
        .map(|source| source.span)
        .collect::<Vec<_>>();
    let background_clause_spans = semantic_document
        .instruction_association
        .association
        .clause_stream
        .clauses
        .iter()
        .filter(|clause| {
            clause.atoms.iter().any(|atom| {
                matches!(
                    atom,
                    ClauseAtom::GrammarMarker {
                        marker_id: crate::MarkerId::JaBackground | crate::MarkerId::EnBackground,
                        ..
                    }
                )
            })
        })
        .map(|clause| clause.span)
        .collect::<Vec<_>>();
    for background in &semantic_document.background_candidates {
        add_explicit(
            &mut projection,
            background.head.span,
            SemanticDeliveryOwner::Background,
            "document:background".to_owned(),
        );
        add_term_explicit(
            &mut projection,
            SemanticDeliveryOwner::Background,
            &background.color,
        );
        add_term_explicit(
            &mut projection,
            SemanticDeliveryOwner::Background,
            &background.action,
        );
        for marker in &background.markers {
            add_syntax(&mut projection, marker.span, "background_grammar");
        }
    }
    for instruction in &semantic_document.ast.instructions {
        project_instruction(instruction, &mut projection);
    }
    for edge in &semantic_document.ast.group_predicates {
        if let Some(target) = &edge.fill_target {
            let meaning =
                crate::semantic_instruction::semantic_fill_target_value(target).to_string();
            for source in target.sources() {
                add_explicit(
                    &mut projection,
                    source.span,
                    SemanticDeliveryOwner::FillTarget,
                    meaning.clone(),
                );
            }
        }
        if let Some(action) = &edge.action {
            add_term_explicit(&mut projection, SemanticDeliveryOwner::Action, action);
        }
        if let Some(position) = &edge.position {
            add_term_explicit(&mut projection, SemanticDeliveryOwner::Position, position);
        }
    }
    for span in &patchable_clause_spans {
        add_hole(
            document,
            &mut projection,
            "unresolved_clause",
            *span,
            SemanticDeliveryOwner::TypedIssue,
            "semantic_clause:unresolved".to_owned(),
        );
    }
    let mut group_marker_spans = semantic_document
        .ast
        .coordinated_head_groups
        .iter()
        .flat_map(|group| &group.markers)
        .map(|marker| marker.span)
        .collect::<Vec<_>>();
    let mut issue_marker_spans = semantic_document
        .instruction_association
        .coordination_issues
        .iter()
        .flat_map(|issue| &issue.markers)
        .map(|marker| marker.span)
        .collect::<Vec<_>>();
    group_marker_spans.sort_by_key(|span| (span.start_byte, span.end_byte));
    issue_marker_spans.sort_by_key(|span| (span.start_byte, span.end_byte));
    let duplicate_group_marker = group_marker_spans.windows(2).any(|pair| pair[0] == pair[1]);
    let duplicate_issue_marker = issue_marker_spans.windows(2).any(|pair| pair[0] == pair[1]);
    let cross_owned_marker = group_marker_spans
        .iter()
        .any(|span| issue_marker_spans.contains(span));
    if group_marker_spans.len() + issue_marker_spans.len()
        != semantic_document
            .instruction_association
            .owned_coordination_marker_count
        || semantic_document
            .instruction_association
            .delivered_coordination_marker_count
            != semantic_document
                .instruction_association
                .owned_coordination_marker_count
        || duplicate_group_marker
        || duplicate_issue_marker
        || cross_owned_marker
    {
        add_blocking(
            &mut projection,
            "coordination_marker_delivery_integrity",
            group_marker_spans
                .first()
                .or(issue_marker_spans.first())
                .copied(),
        );
    }
    for span in group_marker_spans {
        add_syntax(&mut projection, span, "coordinated_head_marker");
    }
    for span in issue_marker_spans {
        add_syntax(&mut projection, span, "coordination_issue_marker");
    }
    for marker in semantic_document
        .instruction_association
        .coordination_issues
        .iter()
        .flat_map(|issue| &issue.continuation_markers)
    {
        add_syntax(&mut projection, marker.span, "continuation_subject_marker");
    }
    let mut restored_failed_heads = Vec::new();
    for issue in &semantic_document.continuation_issues {
        let head_span = issue.instruction.entity.head.source().span;
        if restored_failed_heads.contains(&head_span) {
            continue;
        }
        if let Some(instruction) = semantic_document
            .instruction_association
            .ast
            .instructions
            .iter()
            .find(|instruction| instruction.entity.head.source().span == head_span)
        {
            project_instruction_excluding_claims(
                instruction,
                &exclusive_continuation_claims,
                &semantic_document.continuation_issues,
                &mut projection,
            );
            restored_failed_heads.push(head_span);
        } else {
            add_blocking_with_members(
                &mut projection,
                "missing_continuation_original_instruction",
                Some(issue.marker.span),
                vec![format!(
                    "head={}",
                    semantic_head_key(&issue.instruction.entity.head)
                )],
            );
        }
    }
    for edge in &semantic_document.ast.continuations {
        add_syntax(
            &mut projection,
            edge.reintroduced_head.source().span,
            &format!(
                "continuation_head:{}",
                continuation_target_key(&edge.target)
            ),
        );
        add_syntax(
            &mut projection,
            edge.marker.span,
            "continuation_subject_marker",
        );
    }

    let consumed_continuation_spans = semantic_document
        .ast
        .continuations
        .iter()
        .flat_map(|edge| &edge.consumed_upstream_spans)
        .copied()
        .chain(
            exclusive_continuation_claims
                .values()
                .filter(|group| {
                    group.issue_indices.len() > 1
                        && exclusive_claim_owner(group, &semantic_document.continuation_issues)
                            .is_some()
                })
                .map(|group| group.claim_span),
        )
        .collect::<Vec<_>>();

    let association = &semantic_document.instruction_association.association;
    for issue in &association.sequence_issues {
        let issue_spans = std::iter::once(issue.operator.provenance.source.span)
            .chain(issue.items.iter().map(|item| item.provenance.source.span))
            .chain(issue.markers.iter().map(|marker| marker.span))
            .collect::<Vec<_>>();
        if spans_share_clause(&issue_spans, &patchable_clause_spans) {
            continue;
        }
        add_blocking_with_members(
            &mut projection,
            issue.kind.as_str(),
            Some(issue.operator.provenance.source.span),
            issue.items.iter().map(term_key).collect(),
        );
        for item in &issue.items {
            add_syntax(
                &mut projection,
                item.provenance.source.span,
                "invalid_sequence_item",
            );
        }
        for marker in &issue.markers {
            add_syntax(&mut projection, marker.span, "invalid_sequence_grammar");
        }
    }
    for issue in &association.issues {
        if issue.upstream_diagnostic.is_none()
            && !issue.occurrences.is_empty()
            && issue
                .occurrences
                .iter()
                .all(|occurrence| background_spans.contains(&occurrence.source().span))
        {
            continue;
        }
        let issue_spans = issue
            .occurrences
            .iter()
            .map(|occurrence| occurrence.source().span)
            .collect::<Vec<_>>();
        if issue.kind == SemanticAssociationIssueKind::MissingEntityHead
            && issue.upstream_diagnostic.is_none()
            && !issue.occurrences.is_empty()
            && !spans_share_clause(&issue_spans, &background_clause_spans)
        {
            continue;
        }
        let span = issue
            .upstream_diagnostic
            .as_ref()
            .map(|diagnostic| diagnostic.span)
            .or_else(|| {
                issue
                    .occurrences
                    .first()
                    .map(|occurrence| occurrence.source().span)
            });
        let kind = issue.kind.as_str();
        let mut issue_spans = issue_spans;
        issue_spans.extend(
            issue
                .upstream_diagnostic
                .iter()
                .map(|diagnostic| diagnostic.span),
        );
        if spans_share_clause(&issue_spans, &patchable_clause_spans) {
            continue;
        }
        match issue.kind {
            SemanticAssociationIssueKind::UpstreamHole => {
                if let Some(span) = span {
                    add_hole(
                        document,
                        &mut projection,
                        kind,
                        span,
                        SemanticDeliveryOwner::Quantity,
                        "semantic_association:upstream_hole".to_owned(),
                    );
                } else {
                    add_blocking(&mut projection, kind, None);
                }
            }
            SemanticAssociationIssueKind::MacroParameterBinding(
                MacroParameterBindingDiagnosticKind::MissingCompatibleFact,
            ) => {
                if let Some(span) = span {
                    add_hole(
                        document,
                        &mut projection,
                        kind,
                        span,
                        SemanticDeliveryOwner::EntityHead,
                        format!("semantic_association:{kind}"),
                    );
                } else {
                    add_blocking(&mut projection, kind, None);
                }
            }
            SemanticAssociationIssueKind::AmbiguousEntityOwnership => {
                for occurrence in issue.occurrences.iter().filter(|occurrence| {
                    !consumed_continuation_spans.contains(&occurrence.source().span)
                        && !background_spans.contains(&occurrence.source().span)
                        && !span_is_in_clause(occurrence.source().span, &patchable_clause_spans)
                        && !span_is_in_clause(
                            occurrence.source().span,
                            &deferred_continuation_clause_spans,
                        )
                }) {
                    add_conflict(
                        &mut projection,
                        kind,
                        Some(occurrence.source().span),
                        vec![owned_occurrence_key(occurrence)],
                    );
                }
            }
            SemanticAssociationIssueKind::ConflictingColors
            | SemanticAssociationIssueKind::ConflictingQuantities
            | SemanticAssociationIssueKind::ConflictingThinness
            | SemanticAssociationIssueKind::ConflictingRelativeScales
            | SemanticAssociationIssueKind::ConflictingExplicitGeometries
            | SemanticAssociationIssueKind::ConflictingNumericPositions
            | SemanticAssociationIssueKind::ConflictingRelativeAndExplicitGeometry
            | SemanticAssociationIssueKind::ConflictingTouches
            | SemanticAssociationIssueKind::ConflictingContinuities
            | SemanticAssociationIssueKind::ConflictingAngles
            | SemanticAssociationIssueKind::ConflictingSurfaceQualities
            | SemanticAssociationIssueKind::ConflictingSurfaceIntensities
            | SemanticAssociationIssueKind::ConflictingFluctuationAmplitudes
            | SemanticAssociationIssueKind::ConflictingFluctuationFrequencies
            | SemanticAssociationIssueKind::ConflictingFluctuationQualities
            | SemanticAssociationIssueKind::ConflictingShapeConstraints
            | SemanticAssociationIssueKind::ConflictingProportionAspects
            | SemanticAssociationIssueKind::ConflictingProportionWidthExtents
            | SemanticAssociationIssueKind::ConflictingProportionArcForms
            | SemanticAssociationIssueKind::UpstreamConflict
            | SemanticAssociationIssueKind::MacroResolution(
                MacroInvocationResolutionDiagnosticKind::AmbiguousLockPrefix
                | MacroInvocationResolutionDiagnosticKind::DuplicateMatchingDefinition,
            )
            | SemanticAssociationIssueKind::MacroParameterBinding(
                MacroParameterBindingDiagnosticKind::AmbiguousCompleteAssignment
                | MacroParameterBindingDiagnosticKind::SharedFact,
            ) => add_conflict(
                &mut projection,
                kind,
                span,
                issue.occurrences.iter().map(owned_occurrence_key).collect(),
            ),
            SemanticAssociationIssueKind::MissingEntityHead
            | SemanticAssociationIssueKind::IncompleteNumericGeometry
            | SemanticAssociationIssueKind::IncompleteNumericPosition
            | SemanticAssociationIssueKind::UnownedExactDecimal
            | SemanticAssociationIssueKind::UnknownSurfaceDimension
            | SemanticAssociationIssueKind::ConflictingFluctuationSpreads
            | SemanticAssociationIssueKind::UnknownFluctuationDimension
            | SemanticAssociationIssueKind::UnknownProportionDimension
            | SemanticAssociationIssueKind::UpstreamUnknown
            | SemanticAssociationIssueKind::MacroResolution(_)
            | SemanticAssociationIssueKind::MacroParameterBinding(_) => {
                add_blocking(&mut projection, kind, span)
            }
        }
    }

    for issue in &semantic_document.instruction_association.issues {
        if !issue.occurrences.is_empty()
            && issue.occurrences.iter().all(|occurrence| {
                background_spans.contains(&occurrence.term.provenance.source.span)
            })
        {
            continue;
        }
        let span = issue
            .occurrences
            .first()
            .map(|occurrence| occurrence.term.provenance.source.span);
        let issue_spans = issue
            .occurrences
            .iter()
            .map(|occurrence| occurrence.term.provenance.source.span)
            .collect::<Vec<_>>();
        if spans_share_clause(&issue_spans, &patchable_clause_spans) {
            continue;
        }
        if (issue.kind != SemanticInstructionIssueKind::MissingActionEntity
            || !spans_share_clause(&issue_spans, &background_clause_spans))
            && matches!(
                issue.kind,
                SemanticInstructionIssueKind::MissingActionEntity
                    | SemanticInstructionIssueKind::MissingLayoutDirectionEntity
                    | SemanticInstructionIssueKind::MissingPositionEntity
            )
            && !issue.occurrences.is_empty()
        {
            continue;
        }
        match issue.kind {
            SemanticInstructionIssueKind::AmbiguousActionOwnership
            | SemanticInstructionIssueKind::AmbiguousLayoutDirectionOwnership
            | SemanticInstructionIssueKind::AmbiguousPositionOwnership => {
                for occurrence in issue.occurrences.iter().filter(|occurrence| {
                    !consumed_continuation_spans.contains(&occurrence.term.provenance.source.span)
                        && !background_spans.contains(&occurrence.term.provenance.source.span)
                        && !span_is_in_clause(
                            occurrence.term.provenance.source.span,
                            &patchable_clause_spans,
                        )
                        && !span_is_in_clause(
                            occurrence.term.provenance.source.span,
                            &deferred_continuation_clause_spans,
                        )
                }) {
                    add_conflict(
                        &mut projection,
                        issue.kind.as_str(),
                        Some(occurrence.term.provenance.source.span),
                        vec![term_key(&occurrence.term)],
                    );
                }
            }
            SemanticInstructionIssueKind::ConflictingActions
            | SemanticInstructionIssueKind::ConflictingLayoutDirections
            | SemanticInstructionIssueKind::ConflictingPositions => add_conflict(
                &mut projection,
                issue.kind.as_str(),
                span,
                issue
                    .occurrences
                    .iter()
                    .map(|occurrence| term_key(&occurrence.term))
                    .collect(),
            ),
            SemanticInstructionIssueKind::MissingActionEntity
            | SemanticInstructionIssueKind::MissingLayoutDirectionEntity
            | SemanticInstructionIssueKind::MissingPositionEntity => {
                add_blocking(&mut projection, issue.kind.as_str(), span)
            }
        }
    }

    for issue in &semantic_document
        .instruction_association
        .coordination_issues
    {
        let issue_spans = issue
            .markers
            .iter()
            .chain(&issue.continuation_markers)
            .map(|marker| marker.span)
            .chain(issue.claim_spans.iter().copied())
            .chain(
                issue
                    .predicates
                    .iter()
                    .map(|predicate| predicate.term.provenance.source.span),
            )
            .collect::<Vec<_>>();
        if spans_share_clause(&issue_spans, &patchable_clause_spans) {
            continue;
        }
        let mut members = issue
            .member_instruction_indices
            .iter()
            .map(|index| format!("member={index}"))
            .collect::<Vec<_>>();
        members.extend(
            issue.markers.iter().map(|marker| {
                format!("marker={}:{}", marker.span.start_byte, marker.span.end_byte)
            }),
        );
        members.extend(
            issue
                .candidate_instruction_indices
                .iter()
                .map(|index| format!("continuation_candidate={index}")),
        );
        members.extend(
            issue
                .claim_spans
                .iter()
                .map(|span| format!("claim={}:{}", span.start_byte, span.end_byte)),
        );
        if let SemanticIssueCausalProvenance::UpstreamDiagnostics(causes) = &issue.causal_provenance
        {
            members.extend(causes.iter().map(|cause| {
                format!(
                    "cause={}:{}:{}:{}",
                    cause.relation.as_str(),
                    neutral_diagnostic_kind_key(cause.diagnostic_kind),
                    cause.span.start_byte,
                    cause.span.end_byte
                )
            }));
        }
        if issue.predicates.is_empty() {
            match issue.kind {
                SemanticCoordinationIssueKind::PredicateOwnershipConflict
                | SemanticCoordinationIssueKind::ContinuationOwnershipConflict
                | SemanticCoordinationIssueKind::ConflictingGroupActions
                | SemanticCoordinationIssueKind::ConflictingGroupPositions => {
                    add_ordered_conflict(
                        &mut projection,
                        issue.kind.as_str(),
                        issue.claim_spans.first().copied(),
                        members,
                    );
                }
                SemanticCoordinationIssueKind::MissingLeftHead
                | SemanticCoordinationIssueKind::MissingRightHead
                | SemanticCoordinationIssueKind::MissingBothHeads
                | SemanticCoordinationIssueKind::BlockedBoundary
                | SemanticCoordinationIssueKind::OverlappingChain => add_blocking_with_members(
                    &mut projection,
                    issue.kind.as_str(),
                    issue.markers.first().map(|marker| marker.span),
                    members,
                ),
            }
            continue;
        }
        for predicate in &issue.predicates {
            let owner = match predicate.role {
                SemanticInstructionOccurrenceRole::Action => SemanticDeliveryOwner::Action,
                SemanticInstructionOccurrenceRole::Position => SemanticDeliveryOwner::Position,
                SemanticInstructionOccurrenceRole::LayoutDirection => {
                    SemanticDeliveryOwner::LayoutDirection
                }
            };
            let mut candidates = members.clone();
            candidates.push(format!(
                "owner={}:{}",
                owner.as_str(),
                term_key(&predicate.term)
            ));
            match issue.kind {
                SemanticCoordinationIssueKind::MissingLeftHead
                | SemanticCoordinationIssueKind::MissingRightHead
                | SemanticCoordinationIssueKind::MissingBothHeads
                | SemanticCoordinationIssueKind::BlockedBoundary
                | SemanticCoordinationIssueKind::OverlappingChain => add_blocking_with_members(
                    &mut projection,
                    issue.kind.as_str(),
                    Some(predicate.term.provenance.source.span),
                    candidates,
                ),
                SemanticCoordinationIssueKind::PredicateOwnershipConflict
                | SemanticCoordinationIssueKind::ContinuationOwnershipConflict
                | SemanticCoordinationIssueKind::ConflictingGroupActions
                | SemanticCoordinationIssueKind::ConflictingGroupPositions => add_ordered_conflict(
                    &mut projection,
                    issue.kind.as_str(),
                    Some(predicate.term.provenance.source.span),
                    candidates,
                ),
            }
        }
    }

    for issue in &semantic_document.instruction_association.relation_issues {
        let span = issue
            .occurrences
            .first()
            .map(|occurrence| occurrence.provenance.span);
        match issue.kind {
            SemanticRelationIssueKind::AmbiguousCurrentInstructionOwnership => {
                for occurrence in &issue.occurrences {
                    add_conflict(
                        &mut projection,
                        issue.kind.as_str(),
                        Some(occurrence.provenance.span),
                        vec![format!(
                            "{}:{}",
                            occurrence.kind.as_str(),
                            occurrence.reference.as_str()
                        )],
                    );
                }
            }
            SemanticRelationIssueKind::ConflictingRelations
            | SemanticRelationIssueKind::TargetPrimitiveMismatch => add_conflict(
                &mut projection,
                issue.kind.as_str(),
                span,
                issue
                    .occurrences
                    .iter()
                    .map(|occurrence| {
                        format!(
                            "{}:{}",
                            occurrence.kind.as_str(),
                            occurrence.reference.as_str()
                        )
                    })
                    .collect(),
            ),
            SemanticRelationIssueKind::MissingCurrentInstruction
            | SemanticRelationIssueKind::MissingPreviousOne
            | SemanticRelationIssueKind::MissingPreviousTwo => {
                if let Some(span) = span {
                    add_hole(
                        document,
                        &mut projection,
                        issue.kind.as_str(),
                        span,
                        SemanticDeliveryOwner::Relation,
                        format!("semantic_relation:{}", issue.kind.as_str()),
                    );
                } else {
                    add_blocking(&mut projection, issue.kind.as_str(), None);
                }
            }
        }
    }

    for issue in &semantic_document.issues {
        match issue.kind {
            SemanticDocumentIssueKind::ConflictingGrounds
            | SemanticDocumentIssueKind::ConflictingBackgrounds => add_conflict(
                &mut projection,
                issue.kind.as_str(),
                issue
                    .occurrences
                    .first()
                    .map(|term| term.provenance.source.span),
                issue.occurrences.iter().map(term_key).collect(),
            ),
        }
    }
    project_continuation_issues(
        &semantic_document.continuation_issues,
        &deferred_continuation_clause_spans,
        &mut projection,
    );

    let covered_spans = projection
        .deliveries
        .iter()
        .filter_map(|delivery| delivery.span)
        .collect::<Vec<_>>();
    for clause in &association.clause_stream.clauses {
        for atom in &clause.atoms {
            if !covered_spans.contains(&atom.span()) {
                let kind = match atom {
                    ClauseAtom::CoreRole(_) => "core_role_transport",
                    ClauseAtom::CoreModifier(_) => "core_modifier_transport",
                    ClauseAtom::RemainingRole(_) => "remaining_role_transport",
                    ClauseAtom::UnattachedExactNumber(_) => "exact_number_transport",
                    ClauseAtom::GrammarMarker { .. } => "function_word",
                    ClauseAtom::FunctionWord { .. } => "function_word",
                    ClauseAtom::SaijikiRelation { .. } => "relation_transport",
                    ClauseAtom::UnresolvedDiagnostic(_) => "diagnostic_transport",
                };
                add_syntax(&mut projection, atom.span(), kind);
            }
        }
    }

    projection
}

/// A support-only hole has no drawable, quantity, relation, or modifier owner.
/// This recognizes existing compiler evidence, not additional source grammar.
pub fn isolated_support_clause_owner(
    clause: &crate::ClauseSegment,
) -> Option<SemanticDeliveryOwner> {
    let mut grounds = 0;
    let mut colors = 0;
    let mut background = false;
    for atom in &clause.atoms {
        match atom {
            ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Ground => grounds += 1,
            ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Color => colors += 1,
            ClauseAtom::GrammarMarker { marker_id, .. } => {
                background |= matches!(
                    marker_id,
                    crate::MarkerId::JaBackground | crate::MarkerId::EnBackground
                );
            }
            ClauseAtom::FunctionWord { .. } => {}
            ClauseAtom::UnresolvedDiagnostic(diagnostic)
                if diagnostic.kind == NeutralDiagnosticKind::Unknown && !diagnostic.recognized => {}
            _ => return None,
        }
    }
    match (grounds, colors, background) {
        (1, 0, false) => Some(SemanticDeliveryOwner::Ground),
        (0, 1, true) => Some(SemanticDeliveryOwner::Background),
        _ => None,
    }
}

fn patchable_unresolved_clause_spans(
    semantic_document: &SemanticDocumentResult,
    unresolved_clause_spans: &[SourceSpan],
) -> Vec<SourceSpan> {
    semantic_document
        .instruction_association
        .association
        .clause_stream
        .clauses
        .iter()
        .filter(|clause| unresolved_clause_spans.contains(&clause.span))
        .filter(|clause| {
            let has_primitive_or_ground = clause.atoms.iter().any(|atom| {
                matches!(
                    atom,
                    ClauseAtom::CoreRole(term)
                        if matches!(term.role, CoreRoleKind::Primitive | CoreRoleKind::Ground)
                )
            });
            let has_color = clause.atoms.iter().any(|atom| {
                matches!(atom, ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Color)
            });
            let has_background = clause.atoms.iter().any(|atom| {
                matches!(
                    atom,
                    ClauseAtom::GrammarMarker {
                        marker_id: crate::MarkerId::JaBackground | crate::MarkerId::EnBackground,
                        ..
                    }
                )
            });
            has_primitive_or_ground || has_color && has_background
        })
        .map(|clause| clause.span)
        .collect()
}

fn unresolved_clause_spans(semantic_document: &SemanticDocumentResult) -> Vec<SourceSpan> {
    let unresolved_spans = semantic_document
        .instruction_association
        .association
        .issues
        .iter()
        .filter(|issue| issue.kind == SemanticAssociationIssueKind::UpstreamUnknown)
        .filter_map(|issue| issue.upstream_diagnostic.as_ref())
        .filter(|diagnostic| {
            diagnostic.kind == NeutralDiagnosticKind::Unknown && !diagnostic.recognized
        })
        .map(|diagnostic| diagnostic.span)
        .collect::<Vec<_>>();
    semantic_document
        .instruction_association
        .association
        .clause_stream
        .clauses
        .iter()
        .filter(|clause| {
            unresolved_spans.iter().any(|span| {
                clause.span.start_byte <= span.start_byte && span.end_byte <= clause.span.end_byte
            })
        })
        .map(|clause| clause.span)
        .collect()
}

fn spans_share_clause(spans: &[SourceSpan], clauses: &[SourceSpan]) -> bool {
    !spans.is_empty()
        && clauses.iter().any(|clause| {
            spans.iter().all(|span| {
                clause.start_byte <= span.start_byte && span.end_byte <= clause.end_byte
            })
        })
}

fn span_is_in_clause(span: SourceSpan, clauses: &[SourceSpan]) -> bool {
    clauses
        .iter()
        .any(|clause| clause.start_byte <= span.start_byte && span.end_byte <= clause.end_byte)
}

fn deferred_continuation_clause_spans(
    semantic_document: &SemanticDocumentResult,
    patchable_clause_spans: &[SourceSpan],
) -> Vec<SourceSpan> {
    semantic_document
        .continuation_issues
        .iter()
        .filter(|issue| {
            matches!(
                &issue.causal_provenance,
                SemanticIssueCausalProvenance::UpstreamDiagnostics(causes)
                    if !causes.is_empty()
                        && causes.iter().all(|cause| {
                            span_is_in_clause(cause.span, patchable_clause_spans)
                        })
            )
        })
        .filter_map(|issue| {
            semantic_document
                .instruction_association
                .association
                .clause_stream
                .clauses
                .iter()
                .find(|clause| {
                    clause.span.start_byte <= issue.marker.span.start_byte
                        && issue.predicate_span.end_byte <= clause.span.end_byte
                })
                .map(|clause| clause.span)
        })
        .collect()
}

const fn neutral_diagnostic_kind_key(kind: NeutralDiagnosticKind) -> &'static str {
    match kind {
        NeutralDiagnosticKind::Hole => "hole",
        NeutralDiagnosticKind::Conflict => "conflict",
        NeutralDiagnosticKind::Unknown => "unknown",
    }
}

fn project_continuation_issues(
    issues: &[SemanticContinuationIssue],
    deferred_clause_spans: &[SourceSpan],
    projection: &mut Projection,
) {
    let exclusive_claims = exclusive_continuation_claim_groups(issues);
    let exclusive_issue_indices = exclusive_claims
        .values()
        .filter(|group| group.issue_indices.len() > 1)
        .flat_map(|group| group.issue_indices.iter().copied())
        .collect::<Vec<_>>();
    let mut groups = BTreeMap::<(usize, usize), ContinuationIssueProjection>::new();
    for (issue_index, issue) in issues.iter().enumerate() {
        if exclusive_issue_indices.contains(&issue_index)
            || span_is_in_clause(issue.marker.span, deferred_clause_spans)
        {
            continue;
        }
        let group = groups
            .entry((issue.marker.span.start_byte, issue.marker.span.end_byte))
            .or_default();
        group.kinds.push(issue.kind.as_str().to_owned());
        group
            .members
            .push(format!("issue:{issue_index}={}", issue.kind.as_str()));
        group.members.push(format!(
            "head:{issue_index}={}",
            semantic_head_key(&issue.instruction.entity.head)
        ));
        for (predicate_index, predicate) in instruction_predicate_keys(&issue.instruction)
            .into_iter()
            .enumerate()
        {
            group.members.push(format!(
                "predicate:{issue_index}:{predicate_index}={predicate}"
            ));
        }
        for (candidate_index, candidate) in issue.candidate_targets.iter().enumerate() {
            group.members.push(format!(
                "candidate:{issue_index}:{candidate_index}={}",
                continuation_target_key(candidate)
            ));
        }
        group.conflict |= matches!(
            issue.kind,
            SemanticContinuationIssueKind::AmbiguousTarget
                | SemanticContinuationIssueKind::ConflictingPredicate
        );
    }

    for ((start_byte, end_byte), group) in groups {
        let mut kinds = Vec::new();
        for kind in group.kinds {
            if !kinds.contains(&kind) {
                kinds.push(kind);
            }
        }
        let kind = if kinds.len() == 1 {
            kinds.pop().expect("one continuation issue kind")
        } else {
            format!("continuation_issue_set:{}", kinds.join(","))
        };
        let span = Some(SourceSpan {
            start_byte,
            end_byte,
        });
        if group.conflict {
            add_ordered_conflict(projection, &kind, span, group.members);
        } else {
            add_blocking_with_members(projection, &kind, span, group.members);
        }
    }

    for group in exclusive_claims
        .values()
        .filter(|group| group.issue_indices.len() > 1)
    {
        let claim_owner = exclusive_claim_owner(group, issues);
        let mut members = vec![format!(
            "owner={}",
            claim_owner.map_or("invalid", SemanticDeliveryOwner::as_str)
        )];
        for issue_index in &group.issue_indices {
            let issue = &issues[*issue_index];
            members.push(format!("issue:{issue_index}={}", issue.kind.as_str()));
            members.push(format!(
                "head:{issue_index}={}",
                semantic_head_key(&issue.instruction.entity.head)
            ));
            members.push(format!(
                "marker:{issue_index}={}:{}",
                issue.marker.span.start_byte, issue.marker.span.end_byte
            ));
            for (_, predicate) in
                instruction_predicate_deliveries_for_span(&issue.instruction, group.claim_span)
            {
                members.push(format!("predicate:{issue_index}={predicate}"));
            }
            for (candidate_index, candidate) in issue.candidate_targets.iter().enumerate() {
                members.push(format!(
                    "candidate:{issue_index}:{candidate_index}={}",
                    continuation_target_key(candidate)
                ));
            }
        }
        let span = Some(group.claim_span);
        if claim_owner.is_some() {
            add_ordered_conflict(
                projection,
                SemanticContinuationIssueKind::AmbiguousTarget.as_str(),
                span,
                members,
            );
        } else {
            add_blocking_with_members(
                projection,
                "continuation_claim_owner_integrity",
                span,
                members,
            );
        }
    }
}

fn exclusive_continuation_claim_groups(
    issues: &[SemanticContinuationIssue],
) -> BTreeMap<ContinuationClaimKey, ExclusiveContinuationClaimProjection> {
    let mut groups = BTreeMap::new();
    for (issue_index, issue) in issues.iter().enumerate() {
        let Some(claim_spans) = exclusive_continuation_issue_claim_spans(issue) else {
            continue;
        };
        for claim_span in claim_spans {
            let group = groups
                .entry((claim_span.start_byte, claim_span.end_byte))
                .or_insert_with(|| ExclusiveContinuationClaimProjection {
                    claim_span: *claim_span,
                    issue_indices: Vec::new(),
                });
            group.issue_indices.push(issue_index);
        }
    }
    groups
}

fn exclusive_claim_owner(
    group: &ExclusiveContinuationClaimProjection,
    issues: &[SemanticContinuationIssue],
) -> Option<SemanticDeliveryOwner> {
    let mut owner = None;
    for issue_index in &group.issue_indices {
        let deliveries = instruction_predicate_deliveries_for_span(
            &issues[*issue_index].instruction,
            group.claim_span,
        );
        let [(candidate, _)] = deliveries.as_slice() else {
            return None;
        };
        if owner.is_some_and(|owner| owner != *candidate) {
            return None;
        }
        owner = Some(*candidate);
    }
    owner
}

fn instruction_predicate_deliveries_for_span(
    instruction: &SemanticInstruction,
    claim_span: SourceSpan,
) -> Vec<(SemanticDeliveryOwner, String)> {
    let mut projected = Projection::default();
    project_instruction(instruction, &mut projected);
    projected
        .deliveries
        .into_iter()
        .filter(|delivery| delivery.span == Some(claim_span))
        .filter(|delivery| {
            !matches!(
                delivery.identity.owner,
                SemanticDeliveryOwner::EntityHead | SemanticDeliveryOwner::MacroParameter
            )
        })
        .map(|delivery| {
            (
                delivery.identity.owner,
                format!(
                    "{}:{}",
                    delivery.identity.owner.as_str(),
                    delivery.identity.canonical_key
                ),
            )
        })
        .collect()
}

fn semantic_head_key(head: &SemanticHead) -> String {
    match head {
        SemanticHead::Primitive(term) => format!("primitive:{}", term_key(term)),
        SemanticHead::MacroInvocation(head) => format!(
            "macro:{}@{}#{}",
            head.qualified_name, head.definition_version, head.definition_digest
        ),
    }
}

fn instruction_predicate_keys(instruction: &SemanticInstruction) -> Vec<String> {
    let mut projected = Projection::default();
    project_instruction(instruction, &mut projected);
    projected.deliveries.sort_by_key(|delivery| {
        let span = delivery
            .span
            .expect("instruction delivery has a source span");
        (span.start_byte, span.end_byte)
    });
    projected
        .deliveries
        .into_iter()
        .filter(|delivery| {
            !matches!(
                delivery.identity.owner,
                SemanticDeliveryOwner::EntityHead | SemanticDeliveryOwner::MacroParameter
            )
        })
        .map(|delivery| {
            format!(
                "{}:{}",
                delivery.identity.owner.as_str(),
                delivery.identity.canonical_key
            )
        })
        .collect()
}

fn continuation_target_key(target: &SemanticContinuationTarget) -> String {
    match target {
        SemanticContinuationTarget::Primitive(identity) => {
            format!("primitive:{}:{}", identity.category, identity.id)
        }
        SemanticContinuationTarget::MacroInvocation {
            qualified_name,
            definition_version,
            definition_digest,
        } => format!("macro:{qualified_name}@{definition_version}#{definition_digest}"),
    }
}

fn project_instruction_excluding_claims(
    instruction: &SemanticInstruction,
    claims: &BTreeMap<ContinuationClaimKey, ExclusiveContinuationClaimProjection>,
    issues: &[SemanticContinuationIssue],
    projection: &mut Projection,
) {
    let mut restored = Projection::default();
    project_instruction(instruction, &mut restored);
    projection
        .deliveries
        .extend(restored.deliveries.into_iter().filter(|delivery| {
            !claims.values().any(|group| {
                group.issue_indices.len() > 1
                    && delivery.span == Some(group.claim_span)
                    && exclusive_claim_owner(group, issues)
                        .is_some_and(|owner| delivery.identity.owner == owner)
            })
        }));
}

fn project_instruction(instruction: &crate::SemanticInstruction, projection: &mut Projection) {
    if let Some(target) = &instruction.fill_target {
        let meaning = crate::semantic_instruction::semantic_fill_target_value(target).to_string();
        for source in target.sources() {
            add_explicit(
                projection,
                source.span,
                SemanticDeliveryOwner::FillTarget,
                meaning.clone(),
            );
        }
    }
    if let Some(constraint) = &instruction.entity.shape_constraint {
        for source in
            std::iter::once(&constraint.provenance).chain(&constraint.additional_provenance)
        {
            add_explicit(
                projection,
                source.span,
                SemanticDeliveryOwner::ShapeConstraint,
                format!(
                    "regular:{};sides:{:?}",
                    constraint.value.regular, constraint.value.sides
                ),
            );
        }
    }
    match &instruction.entity.head {
        SemanticHead::Primitive(term) => {
            add_term_explicit(projection, SemanticDeliveryOwner::EntityHead, term)
        }
        SemanticHead::MacroInvocation(head) => {
            add_explicit(
                projection,
                head.provenance.source.span,
                SemanticDeliveryOwner::EntityHead,
                format!(
                    "macro:{}@{}#{}",
                    head.qualified_name, head.definition_version, head.definition_digest
                ),
            );
            for parameter in &head.parameters {
                add_explicit(
                    projection,
                    parameter.provenance.span,
                    SemanticDeliveryOwner::MacroParameter,
                    format!(
                        "{}={}",
                        parameter.name,
                        semantic_macro_parameter_value_key(&parameter.value)
                    ),
                );
            }
        }
    }
    if let Some(sequence) = &instruction.sequence {
        add_term_explicit(
            projection,
            SemanticDeliveryOwner::SequenceOperator,
            &sequence.operator,
        );
        for item in &sequence.items {
            add_term_explicit(projection, SemanticDeliveryOwner::SequenceItem, item);
        }
        if let Some(quantity) = &sequence.quantity {
            add_explicit(
                projection,
                quantity.provenance.span,
                SemanticDeliveryOwner::Quantity,
                quantity.value.to_string(),
            );
        }
        for marker in &sequence.markers {
            add_syntax(projection, marker.span, "sequence_grammar");
        }
    }
    for (owner, term) in [
        (
            SemanticDeliveryOwner::Color,
            instruction.entity.color.as_ref(),
        ),
        (
            SemanticDeliveryOwner::Touch,
            instruction.entity.touch.as_ref(),
        ),
        (
            SemanticDeliveryOwner::Continuity,
            instruction.entity.continuity.as_ref(),
        ),
        (
            SemanticDeliveryOwner::Angle,
            instruction.entity.angle.as_ref(),
        ),
        (
            SemanticDeliveryOwner::SurfaceQuality,
            instruction.entity.surface.quality.as_ref(),
        ),
        (
            SemanticDeliveryOwner::SurfaceIntensity,
            instruction.entity.surface.intensity.as_ref(),
        ),
        (
            SemanticDeliveryOwner::FluctuationAmplitude,
            instruction.entity.fluctuation.amplitude.as_ref(),
        ),
        (
            SemanticDeliveryOwner::FluctuationFrequency,
            instruction.entity.fluctuation.frequency.as_ref(),
        ),
        (
            SemanticDeliveryOwner::InkSpread,
            instruction.entity.fluctuation.spread.as_ref(),
        ),
        (
            SemanticDeliveryOwner::FluctuationQuality,
            instruction.entity.fluctuation.quality.as_ref(),
        ),
        (
            SemanticDeliveryOwner::ProportionAspect,
            instruction.entity.proportion.aspect.as_ref(),
        ),
        (
            SemanticDeliveryOwner::ProportionWidthExtent,
            instruction.entity.proportion.width_extent.as_ref(),
        ),
        (
            SemanticDeliveryOwner::ProportionArcForm,
            instruction.entity.proportion.arc_form.as_ref(),
        ),
        (SemanticDeliveryOwner::Action, instruction.action.as_ref()),
        (
            SemanticDeliveryOwner::LayoutDirection,
            instruction.layout_direction.as_ref(),
        ),
        (
            SemanticDeliveryOwner::Position,
            instruction.position.as_ref(),
        ),
    ] {
        if let Some(term) = term {
            add_term_explicit(projection, owner, term);
        }
    }
    for term in &instruction.entity.additional_width_extents {
        add_term_explicit(
            projection,
            SemanticDeliveryOwner::ProportionWidthExtent,
            term,
        );
    }
    if let Some(quantity) = &instruction.entity.quantity {
        add_explicit(
            projection,
            quantity.provenance.span,
            SemanticDeliveryOwner::Quantity,
            quantity.value.to_string(),
        );
    }
    if let Some(thinness) = &instruction.entity.thinness {
        add_explicit(
            projection,
            thinness.provenance.span,
            SemanticDeliveryOwner::Thinness,
            thinness.value.as_str().to_owned(),
        );
    }
    for relative_scale in instruction
        .entity
        .relative_scale
        .iter()
        .chain(&instruction.entity.additional_relative_scales)
    {
        add_explicit(
            projection,
            relative_scale.provenance.span,
            SemanticDeliveryOwner::RelativeScale,
            relative_scale.value.as_str().to_owned(),
        );
    }
    for geometry in instruction
        .entity
        .explicit_geometry
        .iter()
        .chain(&instruction.entity.additional_explicit_geometries)
    {
        add_explicit(
            projection,
            geometry.source().span,
            SemanticDeliveryOwner::ExplicitGeometry,
            compact_json(&crate::semantic_association::semantic_explicit_geometry_value(geometry)),
        );
    }
    if let Some(position) = &instruction.entity.numeric_position {
        add_explicit(
            projection,
            position.source().span,
            SemanticDeliveryOwner::NumericPosition,
            compact_json(&crate::semantic_association::semantic_numeric_position_value(position)),
        );
    }
    if let Some(relation) = &instruction.relation {
        add_explicit(
            projection,
            relation.provenance.span,
            SemanticDeliveryOwner::Relation,
            match (relation.target_endpoint, relation.target_path_selection) {
                (None, None) => {
                    format!("{}:{}", relation.kind.as_str(), relation.reference.as_str())
                }
                (Some(endpoint), None) => format!(
                    "{}:{}:{}",
                    relation.kind.as_str(),
                    relation.reference.as_str(),
                    serde_json::to_string(&endpoint).expect("closed endpoint")
                ),
                (None, Some(selection)) => format!(
                    "{}:{}:{}",
                    relation.kind.as_str(),
                    relation.reference.as_str(),
                    serde_json::to_string(&selection).expect("closed target path selection")
                ),
                (Some(_), Some(_)) => unreachable!("semantic relation target is exclusive"),
            },
        );
    }
}

fn add_term_explicit(
    projection: &mut Projection,
    owner: SemanticDeliveryOwner,
    term: &SemanticTerm,
) {
    add_explicit(
        projection,
        term.provenance.source.span,
        owner,
        term_key(term),
    );
}

fn term_key(term: &SemanticTerm) -> String {
    format!("{}:{}", term.identity.category, term.identity.id)
}

fn semantic_macro_parameter_value_key(value: &SemanticMacroParameterValue) -> String {
    match value {
        SemanticMacroParameterValue::ExactDecimal(value) => {
            format!("exact_decimal:{}:{}", value.coefficient(), value.scale())
        }
        SemanticMacroParameterValue::Integer(value) => format!("integer:{value}"),
        SemanticMacroParameterValue::Number(value) => {
            format!("number:{}", compact_json(&finite_number(*value)))
        }
        SemanticMacroParameterValue::SemanticRef(identity) => {
            format!("semantic_ref:{}:{}", identity.category, identity.id)
        }
    }
}

fn owned_occurrence_key(occurrence: &OwnedSemanticOccurrence) -> String {
    match occurrence {
        OwnedSemanticOccurrence::ShapeConstraint(value) => {
            format!("shape_constraint:{:?}", value.value)
        }
        OwnedSemanticOccurrence::Head(SemanticHead::Primitive(term)) => {
            format!("head:{}", term_key(term))
        }
        OwnedSemanticOccurrence::Head(SemanticHead::MacroInvocation(head)) => format!(
            "macro:{}@{}#{}",
            head.qualified_name, head.definition_version, head.definition_digest
        ),
        OwnedSemanticOccurrence::MacroDiagnostic(provenance) => format!(
            "macro_diagnostic:{}:{}",
            provenance.ordinal,
            provenance.qualified_name.as_deref().unwrap_or("unresolved")
        ),
        OwnedSemanticOccurrence::Color(term)
        | OwnedSemanticOccurrence::Touch(term)
        | OwnedSemanticOccurrence::Continuity(term)
        | OwnedSemanticOccurrence::Angle(term)
        | OwnedSemanticOccurrence::Surface(term)
        | OwnedSemanticOccurrence::Fluctuation(term)
        | OwnedSemanticOccurrence::Proportion(term) => term_key(term),
        OwnedSemanticOccurrence::Quantity(quantity) => {
            format!("quantity:{}", quantity.value)
        }
        OwnedSemanticOccurrence::Thinness(thinness) => {
            format!("thinness:{}", thinness.value.as_str())
        }
        OwnedSemanticOccurrence::RelativeScale(relative_scale) => {
            format!("relative_scale:{}", relative_scale.value.as_str())
        }
        OwnedSemanticOccurrence::ExplicitGeometry(geometry) => format!(
            "explicit_geometry:{}",
            compact_json(&crate::semantic_association::semantic_explicit_geometry_value(geometry))
        ),
        OwnedSemanticOccurrence::NumericPosition(position) => format!(
            "numeric_position:{}",
            compact_json(&crate::semantic_association::semantic_numeric_position_value(position))
        ),
    }
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
                        SemanticDeliveryOwner::ExpandedNode,
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

fn project_expanded_deliveries(
    expansion: &MacroExpansionResult,
    owners: &SemanticMacroExecutionOwners,
    projection: &mut Projection,
) -> Result<(), MacroExpansionDiagnosticKind> {
    let mut seen_semantic_ordinals = BTreeSet::new();
    for invocation in &expansion.expanded {
        let mut matches = owners.owners().iter().filter(|owner| {
            owner.source_invocation_index == invocation.provenance.invocation_index
                && owner.source_ordinal == invocation.provenance.invocation_ordinal
        });
        let Some(owner) = matches.next() else {
            return Err(MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch);
        };
        if matches.next().is_some()
            || !seen_semantic_ordinals.insert(owner.semantic_ordinal)
            || validate_expanded_invocation_owner(owners, owner, invocation, expansion).is_err()
        {
            return Err(MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch);
        }
        for node in flatten_nodes(&invocation.nodes) {
            let descriptor = compact_json(&node_value(node, owners, owner)?);
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
                identity: SemanticDeliveryIdentity {
                    owner: SemanticDeliveryOwner::ExpandedNode,
                    canonical_key: descriptor.clone(),
                },
                descriptor,
                span: Some(provenance.invocation.source_span),
                source_independent: true,
            });
        }
    }
    Ok(())
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

fn add_explicit(
    projection: &mut Projection,
    span: SourceSpan,
    owner: SemanticDeliveryOwner,
    canonical_key: String,
) {
    let descriptor = format!("{}|{canonical_key}", owner.as_str());
    projection.deliveries.push(SemanticDelivery {
        id: ranged_identity("explicit", &descriptor, span, ""),
        kind: SemanticDeliveryKind::Explicit,
        identity: SemanticDeliveryIdentity {
            owner,
            canonical_key,
        },
        descriptor,
        span: Some(span),
        source_independent: true,
    });
}

fn add_syntax(projection: &mut Projection, span: SourceSpan, descriptor: &str) {
    projection.deliveries.push(SemanticDelivery {
        id: ranged_identity("syntax", descriptor, span, ""),
        kind: SemanticDeliveryKind::SyntaxOnly,
        identity: SemanticDeliveryIdentity {
            owner: SemanticDeliveryOwner::SyntaxOnly,
            canonical_key: descriptor.to_owned(),
        },
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
    expected_owner: SemanticDeliveryOwner,
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
        expected_owner,
        upstream_diagnostic_identity: upstream,
    });
    projection.deliveries.push(SemanticDelivery {
        id,
        kind: SemanticDeliveryKind::Hole,
        identity: SemanticDeliveryIdentity {
            owner: SemanticDeliveryOwner::TypedIssue,
            canonical_key: format!("{kind}|expects={}", expected_owner.as_str()),
        },
        descriptor: format!("{kind}|expects={}", expected_owner.as_str()),
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
        identity: SemanticDeliveryIdentity {
            owner: SemanticDeliveryOwner::TypedIssue,
            canonical_key: payload.clone(),
        },
        descriptor: payload,
        span,
        source_independent: true,
    });
}

fn add_ordered_conflict(
    projection: &mut Projection,
    kind: &str,
    span: Option<SourceSpan>,
    candidates: Vec<String>,
) {
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
        identity: SemanticDeliveryIdentity {
            owner: SemanticDeliveryOwner::TypedIssue,
            canonical_key: payload.clone(),
        },
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
        identity: SemanticDeliveryIdentity {
            owner: SemanticDeliveryOwner::TypedIssue,
            canonical_key: kind.to_owned(),
        },
        descriptor: kind.to_owned(),
        span,
        source_independent: false,
    });
}

fn add_blocking_with_members(
    projection: &mut Projection,
    kind: &str,
    span: Option<SourceSpan>,
    members: Vec<String>,
) {
    let payload = format!("{kind}|{}", members.join(","));
    let id = span.map_or_else(
        || identity("blocking", payload.as_bytes()),
        |span| ranged_identity("blocking", kind, span, &payload),
    );
    projection.blocking.push(CompilerBlockingDiagnostic {
        id: id.clone(),
        kind: kind.to_owned(),
        span,
    });
    projection.deliveries.push(SemanticDelivery {
        id,
        kind: SemanticDeliveryKind::BlockingDiagnostic,
        identity: SemanticDeliveryIdentity {
            owner: SemanticDeliveryOwner::TypedIssue,
            canonical_key: payload.clone(),
        },
        descriptor: payload,
        span,
        source_independent: true,
    });
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
}

fn summarize(deliveries: &[SemanticDelivery]) -> DeliverySummary {
    let mut summary = DeliverySummary::default();
    for delivery in deliveries {
        summary.add(delivery.kind);
    }
    summary
}

fn structured_semantic_occurrence_bytes(deliveries: &[SemanticDelivery]) -> Vec<u8> {
    let mut identities = deliveries
        .iter()
        .filter(|delivery| {
            delivery.kind == SemanticDeliveryKind::Explicit
                && delivery.identity.owner != SemanticDeliveryOwner::ExpandedNode
        })
        .map(|delivery| delivery.identity.clone())
        .collect::<Vec<_>>();
    identities.sort();

    let mut bytes = b"inku.structured-semantic-occurrences.v1".to_vec();
    for identity in identities {
        append_field(&mut bytes, identity.owner.as_str().as_bytes());
        append_field(&mut bytes, identity.canonical_key.as_bytes());
    }
    bytes
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
    structured_semantic_occurrence_digest: String,
    canonical_bytes: Option<&[u8]>,
    semantic_source_provenance_digest: Option<String>,
    seeds: &[MacroSeed],
    expanded_meaning_digest: Option<String>,
    expanded_generated_provenance_digest: Option<String>,
    state: CompilerLockState,
) -> TypedDdlCompilerLock {
    let canonical_pre_expansion_digest = canonical_bytes.map(sha256_hex);
    let has_structured_meaning = canonical_pre_expansion_digest.is_some();
    let definition_identities = if has_structured_meaning {
        definition_identities(document, definitions)
    } else {
        Vec::new()
    };
    let macro_seeds = if has_structured_meaning {
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
        structured_semantic_occurrence_digest,
        canonical_pre_expansion_digest,
        semantic_source_provenance_digest,
        geometry_policy_id: GEOMETRY_RESOLUTION_POLICY_ID,
        geometry_policy_digest: geometry_resolution_policy_digest(),
        composition_seed: if has_structured_meaning {
            composition_seed
        } else {
            None
        },
        definition_identities,
        macro_seeds,
        expanded_meaning_digest,
        expanded_generated_provenance_digest,
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
    append_field(
        &mut bytes,
        lock.structured_semantic_occurrence_digest.as_bytes(),
    );
    append_optional(&mut bytes, lock.canonical_pre_expansion_digest.as_deref());
    append_optional(
        &mut bytes,
        lock.semantic_source_provenance_digest.as_deref(),
    );
    append_field(&mut bytes, lock.geometry_policy_id.as_bytes());
    append_field(&mut bytes, lock.geometry_policy_digest.as_bytes());
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
    append_optional(
        &mut bytes,
        lock.expanded_generated_provenance_digest.as_deref(),
    );
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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Stage15InputBoundaryError {
    VisibleSourceDigest,
    SourceLanguage,
    DefinitionProjection,
    ConsumedDefinitionIdentity,
}

pub(crate) fn validate_stage15_input_boundary(
    document: &NormalizedDdlDocument,
    ast: &SemanticDocumentAst,
    lock: &TypedDdlCompilerLock,
    binding: &MacroParameterBindingResult,
    execution_owners: &SemanticMacroExecutionOwners,
) -> Result<(), Stage15InputBoundaryError> {
    if sha256_hex(document.source().as_bytes()) != lock.visible_source_digest {
        return Err(Stage15InputBoundaryError::VisibleSourceDigest);
    }
    if semantic_source_occurrences(ast)
        .iter()
        .any(|occurrence| occurrence.language != document.language())
    {
        return Err(Stage15InputBoundaryError::SourceLanguage);
    }
    if document.macro_locks().len() != lock.definition_identities.len()
        || document
            .macro_locks()
            .iter()
            .zip(&lock.definition_identities)
            .any(|(sidecar, projected)| {
                sidecar.qualified_name() != projected.qualified_name
                    || sidecar.version() != projected.version
                    || sidecar.digest() != projected.sidecar_digest
            })
    {
        return Err(Stage15InputBoundaryError::DefinitionProjection);
    }

    for owner in execution_owners.owners() {
        let Some(complete) = binding.complete.get(owner.binding_index) else {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        };
        let Some(resolved) = binding
            .macro_resolution
            .resolved
            .get(complete.invocation_index)
        else {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        };
        let qualified_name = complete.definition_identity.qualified_name();
        let Some(sidecar) = document
            .macro_locks()
            .iter()
            .find(|sidecar| sidecar.qualified_name() == qualified_name)
        else {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        };
        let Some(projected) = lock
            .definition_identities
            .iter()
            .find(|identity| identity.qualified_name == qualified_name)
        else {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        };
        let resolved_digest = complete.definition_identity.full_digest_hex();
        let sidecar_digest = format!("sha256:{resolved_digest}");
        if resolved.definition_identity != complete.definition_identity
            || resolved.lock.qualified_name != sidecar.qualified_name()
            || resolved.lock.version != sidecar.version()
            || resolved.lock.digest != sidecar.digest()
            || sidecar.version() != complete.definition_identity.version()
            || sidecar.digest() != sidecar_digest
            || projected.version != complete.definition_identity.version()
            || projected.sidecar_digest != sidecar_digest
            || projected.resolved_definition_digest.as_deref() != Some(resolved_digest)
        {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        }
    }
    Ok(())
}

pub(crate) fn validate_execution_projection_boundary(
    document: &NormalizedDdlDocument,
    ast: &SemanticDocumentAst,
    lock: &TypedDdlCompilerLock,
    binding: &MacroParameterBindingResult,
    execution_owners: &SemanticMacroExecutionOwners,
    definitions: &[MacroDefinition],
) -> Result<(), Stage15InputBoundaryError> {
    if sha256_hex(document.source().as_bytes()) != lock.visible_source_digest {
        return Err(Stage15InputBoundaryError::VisibleSourceDigest);
    }
    if semantic_source_occurrences(ast)
        .iter()
        .any(|occurrence| occurrence.language != document.language())
    {
        return Err(Stage15InputBoundaryError::SourceLanguage);
    }
    for sidecar in document.macro_locks() {
        let Some(identity) = definitions
            .iter()
            .filter_map(|definition| definition.identity().ok())
            .find(|identity| identity.qualified_name() == sidecar.qualified_name())
        else {
            return Err(Stage15InputBoundaryError::DefinitionProjection);
        };
        if identity.version() != sidecar.version()
            || format!("sha256:{}", identity.full_digest_hex()) != sidecar.digest()
        {
            return Err(Stage15InputBoundaryError::DefinitionProjection);
        }
    }
    for owner in execution_owners.owners() {
        let Some(complete) = binding.complete.get(owner.binding_index) else {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        };
        let Some(resolved) = binding
            .macro_resolution
            .resolved
            .get(complete.invocation_index)
        else {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        };
        let Some(sidecar) = document.macro_locks().iter().find(|sidecar| {
            sidecar.qualified_name() == complete.definition_identity.qualified_name()
        }) else {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        };
        if resolved.definition_identity != complete.definition_identity
            || resolved.lock.qualified_name != sidecar.qualified_name()
            || resolved.lock.version != sidecar.version()
            || resolved.lock.digest != sidecar.digest()
            || complete.definition_identity.version() != sidecar.version()
            || format!("sha256:{}", complete.definition_identity.full_digest_hex())
                != sidecar.digest()
        {
            return Err(Stage15InputBoundaryError::ConsumedDefinitionIdentity);
        }
    }
    Ok(())
}

pub(crate) fn semantic_source_occurrences(ast: &SemanticDocumentAst) -> Vec<&SourceOccurrence> {
    fn push_term<'a>(occurrences: &mut Vec<&'a SourceOccurrence>, term: &'a SemanticTerm) {
        occurrences.push(&term.provenance.source);
    }

    fn push_head<'a>(occurrences: &mut Vec<&'a SourceOccurrence>, head: &'a SemanticHead) {
        match head {
            SemanticHead::Primitive(term) => push_term(occurrences, term),
            SemanticHead::MacroInvocation(head) => {
                occurrences.push(&head.provenance.source);
                occurrences.extend(
                    head.parameters
                        .iter()
                        .map(|parameter| &parameter.provenance),
                );
            }
        }
    }

    fn push_geometry_value<'a>(
        occurrences: &mut Vec<&'a SourceOccurrence>,
        value: &'a crate::SemanticGeometryValue,
    ) {
        occurrences.push(&value.keyword_provenance);
        occurrences.push(&value.decimal.provenance);
    }

    fn push_entity<'a>(
        occurrences: &mut Vec<&'a SourceOccurrence>,
        entity: &'a crate::SemanticEntity,
    ) {
        push_head(occurrences, &entity.head);
        if let Some(constraint) = &entity.shape_constraint {
            occurrences.push(&constraint.provenance);
            occurrences.extend(&constraint.additional_provenance);
        }
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
            push_term(occurrences, term);
        }
        occurrences.extend(
            entity
                .additional_relative_scales
                .iter()
                .map(|value| &value.provenance),
        );
        occurrences.extend(
            [
                entity.quantity.as_ref().map(|value| &value.provenance),
                entity.thinness.as_ref().map(|value| &value.provenance),
                entity
                    .relative_scale
                    .as_ref()
                    .map(|value| &value.provenance),
            ]
            .into_iter()
            .flatten(),
        );
        for geometry in entity
            .explicit_geometry
            .iter()
            .chain(&entity.additional_explicit_geometries)
        {
            match geometry {
                crate::SemanticExplicitGeometry::Radius(value)
                | crate::SemanticExplicitGeometry::Diameter(value)
                | crate::SemanticExplicitGeometry::Length(value)
                | crate::SemanticExplicitGeometry::Side(value) => {
                    push_geometry_value(occurrences, value);
                }
                crate::SemanticExplicitGeometry::WidthHeight { width, height } => {
                    push_geometry_value(occurrences, width);
                    push_geometry_value(occurrences, height);
                }
                crate::SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => {
                    push_geometry_value(occurrences, chord);
                    push_geometry_value(occurrences, sagitta);
                }
            }
        }
        if let Some(position) = &entity.numeric_position {
            push_geometry_value(occurrences, &position.x);
            push_geometry_value(occurrences, &position.y);
        }
    }

    let mut occurrences = Vec::new();
    if let Some(background) = &ast.background {
        occurrences.extend(background.sources());
    }
    if let Some(ground) = &ast.ground {
        push_term(&mut occurrences, ground);
    }
    for instruction in &ast.instructions {
        if let Some(target) = &instruction.fill_target {
            occurrences.extend(target.sources());
        }
        push_entity(&mut occurrences, &instruction.entity);
        if let Some(direction) = &instruction.layout_direction {
            push_term(&mut occurrences, direction);
        }
        if let Some(action) = &instruction.action {
            push_term(&mut occurrences, action);
        }
        if let Some(position) = &instruction.position {
            push_term(&mut occurrences, position);
        }
        if let Some(relation) = &instruction.relation {
            occurrences.push(&relation.provenance);
        }
    }
    occurrences.extend(
        ast.coordinated_head_groups
            .iter()
            .flat_map(|group| group.markers.iter()),
    );
    for edge in &ast.group_predicates {
        if let Some(target) = &edge.fill_target {
            occurrences.extend(target.sources());
        }
        if let Some(action) = &edge.action {
            push_term(&mut occurrences, action);
        }
        if let Some(position) = &edge.position {
            push_term(&mut occurrences, position);
        }
    }
    for edge in &ast.continuations {
        push_head(&mut occurrences, &edge.reintroduced_head);
        occurrences.push(&edge.marker);
    }
    occurrences
}

/// Canonical source-bearing provenance for the complete returned semantic graph.
pub fn semantic_source_provenance_canonical_bytes(ast: &SemanticDocumentAst) -> Vec<u8> {
    let mut root = BTreeMap::new();
    root.insert("background".to_owned(), ast.background.as_ref().map(|background| {
        serde_json::json!({
            "head": source_occurrence_value(&background.head),
            "color": term_provenance_value(&background.color),
            "action": term_provenance_value(&background.action),
            "markers": background.markers.iter().map(source_occurrence_value).collect::<Vec<_>>()
        })
    }).unwrap_or(Value::Null));
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_SOURCE_PROVENANCE_SCHEMA_ID.to_owned()),
    );
    root.insert(
        "ground".to_owned(),
        ast.ground
            .as_ref()
            .map(term_provenance_value)
            .unwrap_or(Value::Null),
    );
    root.insert(
        "instructions".to_owned(),
        Value::Array(
            ast.instructions
                .iter()
                .map(instruction_provenance_value)
                .collect(),
        ),
    );
    root.insert(
        "coordinated_head_groups".to_owned(),
        Value::Array(
            ast.coordinated_head_groups
                .iter()
                .map(|group| {
                    let mut record = BTreeMap::new();
                    record.insert(
                        "member_instruction_indices".to_owned(),
                        Value::Array(
                            group
                                .member_instruction_indices
                                .iter()
                                .map(|index| Value::Number(Number::from(*index as u64)))
                                .collect(),
                        ),
                    );
                    record.insert(
                        "markers".to_owned(),
                        Value::Array(group.markers.iter().map(source_occurrence_value).collect()),
                    );
                    Value::Object(record.into_iter().collect())
                })
                .collect(),
        ),
    );
    root.insert(
        "group_predicates".to_owned(),
        Value::Array(
            ast.group_predicates
                .iter()
                .map(|edge| {
                    let mut record = BTreeMap::new();
                    if let Some(target) = &edge.fill_target {
                        record.insert("fill_target".to_owned(), serde_json::json!({
                            "meaning": crate::semantic_instruction::semantic_fill_target_value(target),
                            "sources": target.sources().into_iter().map(source_occurrence_value).collect::<Vec<_>>()
                        }));
                    }
                    record.insert(
                        "group_index".to_owned(),
                        Value::Number(Number::from(edge.group_index as u64)),
                    );
                    record.insert(
                        "action".to_owned(),
                        edge.action
                            .as_ref()
                            .map(term_provenance_value)
                            .unwrap_or(Value::Null),
                    );
                    record.insert(
                        "position".to_owned(),
                        edge.position
                            .as_ref()
                            .map(term_provenance_value)
                            .unwrap_or(Value::Null),
                    );
                    Value::Object(record.into_iter().collect())
                })
                .collect(),
        ),
    );
    root.insert(
        "continuations".to_owned(),
        Value::Array(
            ast.continuations
                .iter()
                .map(|edge| {
                    let mut record = BTreeMap::new();
                    record.insert("target".to_owned(), continuation_target_value(&edge.target));
                    record.insert(
                        "target_instruction_index".to_owned(),
                        Value::Number(Number::from(edge.target_instruction_index as u64)),
                    );
                    record.insert(
                        "reintroduced_head".to_owned(),
                        head_provenance_value(&edge.reintroduced_head),
                    );
                    record.insert("marker".to_owned(), source_occurrence_value(&edge.marker));
                    record.insert(
                        "predicate_span".to_owned(),
                        source_span_value(edge.predicate_span),
                    );
                    record.insert(
                        "consumed_upstream_spans".to_owned(),
                        Value::Array(
                            edge.consumed_upstream_spans
                                .iter()
                                .map(|span| source_span_value(*span))
                                .collect(),
                        ),
                    );
                    Value::Object(record.into_iter().collect())
                })
                .collect(),
        ),
    );
    serde_json::to_vec(&root).expect("closed semantic provenance values serialize")
}

fn instruction_provenance_value(instruction: &SemanticInstruction) -> Value {
    let mut record = BTreeMap::new();
    if let Some(target) = &instruction.fill_target {
        record.insert("fill_target".to_owned(), serde_json::json!({
            "meaning": crate::semantic_instruction::semantic_fill_target_value(target),
            "sources": target.sources().into_iter().map(source_occurrence_value).collect::<Vec<_>>()
        }));
    }
    if let Some(direction) = &instruction.layout_direction {
        record.insert(
            "layout_direction".to_owned(),
            term_provenance_value(direction),
        );
    }
    record.insert(
        "entity".to_owned(),
        entity_provenance_value(&instruction.entity),
    );
    record.insert(
        "action".to_owned(),
        instruction
            .action
            .as_ref()
            .map(term_provenance_value)
            .unwrap_or(Value::Null),
    );
    record.insert(
        "position".to_owned(),
        instruction
            .position
            .as_ref()
            .map(term_provenance_value)
            .unwrap_or(Value::Null),
    );
    record.insert(
        "relation".to_owned(),
        instruction
            .relation
            .as_ref()
            .map(|relation| source_occurrence_value(&relation.provenance))
            .unwrap_or(Value::Null),
    );
    Value::Object(record.into_iter().collect())
}

fn entity_provenance_value(entity: &crate::SemanticEntity) -> Value {
    let mut record = BTreeMap::new();
    if !entity.additional_relative_scales.is_empty() {
        record.insert(
            "additional_relative_scales".to_owned(),
            Value::Array(
                entity
                    .additional_relative_scales
                    .iter()
                    .map(|value| source_occurrence_value(&value.provenance))
                    .collect(),
            ),
        );
    }
    if !entity.additional_explicit_geometries.is_empty() {
        record.insert(
            "additional_explicit_geometries".to_owned(),
            Value::Array(
                entity
                    .additional_explicit_geometries
                    .iter()
                    .map(explicit_geometry_provenance_value)
                    .collect(),
            ),
        );
    }
    if !entity.additional_width_extents.is_empty() {
        record.insert(
            "additional_width_extents".to_owned(),
            Value::Array(
                entity
                    .additional_width_extents
                    .iter()
                    .map(term_provenance_value)
                    .collect(),
            ),
        );
    }

    if let Some(constraint) = &entity.shape_constraint {
        record.insert(
            "shape_constraint".to_owned(),
            Value::Array(
                std::iter::once(&constraint.provenance)
                    .chain(&constraint.additional_provenance)
                    .map(source_occurrence_value)
                    .collect(),
            ),
        );
    }
    record.insert("head".to_owned(), head_provenance_value(&entity.head));
    for (field, term) in [
        ("color", entity.color.as_ref()),
        ("touch", entity.touch.as_ref()),
        ("continuity", entity.continuity.as_ref()),
        ("angle", entity.angle.as_ref()),
        ("surface_quality", entity.surface.quality.as_ref()),
        ("surface_intensity", entity.surface.intensity.as_ref()),
        (
            "fluctuation_amplitude",
            entity.fluctuation.amplitude.as_ref(),
        ),
        (
            "fluctuation_frequency",
            entity.fluctuation.frequency.as_ref(),
        ),
        ("fluctuation_quality", entity.fluctuation.quality.as_ref()),
        ("ink_spread", entity.fluctuation.spread.as_ref()),
        ("proportion_aspect", entity.proportion.aspect.as_ref()),
        (
            "proportion_width_extent",
            entity.proportion.width_extent.as_ref(),
        ),
        ("proportion_arc_form", entity.proportion.arc_form.as_ref()),
    ] {
        record.insert(
            field.to_owned(),
            term.map(term_provenance_value).unwrap_or(Value::Null),
        );
    }
    for (field, occurrence) in [
        (
            "quantity",
            entity.quantity.as_ref().map(|value| &value.provenance),
        ),
        (
            "thinness",
            entity.thinness.as_ref().map(|value| &value.provenance),
        ),
        (
            "relative_scale",
            entity
                .relative_scale
                .as_ref()
                .map(|value| &value.provenance),
        ),
    ] {
        record.insert(
            field.to_owned(),
            occurrence
                .map(source_occurrence_value)
                .unwrap_or(Value::Null),
        );
    }
    record.insert(
        "explicit_geometry".to_owned(),
        entity
            .explicit_geometry
            .as_ref()
            .map(explicit_geometry_provenance_value)
            .unwrap_or(Value::Null),
    );
    record.insert(
        "numeric_position".to_owned(),
        entity
            .numeric_position
            .as_ref()
            .map(numeric_position_provenance_value)
            .unwrap_or(Value::Null),
    );
    Value::Object(record.into_iter().collect())
}

fn explicit_geometry_provenance_value(geometry: &crate::SemanticExplicitGeometry) -> Value {
    let values = match geometry {
        crate::SemanticExplicitGeometry::Radius(value)
        | crate::SemanticExplicitGeometry::Diameter(value)
        | crate::SemanticExplicitGeometry::Length(value)
        | crate::SemanticExplicitGeometry::Side(value) => vec![geometry_value_provenance(value)],
        crate::SemanticExplicitGeometry::WidthHeight { width, height } => vec![
            geometry_value_provenance(width),
            geometry_value_provenance(height),
        ],
        crate::SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => vec![
            geometry_value_provenance(chord),
            geometry_value_provenance(sagitta),
        ],
    };
    Value::Array(values)
}

fn numeric_position_provenance_value(position: &crate::SemanticNumericPosition) -> Value {
    Value::Array(vec![
        geometry_value_provenance(&position.x),
        geometry_value_provenance(&position.y),
    ])
}

fn geometry_value_provenance(value: &crate::SemanticGeometryValue) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "keyword".to_owned(),
        source_occurrence_value(&value.keyword_provenance),
    );
    record.insert(
        "decimal".to_owned(),
        source_occurrence_value(&value.decimal.provenance),
    );
    Value::Object(record.into_iter().collect())
}

fn head_provenance_value(head: &SemanticHead) -> Value {
    let mut record = BTreeMap::new();
    match head {
        SemanticHead::Primitive(term) => {
            record.insert("kind".to_owned(), Value::String("primitive".to_owned()));
            record.insert("provenance".to_owned(), term_provenance_value(term));
        }
        SemanticHead::MacroInvocation(head) => {
            record.insert(
                "kind".to_owned(),
                Value::String("macro_invocation".to_owned()),
            );
            record.insert(
                "source".to_owned(),
                source_occurrence_value(&head.provenance.source),
            );
            record.insert(
                "ordinal".to_owned(),
                Value::Number(Number::from(head.provenance.ordinal)),
            );
            record.insert(
                "qualified_name".to_owned(),
                head.provenance
                    .qualified_name
                    .as_ref()
                    .map(|value| Value::String(value.clone()))
                    .unwrap_or(Value::Null),
            );
            record.insert(
                "parameters".to_owned(),
                Value::Array(
                    head.parameters
                        .iter()
                        .map(|parameter| {
                            let mut value = BTreeMap::new();
                            value.insert("name".to_owned(), Value::String(parameter.name.clone()));
                            value.insert(
                                "source".to_owned(),
                                source_occurrence_value(&parameter.provenance),
                            );
                            value.insert(
                                "source_asset_id".to_owned(),
                                parameter
                                    .source_asset_id
                                    .as_ref()
                                    .map(|item| Value::String(item.clone()))
                                    .unwrap_or(Value::Null),
                            );
                            value.insert(
                                "canonical_surface_ja".to_owned(),
                                parameter
                                    .canonical_surface_ja
                                    .as_ref()
                                    .map(|item| Value::String(item.clone()))
                                    .unwrap_or(Value::Null),
                            );
                            Value::Object(value.into_iter().collect())
                        })
                        .collect(),
                ),
            );
        }
    }
    Value::Object(record.into_iter().collect())
}

fn term_provenance_value(term: &SemanticTerm) -> Value {
    let provenance = &term.provenance;
    let mut record = BTreeMap::new();
    record.insert(
        "source".to_owned(),
        source_occurrence_value(&provenance.source),
    );
    record.insert(
        "asset_id".to_owned(),
        Value::String(provenance.asset_id.clone()),
    );
    record.insert(
        "category_key".to_owned(),
        Value::String(provenance.category_key.clone()),
    );
    record.insert(
        "canonical_surface_ja".to_owned(),
        Value::String(provenance.canonical_surface_ja.clone()),
    );
    Value::Object(record.into_iter().collect())
}

fn source_occurrence_value(occurrence: &SourceOccurrence) -> Value {
    let mut record = BTreeMap::new();
    record.insert("span".to_owned(), source_span_value(occurrence.span));
    record.insert(
        "surface".to_owned(),
        Value::String(occurrence.surface.clone()),
    );
    record.insert(
        "language".to_owned(),
        Value::String(occurrence.language.as_str().to_owned()),
    );
    record.insert(
        "region_index".to_owned(),
        Value::Number(Number::from(occurrence.region_index as u64)),
    );
    record.insert(
        "clause_index".to_owned(),
        Value::Number(Number::from(occurrence.clause_index as u64)),
    );
    record.insert(
        "atom_index".to_owned(),
        Value::Number(Number::from(occurrence.atom_index as u64)),
    );
    Value::Object(record.into_iter().collect())
}

fn source_span_value(span: SourceSpan) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "start_byte".to_owned(),
        Value::Number(Number::from(span.start_byte as u64)),
    );
    record.insert(
        "end_byte".to_owned(),
        Value::Number(Number::from(span.end_byte as u64)),
    );
    Value::Object(record.into_iter().collect())
}

/// Canonical generated provenance for the complete returned expanded graph.
pub fn expanded_generated_provenance_canonical_bytes(expansion: &MacroExpansionResult) -> Vec<u8> {
    let mut root = BTreeMap::new();
    root.insert(
        "schema".to_owned(),
        Value::String(EXPANDED_GENERATED_PROVENANCE_SCHEMA_ID.to_owned()),
    );
    root.insert(
        "invocations".to_owned(),
        Value::Array(
            expansion
                .expanded
                .iter()
                .map(expanded_invocation_provenance_value)
                .collect(),
        ),
    );
    serde_json::to_vec(&root).expect("closed generated provenance values serialize")
}

fn expanded_invocation_provenance_value(invocation: &ExpandedMacroInvocation) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "provenance".to_owned(),
        macro_invocation_provenance_value(&invocation.provenance),
    );
    record.insert(
        "nodes".to_owned(),
        Value::Array(
            invocation
                .nodes
                .iter()
                .map(generated_node_provenance_value)
                .collect(),
        ),
    );
    Value::Object(record.into_iter().collect())
}

fn generated_node_provenance_value(node: &ExpandedMacroNode) -> Value {
    let mut record = BTreeMap::new();
    let (kind, body) = match node {
        ExpandedMacroNode::Emit { .. } => ("emit", None),
        ExpandedMacroNode::Group { body, .. } => ("group", Some(body.as_slice())),
        ExpandedMacroNode::Anchor { .. } => ("anchor", None),
        ExpandedMacroNode::Relation { .. } => ("relation", None),
        ExpandedMacroNode::Transform { body, .. } => ("transform", Some(body.as_slice())),
    };
    record.insert("kind".to_owned(), Value::String(kind.to_owned()));
    record.insert(
        "provenance".to_owned(),
        generated_provenance_value(node.provenance()),
    );
    record.insert(
        "body".to_owned(),
        body.map(|nodes| Value::Array(nodes.iter().map(generated_node_provenance_value).collect()))
            .unwrap_or(Value::Null),
    );
    Value::Object(record.into_iter().collect())
}

fn generated_provenance_value(provenance: &GeneratedNodeProvenance) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "invocation".to_owned(),
        macro_invocation_provenance_value(&provenance.invocation),
    );
    record.insert(
        "generated_ordinal".to_owned(),
        Value::Number(Number::from(provenance.generated_ordinal)),
    );
    record.insert(
        "expansion_path".to_owned(),
        Value::Array(provenance.expansion_path.iter().map(path_value).collect()),
    );
    Value::Object(record.into_iter().collect())
}

fn macro_invocation_provenance_value(provenance: &crate::MacroInvocationProvenance) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "schema".to_owned(),
        Value::String(provenance.schema_id.to_owned()),
    );
    record.insert(
        "invocation_index".to_owned(),
        Value::Number(Number::from(provenance.invocation_index as u64)),
    );
    record.insert(
        "invocation_ordinal".to_owned(),
        Value::Number(Number::from(provenance.invocation_ordinal)),
    );
    record.insert(
        "source_span".to_owned(),
        source_span_value(provenance.source_span),
    );
    for (field, value) in [
        (
            "definition_qualified_name",
            provenance.definition_qualified_name.as_str(),
        ),
        ("definition_version", provenance.definition_version.as_str()),
        (
            "definition_full_digest",
            provenance.definition_full_digest.as_str(),
        ),
        ("seed_scheme_id", provenance.seed_scheme_id),
        ("seed_full_digest", provenance.seed_full_digest.as_str()),
    ] {
        record.insert(field.to_owned(), Value::String(value.to_owned()));
    }
    record.insert(
        "resolved_seed".to_owned(),
        Value::Number(Number::from(provenance.resolved_seed)),
    );
    record.insert(
        "effective_composition_seed".to_owned(),
        Value::Number(Number::from(provenance.effective_composition_seed)),
    );
    Value::Object(record.into_iter().collect())
}

/// Canonical expanded meaning bytes with source locators projected through the exact semantic
/// execution-owner mapping. Display and provenance fields remain excluded.
pub fn expanded_meaning_canonical_bytes(
    ast: &SemanticDocumentAst,
    expansion: &MacroExpansionResult,
) -> Result<Vec<u8>, MacroExpansionDiagnosticKind> {
    let owners = semantic_macro_execution_owners(ast, &expansion.parameter_binding)?;
    expanded_meaning_canonical_bytes_with_owners(&owners, expansion)
}

fn validate_expanded_execution_owners(
    owners: &SemanticMacroExecutionOwners,
    expansion: &MacroExpansionResult,
) -> Result<(), MacroExpansionDiagnosticKind> {
    if expansion.expanded.len() != owners.owners().len() {
        return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
    }
    for (owner, invocation) in owners.owners().iter().zip(&expansion.expanded) {
        validate_expanded_invocation_owner(owners, owner, invocation, expansion)?;
    }
    Ok(())
}

fn validate_expanded_invocation_owner(
    owners: &SemanticMacroExecutionOwners,
    owner: &SemanticMacroExecutionOwner,
    invocation: &ExpandedMacroInvocation,
    expansion: &MacroExpansionResult,
) -> Result<(), MacroExpansionDiagnosticKind> {
    let Some(binding) = expansion
        .parameter_binding
        .complete
        .get(owner.binding_index)
    else {
        return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
    };
    let Some(resolved) = expansion
        .parameter_binding
        .macro_resolution
        .resolved
        .get(binding.invocation_index)
    else {
        return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
    };
    let provenance = &invocation.provenance;
    if owner.source_invocation_index != binding.invocation_index
        || owner.source_ordinal != binding.invocation_ordinal
        || provenance.schema_id != crate::MACRO_EXPANSION_SCHEMA_ID
        || provenance.invocation_index != owner.source_invocation_index
        || provenance.invocation_ordinal != owner.source_ordinal
        || provenance.source_span != resolved.span
        || provenance.definition_qualified_name != binding.definition_identity.qualified_name()
        || provenance.definition_version != binding.definition_identity.version()
        || provenance.definition_full_digest != binding.definition_identity.full_digest_hex()
        || owners.semantic_ordinal_for_source(provenance.invocation_ordinal)
            != Some(owner.semantic_ordinal)
        || flatten_nodes(&invocation.nodes)
            .into_iter()
            .any(|node| node.provenance().invocation != *provenance)
    {
        return Err(MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch);
    }
    Ok(())
}

pub(crate) fn expanded_meaning_canonical_bytes_with_owners(
    owners: &SemanticMacroExecutionOwners,
    expansion: &MacroExpansionResult,
) -> Result<Vec<u8>, MacroExpansionDiagnosticKind> {
    if let Some(diagnostic) = expansion.diagnostics.first() {
        return Err(diagnostic.kind);
    }
    validate_expanded_execution_owners(owners, expansion)?;
    let invocations = owners
        .owners()
        .iter()
        .zip(&expansion.expanded)
        .map(|(owner, invocation)| {
            let mut record = BTreeMap::new();
            record.insert(
                "invocation_ordinal".to_owned(),
                Value::Number(Number::from(owner.semantic_ordinal)),
            );
            record.insert(
                "nodes".to_owned(),
                Value::Array(
                    invocation
                        .nodes
                        .iter()
                        .map(|node| node_value(node, owners, owner))
                        .collect::<Result<Vec<_>, _>>()?,
                ),
            );
            Ok(Value::Object(record.into_iter().collect()))
        })
        .collect::<Result<Vec<_>, MacroExpansionDiagnosticKind>>()?;
    let mut root = BTreeMap::new();
    root.insert("invocations".to_owned(), Value::Array(invocations));
    root.insert(
        "schema".to_owned(),
        Value::String(EXPANDED_MACRO_MEANING_SCHEMA_ID.to_owned()),
    );
    Ok(serde_json::to_vec(&root).expect("closed expanded values serialize"))
}

fn node_value(
    node: &ExpandedMacroNode,
    owners: &SemanticMacroExecutionOwners,
    owner: &SemanticMacroExecutionOwner,
) -> Result<Value, MacroExpansionDiagnosticKind> {
    let mut record = BTreeMap::new();
    match node {
        ExpandedMacroNode::Emit {
            binding, fields, ..
        } => {
            record.insert("kind".to_owned(), Value::String("emit".to_owned()));
            record.insert(
                "binding".to_owned(),
                binding
                    .as_ref()
                    .map(|target| target_value(target, owners, owner))
                    .transpose()?
                    .unwrap_or(Value::Null),
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
                Value::Array(
                    body.iter()
                        .map(|node| node_value(node, owners, owner))
                        .collect::<Result<Vec<_>, _>>()?,
                ),
            );
        }
        ExpandedMacroNode::Anchor { target, .. } => {
            record.insert("kind".to_owned(), Value::String("anchor".to_owned()));
            record.insert("target".to_owned(), target_value(target, owners, owner)?);
        }
        ExpandedMacroNode::Relation {
            kind,
            from,
            to,
            target_path_position,
            target_endpoint,
            ..
        } => {
            record.insert("kind".to_owned(), Value::String("relation".to_owned()));
            record.insert("relation".to_owned(), Value::String(kind.clone()));
            record.insert("from".to_owned(), target_value(from, owners, owner)?);
            record.insert("to".to_owned(), target_value(to, owners, owner)?);
            if let Some(endpoint) = target_endpoint {
                record.insert(
                    "target_endpoint".to_owned(),
                    serde_json::to_value(endpoint).expect("closed endpoint"),
                );
            }
            if let Some(position) = target_path_position {
                record.insert(
                    "target_path_position".to_owned(),
                    match position {
                        inku_score::TargetPathPosition::Exact(value) => finite_number(*value),
                        inku_score::TargetPathPosition::Selection(selection) => {
                            serde_json::to_value(selection).expect("closed target path selection")
                        }
                    },
                );
            }
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
                Value::Array(
                    body.iter()
                        .map(|node| node_value(node, owners, owner))
                        .collect::<Result<Vec<_>, _>>()?,
                ),
            );
        }
    }
    Ok(Value::Object(record.into_iter().collect()))
}

fn expanded_value(value: &ExpandedMacroValue) -> Value {
    let mut record = BTreeMap::new();
    match value {
        ExpandedMacroValue::ExactDecimal(value) => {
            record.insert("kind".to_owned(), Value::String("exact_decimal".to_owned()));
            record.insert(
                "coefficient".to_owned(),
                Value::String(value.coefficient().to_string()),
            );
            record.insert("scale".to_owned(), Value::from(value.scale()));
        }
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

fn target_value(
    target: &crate::GeneratedTargetId,
    owners: &SemanticMacroExecutionOwners,
    owner: &SemanticMacroExecutionOwner,
) -> Result<Value, MacroExpansionDiagnosticKind> {
    if target.invocation_ordinal != owner.source_ordinal {
        return Err(MacroExpansionDiagnosticKind::TargetOwnershipMismatch);
    }
    let Some(semantic_ordinal) = owners.semantic_ordinal_for_source(target.invocation_ordinal)
    else {
        return Err(MacroExpansionDiagnosticKind::TargetOwnershipMismatch);
    };
    let mut record = BTreeMap::new();
    record.insert(
        "invocation_ordinal".to_owned(),
        Value::Number(Number::from(semantic_ordinal)),
    );
    record.insert(
        "local_name".to_owned(),
        Value::String(target.local_name.clone()),
    );
    record.insert(
        "path".to_owned(),
        Value::Array(target.expansion_path.iter().map(path_value).collect()),
    );
    Ok(Value::Object(record.into_iter().collect()))
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

pub(crate) fn semantic_macro_execution_owners(
    ast: &SemanticDocumentAst,
    binding: &MacroParameterBindingResult,
) -> Result<SemanticMacroExecutionOwners, MacroExpansionDiagnosticKind> {
    let mut owners = Vec::new();
    let mut explained_binding_indices = Vec::new();

    for instruction in &ast.instructions {
        let SemanticHead::MacroInvocation(head) = &instruction.entity.head else {
            continue;
        };
        let Some(binding_index) = exact_macro_binding_index(head, binding) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        let Some(complete) = binding.complete.get(binding_index) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        if !semantic_macro_parameters_match_complete_binding(&head.parameters, complete) {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        }
        let Ok(semantic_ordinal) = u64::try_from(owners.len()) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        owners.push(SemanticMacroExecutionOwner {
            binding_index,
            source_invocation_index: complete.invocation_index,
            source_ordinal: complete.invocation_ordinal,
            semantic_ordinal,
        });
        explained_binding_indices.push(binding_index);
    }

    for edge in &ast.continuations {
        let SemanticHead::MacroInvocation(head) = &edge.reintroduced_head else {
            continue;
        };
        let Some(target_instruction) = ast.instructions.get(edge.target_instruction_index) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        let SemanticHead::MacroInvocation(target_head) = &target_instruction.entity.head else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        if !macro_head_matches_target(head, &edge.target)
            || !macro_head_matches_target(target_head, &edge.target)
            || !semantic_macro_parameters_have_same_meaning(
                &head.parameters,
                &target_head.parameters,
            )
        {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        }
        let Some(binding_index) = exact_macro_binding_index(head, binding) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        let Some(complete) = binding.complete.get(binding_index) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        if !semantic_macro_parameters_match_complete_binding(&head.parameters, complete) {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        }
        explained_binding_indices.push(binding_index);
    }

    let mapping = SemanticMacroExecutionOwners {
        owners,
        explained_binding_indices,
    };
    mapping
        .expansion_selection()
        .is_valid_for(binding.complete.len())
        .then_some(mapping)
        .ok_or(MacroExpansionDiagnosticKind::BindingOwnershipMismatch)
}

pub(crate) fn semantic_macro_execution_owners_for_projection(
    ast: &SemanticDocumentAst,
    binding: &MacroParameterBindingResult,
    retained_semantic_ordinals: Option<&BTreeMap<u64, u64>>,
    omitted_binding_indices: &BTreeSet<usize>,
) -> Result<SemanticMacroExecutionOwners, MacroExpansionDiagnosticKind> {
    let mut owners = Vec::new();
    let mut explained_binding_indices = omitted_binding_indices.iter().copied().collect::<Vec<_>>();

    for instruction in &ast.instructions {
        let SemanticHead::MacroInvocation(head) = &instruction.entity.head else {
            continue;
        };
        let Some(binding_index) = exact_macro_binding_index(head, binding) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        let Some(complete) = binding.complete.get(binding_index) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        if omitted_binding_indices.contains(&binding_index)
            || !semantic_macro_parameters_match_complete_binding(&head.parameters, complete)
        {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        }
        let semantic_ordinal = match retained_semantic_ordinals {
            Some(ordinals) => *ordinals
                .get(&complete.invocation_ordinal)
                .ok_or(MacroExpansionDiagnosticKind::BindingOwnershipMismatch)?,
            None => u64::try_from(owners.len())
                .map_err(|_| MacroExpansionDiagnosticKind::BindingOwnershipMismatch)?,
        };
        owners.push(SemanticMacroExecutionOwner {
            binding_index,
            source_invocation_index: complete.invocation_index,
            source_ordinal: complete.invocation_ordinal,
            semantic_ordinal,
        });
        explained_binding_indices.push(binding_index);
    }

    for edge in &ast.continuations {
        let SemanticHead::MacroInvocation(head) = &edge.reintroduced_head else {
            continue;
        };
        let Some(binding_index) = exact_macro_binding_index(head, binding) else {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        };
        if omitted_binding_indices.contains(&binding_index) {
            return Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch);
        }
        explained_binding_indices.push(binding_index);
    }

    explained_binding_indices.sort_unstable();
    let mapping = SemanticMacroExecutionOwners {
        owners,
        explained_binding_indices,
    };
    mapping
        .expansion_selection()
        .is_valid_for(binding.complete.len())
        .then_some(mapping)
        .ok_or(MacroExpansionDiagnosticKind::BindingOwnershipMismatch)
}

fn exact_macro_binding_index(
    head: &SemanticMacroInvocationHead,
    binding: &MacroParameterBindingResult,
) -> Option<usize> {
    let mut matches =
        binding
            .complete
            .iter()
            .enumerate()
            .filter_map(|(binding_index, complete)| {
                let resolved = binding
                    .macro_resolution
                    .resolved
                    .get(complete.invocation_index)?;
                (complete.invocation_ordinal == head.provenance.ordinal
                    && complete.clause_index == head.provenance.source.clause_index
                    && complete.atom_index == head.provenance.source.atom_index
                    && resolved.invocation.ordinal() == head.provenance.ordinal
                    && resolved.span == head.provenance.source.span
                    && resolved.clause_index == head.provenance.source.clause_index
                    && resolved.atom_index == head.provenance.source.atom_index
                    && resolved.invocation.qualified_name() == head.qualified_name
                    && head.provenance.qualified_name.as_deref()
                        == Some(head.qualified_name.as_str())
                    && resolved.definition_identity == complete.definition_identity
                    && complete.definition_identity.qualified_name() == head.qualified_name
                    && complete.definition_identity.version() == head.definition_version
                    && complete.definition_identity.full_digest_hex() == head.definition_digest
                    && resolved.lock == head.lock)
                    .then_some(binding_index)
            });
    let binding_index = matches.next()?;
    matches.next().is_none().then_some(binding_index)
}

fn macro_head_matches_target(
    head: &SemanticMacroInvocationHead,
    target: &SemanticContinuationTarget,
) -> bool {
    matches!(
        target,
        SemanticContinuationTarget::MacroInvocation {
            qualified_name,
            definition_version,
            definition_digest,
        } if qualified_name == &head.qualified_name
            && definition_version == &head.definition_version
            && definition_digest == &head.definition_digest
    )
}

#[cfg(test)]
mod execution_owner_join_tests {
    use super::*;
    use crate::{MacroLock, ParameterSchema, ResolvedInstructionLanguage};

    const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
        max_invocations: 16,
        max_depth: 16,
        max_evaluation_steps: 1_000,
        max_nodes_per_invocation: 100,
        max_total_nodes: 500,
    };

    #[test]
    fn stage15_source_occurrence_traversal_covers_serialized_language_evidence() {
        fn language_field_count(value: &Value) -> usize {
            match value {
                Value::Array(values) => values.iter().map(language_field_count).sum(),
                Value::Object(values) => {
                    usize::from(values.contains_key("language"))
                        + values.values().map(language_field_count).sum::<usize>()
                }
                _ => 0,
            }
        }

        let mut compilations = [
            (
                "place one thin pencil line at the center",
                ResolvedInstructionLanguage::En,
            ),
            (
                "place a circle and a line at the center.",
                ResolvedInstructionLanguage::En,
            ),
            (
                "円を中心に置く。円は赤い。",
                ResolvedInstructionLanguage::Ja,
            ),
        ]
        .map(|(source, language)| {
            compile_typed_ddl(
                NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
                &[],
                None,
                LIMITS,
            )
        })
        .into_iter()
        .collect::<Vec<_>>();

        let definition = MacroDefinition::from_json(
            r#"{"schema":"inku.macro-definition.v1","namespace":"Review","heading":"Tint","version":"1.0.0","parameters":{"value":{"type":"semantic_ref","category":"color"}},"components":{},"body":[]}"#,
        )
        .unwrap();
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        compilations.push(compile_typed_ddl(
            NormalizedDdlDocument::new(
                "Review.Tint red",
                ResolvedInstructionLanguage::En,
                vec![lock],
            )
            .unwrap(),
            std::slice::from_ref(&definition),
            None,
            LIMITS,
        ));

        for compilation in compilations {
            let ast = &compilation.semantic_document.as_ref().unwrap().ast;
            assert!(ast.complete, "{}", compilation.document.source());
            let before = semantic_source_provenance_canonical_bytes(ast);
            let occurrences = semantic_source_occurrences(ast);
            let serialized: Value = serde_json::from_slice(&before).unwrap();
            assert_eq!(occurrences.len(), language_field_count(&serialized));
            assert!(
                occurrences
                    .iter()
                    .all(|occurrence| occurrence.language == compilation.document.language())
            );
            assert_eq!(before, semantic_source_provenance_canonical_bytes(ast));
        }
    }

    #[test]
    fn execution_owner_join_rejects_parameter_drift_from_retained_bindings() {
        let definition = MacroDefinition::from_json(
            r#"{"schema":"inku.macro-definition.v1","namespace":"Review","heading":"Tint","version":"1.0.0","parameters":{"value":{"type":"semantic_ref","category":"color"}},"components":{},"body":[]}"#,
        )
        .unwrap();
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        let document = NormalizedDdlDocument::new(
            "Review.Tint red. the Review.Tint red swaying",
            ResolvedInstructionLanguage::En,
            vec![lock],
        )
        .unwrap();
        let binding = bind_macro_parameters(&document, std::slice::from_ref(&definition)).unwrap();
        let semantic = associate_semantic_document_with_macro_binding(&document, binding.clone());
        assert!(semantic.ast.complete);
        assert!(semantic_macro_execution_owners(&semantic.ast, &binding).is_ok());

        let blue = SemanticMacroParameterValue::SemanticRef(crate::SemanticIdentity {
            category: "color".to_owned(),
            id: "blue".to_owned(),
        });
        let mut head_only = semantic.ast.clone();
        let SemanticHead::MacroInvocation(head) = &mut head_only.instructions[0].entity.head else {
            panic!("Tint fixture retains its semantic macro head");
        };
        head.parameters[0].value = blue.clone();
        assert_eq!(
            semantic_macro_execution_owners(&head_only, &binding),
            Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch)
        );

        let mut coupled_heads = semantic.ast.clone();
        let SemanticHead::MacroInvocation(head) = &mut coupled_heads.instructions[0].entity.head
        else {
            panic!("Tint fixture retains its target semantic macro head");
        };
        head.parameters[0].value = blue.clone();
        let SemanticHead::MacroInvocation(head) =
            &mut coupled_heads.continuations[0].reintroduced_head
        else {
            panic!("Tint fixture retains its continuation semantic macro head");
        };
        head.parameters[0].value = blue;
        assert_eq!(
            semantic_macro_execution_owners(&coupled_heads, &binding),
            Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch)
        );

        for mutation in ["missing", "extra", "name", "schema", "duplicate"] {
            let mut ast = semantic.ast.clone();
            let SemanticHead::MacroInvocation(head) = &mut ast.instructions[0].entity.head else {
                unreachable!()
            };
            match mutation {
                "missing" => head.parameters.clear(),
                "extra" => head.parameters.push(head.parameters[0].clone()),
                "name" => head.parameters[0].name = "other".to_owned(),
                "schema" => head.parameters[0].schema = ParameterSchema::Number,
                "duplicate" => {
                    let duplicate = head.parameters[0].clone();
                    head.parameters.push(duplicate);
                }
                _ => unreachable!(),
            }
            assert_eq!(
                semantic_macro_execution_owners(&ast, &binding),
                Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch),
                "{mutation}"
            );
        }
    }

    #[test]
    fn execution_owner_join_rejects_mutated_semantic_source_identity_as_blocking() {
        let definition = MacroDefinition::from_json(
            r#"{"schema":"inku.macro-definition.v1","namespace":"Focus","heading":"Center","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"left_edge"}}}]}"#,
        )
        .unwrap();
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        let document =
            NormalizedDdlDocument::new("Focus.Center", ResolvedInstructionLanguage::En, vec![lock])
                .unwrap();
        let binding = bind_macro_parameters(&document, std::slice::from_ref(&definition)).unwrap();
        let semantic = associate_semantic_document_with_macro_binding(&document, binding.clone());
        assert!(semantic.ast.complete);

        let accepted = semantic_macro_execution_owners(&semantic.ast, &binding).unwrap();
        assert_eq!(
            accepted.owners(),
            [SemanticMacroExecutionOwner {
                binding_index: 0,
                source_invocation_index: 0,
                source_ordinal: 0,
                semantic_ordinal: 0,
            }]
        );

        let mut corrupted_ast = semantic.ast;
        let SemanticHead::MacroInvocation(head) = &mut corrupted_ast.instructions[0].entity.head
        else {
            panic!("locked Focus.Center remains a semantic macro head");
        };
        head.provenance.source.span.end_byte -= 1;

        let rejected = semantic_macro_execution_owners(&corrupted_ast, &binding);
        assert_eq!(
            rejected,
            Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch)
        );
        let expansion = expand_selected_macros(
            binding.clone(),
            std::slice::from_ref(&definition),
            &[],
            LIMITS,
            MacroExpansionSelection::invalid_owner_join(),
        );
        assert_eq!(expansion.parameter_binding, binding);
        assert!(expansion.expanded.is_empty());
        assert_eq!(expansion.diagnostics.len(), 1);
        assert_eq!(
            expansion.diagnostics[0].kind,
            MacroExpansionDiagnosticKind::BindingOwnershipMismatch
        );

        let mut projection = Projection::default();
        project_expansion_diagnostics(&document, &expansion, &mut projection);
        assert!(projection.holes.is_empty());
        assert!(projection.conflicts.is_empty());
        assert_eq!(projection.blocking.len(), 1);
        assert_eq!(projection.blocking[0].kind, "expansion_binding_ownership");
    }

    #[test]
    fn execution_owner_projector_rejects_missing_duplicate_reordered_and_unmapped_outputs() {
        let definition = MacroDefinition::from_json(
            r#"{"schema":"inku.macro-definition.v1","namespace":"Focus","heading":"Named","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"anchor","name":"origin"},{"op":"emit","binding":"center","fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"relation","kind":"touching","from":"origin","to":"center"}]}"#,
        )
        .unwrap();
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        let document = NormalizedDdlDocument::new(
            "a Focus.Named; the red Focus.Named; a blue Focus.Named",
            ResolvedInstructionLanguage::En,
            vec![lock],
        )
        .unwrap();
        let compilation = compile_typed_ddl(
            document,
            std::slice::from_ref(&definition),
            Some(19),
            LIMITS,
        );
        let ast = &compilation.semantic_document.as_ref().unwrap().ast;
        let expansion = compilation.macro_expansion.as_ref().unwrap();
        let owners = semantic_macro_execution_owners(ast, &expansion.parameter_binding).unwrap();
        assert!(expanded_meaning_canonical_bytes(ast, expansion).is_ok());

        let mut missing = expansion.clone();
        missing.expanded.pop();
        assert_eq!(
            expanded_meaning_canonical_bytes(ast, &missing),
            Err(MacroExpansionDiagnosticKind::BindingOwnershipMismatch)
        );
        let mut partial_projection = Projection::default();
        assert!(project_expanded_deliveries(&missing, &owners, &mut partial_projection).is_ok());
        assert_eq!(partial_projection.deliveries.len(), 3);

        let mut duplicate = expansion.clone();
        duplicate.expanded[1] = duplicate.expanded[0].clone();
        assert_eq!(
            expanded_meaning_canonical_bytes(ast, &duplicate),
            Err(MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch)
        );

        let mut reordered = expansion.clone();
        reordered.expanded.swap(0, 1);
        assert_eq!(
            expanded_meaning_canonical_bytes(ast, &reordered),
            Err(MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch)
        );

        let mut unmapped = expansion.clone();
        let ExpandedMacroNode::Emit {
            binding: Some(target),
            ..
        } = &mut unmapped.expanded[1].nodes[1]
        else {
            panic!("named fixture retains the source-owned generated target");
        };
        target.invocation_ordinal += 99;
        assert_eq!(
            expanded_meaning_canonical_bytes(ast, &unmapped),
            Err(MacroExpansionDiagnosticKind::TargetOwnershipMismatch)
        );

        let mut seeds = compilation
            .compiler_lock
            .as_ref()
            .unwrap()
            .macro_seeds
            .clone();
        seeds[1].ordinal = 2;
        assert_eq!(
            owners.validate_seed_identities(
                compilation.pre_expansion_canonical_bytes().unwrap(),
                expansion,
                &seeds,
                Some(19),
            ),
            Err(MacroExpansionDiagnosticKind::MismatchedSeed)
        );
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
