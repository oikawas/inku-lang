//! Runtime-disconnected typed delivery, canonical compiler identity, and lock construction.

use std::collections::BTreeMap;

use serde_json::{Number, Value};
use sha2::{Digest, Sha256};

use crate::{
    ClauseAtom, ExpandedMacroNode, ExpandedMacroValue, ExpansionPathSegment, MacroDefinition,
    MacroExpansionDiagnosticKind, MacroExpansionLimits, MacroExpansionResult,
    MacroInvocationResolutionDiagnosticKind, MacroParameterBindingDiagnosticKind,
    MacroParameterBindingResult, MacroSeed, NeutralDiagnosticKind, NormalizedDdlDocument,
    OwnedSemanticOccurrence, SemanticAssociationIssueKind, SemanticContinuationIssue,
    SemanticContinuationIssueKind, SemanticContinuationTarget, SemanticCoordinationIssueKind,
    SemanticDocumentIssueKind, SemanticDocumentResult, SemanticHead, SemanticInstruction,
    SemanticInstructionIssueKind, SemanticInstructionOccurrenceRole, SemanticIssueCausalProvenance,
    SemanticMacroParameterValue, SemanticRelationIssueKind, SemanticTerm, SourceSpan,
    associate_semantic_document_with_macro_binding, bind_macro_parameters, derive_macro_seed,
    expand_macros, project_macro_semantic_ref,
    semantic_document::exclusive_continuation_issue_claim_spans,
};

const MISSING_CANONICAL_SEMANTIC_IDENTITY: &str = "missing_canonical_semantic_identity";

/// Stable identity for the compilation envelope.
pub const TYPED_DDL_COMPILATION_SCHEMA_ID: &str = "inku.typed-ddl-compilation.v11";
/// Stable identity for source-independent pre-expansion semantic bytes.
pub const CANONICAL_SEMANTIC_DDL_SCHEMA_ID: &str = crate::SEMANTIC_DOCUMENT_SCHEMA_ID;
/// Stable identity for compiler locks.
pub const TYPED_DDL_COMPILER_LOCK_SCHEMA_ID: &str = "inku.typed-ddl-compiler-lock.v12";
/// ASCII domain prefix for the fully framed compiler lock digest.
pub const COMPILER_LOCK_DIGEST_DOMAIN: &[u8] = b"inku.typed-ddl-compiler-lock.v12";

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

/// Closed owner identity for one structured semantic occurrence.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum SemanticDeliveryOwner {
    EntityHead,
    MacroParameter,
    Color,
    Quantity,
    Thinness,
    RelativeScale,
    Touch,
    Continuity,
    Angle,
    SurfaceQuality,
    SurfaceIntensity,
    FluctuationAmplitude,
    FluctuationFrequency,
    FluctuationQuality,
    ProportionAspect,
    ProportionWidthExtent,
    ProportionArcForm,
    Action,
    Position,
    Relation,
    Ground,
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
            Self::Quantity => "quantity",
            Self::Thinness => "thinness",
            Self::RelativeScale => "relative_scale",
            Self::Touch => "touch",
            Self::Continuity => "continuity",
            Self::Angle => "angle",
            Self::SurfaceQuality => "surface_quality",
            Self::SurfaceIntensity => "surface_intensity",
            Self::FluctuationAmplitude => "fluctuation_amplitude",
            Self::FluctuationFrequency => "fluctuation_frequency",
            Self::FluctuationQuality => "fluctuation_quality",
            Self::ProportionAspect => "proportion_aspect",
            Self::ProportionWidthExtent => "proportion_width_extent",
            Self::ProportionArcForm => "proportion_arc_form",
            Self::Action => "action",
            Self::Position => "position",
            Self::Relation => "relation",
            Self::Ground => "ground",
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
    pub structured_semantic_occurrence_digest: String,
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
    sort_projection(&mut projection);
    let structured_semantic_occurrence_digest = sha256_hex(&structured_semantic_occurrence_bytes(
        &projection.deliveries,
    ));
    let canonical_ready = semantic_document.canonical_bytes.is_some();
    let mut seeds = Vec::new();
    let mut expansion = None;

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
        for complete in &binding.complete {
            let resolved = &binding.macro_resolution.resolved[complete.invocation_index];
            seeds.push(derive_macro_seed(
                canonical,
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
        structured_semantic_occurrence_digest,
        semantic_document.canonical_bytes.as_deref(),
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
    let exclusive_continuation_claims =
        exclusive_continuation_claim_groups(&semantic_document.continuation_issues);

    if let Some(ground) = &semantic_document.ast.ground {
        add_term_explicit(&mut projection, SemanticDeliveryOwner::Ground, ground);
    }
    for instruction in &semantic_document.ast.instructions {
        project_instruction(instruction, &mut projection);
    }
    for edge in &semantic_document.ast.group_predicates {
        if let Some(action) = &edge.action {
            add_term_explicit(&mut projection, SemanticDeliveryOwner::Action, action);
        }
        if let Some(position) = &edge.position {
            add_term_explicit(&mut projection, SemanticDeliveryOwner::Position, position);
        }
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
    for issue in &association.issues {
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
            SemanticAssociationIssueKind::MacroResolution(
                MacroInvocationResolutionDiagnosticKind::MissingLock
                | MacroInvocationResolutionDiagnosticKind::MissingDefinition
                | MacroInvocationResolutionDiagnosticKind::InvalidDefinition,
            )
            | SemanticAssociationIssueKind::MacroParameterBinding(
                MacroParameterBindingDiagnosticKind::MissingCompatibleFact
                | MacroParameterBindingDiagnosticKind::UnsupportedSchema
                | MacroParameterBindingDiagnosticKind::NumericRange
                | MacroParameterBindingDiagnosticKind::NumericPrecision,
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
            | SemanticAssociationIssueKind::ConflictingTouches
            | SemanticAssociationIssueKind::ConflictingContinuities
            | SemanticAssociationIssueKind::ConflictingAngles
            | SemanticAssociationIssueKind::ConflictingSurfaceQualities
            | SemanticAssociationIssueKind::ConflictingSurfaceIntensities
            | SemanticAssociationIssueKind::ConflictingFluctuationAmplitudes
            | SemanticAssociationIssueKind::ConflictingFluctuationFrequencies
            | SemanticAssociationIssueKind::ConflictingFluctuationQualities
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
            | SemanticAssociationIssueKind::UnknownSurfaceDimension
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
        let span = issue
            .occurrences
            .first()
            .map(|occurrence| occurrence.term.provenance.source.span);
        match issue.kind {
            SemanticInstructionIssueKind::AmbiguousActionOwnership
            | SemanticInstructionIssueKind::AmbiguousPositionOwnership => {
                for occurrence in issue.occurrences.iter().filter(|occurrence| {
                    !consumed_continuation_spans.contains(&occurrence.term.provenance.source.span)
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
            | SemanticInstructionIssueKind::MissingPositionEntity => {
                add_blocking(&mut projection, issue.kind.as_str(), span)
            }
        }
    }

    for issue in &semantic_document
        .instruction_association
        .coordination_issues
    {
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
            SemanticRelationIssueKind::ConflictingRelations => add_conflict(
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
            SemanticDocumentIssueKind::ConflictingGrounds => add_conflict(
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
    project_continuation_issues(&semantic_document.continuation_issues, &mut projection);

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

const fn neutral_diagnostic_kind_key(kind: NeutralDiagnosticKind) -> &'static str {
    match kind {
        NeutralDiagnosticKind::Hole => "hole",
        NeutralDiagnosticKind::Conflict => "conflict",
        NeutralDiagnosticKind::Unknown => "unknown",
    }
}

fn project_continuation_issues(issues: &[SemanticContinuationIssue], projection: &mut Projection) {
    let exclusive_claims = exclusive_continuation_claim_groups(issues);
    let exclusive_issue_indices = exclusive_claims
        .values()
        .filter(|group| group.issue_indices.len() > 1)
        .flat_map(|group| group.issue_indices.iter().copied())
        .collect::<Vec<_>>();
    let mut groups = BTreeMap::<(usize, usize), ContinuationIssueProjection>::new();
    for (issue_index, issue) in issues.iter().enumerate() {
        if exclusive_issue_indices.contains(&issue_index) {
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
            SemanticDeliveryOwner::Position,
            instruction.position.as_ref(),
        ),
    ] {
        if let Some(term) = term {
            add_term_explicit(projection, owner, term);
        }
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
    if let Some(relative_scale) = &instruction.entity.relative_scale {
        add_explicit(
            projection,
            relative_scale.provenance.span,
            SemanticDeliveryOwner::RelativeScale,
            relative_scale.value.as_str().to_owned(),
        );
    }
    if let Some(relation) = &instruction.relation {
        add_explicit(
            projection,
            relation.provenance.span,
            SemanticDeliveryOwner::Relation,
            format!("{}:{}", relation.kind.as_str(), relation.reference.as_str()),
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
    seeds: &[MacroSeed],
    expanded_meaning_digest: Option<String>,
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
        composition_seed: has_structured_meaning.then_some(composition_seed.unwrap_or(0)),
        definition_identities,
        macro_seeds,
        expanded_meaning_digest,
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
