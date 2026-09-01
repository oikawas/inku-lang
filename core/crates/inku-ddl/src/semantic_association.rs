//! Single-head semantic association over the accepted source-preserving clause stream.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Number, Value};

use crate::{
    AttachmentEvidenceResult, AttachmentMarkerEvidence, AttachmentMarkerKind,
    BoundMacroParameterValue, CanonicalPreviousReference, CanonicalRelationIdentity,
    CanonicalRelationKind, ClauseAtom, ClauseSeparatorKind, ClauseStream, ClauseStreamError,
    CoreModifierValue, CoreRoleKind, EnglishAttachmentMarkerKind, JapaneseAttachmentMarkerKind,
    MacroInvocationResolutionDiagnosticKind, MacroLockResolutionIdentity, MacroParameterBinding,
    MacroParameterBindingDiagnosticKind, MacroParameterBindingResult, NeutralDiagnostic,
    NeutralDiagnosticKind, NormalizedDdlDocument, ParameterSchema, RemainingRoleKind,
    ResolvedInstructionLanguage, SAIJIKI_ASSET_ID, SourceSpan, collect_attachment_evidence,
    project_macro_semantic_ref, saijiki::canonical_relation_identity_is_valid,
};

/// Stable identity for the runtime-disconnected single-head semantic AST.
pub const SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID: &str = "inku.semantic-entity-association.v11";

/// Source-independent semantic identity projected from one accepted Saijiki row.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticIdentity {
    pub category: String,
    pub id: String,
}

/// Exact source location for one association-owned occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceOccurrence {
    pub span: SourceSpan,
    pub surface: String,
    pub language: ResolvedInstructionLanguage,
    pub region_index: usize,
    pub clause_index: usize,
    pub atom_index: usize,
}

/// Closed semantic identity of one accepted explicit previous-object relation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticRelationKind {
    Along,
    NotTouching,
    Cutting,
    Between,
    Touching,
}

impl SemanticRelationKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Along => "along",
            Self::NotTouching => "not_touching",
            Self::Cutting => "cutting",
            Self::Between => "between",
            Self::Touching => "touching",
        }
    }
}

/// Closed source-order reference depth for one explicit relation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticPreviousReference {
    PreviousOne,
    PreviousTwo,
}

impl SemanticPreviousReference {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::PreviousOne => "previous_one",
            Self::PreviousTwo => "previous_two",
        }
    }

    pub(crate) const fn required_previous_count(self) -> usize {
        match self {
            Self::PreviousOne => 1,
            Self::PreviousTwo => 2,
        }
    }
}

/// One accepted full-literal relation atom retained as a source-owned compound occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ExplicitPreviousReferenceOccurrence {
    pub kind: SemanticRelationKind,
    pub reference: SemanticPreviousReference,
    pub provenance: SourceOccurrence,
    pub asset_id: String,
    pub relation_type: String,
}

/// Saijiki identity and localized label retained only as source provenance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticTermProvenance {
    pub source: SourceOccurrence,
    pub asset_id: String,
    pub category_key: String,
    pub canonical_surface_ja: String,
}

/// One source-independent Saijiki meaning with its separate source provenance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticTerm {
    pub identity: SemanticIdentity,
    pub provenance: SemanticTermProvenance,
}

/// One checked, explicit, non-negative numeric quantity and its source provenance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticQuantity {
    pub value: u64,
    pub provenance: SourceOccurrence,
}

/// One explicit core thinness value and its exact source provenance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticThinness {
    pub value: CoreModifierValue,
    pub provenance: SourceOccurrence,
}

/// Canonical value of one source-owned macro parameter.
#[derive(Clone, Debug, PartialEq)]
pub enum SemanticMacroParameterValue {
    Integer(i64),
    Number(f64),
    SemanticRef(SemanticIdentity),
}

/// One complete parameter binding retained by a semantic MacroInvocation head.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticMacroParameterBinding {
    pub name: String,
    pub schema: ParameterSchema,
    pub value: SemanticMacroParameterValue,
    pub provenance: SourceOccurrence,
    pub source_asset_id: Option<String>,
    pub canonical_surface_ja: Option<String>,
}

/// Source-only identity of one resolved visible macro invocation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticMacroInvocationProvenance {
    pub source: SourceOccurrence,
    pub ordinal: u64,
    pub qualified_name: Option<String>,
}

/// One definition-locked, completely bound, still-unexpanded macro semantic head.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticMacroInvocationHead {
    pub qualified_name: String,
    pub definition_version: String,
    pub definition_digest: String,
    pub lock: MacroLockResolutionIdentity,
    pub provenance: SemanticMacroInvocationProvenance,
    pub parameters: Vec<SemanticMacroParameterBinding>,
}

/// Closed semantic entity head kind.
#[derive(Clone, Debug, PartialEq)]
pub enum SemanticHead {
    Primitive(SemanticTerm),
    MacroInvocation(SemanticMacroInvocationHead),
}

impl SemanticHead {
    pub const fn source(&self) -> &SourceOccurrence {
        match self {
            Self::Primitive(term) => &term.provenance.source,
            Self::MacroInvocation(head) => &head.provenance.source,
        }
    }

    const fn occurrence_count(&self) -> usize {
        match self {
            Self::Primitive(_) => 1,
            Self::MacroInvocation(head) => 1 + head.parameters.len(),
        }
    }
}

/// Two independent explicit Surface dimensions. Missing values remain unspecified.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct SemanticSurface {
    pub quality: Option<SemanticTerm>,
    pub intensity: Option<SemanticTerm>,
}

/// Three independent explicit Fluctuation dimensions. Missing values remain unspecified.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct SemanticFluctuation {
    pub amplitude: Option<SemanticTerm>,
    pub frequency: Option<SemanticTerm>,
    pub quality: Option<SemanticTerm>,
}

/// Three independent explicit Proportion dimensions. Missing values remain unspecified.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct SemanticProportion {
    pub aspect: Option<SemanticTerm>,
    pub width_extent: Option<SemanticTerm>,
    pub arc_form: Option<SemanticTerm>,
}

/// One independently owned head entity. A field is absent unless it has one explicit owner.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticEntity {
    pub head: SemanticHead,
    pub color: Option<SemanticTerm>,
    pub quantity: Option<SemanticQuantity>,
    pub thinness: Option<SemanticThinness>,
    pub touch: Option<SemanticTerm>,
    pub continuity: Option<SemanticTerm>,
    pub angle: Option<SemanticTerm>,
    pub surface: SemanticSurface,
    pub fluctuation: SemanticFluctuation,
    pub proportion: SemanticProportion,
}

/// Partial or complete semantic entity sequence in sentence-region source order.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticEntityAssociationAst {
    pub entities: Vec<SemanticEntity>,
    pub complete: bool,
}

/// An association-owned occurrence delivered to a typed issue rather than an AST field.
#[derive(Clone, Debug, PartialEq)]
pub enum OwnedSemanticOccurrence {
    Head(SemanticHead),
    MacroDiagnostic(SemanticMacroInvocationProvenance),
    Color(SemanticTerm),
    Quantity(SemanticQuantity),
    Thinness(SemanticThinness),
    Touch(SemanticTerm),
    Continuity(SemanticTerm),
    Angle(SemanticTerm),
    Surface(SemanticTerm),
    Fluctuation(SemanticTerm),
    Proportion(SemanticTerm),
}

impl OwnedSemanticOccurrence {
    /// Return the byte-exact source occurrence delivered by this issue.
    pub const fn source(&self) -> &SourceOccurrence {
        match self {
            Self::Head(head) => head.source(),
            Self::MacroDiagnostic(provenance) => &provenance.source,
            Self::Color(term)
            | Self::Touch(term)
            | Self::Continuity(term)
            | Self::Angle(term)
            | Self::Surface(term)
            | Self::Fluctuation(term)
            | Self::Proportion(term) => &term.provenance.source,
            Self::Quantity(quantity) => &quantity.provenance,
            Self::Thinness(thinness) => &thinness.provenance,
        }
    }

    const fn occurrence_count(&self) -> usize {
        match self {
            Self::Head(head) => head.occurrence_count(),
            Self::MacroDiagnostic(_)
            | Self::Color(_)
            | Self::Quantity(_)
            | Self::Thinness(_)
            | Self::Touch(_)
            | Self::Continuity(_)
            | Self::Angle(_)
            | Self::Surface(_)
            | Self::Fluctuation(_)
            | Self::Proportion(_) => 1,
        }
    }
}

/// Stable, expected association issue classes for this single-head slice.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticAssociationIssueKind {
    AmbiguousEntityOwnership,
    MissingEntityHead,
    ConflictingColors,
    ConflictingQuantities,
    ConflictingThinness,
    ConflictingTouches,
    ConflictingContinuities,
    ConflictingAngles,
    ConflictingSurfaceQualities,
    ConflictingSurfaceIntensities,
    UnknownSurfaceDimension,
    ConflictingFluctuationAmplitudes,
    ConflictingFluctuationFrequencies,
    ConflictingFluctuationQualities,
    UnknownFluctuationDimension,
    ConflictingProportionAspects,
    ConflictingProportionWidthExtents,
    ConflictingProportionArcForms,
    UnknownProportionDimension,
    UpstreamHole,
    UpstreamConflict,
    UpstreamUnknown,
    MacroResolution(MacroInvocationResolutionDiagnosticKind),
    MacroParameterBinding(MacroParameterBindingDiagnosticKind),
}

impl SemanticAssociationIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::AmbiguousEntityOwnership => "ambiguous_entity_ownership",
            Self::MissingEntityHead => "missing_entity_head",
            Self::ConflictingColors => "conflicting_colors",
            Self::ConflictingQuantities => "conflicting_quantities",
            Self::ConflictingThinness => "conflicting_thinness",
            Self::ConflictingTouches => "conflicting_touches",
            Self::ConflictingContinuities => "conflicting_continuities",
            Self::ConflictingAngles => "conflicting_angles",
            Self::ConflictingSurfaceQualities => "conflicting_surface_qualities",
            Self::ConflictingSurfaceIntensities => "conflicting_surface_intensities",
            Self::UnknownSurfaceDimension => "unknown_surface_dimension",
            Self::ConflictingFluctuationAmplitudes => "conflicting_fluctuation_amplitudes",
            Self::ConflictingFluctuationFrequencies => "conflicting_fluctuation_frequencies",
            Self::ConflictingFluctuationQualities => "conflicting_fluctuation_qualities",
            Self::UnknownFluctuationDimension => "unknown_fluctuation_dimension",
            Self::ConflictingProportionAspects => "conflicting_proportion_aspects",
            Self::ConflictingProportionWidthExtents => "conflicting_proportion_width_extents",
            Self::ConflictingProportionArcForms => "conflicting_proportion_arc_forms",
            Self::UnknownProportionDimension => "unknown_proportion_dimension",
            Self::UpstreamHole => "upstream_hole",
            Self::UpstreamConflict => "upstream_conflict",
            Self::UpstreamUnknown => "upstream_unknown",
            Self::MacroResolution(kind) => macro_resolution_issue_kind(kind),
            Self::MacroParameterBinding(kind) => macro_parameter_binding_issue_kind(kind),
        }
    }
}

const fn macro_resolution_issue_kind(
    kind: MacroInvocationResolutionDiagnosticKind,
) -> &'static str {
    match kind {
        MacroInvocationResolutionDiagnosticKind::MissingLock => "macro_resolution_missing_lock",
        MacroInvocationResolutionDiagnosticKind::AmbiguousLockPrefix => {
            "macro_resolution_ambiguous_lock_prefix"
        }
        MacroInvocationResolutionDiagnosticKind::MissingDefinition => {
            "macro_resolution_missing_definition"
        }
        MacroInvocationResolutionDiagnosticKind::DuplicateMatchingDefinition => {
            "macro_resolution_duplicate_matching_definition"
        }
        MacroInvocationResolutionDiagnosticKind::InvalidDefinition => {
            "macro_resolution_invalid_definition"
        }
        MacroInvocationResolutionDiagnosticKind::QualifiedNameMismatch => {
            "macro_resolution_qualified_name_mismatch"
        }
        MacroInvocationResolutionDiagnosticKind::VersionMismatch => {
            "macro_resolution_version_mismatch"
        }
        MacroInvocationResolutionDiagnosticKind::DigestMismatch => {
            "macro_resolution_digest_mismatch"
        }
        MacroInvocationResolutionDiagnosticKind::SourceClauseAtomMismatch => {
            "macro_resolution_source_clause_atom_mismatch"
        }
    }
}

const fn macro_parameter_binding_issue_kind(
    kind: MacroParameterBindingDiagnosticKind,
) -> &'static str {
    match kind {
        MacroParameterBindingDiagnosticKind::MissingCompatibleFact => {
            "macro_binding_missing_compatible_fact"
        }
        MacroParameterBindingDiagnosticKind::AmbiguousCompleteAssignment => {
            "macro_binding_ambiguous_complete_assignment"
        }
        MacroParameterBindingDiagnosticKind::SharedFact => "macro_binding_shared_fact",
        MacroParameterBindingDiagnosticKind::UnsupportedSchema => {
            "macro_binding_unsupported_schema"
        }
        MacroParameterBindingDiagnosticKind::NumericRange => "macro_binding_numeric_range",
        MacroParameterBindingDiagnosticKind::NumericPrecision => "macro_binding_numeric_precision",
        MacroParameterBindingDiagnosticKind::DefinitionIdentityOwnershipMismatch => {
            "macro_binding_definition_identity_ownership_mismatch"
        }
        MacroParameterBindingDiagnosticKind::SourceClauseAtomOwnershipMismatch => {
            "macro_binding_source_clause_atom_ownership_mismatch"
        }
    }
}

/// One typed issue with either its owned occurrences or its unchanged upstream diagnostic.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticAssociationIssue {
    pub kind: SemanticAssociationIssueKind,
    pub region_index: usize,
    pub occurrences: Vec<OwnedSemanticOccurrence>,
    pub upstream_diagnostic: Option<NeutralDiagnostic>,
}

/// Source-preserving association result. Entity counts and compound-reference counts remain
/// separate so the accepted I-592 occurrence accounting is not recounted by this slice.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticAssociationResult {
    pub schema_id: &'static str,
    pub clause_stream: ClauseStream,
    pub ast: SemanticEntityAssociationAst,
    pub issues: Vec<SemanticAssociationIssue>,
    pub canonical_bytes: Option<Vec<u8>>,
    pub owned_occurrence_count: usize,
    pub delivered_occurrence_count: usize,
    pub explicit_previous_references: Vec<ExplicitPreviousReferenceOccurrence>,
    pub owned_compound_reference_count: usize,
    pub delivered_compound_reference_count: usize,
    pub macro_parameter_binding: Option<MacroParameterBindingResult>,
    pub(crate) clause_topology: ClauseTopologyEvidence,
}

impl SemanticAssociationResult {
    pub(crate) fn macro_parameter_owns_span(&self, span: SourceSpan) -> bool {
        self.macro_parameter_binding
            .as_ref()
            .is_some_and(|binding| {
                binding
                    .complete
                    .iter()
                    .flat_map(|complete| &complete.parameters)
                    .any(|parameter| parameter.source_span == span)
            })
    }
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub(crate) struct ClauseTopologyEvidence {
    pub attachment_markers: Vec<AttachmentMarkerEvidence>,
    pub determiner_starts: BTreeSet<usize>,
}

impl ClauseTopologyEvidence {
    fn from_attachment(attachment: &AttachmentEvidenceResult) -> Self {
        Self {
            attachment_markers: attachment.evidence.clone(),
            determiner_starts: attachment
                .noun_phrase
                .evidence
                .iter()
                .map(|evidence| evidence.determiner.span.start_byte)
                .collect(),
        }
    }
}

#[derive(Default)]
struct AssociationRegion {
    heads: Vec<SemanticHead>,
    colors: Vec<SemanticTerm>,
    quantities: Vec<SemanticQuantity>,
    thinnesses: Vec<SemanticThinness>,
    touches: Vec<SemanticTerm>,
    continuities: Vec<SemanticTerm>,
    angles: Vec<SemanticTerm>,
    surface_qualities: Vec<SemanticTerm>,
    surface_intensities: Vec<SemanticTerm>,
    unclassified_surfaces: Vec<SemanticTerm>,
    fluctuation_amplitudes: Vec<SemanticTerm>,
    fluctuation_frequencies: Vec<SemanticTerm>,
    fluctuation_qualities: Vec<SemanticTerm>,
    unclassified_fluctuations: Vec<SemanticTerm>,
    proportion_aspects: Vec<SemanticTerm>,
    proportion_width_extents: Vec<SemanticTerm>,
    proportion_arc_forms: Vec<SemanticTerm>,
    unclassified_proportions: Vec<SemanticTerm>,
    diagnostics: Vec<NeutralDiagnostic>,
}

#[derive(Default)]
struct PreHeadPhraseOwnership {
    modifier_starts_by_head: BTreeMap<usize, BTreeSet<usize>>,
}

impl PreHeadPhraseOwnership {
    fn insert(&mut self, head_span: SourceSpan, modifier_span: SourceSpan) {
        self.modifier_starts_by_head
            .entry(head_span.start_byte)
            .or_default()
            .insert(modifier_span.start_byte);
    }

    fn owns(&self, head: &SemanticHead, occurrence_span: SourceSpan) -> bool {
        self.modifier_starts_by_head
            .get(&head.source().span.start_byte)
            .is_some_and(|starts| starts.contains(&occurrence_span.start_byte))
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum SurfaceDimension {
    Quality,
    Intensity,
}

fn classify_surface_dimension(canonical_id: &str) -> Option<SurfaceDimension> {
    match canonical_id {
        "none" | "solid" | "wash" | "grain" | "stipple" | "hatch" | "crosshatch" | "bleed"
        | "aquatint" => Some(SurfaceDimension::Quality),
        "dense" | "faint" => Some(SurfaceDimension::Intensity),
        _ => None,
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum FluctuationDimension {
    Amplitude,
    Frequency,
    Quality,
}

fn classify_fluctuation_dimension(canonical_id: &str) -> Option<FluctuationDimension> {
    match canonical_id {
        "fine" | "large" => Some(FluctuationDimension::Amplitude),
        "quickly" | "slowly" => Some(FluctuationDimension::Frequency),
        "swaying" | "undulating" | "trembling" | "blurring" => Some(FluctuationDimension::Quality),
        _ => None,
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ProportionDimension {
    Aspect,
    WidthExtent,
    ArcForm,
}

fn classify_proportion_dimension(canonical_id: &str) -> Option<ProportionDimension> {
    match canonical_id {
        "tall" | "wide" => Some(ProportionDimension::Aspect),
        "full_width" | "half_width" => Some(ProportionDimension::WidthExtent),
        "semicircle" | "waxing" | "waning" | "crescent" => Some(ProportionDimension::ArcForm),
        _ => None,
    }
}

fn collect_pre_head_phrase_ownership(
    attachment_evidence: &AttachmentEvidenceResult,
    macro_parameter_binding: Option<&MacroParameterBindingResult>,
) -> PreHeadPhraseOwnership {
    let clause_stream = &attachment_evidence.noun_phrase.clause_stream;
    let mut heads = clause_stream
        .clauses
        .iter()
        .enumerate()
        .flat_map(|(clause_index, clause)| {
            clause.atoms.iter().filter_map(move |atom| match atom {
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive => {
                    Some((term.span, clause_index))
                }
                _ => None,
            })
        })
        .collect::<Vec<_>>();
    if let Some(binding) = macro_parameter_binding {
        for complete in &binding.complete {
            let resolved = binding
                .macro_resolution
                .resolved
                .get(complete.invocation_index)
                .expect("accepted I-581 binding references one resolved invocation");
            heads.push((resolved.span, resolved.clause_index));
        }
    }
    heads.sort_by_key(|(span, _)| span.start_byte);
    heads.dedup_by_key(|(span, _)| span.start_byte);

    let head_starts = heads
        .iter()
        .map(|(span, _)| span.start_byte)
        .collect::<BTreeSet<_>>();
    let genitive_marker_starts = attachment_evidence
        .evidence
        .iter()
        .filter(|evidence| {
            matches!(
                evidence.marker,
                AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::No)
                    | AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::Of)
            )
        })
        .map(|evidence| evidence.span.start_byte)
        .collect::<BTreeSet<_>>();

    let mut ownership = PreHeadPhraseOwnership::default();
    for (head_span, clause_index) in heads {
        let determiner_evidence =
            attachment_evidence
                .noun_phrase
                .evidence
                .iter()
                .find(|evidence| {
                    evidence.clause_index == clause_index
                        && evidence
                            .head_candidate
                            .as_ref()
                            .is_some_and(|candidate| candidate.span == head_span)
                });
        let phrase_floor = determiner_evidence.map(|evidence| {
            evidence
                .opaque_pre_head_span
                .map_or(evidence.determiner.span.end_byte, |span| span.start_byte)
        });
        let clause = clause_stream
            .clauses
            .get(clause_index)
            .expect("accepted head provenance references one clause");

        for atom in clause
            .atoms
            .iter()
            .rev()
            .filter(|atom| atom.span().end_byte <= head_span.start_byte)
        {
            let span = atom.span();
            if phrase_floor.is_some_and(|floor| span.end_byte <= floor)
                || head_starts.contains(&span.start_byte)
            {
                break;
            }
            match atom {
                ClauseAtom::UnresolvedDiagnostic(_) => break,
                ClauseAtom::FunctionWord { .. } => {
                    if !genitive_marker_starts.contains(&span.start_byte) {
                        break;
                    }
                }
                _ if is_pre_head_modifier_atom(atom) => ownership.insert(head_span, span),
                _ => {}
            }
        }
    }
    collect_japanese_post_head_quantity_ownership(
        attachment_evidence,
        macro_parameter_binding,
        &mut ownership,
    );
    ownership
}

fn collect_japanese_post_head_quantity_ownership(
    attachment: &AttachmentEvidenceResult,
    macro_parameter_binding: Option<&MacroParameterBindingResult>,
    ownership: &mut PreHeadPhraseOwnership,
) {
    let wo_markers = attachment.evidence.iter().filter(|evidence| {
        evidence.marker == AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wo)
    });
    for marker in wo_markers {
        let clause = &attachment.noun_phrase.clause_stream.clauses[marker.clause_index];
        let lower_bound = clause
            .atoms
            .iter()
            .filter(|atom| atom.span().end_byte <= marker.span.start_byte)
            .filter(|atom| {
                matches!(
                    atom,
                    ClauseAtom::RemainingRole(term)
                        if term.role == RemainingRoleKind::Motion
                            && !macro_parameter_binding.is_some_and(|binding| {
                                macro_parameter_binding_owns_span(binding, term.span)
                            })
                )
            })
            .map(|atom| atom.span().end_byte)
            .max()
            .unwrap_or(clause.span.start_byte);
        let heads = clause
            .atoms
            .iter()
            .filter_map(|atom| match atom {
                ClauseAtom::CoreRole(term)
                    if term.role == CoreRoleKind::Primitive
                        && lower_bound <= term.span.start_byte
                        && term.span.end_byte <= marker.span.start_byte =>
                {
                    Some(term.span)
                }
                _ => None,
            })
            .chain(macro_parameter_binding.into_iter().flat_map(|binding| {
                binding.complete.iter().filter_map(|complete| {
                    let resolved = &binding.macro_resolution.resolved[complete.invocation_index];
                    (resolved.clause_index == marker.clause_index
                        && lower_bound <= resolved.span.start_byte
                        && resolved.span.end_byte <= marker.span.start_byte)
                        .then_some(resolved.span)
                })
            }))
            .collect::<Vec<_>>();
        if heads.len() != 1 {
            continue;
        }
        let head_span = heads[0];
        let predicate_end = clause
            .atoms
            .iter()
            .filter(|atom| marker.span.end_byte <= atom.span().start_byte)
            .filter(|atom| {
                matches!(atom, ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive)
                    || matches!(atom, ClauseAtom::UnresolvedDiagnostic(_))
            })
            .map(|atom| atom.span().start_byte)
            .chain(
                attachment
                    .evidence
                    .iter()
                    .filter(|candidate| {
                        candidate.clause_index == marker.clause_index
                            && candidate.marker
                                == AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wo)
                            && marker.span.end_byte <= candidate.span.start_byte
                    })
                    .map(|candidate| candidate.span.start_byte),
            )
            .min()
            .unwrap_or(clause.span.end_byte);
        let motions = clause
            .atoms
            .iter()
            .filter_map(|atom| match atom {
                ClauseAtom::RemainingRole(term)
                    if term.role == RemainingRoleKind::Motion
                        && marker.span.end_byte <= term.span.start_byte
                        && term.span.end_byte <= predicate_end
                        && !macro_parameter_binding.is_some_and(|binding| {
                            macro_parameter_binding_owns_span(binding, term.span)
                        }) =>
                {
                    Some(term.span)
                }
                _ => None,
            })
            .collect::<Vec<_>>();
        if motions.len() != 1 {
            continue;
        }
        for quantity in clause.atoms.iter().filter_map(|atom| match atom {
            ClauseAtom::UnattachedExactNumber(quantity)
                if marker.span.end_byte <= quantity.span.start_byte
                    && quantity.span.end_byte <= motions[0].start_byte
                    && !macro_parameter_binding.is_some_and(|binding| {
                        macro_parameter_binding_owns_span(binding, quantity.span)
                    }) =>
            {
                Some(quantity.span)
            }
            _ => None,
        }) {
            ownership.insert(head_span, quantity);
        }
    }
}

fn is_pre_head_modifier_atom(atom: &ClauseAtom) -> bool {
    matches!(
        atom,
        ClauseAtom::CoreRole(term)
            if matches!(
                term.role,
                CoreRoleKind::Color | CoreRoleKind::Touch | CoreRoleKind::Surface
            )
    ) || matches!(
        atom,
        ClauseAtom::RemainingRole(term)
            if matches!(
                term.role,
                RemainingRoleKind::Continuity
                    | RemainingRoleKind::Angle
                    | RemainingRoleKind::Fluctuation
                    | RemainingRoleKind::Proportion
            )
    ) || matches!(
        atom,
        ClauseAtom::CoreModifier(term)
            if term.identity.dimension == crate::CoreModifierDimension::Thinness
    ) || matches!(atom, ClauseAtom::UnattachedExactNumber(_))
}

/// Associate the closed entity roles and explicit numeric quantity within sentence regions.
///
/// The accepted attachment entrypoint is invoked exactly once and its owned clause stream is
/// retained. Sentence endings close a region, while line breaks remain phrase boundaries.
pub fn associate_semantic_entities(
    document: &NormalizedDdlDocument,
) -> Result<SemanticAssociationResult, ClauseStreamError> {
    let attachment_evidence = collect_attachment_evidence(document)?;
    let pre_head_ownership = collect_pre_head_phrase_ownership(&attachment_evidence, None);
    let clause_topology = ClauseTopologyEvidence::from_attachment(&attachment_evidence);
    let clause_stream = attachment_evidence.noun_phrase.clause_stream;
    Ok(build_semantic_entities(
        document,
        clause_stream,
        None,
        pre_head_ownership,
        clause_topology,
    ))
}

/// Associate semantic entities from one caller-owned accepted I-581 result without rerunning it.
pub fn associate_semantic_entities_with_macro_binding(
    document: &NormalizedDdlDocument,
    macro_parameter_binding: MacroParameterBindingResult,
) -> SemanticAssociationResult {
    let attachment_evidence = &macro_parameter_binding
        .macro_resolution
        .relation_reference_evidence
        .attachment_evidence;
    let pre_head_ownership =
        collect_pre_head_phrase_ownership(attachment_evidence, Some(&macro_parameter_binding));
    let clause_topology = ClauseTopologyEvidence::from_attachment(attachment_evidence);
    let clause_stream = macro_parameter_binding
        .macro_resolution
        .relation_reference_evidence
        .attachment_evidence
        .noun_phrase
        .clause_stream
        .clone();
    build_semantic_entities(
        document,
        clause_stream,
        Some(macro_parameter_binding),
        pre_head_ownership,
        clause_topology,
    )
}

fn build_semantic_entities(
    document: &NormalizedDdlDocument,
    clause_stream: ClauseStream,
    macro_parameter_binding: Option<MacroParameterBindingResult>,
    pre_head_ownership: PreHeadPhraseOwnership,
    clause_topology: ClauseTopologyEvidence,
) -> SemanticAssociationResult {
    let mut regions = BTreeMap::<usize, AssociationRegion>::new();
    let mut issues = Vec::new();
    let mut owned_occurrence_count = 0;
    let mut explicit_previous_references = Vec::new();

    for (clause_index, clause) in clause_stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            if macro_parameter_binding
                .as_ref()
                .is_some_and(|binding| macro_parameter_binding_owns_span(binding, atom.span()))
            {
                continue;
            }
            let region_index = sentence_region_index(&clause_stream, atom.span());
            let region = regions.entry(region_index).or_default();
            match atom {
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive => {
                    region.heads.push(SemanticHead::Primitive(project_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    )));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Color => {
                    region.colors.push(project_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Touch => {
                    region.touches.push(project_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Surface => {
                    let term = project_term(document, term, region_index, clause_index, atom_index);
                    match classify_surface_dimension(&term.identity.id) {
                        Some(SurfaceDimension::Quality) => region.surface_qualities.push(term),
                        Some(SurfaceDimension::Intensity) => region.surface_intensities.push(term),
                        None => region.unclassified_surfaces.push(term),
                    }
                    owned_occurrence_count += 1;
                }
                ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Continuity => {
                    region.continuities.push(project_remaining_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Angle => {
                    region.angles.push(project_remaining_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Fluctuation => {
                    let term = project_remaining_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    );
                    match classify_fluctuation_dimension(&term.identity.id) {
                        Some(FluctuationDimension::Amplitude) => {
                            region.fluctuation_amplitudes.push(term)
                        }
                        Some(FluctuationDimension::Frequency) => {
                            region.fluctuation_frequencies.push(term)
                        }
                        Some(FluctuationDimension::Quality) => {
                            region.fluctuation_qualities.push(term)
                        }
                        None => region.unclassified_fluctuations.push(term),
                    }
                    owned_occurrence_count += 1;
                }
                ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Proportion => {
                    let term = project_remaining_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    );
                    match classify_proportion_dimension(&term.identity.id) {
                        Some(ProportionDimension::Aspect) => region.proportion_aspects.push(term),
                        Some(ProportionDimension::WidthExtent) => {
                            region.proportion_width_extents.push(term)
                        }
                        Some(ProportionDimension::ArcForm) => {
                            region.proportion_arc_forms.push(term)
                        }
                        None => region.unclassified_proportions.push(term),
                    }
                    owned_occurrence_count += 1;
                }
                ClauseAtom::UnattachedExactNumber(quantity) => {
                    region.quantities.push(SemanticQuantity {
                        value: quantity.value,
                        provenance: source_occurrence(
                            document,
                            quantity.span,
                            region_index,
                            clause_index,
                            atom_index,
                        ),
                    });
                    owned_occurrence_count += 1;
                }
                ClauseAtom::CoreModifier(modifier) => {
                    region.thinnesses.push(SemanticThinness {
                        value: modifier.identity.value,
                        provenance: source_occurrence(
                            document,
                            modifier.span,
                            region_index,
                            clause_index,
                            atom_index,
                        ),
                    });
                    owned_occurrence_count += 1;
                }
                ClauseAtom::UnresolvedDiagnostic(diagnostic) => {
                    if !macro_parameter_binding
                        .as_ref()
                        .is_some_and(|binding| macro_invocation_owns_span(binding, diagnostic.span))
                    {
                        region.diagnostics.push(diagnostic.clone());
                    }
                }
                ClauseAtom::SaijikiRelation {
                    asset_id,
                    relation_type,
                    canonical_identity,
                    surface,
                    span,
                } => {
                    match explicit_previous_reference_occurrence(
                        document,
                        asset_id,
                        relation_type,
                        *canonical_identity,
                        *span,
                        region_index,
                        clause_index,
                        atom_index,
                    ) {
                        Ok(Some(occurrence)) => explicit_previous_references.push(occurrence),
                        Ok(None) => {}
                        Err(()) => issues.push(SemanticAssociationIssue {
                            kind: SemanticAssociationIssueKind::UpstreamConflict,
                            region_index,
                            occurrences: Vec::new(),
                            upstream_diagnostic: Some(NeutralDiagnostic {
                                span: *span,
                                surface: surface.clone(),
                                kind: NeutralDiagnosticKind::Conflict,
                                recognized: true,
                            }),
                        }),
                    }
                }
                ClauseAtom::CoreRole(_)
                | ClauseAtom::RemainingRole(_)
                | ClauseAtom::FunctionWord { .. } => {}
            }
        }
    }

    if let Some(binding) = &macro_parameter_binding {
        append_macro_ownership(
            document,
            &clause_stream,
            binding,
            &mut regions,
            &mut issues,
            &mut owned_occurrence_count,
        );
    }

    let mut entities = Vec::new();
    for (region_index, region) in regions {
        associate_region(
            region_index,
            region,
            &pre_head_ownership,
            &mut entities,
            &mut issues,
        );
    }

    let delivered_occurrence_count = entities.iter().map(entity_occurrence_count).sum::<usize>()
        + issues
            .iter()
            .flat_map(|issue| &issue.occurrences)
            .map(OwnedSemanticOccurrence::occurrence_count)
            .sum::<usize>();
    assert_eq!(
        delivered_occurrence_count, owned_occurrence_count,
        "semantic association must deliver every owned occurrence exactly once"
    );
    let owned_compound_reference_count = explicit_previous_references.len();
    let delivered_compound_reference_count = explicit_previous_references.len();
    assert_eq!(
        delivered_compound_reference_count, owned_compound_reference_count,
        "semantic association must retain every full-literal compound exactly once"
    );

    let ast = SemanticEntityAssociationAst {
        entities,
        complete: issues.is_empty(),
    };
    let canonical_bytes = ast.complete.then(|| canonical_ast_bytes(&ast));

    SemanticAssociationResult {
        schema_id: SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
        clause_stream,
        ast,
        issues,
        canonical_bytes,
        owned_occurrence_count,
        delivered_occurrence_count,
        explicit_previous_references,
        owned_compound_reference_count,
        delivered_compound_reference_count,
        macro_parameter_binding,
        clause_topology,
    }
}

fn macro_parameter_binding_owns_span(
    binding: &MacroParameterBindingResult,
    span: SourceSpan,
) -> bool {
    binding
        .complete
        .iter()
        .flat_map(|complete| &complete.parameters)
        .any(|parameter| parameter.source_span == span)
}

fn macro_invocation_owns_span(binding: &MacroParameterBindingResult, span: SourceSpan) -> bool {
    binding
        .macro_resolution
        .resolved
        .iter()
        .any(|resolved| resolved.span == span)
        || binding
            .macro_resolution
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.span == span)
}

fn append_macro_ownership(
    document: &NormalizedDdlDocument,
    clause_stream: &ClauseStream,
    binding: &MacroParameterBindingResult,
    regions: &mut BTreeMap<usize, AssociationRegion>,
    issues: &mut Vec<SemanticAssociationIssue>,
    owned_occurrence_count: &mut usize,
) {
    for complete in &binding.complete {
        let resolved = binding
            .macro_resolution
            .resolved
            .get(complete.invocation_index)
            .expect("accepted I-581 binding references one resolved invocation");
        assert_eq!(
            complete.definition_identity, resolved.definition_identity,
            "accepted I-581 binding retains the resolved definition identity"
        );
        let head = SemanticHead::MacroInvocation(semantic_macro_head(
            document,
            clause_stream,
            resolved,
            complete,
        ));
        let region_index = head.source().region_index;
        *owned_occurrence_count += head.occurrence_count();
        regions.entry(region_index).or_default().heads.push(head);
    }

    for diagnostic in &binding.macro_resolution.diagnostics {
        let provenance = SemanticMacroInvocationProvenance {
            source: source_occurrence(
                document,
                diagnostic.span,
                sentence_region_index(clause_stream, diagnostic.span),
                diagnostic
                    .clause_index
                    .expect("accepted I-580 diagnostic retains its clause owner"),
                diagnostic
                    .atom_index
                    .expect("accepted I-580 diagnostic retains its atom owner"),
            ),
            ordinal: diagnostic.ordinal,
            qualified_name: diagnostic
                .invocation
                .as_ref()
                .map(|invocation| invocation.qualified_name()),
        };
        *owned_occurrence_count += 1;
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::MacroResolution(diagnostic.kind),
            region_index: provenance.source.region_index,
            occurrences: vec![OwnedSemanticOccurrence::MacroDiagnostic(provenance)],
            upstream_diagnostic: None,
        });
    }

    for diagnostic in &binding.diagnostics {
        let resolved = binding
            .macro_resolution
            .resolved
            .get(diagnostic.invocation_index)
            .expect("accepted I-581 diagnostic references one resolved invocation");
        let provenance = macro_invocation_provenance(document, clause_stream, resolved);
        *owned_occurrence_count += 1;
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::MacroParameterBinding(diagnostic.kind),
            region_index: provenance.source.region_index,
            occurrences: vec![OwnedSemanticOccurrence::MacroDiagnostic(provenance)],
            upstream_diagnostic: None,
        });
    }
}

fn semantic_macro_head(
    document: &NormalizedDdlDocument,
    clause_stream: &ClauseStream,
    resolved: &crate::ResolvedMacroInvocation,
    complete: &crate::CompleteMacroParameterBinding,
) -> SemanticMacroInvocationHead {
    let mut parameters = complete
        .parameters
        .iter()
        .map(|parameter| semantic_macro_parameter(document, clause_stream, parameter))
        .collect::<Vec<_>>();
    parameters.sort_by(|left, right| left.name.cmp(&right.name));
    SemanticMacroInvocationHead {
        qualified_name: resolved.invocation.qualified_name(),
        definition_version: resolved.definition_identity.version().to_owned(),
        definition_digest: resolved.definition_identity.full_digest_hex().to_owned(),
        lock: resolved.lock.clone(),
        provenance: macro_invocation_provenance(document, clause_stream, resolved),
        parameters,
    }
}

fn macro_invocation_provenance(
    document: &NormalizedDdlDocument,
    clause_stream: &ClauseStream,
    resolved: &crate::ResolvedMacroInvocation,
) -> SemanticMacroInvocationProvenance {
    SemanticMacroInvocationProvenance {
        source: source_occurrence(
            document,
            resolved.span,
            sentence_region_index(clause_stream, resolved.span),
            resolved.clause_index,
            resolved.atom_index,
        ),
        ordinal: resolved.invocation.ordinal(),
        qualified_name: Some(resolved.invocation.qualified_name()),
    }
}

fn semantic_macro_parameter(
    document: &NormalizedDdlDocument,
    clause_stream: &ClauseStream,
    parameter: &MacroParameterBinding,
) -> SemanticMacroParameterBinding {
    assert_eq!(
        parameter.source_span,
        parameter.value.source_span(),
        "accepted I-581 parameter value retains its owned source span"
    );
    let (value, source_asset_id, canonical_surface_ja) = match &parameter.value {
        BoundMacroParameterValue::Integer { value, .. } => {
            (SemanticMacroParameterValue::Integer(*value), None, None)
        }
        BoundMacroParameterValue::Number { value, .. } => {
            (SemanticMacroParameterValue::Number(*value), None, None)
        }
        BoundMacroParameterValue::SemanticRef {
            category,
            canonical_id,
            source_asset_id,
            canonical_surface_ja,
            ..
        } => (
            SemanticMacroParameterValue::SemanticRef(SemanticIdentity {
                category: category.clone(),
                id: canonical_id.clone(),
            }),
            Some(source_asset_id.clone()),
            Some(canonical_surface_ja.clone()),
        ),
    };
    SemanticMacroParameterBinding {
        name: parameter.parameter_name.clone(),
        schema: parameter.parameter_schema.clone(),
        value,
        provenance: source_occurrence(
            document,
            parameter.source_span,
            sentence_region_index(clause_stream, parameter.source_span),
            parameter.source_fact_clause_index,
            parameter.source_fact_atom_index,
        ),
        source_asset_id,
        canonical_surface_ja,
    }
}

#[allow(clippy::too_many_arguments)]
fn explicit_previous_reference_occurrence(
    document: &NormalizedDdlDocument,
    asset_id: &str,
    relation_type: &str,
    canonical_identity: CanonicalRelationIdentity,
    span: SourceSpan,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> Result<Option<ExplicitPreviousReferenceOccurrence>, ()> {
    if asset_id != SAIJIKI_ASSET_ID
        || !canonical_relation_identity_is_valid(relation_type, canonical_identity)
    {
        return Err(());
    }
    let Some(reference) = canonical_identity.previous_reference else {
        return Ok(None);
    };
    let kind = match canonical_identity.kind {
        CanonicalRelationKind::Along => SemanticRelationKind::Along,
        CanonicalRelationKind::NotTouching => SemanticRelationKind::NotTouching,
        CanonicalRelationKind::Cutting => SemanticRelationKind::Cutting,
        CanonicalRelationKind::Between => SemanticRelationKind::Between,
        CanonicalRelationKind::Touching => SemanticRelationKind::Touching,
    };
    let reference = match reference {
        CanonicalPreviousReference::PreviousOne => SemanticPreviousReference::PreviousOne,
        CanonicalPreviousReference::PreviousTwo => SemanticPreviousReference::PreviousTwo,
    };
    Ok(Some(ExplicitPreviousReferenceOccurrence {
        kind,
        reference,
        provenance: source_occurrence(document, span, region_index, clause_index, atom_index),
        asset_id: asset_id.to_owned(),
        relation_type: relation_type.to_owned(),
    }))
}

pub(crate) fn sentence_region_index(stream: &ClauseStream, span: SourceSpan) -> usize {
    stream
        .separators
        .iter()
        .filter(|separator| {
            separator.kind == ClauseSeparatorKind::SentenceEnd
                && separator.span.end_byte <= span.start_byte
        })
        .count()
}

fn project_term(
    document: &NormalizedDdlDocument,
    term: &crate::CoreRoleTerm,
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

fn project_remaining_term(
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

pub(crate) fn project_semantic_term(
    document: &NormalizedDdlDocument,
    asset_id: &str,
    category_key: &str,
    canonical_surface_ja: &str,
    span: SourceSpan,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> SemanticTerm {
    let projected = project_macro_semantic_ref(category_key, canonical_surface_ja)
        .expect("accepted typed Saijiki term has a canonical semantic identity");
    SemanticTerm {
        identity: SemanticIdentity {
            category: projected.category,
            id: projected.canonical_id,
        },
        provenance: SemanticTermProvenance {
            source: source_occurrence(document, span, region_index, clause_index, atom_index),
            asset_id: asset_id.to_owned(),
            category_key: category_key.to_owned(),
            canonical_surface_ja: canonical_surface_ja.to_owned(),
        },
    }
}

fn source_occurrence(
    document: &NormalizedDdlDocument,
    span: SourceSpan,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> SourceOccurrence {
    SourceOccurrence {
        span,
        surface: document.source()[span.start_byte..span.end_byte].to_owned(),
        language: document.language(),
        region_index,
        clause_index,
        atom_index,
    }
}

fn associate_region(
    region_index: usize,
    mut region: AssociationRegion,
    pre_head_ownership: &PreHeadPhraseOwnership,
    entities: &mut Vec<SemanticEntity>,
    issues: &mut Vec<SemanticAssociationIssue>,
) {
    if region.heads.len() > 1 {
        region
            .heads
            .sort_by_key(|head| head.source().span.start_byte);
        for head in std::mem::take(&mut region.heads) {
            let owned_region = take_pre_head_region(&mut region, head, pre_head_ownership);
            associate_region(
                region_index,
                owned_region,
                pre_head_ownership,
                entities,
                issues,
            );
        }
        let surface_occurrences = take_surface_occurrences(&mut region);
        let fluctuation_occurrences = take_fluctuation_occurrences(&mut region);
        let proportion_occurrences = take_proportion_occurrences(&mut region);
        let mut occurrences = region
            .colors
            .drain(..)
            .map(OwnedSemanticOccurrence::Color)
            .chain(
                region
                    .quantities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Quantity),
            )
            .chain(
                region
                    .thinnesses
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Thinness),
            )
            .chain(region.touches.drain(..).map(OwnedSemanticOccurrence::Touch))
            .chain(
                region
                    .continuities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Continuity),
            )
            .chain(region.angles.drain(..).map(OwnedSemanticOccurrence::Angle))
            .chain(surface_occurrences)
            .chain(fluctuation_occurrences)
            .chain(proportion_occurrences)
            .collect::<Vec<_>>();
        occurrences.sort_by_key(|occurrence| occurrence.source().span.start_byte);
        if !occurrences.is_empty() {
            issues.push(SemanticAssociationIssue {
                kind: SemanticAssociationIssueKind::AmbiguousEntityOwnership,
                region_index,
                occurrences,
                upstream_diagnostic: None,
            });
        }
        append_upstream_issues(region_index, region.diagnostics, issues);
        return;
    }

    if region.heads.is_empty() {
        let surface_occurrences = take_surface_occurrences(&mut region);
        let fluctuation_occurrences = take_fluctuation_occurrences(&mut region);
        let proportion_occurrences = take_proportion_occurrences(&mut region);
        let mut occurrences = region
            .colors
            .drain(..)
            .map(OwnedSemanticOccurrence::Color)
            .chain(
                region
                    .quantities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Quantity),
            )
            .chain(
                region
                    .thinnesses
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Thinness),
            )
            .chain(region.touches.drain(..).map(OwnedSemanticOccurrence::Touch))
            .chain(
                region
                    .continuities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Continuity),
            )
            .chain(region.angles.drain(..).map(OwnedSemanticOccurrence::Angle))
            .chain(surface_occurrences)
            .chain(fluctuation_occurrences)
            .chain(proportion_occurrences)
            .collect::<Vec<_>>();
        occurrences.sort_by_key(|occurrence| occurrence.source().span.start_byte);
        if !occurrences.is_empty() {
            issues.push(SemanticAssociationIssue {
                kind: SemanticAssociationIssueKind::MissingEntityHead,
                region_index,
                occurrences,
                upstream_diagnostic: None,
            });
        }
        append_upstream_issues(region_index, region.diagnostics, issues);
        return;
    }

    let diagnostics = std::mem::take(&mut region.diagnostics);
    let head = region.heads.pop().expect("single head was checked");
    let mut owned_region = take_pre_head_region(&mut region, head, pre_head_ownership);
    let occurrences = take_all_modifier_occurrences(&mut region);
    if !occurrences.is_empty() {
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::AmbiguousEntityOwnership,
            region_index,
            occurrences,
            upstream_diagnostic: None,
        });
    }
    let head = owned_region
        .heads
        .pop()
        .expect("bounded phrase retains its head");
    let color = select_term(
        owned_region.colors,
        OwnedSemanticOccurrence::Color,
        SemanticAssociationIssueKind::ConflictingColors,
        region_index,
        issues,
    );
    let quantity = match owned_region.quantities.len() {
        0 => None,
        1 => owned_region.quantities.pop(),
        _ => {
            let occurrences = owned_region
                .quantities
                .drain(..)
                .map(OwnedSemanticOccurrence::Quantity)
                .collect();
            issues.push(SemanticAssociationIssue {
                kind: SemanticAssociationIssueKind::ConflictingQuantities,
                region_index,
                occurrences,
                upstream_diagnostic: None,
            });
            None
        }
    };
    let thinness = match owned_region.thinnesses.len() {
        0 => None,
        1 => owned_region.thinnesses.pop(),
        _ => {
            issues.push(SemanticAssociationIssue {
                kind: SemanticAssociationIssueKind::ConflictingThinness,
                region_index,
                occurrences: owned_region
                    .thinnesses
                    .into_iter()
                    .map(OwnedSemanticOccurrence::Thinness)
                    .collect(),
                upstream_diagnostic: None,
            });
            None
        }
    };
    let touch = select_term(
        owned_region.touches,
        OwnedSemanticOccurrence::Touch,
        SemanticAssociationIssueKind::ConflictingTouches,
        region_index,
        issues,
    );
    let continuity = select_term(
        owned_region.continuities,
        OwnedSemanticOccurrence::Continuity,
        SemanticAssociationIssueKind::ConflictingContinuities,
        region_index,
        issues,
    );
    let angle = select_term(
        owned_region.angles,
        OwnedSemanticOccurrence::Angle,
        SemanticAssociationIssueKind::ConflictingAngles,
        region_index,
        issues,
    );
    let quality = select_term(
        owned_region.surface_qualities,
        OwnedSemanticOccurrence::Surface,
        SemanticAssociationIssueKind::ConflictingSurfaceQualities,
        region_index,
        issues,
    );
    let intensity = select_term(
        owned_region.surface_intensities,
        OwnedSemanticOccurrence::Surface,
        SemanticAssociationIssueKind::ConflictingSurfaceIntensities,
        region_index,
        issues,
    );
    if !owned_region.unclassified_surfaces.is_empty() {
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::UnknownSurfaceDimension,
            region_index,
            occurrences: owned_region
                .unclassified_surfaces
                .into_iter()
                .map(OwnedSemanticOccurrence::Surface)
                .collect(),
            upstream_diagnostic: None,
        });
    }
    let amplitude = select_term(
        owned_region.fluctuation_amplitudes,
        OwnedSemanticOccurrence::Fluctuation,
        SemanticAssociationIssueKind::ConflictingFluctuationAmplitudes,
        region_index,
        issues,
    );
    let frequency = select_term(
        owned_region.fluctuation_frequencies,
        OwnedSemanticOccurrence::Fluctuation,
        SemanticAssociationIssueKind::ConflictingFluctuationFrequencies,
        region_index,
        issues,
    );
    let fluctuation_quality = select_term(
        owned_region.fluctuation_qualities,
        OwnedSemanticOccurrence::Fluctuation,
        SemanticAssociationIssueKind::ConflictingFluctuationQualities,
        region_index,
        issues,
    );
    if !owned_region.unclassified_fluctuations.is_empty() {
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::UnknownFluctuationDimension,
            region_index,
            occurrences: owned_region
                .unclassified_fluctuations
                .into_iter()
                .map(OwnedSemanticOccurrence::Fluctuation)
                .collect(),
            upstream_diagnostic: None,
        });
    }
    let aspect = select_term(
        owned_region.proportion_aspects,
        OwnedSemanticOccurrence::Proportion,
        SemanticAssociationIssueKind::ConflictingProportionAspects,
        region_index,
        issues,
    );
    let width_extent = select_term(
        owned_region.proportion_width_extents,
        OwnedSemanticOccurrence::Proportion,
        SemanticAssociationIssueKind::ConflictingProportionWidthExtents,
        region_index,
        issues,
    );
    let arc_form = select_term(
        owned_region.proportion_arc_forms,
        OwnedSemanticOccurrence::Proportion,
        SemanticAssociationIssueKind::ConflictingProportionArcForms,
        region_index,
        issues,
    );
    if !owned_region.unclassified_proportions.is_empty() {
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::UnknownProportionDimension,
            region_index,
            occurrences: owned_region
                .unclassified_proportions
                .into_iter()
                .map(OwnedSemanticOccurrence::Proportion)
                .collect(),
            upstream_diagnostic: None,
        });
    }
    entities.push(SemanticEntity {
        head,
        color,
        quantity,
        thinness,
        touch,
        continuity,
        angle,
        surface: SemanticSurface { quality, intensity },
        fluctuation: SemanticFluctuation {
            amplitude,
            frequency,
            quality: fluctuation_quality,
        },
        proportion: SemanticProportion {
            aspect,
            width_extent,
            arc_form,
        },
    });
    append_upstream_issues(region_index, diagnostics, issues);
}

fn take_all_modifier_occurrences(region: &mut AssociationRegion) -> Vec<OwnedSemanticOccurrence> {
    let surface_occurrences = take_surface_occurrences(region);
    let fluctuation_occurrences = take_fluctuation_occurrences(region);
    let proportion_occurrences = take_proportion_occurrences(region);
    let mut occurrences = region
        .colors
        .drain(..)
        .map(OwnedSemanticOccurrence::Color)
        .chain(
            region
                .quantities
                .drain(..)
                .map(OwnedSemanticOccurrence::Quantity),
        )
        .chain(
            region
                .thinnesses
                .drain(..)
                .map(OwnedSemanticOccurrence::Thinness),
        )
        .chain(region.touches.drain(..).map(OwnedSemanticOccurrence::Touch))
        .chain(
            region
                .continuities
                .drain(..)
                .map(OwnedSemanticOccurrence::Continuity),
        )
        .chain(region.angles.drain(..).map(OwnedSemanticOccurrence::Angle))
        .chain(surface_occurrences)
        .chain(fluctuation_occurrences)
        .chain(proportion_occurrences)
        .collect::<Vec<_>>();
    occurrences.sort_by_key(|occurrence| occurrence.source().span.start_byte);
    occurrences
}

fn take_pre_head_region(
    region: &mut AssociationRegion,
    head: SemanticHead,
    ownership: &PreHeadPhraseOwnership,
) -> AssociationRegion {
    AssociationRegion {
        colors: take_owned_terms(&mut region.colors, &head, ownership),
        quantities: take_owned_quantities(&mut region.quantities, &head, ownership),
        thinnesses: take_owned_thinnesses(&mut region.thinnesses, &head, ownership),
        touches: take_owned_terms(&mut region.touches, &head, ownership),
        continuities: take_owned_terms(&mut region.continuities, &head, ownership),
        angles: take_owned_terms(&mut region.angles, &head, ownership),
        surface_qualities: take_owned_terms(&mut region.surface_qualities, &head, ownership),
        surface_intensities: take_owned_terms(&mut region.surface_intensities, &head, ownership),
        unclassified_surfaces: take_owned_terms(
            &mut region.unclassified_surfaces,
            &head,
            ownership,
        ),
        fluctuation_amplitudes: take_owned_terms(
            &mut region.fluctuation_amplitudes,
            &head,
            ownership,
        ),
        fluctuation_frequencies: take_owned_terms(
            &mut region.fluctuation_frequencies,
            &head,
            ownership,
        ),
        fluctuation_qualities: take_owned_terms(
            &mut region.fluctuation_qualities,
            &head,
            ownership,
        ),
        unclassified_fluctuations: take_owned_terms(
            &mut region.unclassified_fluctuations,
            &head,
            ownership,
        ),
        proportion_aspects: take_owned_terms(&mut region.proportion_aspects, &head, ownership),
        proportion_width_extents: take_owned_terms(
            &mut region.proportion_width_extents,
            &head,
            ownership,
        ),
        proportion_arc_forms: take_owned_terms(&mut region.proportion_arc_forms, &head, ownership),
        unclassified_proportions: take_owned_terms(
            &mut region.unclassified_proportions,
            &head,
            ownership,
        ),
        heads: vec![head],
        diagnostics: Vec::new(),
    }
}

fn take_owned_terms(
    terms: &mut Vec<SemanticTerm>,
    head: &SemanticHead,
    ownership: &PreHeadPhraseOwnership,
) -> Vec<SemanticTerm> {
    let (owned, remaining) = std::mem::take(terms)
        .into_iter()
        .partition(|term| ownership.owns(head, term.provenance.source.span));
    *terms = remaining;
    owned
}

fn take_owned_quantities(
    quantities: &mut Vec<SemanticQuantity>,
    head: &SemanticHead,
    ownership: &PreHeadPhraseOwnership,
) -> Vec<SemanticQuantity> {
    let (owned, remaining) = std::mem::take(quantities)
        .into_iter()
        .partition(|quantity| ownership.owns(head, quantity.provenance.span));
    *quantities = remaining;
    owned
}

fn take_owned_thinnesses(
    thinnesses: &mut Vec<SemanticThinness>,
    head: &SemanticHead,
    ownership: &PreHeadPhraseOwnership,
) -> Vec<SemanticThinness> {
    let (owned, remaining) = std::mem::take(thinnesses)
        .into_iter()
        .partition(|thinness| ownership.owns(head, thinness.provenance.span));
    *thinnesses = remaining;
    owned
}

fn take_surface_occurrences(region: &mut AssociationRegion) -> Vec<OwnedSemanticOccurrence> {
    region
        .surface_qualities
        .drain(..)
        .chain(region.surface_intensities.drain(..))
        .chain(region.unclassified_surfaces.drain(..))
        .map(OwnedSemanticOccurrence::Surface)
        .collect()
}

fn take_fluctuation_occurrences(region: &mut AssociationRegion) -> Vec<OwnedSemanticOccurrence> {
    region
        .fluctuation_amplitudes
        .drain(..)
        .chain(region.fluctuation_frequencies.drain(..))
        .chain(region.fluctuation_qualities.drain(..))
        .chain(region.unclassified_fluctuations.drain(..))
        .map(OwnedSemanticOccurrence::Fluctuation)
        .collect()
}

fn take_proportion_occurrences(region: &mut AssociationRegion) -> Vec<OwnedSemanticOccurrence> {
    region
        .proportion_aspects
        .drain(..)
        .chain(region.proportion_width_extents.drain(..))
        .chain(region.proportion_arc_forms.drain(..))
        .chain(region.unclassified_proportions.drain(..))
        .map(OwnedSemanticOccurrence::Proportion)
        .collect()
}

fn select_term(
    mut terms: Vec<SemanticTerm>,
    into_occurrence: fn(SemanticTerm) -> OwnedSemanticOccurrence,
    conflict_kind: SemanticAssociationIssueKind,
    region_index: usize,
    issues: &mut Vec<SemanticAssociationIssue>,
) -> Option<SemanticTerm> {
    match terms.len() {
        0 => None,
        1 => terms.pop(),
        _ => {
            issues.push(SemanticAssociationIssue {
                kind: conflict_kind,
                region_index,
                occurrences: terms.into_iter().map(into_occurrence).collect(),
                upstream_diagnostic: None,
            });
            None
        }
    }
}

fn append_upstream_issues(
    region_index: usize,
    mut diagnostics: Vec<NeutralDiagnostic>,
    issues: &mut Vec<SemanticAssociationIssue>,
) {
    diagnostics.sort_by_key(|diagnostic| diagnostic.span.start_byte);
    issues.extend(
        diagnostics
            .into_iter()
            .map(|diagnostic| SemanticAssociationIssue {
                kind: match diagnostic.kind {
                    NeutralDiagnosticKind::Hole => SemanticAssociationIssueKind::UpstreamHole,
                    NeutralDiagnosticKind::Conflict => {
                        SemanticAssociationIssueKind::UpstreamConflict
                    }
                    NeutralDiagnosticKind::Unknown => SemanticAssociationIssueKind::UpstreamUnknown,
                },
                region_index,
                occurrences: Vec::new(),
                upstream_diagnostic: Some(diagnostic),
            }),
    );
}

fn entity_occurrence_count(entity: &SemanticEntity) -> usize {
    entity.head.occurrence_count()
        + usize::from(entity.color.is_some())
        + usize::from(entity.quantity.is_some())
        + usize::from(entity.thinness.is_some())
        + usize::from(entity.touch.is_some())
        + usize::from(entity.continuity.is_some())
        + usize::from(entity.angle.is_some())
        + usize::from(entity.surface.quality.is_some())
        + usize::from(entity.surface.intensity.is_some())
        + usize::from(entity.fluctuation.amplitude.is_some())
        + usize::from(entity.fluctuation.frequency.is_some())
        + usize::from(entity.fluctuation.quality.is_some())
        + usize::from(entity.proportion.aspect.is_some())
        + usize::from(entity.proportion.width_extent.is_some())
        + usize::from(entity.proportion.arc_form.is_some())
}

fn canonical_ast_bytes(ast: &SemanticEntityAssociationAst) -> Vec<u8> {
    let entities = ast
        .entities
        .iter()
        .map(semantic_entity_value)
        .collect::<Vec<_>>();
    let mut root = BTreeMap::new();
    root.insert("entities".to_owned(), Value::Array(entities));
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID.to_owned()),
    );
    serde_json::to_vec(&root).expect("closed semantic association AST serializes")
}

pub(crate) fn semantic_entity_value(entity: &SemanticEntity) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "angle".to_owned(),
        entity
            .angle
            .as_ref()
            .map(|angle| semantic_identity_value(&angle.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "color".to_owned(),
        entity
            .color
            .as_ref()
            .map(|color| semantic_identity_value(&color.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "continuity".to_owned(),
        entity
            .continuity
            .as_ref()
            .map(|continuity| semantic_identity_value(&continuity.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "fluctuation".to_owned(),
        semantic_fluctuation_value(&entity.fluctuation),
    );
    record.insert("head".to_owned(), semantic_head_value(&entity.head));
    record.insert(
        "proportion".to_owned(),
        semantic_proportion_value(&entity.proportion),
    );
    record.insert(
        "surface".to_owned(),
        semantic_surface_value(&entity.surface),
    );
    record.insert(
        "touch".to_owned(),
        entity
            .touch
            .as_ref()
            .map(|touch| semantic_identity_value(&touch.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "thinness".to_owned(),
        entity
            .thinness
            .as_ref()
            .map(|thinness| Value::String(thinness.value.as_str().to_owned()))
            .unwrap_or(Value::Null),
    );
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

fn semantic_head_value(head: &SemanticHead) -> Value {
    match head {
        SemanticHead::Primitive(term) => semantic_identity_value(&term.identity),
        SemanticHead::MacroInvocation(head) => semantic_macro_head_value(head),
    }
}

fn semantic_macro_head_value(head: &SemanticMacroInvocationHead) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "definition_digest".to_owned(),
        Value::String(head.definition_digest.clone()),
    );
    record.insert(
        "definition_version".to_owned(),
        Value::String(head.definition_version.clone()),
    );
    record.insert(
        "kind".to_owned(),
        Value::String("macro_invocation".to_owned()),
    );
    record.insert(
        "parameters".to_owned(),
        Value::Array(
            head.parameters
                .iter()
                .map(semantic_macro_parameter_value)
                .collect(),
        ),
    );
    record.insert(
        "qualified_name".to_owned(),
        Value::String(head.qualified_name.clone()),
    );
    Value::Object(record.into_iter().collect())
}

fn semantic_macro_parameter_value(parameter: &SemanticMacroParameterBinding) -> Value {
    let mut record = BTreeMap::new();
    record.insert("name".to_owned(), Value::String(parameter.name.clone()));
    record.insert(
        "schema".to_owned(),
        serde_json::to_value(&parameter.schema).expect("closed parameter schema serializes"),
    );
    record.insert(
        "value".to_owned(),
        match &parameter.value {
            SemanticMacroParameterValue::Integer(value) => Value::Number(Number::from(*value)),
            SemanticMacroParameterValue::Number(value) => Value::Number(
                Number::from_f64(*value).expect("accepted macro Number binding is finite"),
            ),
            SemanticMacroParameterValue::SemanticRef(identity) => semantic_identity_value(identity),
        },
    );
    Value::Object(record.into_iter().collect())
}

fn semantic_surface_value(surface: &SemanticSurface) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "intensity".to_owned(),
        surface
            .intensity
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "quality".to_owned(),
        surface
            .quality
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    Value::Object(record.into_iter().collect())
}

fn semantic_fluctuation_value(fluctuation: &SemanticFluctuation) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "amplitude".to_owned(),
        fluctuation
            .amplitude
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "frequency".to_owned(),
        fluctuation
            .frequency
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "quality".to_owned(),
        fluctuation
            .quality
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    Value::Object(record.into_iter().collect())
}

fn semantic_proportion_value(proportion: &SemanticProportion) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "arc_form".to_owned(),
        proportion
            .arc_form
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "aspect".to_owned(),
        proportion
            .aspect
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "width_extent".to_owned(),
        proportion
            .width_extent
            .as_ref()
            .map(|term| semantic_identity_value(&term.identity))
            .unwrap_or(Value::Null),
    );
    Value::Object(record.into_iter().collect())
}

pub(crate) fn semantic_identity_value(identity: &SemanticIdentity) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "category".to_owned(),
        Value::String(identity.category.clone()),
    );
    record.insert("id".to_owned(), Value::String(identity.id.clone()));
    Value::Object(record.into_iter().collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::CanonicalRelationForm;

    #[test]
    fn contradictory_relation_identity_blocks_semantic_edge_and_canonical_bytes() {
        let document = NormalizedDdlDocument::new(
            "circle along".to_owned(),
            ResolvedInstructionLanguage::En,
            Vec::new(),
        )
        .expect("test source forms a document");
        let mut stream =
            crate::parse_clause_stream(&document).expect("test source forms a clause stream");
        let relation = stream
            .clauses
            .iter_mut()
            .flat_map(|clause| &mut clause.atoms)
            .find_map(|atom| match atom {
                ClauseAtom::SaijikiRelation {
                    canonical_identity, ..
                } => Some(canonical_identity),
                _ => None,
            })
            .expect("test source has one relation atom");
        relation.form = CanonicalRelationForm::FullLiteral;

        let result = build_semantic_entities(
            &document,
            stream,
            None,
            PreHeadPhraseOwnership::default(),
            ClauseTopologyEvidence::default(),
        );

        assert!(result.explicit_previous_references.is_empty());
        assert!(result.canonical_bytes.is_none());
        assert_eq!(result.issues.len(), 1);
        assert_eq!(
            result.issues[0].kind,
            SemanticAssociationIssueKind::UpstreamConflict
        );
        let diagnostic = result.issues[0]
            .upstream_diagnostic
            .as_ref()
            .expect("identity conflict retains a typed source diagnostic");
        assert_eq!(diagnostic.kind, NeutralDiagnosticKind::Conflict);
        assert_eq!(diagnostic.surface, "along");
    }
}
