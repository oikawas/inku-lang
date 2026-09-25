//! Single-head semantic association over the accepted source-preserving clause stream.

use std::collections::{BTreeMap, BTreeSet};

use serde::Serialize;
use serde_json::{Number, Value};

use crate::{
    AttachmentEvidenceResult, AttachmentMarkerEvidence, AttachmentMarkerKind,
    BoundMacroParameterValue, CanonicalPreviousReference, CanonicalRelationIdentity,
    CanonicalRelationKind, ClauseAtom, ClauseSeparatorKind, ClauseStream, ClauseStreamError,
    CoreModifierValue, CoreRoleKind, EnglishAttachmentMarkerKind, EnglishDeterminerKind,
    JapaneseAttachmentMarkerKind, MacroInvocationResolutionDiagnosticKind,
    MacroLockResolutionIdentity, MacroParameterBinding, MacroParameterBindingDiagnosticKind,
    MacroParameterBindingResult, MarkerId, NeutralDiagnostic, NeutralDiagnosticKind,
    NormalizedDdlDocument, ParameterSchema, RemainingRoleKind, ResolvedInstructionLanguage,
    SAIJIKI_ASSET_ID,
    SemanticExplicitGeometry, SemanticNumericPosition, SourceSpan, collect_attachment_evidence,
    geometry::{GeometrySyntaxIssueKind, analyze_clause_geometry},
    project_macro_semantic_ref,
    saijiki::canonical_relation_identity_is_valid,
};

/// Stable identity for the single-head semantic AST.
pub const SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID: &str = "inku.semantic-entity-association.v19";

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

/// Closed structural relation proving how one upstream diagnostic blocked typed ownership.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticUpstreamCausalRelation {
    MissingEntityHeadGap,
    EntityOwnershipPath,
    InstructionOwnershipPath,
    ContinuationBoundary,
}

impl SemanticUpstreamCausalRelation {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MissingEntityHeadGap => "missing_entity_head_gap",
            Self::EntityOwnershipPath => "entity_ownership_path",
            Self::InstructionOwnershipPath => "instruction_ownership_path",
            Self::ContinuationBoundary => "continuation_boundary",
        }
    }
}

/// Source-ordered identity of one existing upstream diagnostic occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticUpstreamDiagnosticCause {
    pub relation: SemanticUpstreamCausalRelation,
    pub diagnostic_kind: NeutralDiagnosticKind,
    pub recognized: bool,
    pub span: SourceSpan,
    pub region_index: usize,
    pub clause_index: usize,
    pub atom_index: usize,
}

/// Explicit causal attribution for one existing typed issue.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SemanticIssueCausalProvenance {
    Unattributed,
    UpstreamDiagnostics(Vec<SemanticUpstreamDiagnosticCause>),
}

/// Closed semantic identity of one accepted explicit previous-object relation.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SemanticRelationKind {
    Along,
    NotTouching,
    Cutting,
    Between,
    Touching,
    Connected,
    Mirrored,
}

impl SemanticRelationKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Along => "along",
            Self::NotTouching => "not_touching",
            Self::Cutting => "cutting",
            Self::Between => "between",
            Self::Touching => "touching",
            Self::Connected => "connected",
            Self::Mirrored => "mirrored",
        }
    }
}

/// Closed source-order reference depth for one explicit relation.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
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
    pub target: Option<crate::saijiki::TouchingLiteralTarget>,
    pub target_endpoint: Option<inku_score::Endpoint>,
    pub target_path_selection: Option<inku_score::TargetPathSelection>,
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

/// One source-authored finite sequence applied over instances of a drawing instruction.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticSequence {
    pub kind: SemanticSequenceKind,
    pub operator: SemanticTerm,
    pub items: Vec<SemanticTerm>,
    pub units: Vec<SemanticSequenceUnit>,
    pub quantity: Option<SemanticQuantity>,
    pub markers: Vec<SourceOccurrence>,
}

/// Closed sequence payload. Color retains its established compact wire path;
/// other fields and complete source units lower through cycle members.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticSequenceKind {
    Color,
    Field(SemanticSequenceField),
    Units,
}

/// Closed typed fields whose values can form complete ordinary templates.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticSequenceField {
    Touch,
    Continuity,
    Angle,
    SurfaceQuality,
    SurfaceIntensity,
    FluctuationAmplitude,
    FluctuationFrequency,
    FluctuationQuality,
    FluctuationSpread,
    ProportionAspect,
    ProportionWidthExtent,
    ProportionArcForm,
}

impl SemanticSequenceField {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Touch => "touch",
            Self::Continuity => "continuity",
            Self::Angle => "angle",
            Self::SurfaceQuality => "surface_quality",
            Self::SurfaceIntensity => "surface_intensity",
            Self::FluctuationAmplitude => "fluctuation_amplitude",
            Self::FluctuationFrequency => "fluctuation_frequency",
            Self::FluctuationQuality => "fluctuation_quality",
            Self::FluctuationSpread => "ink_spread",
            Self::ProportionAspect => "proportion_aspect",
            Self::ProportionWidthExtent => "proportion_width_extent",
            Self::ProportionArcForm => "proportion_arc_form",
        }
    }
}

/// One ordered complete-body item. Multiple indices form one anonymous `組` / `group of`.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticSequenceUnit {
    pub member_entity_indices: Vec<usize>,
    pub source_span: SourceSpan,
}

/// One sequence and the entity occurrence that owns its eventual instruction predicate.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticEntitySequence {
    pub target_entity_index: usize,
    pub sequence: SemanticSequence,
}

/// A recognized sequence phrase that cannot acquire one complete structural meaning.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticSequenceIssueKind {
    AmbiguousTarget,
    MissingItems,
    InvalidAlternatingCardinality,
    InvalidConnectors,
    MultipleOperators,
    MixedFields,
    InvalidUnitSyntax,
    MissingQuantityOwner,
}

impl SemanticSequenceIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::AmbiguousTarget => "ambiguous_sequence_target",
            Self::MissingItems => "missing_sequence_items",
            Self::InvalidAlternatingCardinality => "invalid_alternating_cardinality",
            Self::InvalidConnectors => "invalid_sequence_connectors",
            Self::MultipleOperators => "multiple_sequence_operators",
            Self::MixedFields => "mixed_sequence_fields",
            Self::InvalidUnitSyntax => "invalid_sequence_unit_syntax",
            Self::MissingQuantityOwner => "missing_sequence_quantity_owner",
        }
    }
}

/// Source-owned evidence for one invalid known sequence phrase.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticSequenceIssue {
    pub kind: SemanticSequenceIssueKind,
    pub operator: SemanticTerm,
    pub items: Vec<SemanticTerm>,
    pub quantity: Option<SemanticQuantity>,
    pub markers: Vec<SourceOccurrence>,
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

/// One explicit core relative-scale value and its exact source provenance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticRelativeScale {
    pub value: CoreModifierValue,
    pub provenance: SourceOccurrence,
}

/// Canonical value of one source-owned macro parameter.
#[derive(Clone, Debug, PartialEq)]
pub enum SemanticMacroParameterValue {
    ExactDecimal(crate::ExactDecimal),
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

pub(crate) fn semantic_macro_parameters_have_same_meaning(
    left: &[SemanticMacroParameterBinding],
    right: &[SemanticMacroParameterBinding],
) -> bool {
    if left.len() != right.len()
        || left
            .iter()
            .map(|parameter| &parameter.name)
            .collect::<BTreeSet<_>>()
            .len()
            != left.len()
        || right
            .iter()
            .map(|parameter| &parameter.name)
            .collect::<BTreeSet<_>>()
            .len()
            != right.len()
    {
        return false;
    }

    left.iter().all(|parameter| {
        right.iter().any(|candidate| {
            candidate.name == parameter.name
                && candidate.schema == parameter.schema
                && candidate.value == parameter.value
        })
    })
}

pub(crate) fn semantic_macro_parameters_match_complete_binding(
    parameters: &[SemanticMacroParameterBinding],
    complete: &crate::CompleteMacroParameterBinding,
) -> bool {
    if parameters.len() != complete.parameters.len()
        || parameters
            .iter()
            .map(|parameter| &parameter.name)
            .collect::<BTreeSet<_>>()
            .len()
            != parameters.len()
        || complete
            .parameters
            .iter()
            .map(|parameter| &parameter.parameter_name)
            .collect::<BTreeSet<_>>()
            .len()
            != complete.parameters.len()
    {
        return false;
    }

    parameters.iter().all(|parameter| {
        complete.parameters.iter().any(|candidate| {
            candidate.parameter_name == parameter.name
                && candidate.parameter_schema == parameter.schema
                && semantic_macro_parameter_value_from_bound(&candidate.value) == parameter.value
        })
    })
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

/// Four independent explicit Fluctuation dimensions. Missing values remain unspecified.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct SemanticFluctuation {
    pub spread: Option<SemanticTerm>,
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
    pub shape_constraint: Option<crate::SemanticShapeConstraint>,
    pub head: SemanticHead,
    pub color: Option<SemanticTerm>,
    pub quantity: Option<SemanticQuantity>,
    pub thinness: Option<SemanticThinness>,
    pub relative_scale: Option<SemanticRelativeScale>,
    pub explicit_geometry: Option<SemanticExplicitGeometry>,
    /// Additional original size candidates, resolved after canvas selection.
    pub additional_relative_scales: Vec<SemanticRelativeScale>,
    pub additional_explicit_geometries: Vec<SemanticExplicitGeometry>,
    pub additional_width_extents: Vec<SemanticTerm>,
    pub numeric_position: Option<SemanticNumericPosition>,
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
    pub sequences: Vec<SemanticEntitySequence>,
    pub complete: bool,
}

/// An association-owned occurrence delivered to a typed issue rather than an AST field.
#[derive(Clone, Debug, PartialEq)]
pub enum OwnedSemanticOccurrence {
    ShapeConstraint(crate::SemanticShapeConstraint),
    Head(SemanticHead),
    MacroDiagnostic(SemanticMacroInvocationProvenance),
    Color(SemanticTerm),
    Quantity(SemanticQuantity),
    Thinness(SemanticThinness),
    RelativeScale(SemanticRelativeScale),
    ExplicitGeometry(SemanticExplicitGeometry),
    NumericPosition(SemanticNumericPosition),
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
            Self::ShapeConstraint(value) => &value.provenance,
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
            Self::RelativeScale(relative_scale) => &relative_scale.provenance,
            Self::ExplicitGeometry(geometry) => geometry.source(),
            Self::NumericPosition(position) => position.source(),
        }
    }

    const fn occurrence_count(&self) -> usize {
        match self {
            Self::ShapeConstraint(value) => 1 + value.additional_provenance.len(),
            Self::Head(head) => head.occurrence_count(),
            Self::MacroDiagnostic(_)
            | Self::Color(_)
            | Self::Quantity(_)
            | Self::Thinness(_)
            | Self::RelativeScale(_)
            | Self::ExplicitGeometry(_)
            | Self::NumericPosition(_)
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
    ConflictingShapeConstraints,
    AmbiguousEntityOwnership,
    MissingEntityHead,
    ConflictingColors,
    ConflictingQuantities,
    ConflictingThinness,
    ConflictingRelativeScales,
    ConflictingExplicitGeometries,
    ConflictingNumericPositions,
    ConflictingRelativeAndExplicitGeometry,
    IncompleteNumericGeometry,
    IncompleteNumericPosition,
    UnownedExactDecimal,
    ConflictingTouches,
    ConflictingContinuities,
    ConflictingAngles,
    ConflictingSurfaceQualities,
    ConflictingSurfaceIntensities,
    UnknownSurfaceDimension,
    ConflictingFluctuationAmplitudes,
    ConflictingFluctuationFrequencies,
    ConflictingFluctuationQualities,
    ConflictingFluctuationSpreads,
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
            Self::ConflictingRelativeScales => "conflicting_relative_scales",
            Self::ConflictingExplicitGeometries => "conflicting_explicit_geometries",
            Self::ConflictingNumericPositions => "conflicting_numeric_positions",
            Self::ConflictingRelativeAndExplicitGeometry => {
                "conflicting_relative_and_explicit_geometry"
            }
            Self::IncompleteNumericGeometry => "incomplete_numeric_geometry",
            Self::IncompleteNumericPosition => "incomplete_numeric_position",
            Self::UnownedExactDecimal => "unowned_exact_decimal",
            Self::ConflictingTouches => "conflicting_touches",
            Self::ConflictingContinuities => "conflicting_continuities",
            Self::ConflictingAngles => "conflicting_angles",
            Self::ConflictingSurfaceQualities => "conflicting_surface_qualities",
            Self::ConflictingSurfaceIntensities => "conflicting_surface_intensities",
            Self::UnknownSurfaceDimension => "unknown_surface_dimension",
            Self::ConflictingFluctuationAmplitudes => "conflicting_fluctuation_amplitudes",
            Self::ConflictingFluctuationFrequencies => "conflicting_fluctuation_frequencies",
            Self::ConflictingFluctuationQualities => "conflicting_fluctuation_qualities",
            Self::ConflictingFluctuationSpreads => "conflicting_fluctuation_spreads",
            Self::UnknownFluctuationDimension => "unknown_fluctuation_dimension",
            Self::ConflictingShapeConstraints => "conflicting_shape_constraints",
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
    pub causal_provenance: SemanticIssueCausalProvenance,
}

/// Source-preserving association result. Entity counts and compound-reference counts remain
/// separate so the accepted I-592 occurrence accounting is not recounted by this slice.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticAssociationResult {
    pub schema_id: &'static str,
    pub clause_stream: ClauseStream,
    pub ast: SemanticEntityAssociationAst,
    pub issues: Vec<SemanticAssociationIssue>,
    pub sequence_issues: Vec<SemanticSequenceIssue>,
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
                    .any(|parameter| parameter.owns_span(span))
            })
    }
}

#[derive(Clone, Debug)]
struct PendingSemanticSequence {
    target_head_start: usize,
    sequence: SemanticSequence,
    unit_head_starts: Vec<Vec<usize>>,
}

fn collect_semantic_sequences(
    document: &NormalizedDdlDocument,
    stream: &ClauseStream,
) -> (
    Vec<PendingSemanticSequence>,
    Vec<SemanticSequenceIssue>,
    BTreeSet<usize>,
) {
    let mut pending = Vec::new();
    let mut issues = Vec::new();
    let mut claimed_color_starts = BTreeSet::new();

    for (clause_index, clause) in stream.clauses.iter().enumerate() {
        let operators = clause
            .atoms
            .iter()
            .enumerate()
            .filter_map(|(atom_index, atom)| match atom {
                ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Sequence => {
                    Some((atom_index, term))
                }
                _ => None,
            })
            .collect::<Vec<_>>();
        if operators.len() > 1 {
            let region_index = sentence_region_index(stream, operators[0].1.span);
            let mut clause_color_indices = BTreeSet::new();
            let mut clause_marker_indices = BTreeSet::new();
            for (operator_index, operator_term) in &operators {
                let operator = project_remaining_term(
                    document,
                    operator_term,
                    region_index,
                    clause_index,
                    *operator_index,
                );
                let color_indices = sequence_color_indices(
                    document.language(),
                    clause,
                    *operator_index,
                    operator.identity.id.as_str(),
                );
                clause_marker_indices.extend(sequence_marker_indices(
                    document.language(),
                    clause,
                    *operator_index,
                    &color_indices,
                    operator.identity.id.as_str(),
                ));
                clause_color_indices.extend(color_indices);
            }
            let clause_color_indices = clause_color_indices.into_iter().collect::<Vec<_>>();
            let clause_marker_indices = clause_marker_indices.into_iter().collect::<Vec<_>>();
            for &atom_index in &clause_color_indices {
                if let ClauseAtom::CoreRole(term) = &clause.atoms[atom_index] {
                    claimed_color_starts.insert(term.span.start_byte);
                }
            }
            for (issue_index, (operator_index, operator_term)) in operators.into_iter().enumerate()
            {
                let operator = project_remaining_term(
                    document,
                    operator_term,
                    region_index,
                    clause_index,
                    operator_index,
                );
                let items = if issue_index == 0 {
                    clause_color_indices
                        .iter()
                        .filter_map(|&atom_index| match &clause.atoms[atom_index] {
                            ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Color => {
                                Some(project_term(
                                    document,
                                    term,
                                    region_index,
                                    clause_index,
                                    atom_index,
                                ))
                            }
                            _ => None,
                        })
                        .collect()
                } else {
                    Vec::new()
                };
                let markers = if issue_index == 0 {
                    clause_marker_indices
                        .iter()
                        .map(|&atom_index| {
                            source_occurrence(
                                document,
                                clause.atoms[atom_index].span(),
                                region_index,
                                clause_index,
                                atom_index,
                            )
                        })
                        .collect()
                } else {
                    Vec::new()
                };
                issues.push(SemanticSequenceIssue {
                    kind: SemanticSequenceIssueKind::MultipleOperators,
                    operator,
                    items,
                    quantity: None,
                    markers,
                });
            }
            continue;
        }
        for (operator_index, operator_term) in operators {
            let region_index = sentence_region_index(stream, operator_term.span);
            let operator = project_remaining_term(
                document,
                operator_term,
                region_index,
                clause_index,
                operator_index,
            );
            let color_indices = sequence_color_indices(
                document.language(),
                clause,
                operator_index,
                operator.identity.id.as_str(),
            );
            let items = color_indices
                .iter()
                .filter_map(|&atom_index| match &clause.atoms[atom_index] {
                    ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Color => Some(
                        project_term(document, term, region_index, clause_index, atom_index),
                    ),
                    _ => None,
                })
                .collect::<Vec<_>>();
            let marker_indices = sequence_marker_indices(
                document.language(),
                clause,
                operator_index,
                &color_indices,
                operator.identity.id.as_str(),
            );
            let markers = marker_indices
                .iter()
                .map(|&atom_index| {
                    source_occurrence(
                        document,
                        clause.atoms[atom_index].span(),
                        region_index,
                        clause_index,
                        atom_index,
                    )
                })
                .collect::<Vec<_>>();
            let targets = clause
                .atoms
                .iter()
                .filter_map(|atom| match atom {
                    ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive => {
                        Some(term.span.start_byte)
                    }
                    _ => None,
                })
                .collect::<Vec<_>>();
            // Multiple complete heads belong to the ordinary member-sequence grammar;
            // a single head with no colors may still be a typed non-color field cycle.
            if targets.len() != 1 || color_indices.is_empty() {
                continue;
            }
            for &atom_index in &color_indices {
                claimed_color_starts.insert(clause.atoms[atom_index].span().start_byte);
            }
            let issue = if targets.len() != 1 {
                Some(SemanticSequenceIssueKind::AmbiguousTarget)
            } else if items.is_empty() {
                Some(SemanticSequenceIssueKind::MissingItems)
            } else if operator.identity.id == "alternating" && items.len() != 2 {
                Some(SemanticSequenceIssueKind::InvalidAlternatingCardinality)
            } else if !sequence_connectors_are_valid(
                document,
                clause,
                operator_index,
                &color_indices,
                operator.identity.id.as_str(),
            ) {
                Some(SemanticSequenceIssueKind::InvalidConnectors)
            } else {
                None
            };
            let sequence = SemanticSequence {
                kind: SemanticSequenceKind::Color,
                operator,
                items,
                units: Vec::new(),
                quantity: None,
                markers,
            };
            if let Some(kind) = issue {
                issues.push(SemanticSequenceIssue {
                    kind,
                    operator: sequence.operator,
                    items: sequence.items,
                    quantity: sequence.quantity,
                    markers: sequence.markers,
                });
            } else {
                pending.push(PendingSemanticSequence {
                    target_head_start: targets[0],
                    sequence,
                    unit_head_starts: Vec::new(),
                });
            }
        }
    }
    (pending, issues, claimed_color_starts)
}

fn collect_semantic_member_sequences(
    document: &NormalizedDdlDocument,
    stream: &ClauseStream,
    macro_parameter_binding: Option<&MacroParameterBindingResult>,
    excluded_operator_starts: &BTreeSet<usize>,
) -> (
    Vec<PendingSemanticSequence>,
    Vec<SemanticSequenceIssue>,
    BTreeSet<usize>,
    BTreeSet<usize>,
) {
    let mut pending = Vec::new();
    let mut issues = Vec::new();
    let mut claimed_value_starts = BTreeSet::new();
    let mut claimed_quantity_starts = BTreeSet::new();

    for (clause_index, clause) in stream.clauses.iter().enumerate() {
        let operators = clause
            .atoms
            .iter()
            .enumerate()
            .filter_map(|(index, atom)| match atom {
                ClauseAtom::RemainingRole(term)
                    if term.role == RemainingRoleKind::Sequence
                        && !excluded_operator_starts.contains(&term.span.start_byte) =>
                {
                    Some((index, term))
                }
                _ => None,
            })
            .collect::<Vec<_>>();
        if operators.is_empty() {
            continue;
        }
        if operators.len() > 1 {
            for (operator_index, term) in operators {
                let region_index = sentence_region_index(stream, term.span);
                issues.push(SemanticSequenceIssue {
                    kind: SemanticSequenceIssueKind::MultipleOperators,
                    operator: project_remaining_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        operator_index,
                    ),
                    items: Vec::new(),
                    quantity: None,
                    markers: Vec::new(),
                });
            }
            continue;
        }
        let (operator_index, operator_term) = operators[0];
        let region_index = sentence_region_index(stream, operator_term.span);
        let operator = project_remaining_term(
            document,
            operator_term,
            region_index,
            clause_index,
            operator_index,
        );
        let mut head_indices = clause
            .atoms
            .iter()
            .enumerate()
            .filter_map(|(index, atom)| match atom {
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive => Some(index),
                _ => None,
            })
            .collect::<Vec<_>>();
        if let Some(binding) = macro_parameter_binding {
            head_indices.extend(binding.complete.iter().filter_map(|complete| {
                (complete.clause_index == clause_index).then_some(complete.atom_index)
            }));
            head_indices.sort_unstable();
            head_indices.dedup();
        }
        let quantity_indices = clause
            .atoms
            .iter()
            .enumerate()
            .filter_map(|(index, atom)| {
                matches!(atom, ClauseAtom::UnattachedExactNumber(_)).then_some(index)
            })
            .collect::<Vec<_>>();
        let quantity = (quantity_indices.len() == 1).then(|| {
            let index = quantity_indices[0];
            let ClauseAtom::UnattachedExactNumber(number) = &clause.atoms[index] else {
                unreachable!()
            };
            SemanticQuantity {
                value: number.value,
                provenance: source_occurrence(
                    document,
                    number.span,
                    region_index,
                    clause_index,
                    index,
                ),
            }
        });

        if head_indices.len() == 1 {
            let field_indices = sequence_field_indices(
                document.language(),
                clause,
                operator_index,
                operator.identity.id.as_str(),
            );
            if !field_indices.is_empty() {
                let items = field_indices
                    .iter()
                    .filter_map(|&index| {
                        project_sequence_field_term(
                            document,
                            &clause.atoms[index],
                            region_index,
                            clause_index,
                            index,
                        )
                    })
                    .collect::<Vec<_>>();
                let fields = items
                    .iter()
                    .filter_map(sequence_field_for_term)
                    .collect::<Vec<_>>();
                let markers = member_sequence_markers(
                    document,
                    clause,
                    clause_index,
                    region_index,
                    operator_index,
                    &field_indices,
                );
                let field = fields.first().copied();
                let issue = if field.is_none()
                    || fields.len() != items.len()
                    || fields.iter().any(|candidate| Some(*candidate) != field)
                {
                    Some(SemanticSequenceIssueKind::MixedFields)
                } else if operator.identity.id == "alternating" && items.len() != 2 {
                    Some(SemanticSequenceIssueKind::InvalidAlternatingCardinality)
                } else if !sequence_connectors_are_valid(
                    document,
                    clause,
                    operator_index,
                    &field_indices,
                    operator.identity.id.as_str(),
                ) {
                    Some(SemanticSequenceIssueKind::InvalidConnectors)
                } else if quantity_indices.len() > 1 {
                    Some(SemanticSequenceIssueKind::MissingQuantityOwner)
                } else {
                    None
                };
                for &index in &field_indices {
                    claimed_value_starts.insert(clause.atoms[index].span().start_byte);
                }
                if let Some(quantity) = &quantity {
                    claimed_quantity_starts.insert(quantity.provenance.span.start_byte);
                }
                let sequence = SemanticSequence {
                    kind: SemanticSequenceKind::Field(
                        field.unwrap_or(SemanticSequenceField::Touch),
                    ),
                    operator,
                    items,
                    units: Vec::new(),
                    quantity,
                    markers,
                };
                if let Some(kind) = issue {
                    issues.push(SemanticSequenceIssue {
                        kind,
                        operator: sequence.operator,
                        items: sequence.items,
                        quantity: sequence.quantity,
                        markers: sequence.markers,
                    });
                } else {
                    pending.push(PendingSemanticSequence {
                        target_head_start: clause.atoms[head_indices[0]].span().start_byte,
                        sequence,
                        unit_head_starts: Vec::new(),
                    });
                }
                continue;
            }
        }

        let unit_head_indices = sequence_unit_head_indices(
            document,
            clause,
            operator_index,
            &head_indices,
            operator.identity.id.as_str(),
        );
        let flat_item_count = unit_head_indices.len();
        let markers = member_sequence_markers(
            document,
            clause,
            clause_index,
            region_index,
            operator_index,
            &head_indices,
        );
        let issue = if unit_head_indices.is_empty() || unit_head_indices.iter().any(Vec::is_empty) {
            Some(SemanticSequenceIssueKind::InvalidUnitSyntax)
        } else if operator.identity.id == "alternating" && flat_item_count != 2 {
            Some(SemanticSequenceIssueKind::InvalidAlternatingCardinality)
        } else if quantity_indices.len() > 1 {
            Some(SemanticSequenceIssueKind::MissingQuantityOwner)
        } else {
            None
        };
        if let Some(quantity) = &quantity {
            claimed_quantity_starts.insert(quantity.provenance.span.start_byte);
        }
        let unit_head_starts = unit_head_indices
            .iter()
            .map(|indices| {
                indices
                    .iter()
                    .map(|&index| clause.atoms[index].span().start_byte)
                    .collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();
        let sequence = SemanticSequence {
            kind: SemanticSequenceKind::Units,
            operator,
            items: Vec::new(),
            units: Vec::new(),
            quantity,
            markers,
        };
        if let Some(kind) = issue {
            issues.push(SemanticSequenceIssue {
                kind,
                operator: sequence.operator,
                items: Vec::new(),
                quantity: sequence.quantity,
                markers: sequence.markers,
            });
        } else {
            pending.push(PendingSemanticSequence {
                target_head_start: unit_head_starts[0][0],
                sequence,
                unit_head_starts,
            });
        }
    }
    (
        pending,
        issues,
        claimed_value_starts,
        claimed_quantity_starts,
    )
}

fn sequence_field_candidate(atom: &ClauseAtom) -> bool {
    matches!(
        atom,
        ClauseAtom::CoreRole(term)
            if matches!(term.role, CoreRoleKind::Touch | CoreRoleKind::Surface)
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
    )
}

fn sequence_field_for_term(term: &SemanticTerm) -> Option<SemanticSequenceField> {
    match (term.identity.category.as_str(), term.identity.id.as_str()) {
        ("touch", _) => Some(SemanticSequenceField::Touch),
        ("continuity", _) => Some(SemanticSequenceField::Continuity),
        ("angle", _) => Some(SemanticSequenceField::Angle),
        ("surface", id) => match classify_surface_dimension(id) {
            Some(SurfaceDimension::Quality) => Some(SemanticSequenceField::SurfaceQuality),
            Some(SurfaceDimension::Intensity) => Some(SemanticSequenceField::SurfaceIntensity),
            None => None,
        },
        ("variation", id) => match classify_fluctuation_dimension(id) {
            Some(FluctuationDimension::Amplitude) => {
                Some(SemanticSequenceField::FluctuationAmplitude)
            }
            Some(FluctuationDimension::Frequency) => {
                Some(SemanticSequenceField::FluctuationFrequency)
            }
            Some(FluctuationDimension::Quality) => Some(SemanticSequenceField::FluctuationQuality),
            Some(FluctuationDimension::Spread) => Some(SemanticSequenceField::FluctuationSpread),
            None => None,
        },
        ("ratio", id) => match classify_proportion_dimension(id) {
            Some(ProportionDimension::Aspect) => Some(SemanticSequenceField::ProportionAspect),
            Some(ProportionDimension::WidthExtent) => {
                Some(SemanticSequenceField::ProportionWidthExtent)
            }
            Some(ProportionDimension::ArcForm) => Some(SemanticSequenceField::ProportionArcForm),
            None => None,
        },
        _ => None,
    }
}

fn sequence_field_indices(
    language: ResolvedInstructionLanguage,
    clause: &crate::ClauseSegment,
    operator_index: usize,
    operator_id: &str,
) -> Vec<usize> {
    let repeating_index = clause.atoms[..operator_index].iter().rposition(|atom| {
        matches!(atom, ClauseAtom::GrammarMarker { marker_id: MarkerId::EnRepeating, .. })
    });
    clause
        .atoms
        .iter()
        .enumerate()
        .filter_map(|(index, atom)| {
            sequence_field_candidate(atom).then_some(())?;
            match (language, operator_id) {
                (ResolvedInstructionLanguage::Ja, _) => (index < operator_index).then_some(index),
                (ResolvedInstructionLanguage::En, "alternating") => {
                    (index > operator_index).then_some(index)
                }
                (ResolvedInstructionLanguage::En, "in_order") => repeating_index
                    .is_some_and(|repeating| repeating < index && index < operator_index)
                    .then_some(index),
                _ => None,
            }
        })
        .collect()
}

fn project_sequence_field_term(
    document: &NormalizedDdlDocument,
    atom: &ClauseAtom,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> Option<SemanticTerm> {
    match atom {
        ClauseAtom::CoreRole(term) => Some(project_term(
            document,
            term,
            region_index,
            clause_index,
            atom_index,
        )),
        ClauseAtom::RemainingRole(term) => Some(project_remaining_term(
            document,
            term,
            region_index,
            clause_index,
            atom_index,
        )),
        _ => None,
    }
}

fn sequence_unit_head_indices(
    document: &NormalizedDdlDocument,
    clause: &crate::ClauseSegment,
    operator_index: usize,
    head_indices: &[usize],
    operator_id: &str,
) -> Vec<Vec<usize>> {
    let selected = head_indices
        .iter()
        .copied()
        .filter(|index| match (document.language(), operator_id) {
            (ResolvedInstructionLanguage::Ja, _) => *index < operator_index,
            (ResolvedInstructionLanguage::En, "alternating") => *index > operator_index,
            (ResolvedInstructionLanguage::En, "in_order") => *index < operator_index,
            _ => false,
        })
        .collect::<Vec<_>>();
    let group_index = clause.atoms.iter().enumerate().find_map(|(index, atom)| {
        matches!(atom, ClauseAtom::GrammarMarker {
            marker_id: MarkerId::JaGroup | MarkerId::EnGroupOf,
            ..
        })
        .then_some(index)
    });
    let Some(group_index) = group_index else {
        return selected.into_iter().map(|index| vec![index]).collect();
    };
    match document.language() {
        ResolvedInstructionLanguage::Ja => {
            let grouped = selected
                .iter()
                .copied()
                .filter(|index| *index < group_index)
                .collect::<Vec<_>>();
            let mut units = vec![grouped];
            units.extend(
                selected
                    .iter()
                    .copied()
                    .filter(|index| *index > group_index)
                    .map(|index| vec![index]),
            );
            units
        }
        ResolvedInstructionLanguage::En => {
            let with_index = clause.atoms.iter().enumerate().find_map(|(index, atom)| {
                (index > group_index
                    && matches!(atom, ClauseAtom::GrammarMarker {
                        marker_id: MarkerId::EnWith,
                        ..
                    }))
                .then_some(index)
            });
            let Some(with_index) = with_index else {
                return Vec::new();
            };
            let grouped = selected
                .iter()
                .copied()
                .filter(|index| group_index < *index && *index < with_index)
                .collect::<Vec<_>>();
            let rest = selected
                .iter()
                .copied()
                .filter(|index| *index > with_index)
                .collect::<Vec<_>>();
            vec![grouped, rest]
        }
    }
}

fn member_sequence_markers(
    document: &NormalizedDdlDocument,
    clause: &crate::ClauseSegment,
    clause_index: usize,
    region_index: usize,
    operator_index: usize,
    item_indices: &[usize],
) -> Vec<SourceOccurrence> {
    let start = item_indices
        .first()
        .copied()
        .unwrap_or(operator_index)
        .min(operator_index);
    let end = item_indices
        .last()
        .copied()
        .unwrap_or(operator_index)
        .max(operator_index);
    clause
        .atoms
        .iter()
        .enumerate()
        .filter_map(|(index, atom)| {
            let in_range = start <= index
                && (index <= end
                    || (matches!(document.language(), ResolvedInstructionLanguage::Ja)
                        && matches!(atom, ClauseAtom::GrammarMarker {
                            marker_id: MarkerId::JaSequenceTe | MarkerId::JaRepeat,
                            ..
                        })));
            in_range
                .then(|| match atom {
                    ClauseAtom::GrammarMarker { span, .. }
                    | ClauseAtom::FunctionWord { span, .. } => Some(source_occurrence(
                        document,
                        *span,
                        region_index,
                        clause_index,
                        index,
                    )),
                _ => None,
                })
                .flatten()
        })
        .collect()
}

fn sequence_color_indices(
    language: ResolvedInstructionLanguage,
    clause: &crate::ClauseSegment,
    operator_index: usize,
    operator_id: &str,
) -> Vec<usize> {
    let repeating_index = clause.atoms[..operator_index]
        .iter()
        .rposition(|atom| matches!(atom, ClauseAtom::GrammarMarker { marker_id: MarkerId::EnRepeating, .. }));
    clause
        .atoms
        .iter()
        .enumerate()
        .filter_map(|(index, atom)| {
            let ClauseAtom::CoreRole(term) = atom else {
                return None;
            };
            if term.role != CoreRoleKind::Color {
                return None;
            }
            let selected = match (language, operator_id) {
                (ResolvedInstructionLanguage::Ja, _) => index < operator_index,
                (ResolvedInstructionLanguage::En, "alternating") => index > operator_index,
                (ResolvedInstructionLanguage::En, "in_order") => repeating_index
                    .is_some_and(|repeating| repeating < index && index < operator_index),
                _ => false,
            };
            selected.then_some(index)
        })
        .collect()
}

fn sequence_marker_indices(
    language: ResolvedInstructionLanguage,
    clause: &crate::ClauseSegment,
    operator_index: usize,
    color_indices: &[usize],
    operator_id: &str,
) -> Vec<usize> {
    let first = color_indices
        .first()
        .copied()
        .unwrap_or(operator_index)
        .min(operator_index);
    let last = color_indices
        .last()
        .copied()
        .unwrap_or(operator_index)
        .max(operator_index);
    clause
        .atoms
        .iter()
        .enumerate()
        .filter_map(|(index, atom)| {
            let sequence_marker = match language {
                ResolvedInstructionLanguage::Ja => {
                    first <= index
                        && (index <= last
                            || (last < index
                                && matches!(atom, ClauseAtom::GrammarMarker {
                                    marker_id: MarkerId::JaSequenceTe | MarkerId::JaRepeat,
                                    ..
                                })))
                }
                ResolvedInstructionLanguage::En => {
                    (first <= index && index <= last)
                        || (operator_id == "in_order"
                            && matches!(atom, ClauseAtom::GrammarMarker {
                                marker_id: MarkerId::EnRepeating,
                                ..
                            }))
                }
            };
            (sequence_marker
                && matches!(atom, ClauseAtom::GrammarMarker { .. } | ClauseAtom::FunctionWord { .. }))
            .then_some(index)
        })
        .collect()
}

fn sequence_connectors_are_valid(
    document: &NormalizedDdlDocument,
    clause: &crate::ClauseSegment,
    operator_index: usize,
    color_indices: &[usize],
    operator_id: &str,
) -> bool {
    let exact_markers = |marker_ids: &[MarkerId], start: usize, end: usize| {
        let atoms = &clause.atoms[start..end];
        atoms.len() == marker_ids.len()
            && atoms.iter().zip(marker_ids).all(|(atom, expected)| {
                matches!(atom, ClauseAtom::GrammarMarker { marker_id, .. }
                    if marker_id == expected)
            })
    };
    match (document.language(), operator_id) {
        (ResolvedInstructionLanguage::Ja, "alternating") => {
            color_indices.len() == 2
                && exact_markers(&[MarkerId::JaTo], color_indices[0] + 1, color_indices[1])
                && exact_markers(&[MarkerId::JaWo], color_indices[1] + 1, operator_index)
                && sequence_suffix_is_exact(clause, operator_index, MarkerId::JaSequenceTe)
        }
        (ResolvedInstructionLanguage::Ja, "in_order") => {
            let Some(&last) = color_indices.last() else {
                return false;
            };
            exact_markers(&[MarkerId::JaNo], last + 1, operator_index)
                && sequence_suffix_is_exact(clause, operator_index, MarkerId::JaRepeat)
                && color_indices.windows(2).all(|pair| {
                    exact_markers(&[], pair[0] + 1, pair[1])
                        && document.source()[clause.atoms[pair[0]].span().end_byte
                            ..clause.atoms[pair[1]].span().start_byte]
                            .chars()
                            .all(|character| character.is_whitespace() || character == '・')
                })
        }
        (ResolvedInstructionLanguage::En, "alternating") => {
            color_indices.len() == 2
                && exact_markers(&[], operator_index + 1, color_indices[0])
                && exact_markers(&[MarkerId::EnAnd], color_indices[0] + 1, color_indices[1])
        }
        (ResolvedInstructionLanguage::En, "in_order") => {
            let Some(&first) = color_indices.first() else {
                return false;
            };
            let Some(repeating_index) = clause.atoms[..first].iter().rposition(|atom| {
                matches!(atom, ClauseAtom::GrammarMarker { marker_id: MarkerId::EnRepeating, .. })
            }) else {
                return false;
            };
            exact_markers(&[], repeating_index + 1, first)
                && exact_markers(&[], last_color_index(color_indices) + 1, operator_index)
                && color_indices.windows(2).enumerate().all(|(index, pair)| {
                    let expected: &[MarkerId] = if index + 1 == color_indices.len() - 1 {
                        &[MarkerId::EnAnd]
                    } else {
                        &[]
                    };
                    exact_markers(expected, pair[0] + 1, pair[1])
                })
        }
        _ => false,
    }
}

fn sequence_suffix_is_exact(
    clause: &crate::ClauseSegment,
    operator_index: usize,
    expected: MarkerId,
) -> bool {
    matches!(
        clause.atoms.get(operator_index + 1),
        Some(ClauseAtom::GrammarMarker { marker_id, .. }) if *marker_id == expected
    )
}

fn last_color_index(color_indices: &[usize]) -> usize {
    *color_indices.last().expect("nonempty sequence was checked")
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub(crate) struct ClauseTopologyEvidence {
    pub attachment_markers: Vec<AttachmentMarkerEvidence>,
    pub determiner_starts: BTreeSet<usize>,
    pub english_determiner_phrases: Vec<EnglishDeterminerPhraseEvidence>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct EnglishDeterminerPhraseEvidence {
    pub kind: EnglishDeterminerKind,
    pub clause_index: usize,
    pub determiner_span: SourceSpan,
    pub candidate_region_span: SourceSpan,
    pub head_candidate_span: Option<SourceSpan>,
    pub canonical_candidate_spans: Vec<SourceSpan>,
}

impl ClauseTopologyEvidence {
    pub(crate) fn from_attachment(attachment: &AttachmentEvidenceResult) -> Self {
        Self {
            attachment_markers: attachment.evidence.clone(),
            determiner_starts: attachment
                .noun_phrase
                .evidence
                .iter()
                .map(|evidence| evidence.determiner.span.start_byte)
                .collect(),
            english_determiner_phrases: attachment
                .noun_phrase
                .evidence
                .iter()
                .map(|evidence| EnglishDeterminerPhraseEvidence {
                    kind: evidence.determiner.kind,
                    clause_index: evidence.clause_index,
                    determiner_span: evidence.determiner.span,
                    candidate_region_span: evidence.candidate_region_span,
                    head_candidate_span: evidence
                        .head_candidate
                        .as_ref()
                        .map(|candidate| candidate.span),
                    canonical_candidate_spans: evidence
                        .head_candidate
                        .as_ref()
                        .map(|candidate| vec![candidate.span])
                        .unwrap_or_else(|| {
                            attachment
                                .noun_phrase
                                .diagnostics
                                .iter()
                                .find(|diagnostic| {
                                    diagnostic.clause_index == evidence.clause_index
                                        && diagnostic.determiner_span == evidence.determiner.span
                                        && diagnostic.candidate_region_span
                                            == evidence.candidate_region_span
                                })
                                .map(|diagnostic| {
                                    diagnostic
                                        .candidates
                                        .iter()
                                        .map(|candidate| candidate.span)
                                        .collect()
                                })
                                .unwrap_or_default()
                        }),
                })
                .collect(),
        }
    }
}

#[derive(Default)]
struct AssociationRegion {
    shape_constraints: Vec<crate::SemanticShapeConstraint>,
    heads: Vec<SemanticHead>,
    colors: Vec<SemanticTerm>,
    quantities: Vec<SemanticQuantity>,
    thinnesses: Vec<SemanticThinness>,
    relative_scales: Vec<SemanticRelativeScale>,
    explicit_geometries: Vec<SemanticExplicitGeometry>,
    numeric_positions: Vec<SemanticNumericPosition>,
    touches: Vec<SemanticTerm>,
    continuities: Vec<SemanticTerm>,
    angles: Vec<SemanticTerm>,
    surface_qualities: Vec<SemanticTerm>,
    surface_intensities: Vec<SemanticTerm>,
    unclassified_surfaces: Vec<SemanticTerm>,
    fluctuation_amplitudes: Vec<SemanticTerm>,
    fluctuation_frequencies: Vec<SemanticTerm>,
    fluctuation_qualities: Vec<SemanticTerm>,
    fluctuation_spreads: Vec<SemanticTerm>,
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

use crate::fluctuation::{FluctuationDimension, classify_fluctuation_dimension};

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

pub(crate) fn primitive_phrase_modifier_starts(
    attachment_evidence: &AttachmentEvidenceResult,
) -> BTreeSet<usize> {
    collect_pre_head_phrase_ownership(attachment_evidence, None)
        .modifier_starts_by_head
        .into_values()
        .flatten()
        .collect()
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
            if macro_parameter_binding
                .is_some_and(|binding| macro_parameter_binding_owns_span(binding, span))
            {
                continue;
            }
            if phrase_floor.is_some_and(|floor| span.end_byte <= floor)
                || head_starts.contains(&span.start_byte)
            {
                break;
            }
            match atom {
                ClauseAtom::UnresolvedDiagnostic(_) => break,
                ClauseAtom::GrammarMarker { .. } => {
                    if !genitive_marker_starts.contains(&span.start_byte) {
                        break;
                    }
                }
                // The counter of a pre-head count stays inside the noun phrase,
                // so modifiers before it still reach the head, e.g.
                // `細い 三 本 の 黒い 線`.
                ClauseAtom::FunctionWord { surface, .. }
                    if crate::parser::is_japanese_counter_surface(surface)
                        && clause.atoms.iter().any(|candidate| {
                            matches!(candidate, ClauseAtom::UnattachedExactNumber(number)
                                if number.span.end_byte == span.start_byte)
                        }) => {}
                ClauseAtom::FunctionWord { .. } => break,
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
            if matches!(
                term.identity.dimension,
                crate::CoreModifierDimension::Thinness
                    | crate::CoreModifierDimension::RelativeScale
                    | crate::CoreModifierDimension::ShapeForm
                    | crate::CoreModifierDimension::ShapeSides
            )
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
    let (mut pending_sequences, mut sequence_issues, claimed_sequence_colors) =
        collect_semantic_sequences(document, &attachment_evidence.noun_phrase.clause_stream);
    let excluded_operator_starts = pending_sequences
        .iter()
        .map(|sequence| sequence.sequence.operator.provenance.source.span.start_byte)
        .chain(
            sequence_issues
                .iter()
                .map(|issue| issue.operator.provenance.source.span.start_byte),
        )
        .collect();
    let (member_sequences, member_issues, claimed_sequence_values, claimed_sequence_quantities) =
        collect_semantic_member_sequences(
            document,
            &attachment_evidence.noun_phrase.clause_stream,
            None,
            &excluded_operator_starts,
        );
    pending_sequences.extend(member_sequences);
    sequence_issues.extend(member_issues);
    let pre_head_ownership = collect_pre_head_phrase_ownership(&attachment_evidence, None);
    let clause_topology = ClauseTopologyEvidence::from_attachment(&attachment_evidence);
    let clause_stream = attachment_evidence.noun_phrase.clause_stream;
    Ok(build_semantic_entities(
        document,
        clause_stream,
        None,
        pre_head_ownership,
        clause_topology,
        pending_sequences,
        sequence_issues,
        claimed_sequence_colors,
        claimed_sequence_values,
        claimed_sequence_quantities,
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
    let (mut pending_sequences, mut sequence_issues, claimed_sequence_colors) =
        collect_semantic_sequences(document, &clause_stream);
    let excluded_operator_starts = pending_sequences
        .iter()
        .map(|sequence| sequence.sequence.operator.provenance.source.span.start_byte)
        .chain(
            sequence_issues
                .iter()
                .map(|issue| issue.operator.provenance.source.span.start_byte),
        )
        .collect();
    let (member_sequences, member_issues, claimed_sequence_values, claimed_sequence_quantities) =
        collect_semantic_member_sequences(
            document,
            &clause_stream,
            Some(&macro_parameter_binding),
            &excluded_operator_starts,
        );
    pending_sequences.extend(member_sequences);
    sequence_issues.extend(member_issues);
    build_semantic_entities(
        document,
        clause_stream,
        Some(macro_parameter_binding),
        pre_head_ownership,
        clause_topology,
        pending_sequences,
        sequence_issues,
        claimed_sequence_colors,
        claimed_sequence_values,
        claimed_sequence_quantities,
    )
}

pub(crate) fn is_layout_direction(
    document: &NormalizedDdlDocument,
    stream: &ClauseStream,
    topology: &ClauseTopologyEvidence,
    term: &crate::RemainingRoleTerm,
) -> bool {
    if term.role != RemainingRoleKind::Angle {
        return false;
    }
    match document.language() {
        crate::ResolvedInstructionLanguage::En => crate::saijiki::is_angle_adverb(
            &document.source()[term.span.start_byte..term.span.end_byte],
            &term.canonical_surface_ja,
        ),
        crate::ResolvedInstructionLanguage::Ja => {
            topology.attachment_markers.iter().any(|marker| {
                marker.marker == AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Ni)
                    && term.span.end_byte <= marker.span.start_byte
                    && stream.clauses[marker.clause_index]
                        .atoms
                        .iter()
                        .any(|atom| atom.span() == term.span)
                    && stream.clauses[marker.clause_index]
                        .atoms
                        .iter()
                        .all(|atom| {
                            atom.span().end_byte <= term.span.end_byte
                                || marker.span.start_byte <= atom.span().start_byte
                        })
            })
        }
    }
}

fn build_semantic_entities(
    document: &NormalizedDdlDocument,
    clause_stream: ClauseStream,
    macro_parameter_binding: Option<MacroParameterBindingResult>,
    mut pre_head_ownership: PreHeadPhraseOwnership,
    clause_topology: ClauseTopologyEvidence,
    pending_sequences: Vec<PendingSemanticSequence>,
    mut sequence_issues: Vec<SemanticSequenceIssue>,
    claimed_sequence_colors: BTreeSet<usize>,
    claimed_sequence_values: BTreeSet<usize>,
    claimed_sequence_quantities: BTreeSet<usize>,
) -> SemanticAssociationResult {
    let mut regions = BTreeMap::<usize, AssociationRegion>::new();
    let mut issues = Vec::new();
    let mut owned_occurrence_count = 0;
    let mut explicit_previous_references = Vec::new();

    for (clause_index, clause) in clause_stream.clauses.iter().enumerate() {
        let region_index = sentence_region_index(
            &clause_stream,
            clause
                .atoms
                .first()
                .map(ClauseAtom::span)
                .unwrap_or(clause.span),
        );
        let mut geometry_analysis =
            analyze_clause_geometry(document, clause, clause_index, region_index);
        if let Some(binding) = &macro_parameter_binding {
            let consumed = |value: &crate::SemanticGeometryValue| {
                macro_parameter_binding_owns_span(binding, value.decimal.provenance.span)
            };
            geometry_analysis
                .geometries
                .retain(|geometry| match geometry {
                    SemanticExplicitGeometry::Radius(value)
                    | SemanticExplicitGeometry::Diameter(value)
                    | SemanticExplicitGeometry::Length(value)
                    | SemanticExplicitGeometry::Side(value) => !consumed(value),
                    SemanticExplicitGeometry::WidthHeight { width, height } => {
                        !(consumed(width) && consumed(height))
                    }
                    SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => {
                        !(consumed(chord) && consumed(sagitta))
                    }
                });
            geometry_analysis
                .positions
                .retain(|position| !(consumed(&position.x) && consumed(&position.y)));
            geometry_analysis
                .issues
                .retain(|issue| !macro_parameter_binding_owns_span(binding, issue.span));
        }
        let consumed_geometry_numbers = geometry_analysis.consumed_numeric_spans.clone();
        owned_occurrence_count += geometry_analysis.geometries.len();
        owned_occurrence_count += geometry_analysis.positions.len();
        regions
            .entry(region_index)
            .or_default()
            .explicit_geometries
            .extend(geometry_analysis.geometries);
        regions
            .entry(region_index)
            .or_default()
            .numeric_positions
            .extend(geometry_analysis.positions);
        for geometry_issue in geometry_analysis.issues {
            let kind = match geometry_issue.kind {
                GeometrySyntaxIssueKind::IncompleteGeometry => {
                    SemanticAssociationIssueKind::IncompleteNumericGeometry
                }
                GeometrySyntaxIssueKind::IncompletePosition => {
                    SemanticAssociationIssueKind::IncompleteNumericPosition
                }
                GeometrySyntaxIssueKind::UnownedDecimal => {
                    SemanticAssociationIssueKind::UnownedExactDecimal
                }
            };
            issues.push(SemanticAssociationIssue {
                kind,
                region_index,
                occurrences: Vec::new(),
                upstream_diagnostic: Some(NeutralDiagnostic {
                    span: geometry_issue.span,
                    surface: document.source()
                        [geometry_issue.span.start_byte..geometry_issue.span.end_byte]
                        .to_owned(),
                    kind: NeutralDiagnosticKind::Hole,
                    recognized: true,
                }),
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            });
        }
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            if macro_parameter_binding
                .as_ref()
                .is_some_and(|binding| macro_parameter_binding_owns_span(binding, atom.span()))
            {
                continue;
            }
            if claimed_sequence_values.contains(&atom.span().start_byte)
                || claimed_sequence_quantities.contains(&atom.span().start_byte)
            {
                owned_occurrence_count += 1;
                continue;
            }
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
                    if claimed_sequence_colors.contains(&term.span.start_byte) {
                        owned_occurrence_count += 1;
                        continue;
                    }
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
                    if is_layout_direction(document, &clause_stream, &clause_topology, term) {
                        continue;
                    }
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
                        Some(FluctuationDimension::Spread) => region.fluctuation_spreads.push(term),
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
                ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Sequence => {
                    owned_occurrence_count += 1;
                }
                ClauseAtom::UnattachedExactNumber(quantity) => {
                    if consumed_geometry_numbers
                        .contains(&(quantity.span.start_byte, quantity.span.end_byte))
                    {
                        continue;
                    }
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
                    let provenance = source_occurrence(
                        document,
                        modifier.span,
                        region_index,
                        clause_index,
                        atom_index,
                    );
                    match modifier.identity.dimension {
                        crate::CoreModifierDimension::ShapeForm
                        | crate::CoreModifierDimension::ShapeSides => {
                            region
                                .shape_constraints
                                .push(crate::SemanticShapeConstraint {
                                    value: crate::ShapeConstraint {
                                        regular: true,
                                        sides: if let CoreModifierValue::Sides(sides) =
                                            modifier.identity.value
                                        {
                                            Some(sides)
                                        } else {
                                            None
                                        },
                                    },
                                    provenance,
                                    additional_provenance: Vec::new(),
                                });
                        }
                        crate::CoreModifierDimension::Thinness => {
                            region.thinnesses.push(SemanticThinness {
                                value: modifier.identity.value,
                                provenance,
                            });
                        }
                        crate::CoreModifierDimension::RelativeScale => {
                            region.relative_scales.push(SemanticRelativeScale {
                                value: modifier.identity.value,
                                provenance,
                            });
                        }
                    }
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
                            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
                | ClauseAtom::GrammarMarker { .. }
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

    associate_fill_geometry_ownership(document, &clause_stream, &regions, &mut pre_head_ownership);
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
    for entity in &mut entities {
        let source = entity.head.source();
        if let Some(ClauseAtom::CoreRole(term)) = clause_stream
            .clauses
            .get(source.clause_index)
            .and_then(|clause| clause.atoms.get(source.atom_index))
        {
            if term.span == source.span {
                if let Some(value) = term.shape_constraint {
                    let head_constraint = crate::SemanticShapeConstraint {
                        value,
                        provenance: source.clone(),
                        additional_provenance: Vec::new(),
                    };
                    if let Some(existing) = &mut entity.shape_constraint {
                        if existing.value.sides.is_some()
                            && value.sides.is_some()
                            && existing.value.sides != value.sides
                        {
                            issues.push(SemanticAssociationIssue {
                                kind: SemanticAssociationIssueKind::ConflictingShapeConstraints,
                                region_index: source.region_index,
                                occurrences: Vec::new(),
                                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
                                upstream_diagnostic: Some(NeutralDiagnostic {
                                    span: source.span,
                                    surface: source.surface.clone(),
                                    kind: NeutralDiagnosticKind::Conflict,
                                    recognized: true,
                                }),
                            });
                        }
                        existing.value.regular |= value.regular;
                        existing.value.sides = existing.value.sides.or(value.sides);
                        existing.additional_provenance.push(source.clone());
                    } else {
                        entity.shape_constraint = Some(head_constraint);
                    }
                }
            }
        }
    }
    attach_association_causal_provenance(&clause_stream, &entities, &mut issues);

    let mut sequences = Vec::new();
    for mut pending in pending_sequences {
        if let Some(target_entity_index) = entities
            .iter()
            .position(|entity| entity.head.source().span.start_byte == pending.target_head_start)
        {
            if !pending.unit_head_starts.is_empty() {
                let mut units = Vec::new();
                let mut valid = true;
                for starts in &pending.unit_head_starts {
                    let indices = starts
                        .iter()
                        .filter_map(|start| {
                            entities
                                .iter()
                                .position(|entity| entity.head.source().span.start_byte == *start)
                        })
                        .collect::<Vec<_>>();
                    if indices.len() != starts.len() {
                        valid = false;
                        break;
                    }
                    let first = entities[indices[0]].head.source().span;
                    let last = entities[*indices.last().expect("nonempty unit")]
                        .head
                        .source()
                        .span;
                    units.push(SemanticSequenceUnit {
                        member_entity_indices: indices,
                        source_span: SourceSpan {
                            start_byte: first.start_byte,
                            end_byte: last.end_byte,
                        },
                    });
                }
                if !valid {
                    sequence_issues.push(SemanticSequenceIssue {
                        kind: SemanticSequenceIssueKind::AmbiguousTarget,
                        operator: pending.sequence.operator,
                        items: pending.sequence.items,
                        quantity: pending.sequence.quantity,
                        markers: pending.sequence.markers,
                    });
                    continue;
                }
                pending.sequence.units = units;
            }
            sequences.push(SemanticEntitySequence {
                target_entity_index,
                sequence: pending.sequence,
            });
        } else {
            sequence_issues.push(SemanticSequenceIssue {
                kind: SemanticSequenceIssueKind::AmbiguousTarget,
                operator: pending.sequence.operator,
                items: pending.sequence.items,
                quantity: pending.sequence.quantity,
                markers: pending.sequence.markers,
            });
        }
    }

    let delivered_occurrence_count = entities.iter().map(entity_occurrence_count).sum::<usize>()
        + issues
            .iter()
            .flat_map(|issue| &issue.occurrences)
            .map(OwnedSemanticOccurrence::occurrence_count)
            .sum::<usize>()
        + sequences
            .iter()
            .map(|sequence| {
                1 + sequence.sequence.items.len()
                    + usize::from(sequence.sequence.quantity.is_some())
            })
            .sum::<usize>()
        + sequence_issues
            .iter()
            .map(|issue| 1 + issue.items.len() + usize::from(issue.quantity.is_some()))
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
        sequences,
        complete: issues.is_empty() && sequence_issues.is_empty(),
    };
    let canonical_bytes = ast.complete.then(|| canonical_ast_bytes(&ast));

    SemanticAssociationResult {
        schema_id: SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
        clause_stream,
        ast,
        issues,
        sequence_issues,
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

fn associate_fill_geometry_ownership(
    document: &NormalizedDdlDocument,
    stream: &ClauseStream,
    regions: &BTreeMap<usize, AssociationRegion>,
    ownership: &mut PreHeadPhraseOwnership,
) {
    for clause in &stream.clauses {
        let actions = clause
            .atoms
            .iter()
            .filter_map(|atom| match atom {
                ClauseAtom::RemainingRole(term)
                    if term.role == crate::RemainingRoleKind::Motion =>
                {
                    Some(term)
                }
                _ => None,
            })
            .collect::<Vec<_>>();
        let [action] = actions.as_slice() else {
            continue;
        };
        if !crate::project_macro_semantic_ref(&action.category_key, &action.canonical_surface_ja)
            .is_some_and(|identity| {
                identity.category == "movement" && identity.canonical_id == "fill"
            })
        {
            continue;
        }
        let Some((target, motif, _)) = crate::semantic_instruction::fill_phrase_ranges(
            document.language(),
            clause,
            action.span,
        ) else {
            continue;
        };
        let Some(region) = regions.get(&sentence_region_index(stream, action.span)) else {
            continue;
        };
        for range in [target, motif] {
            let within = |span: SourceSpan| {
                range.start_byte <= span.start_byte && span.end_byte <= range.end_byte
            };
            let heads = region
                .heads
                .iter()
                .filter(|head| within(head.source().span))
                .collect::<Vec<_>>();
            let [head] = heads.as_slice() else {
                continue;
            };
            let value_within = |value: &crate::SemanticGeometryValue| {
                within(value.keyword_provenance.span) && within(value.decimal.provenance.span)
            };
            for geometry in &region.explicit_geometries {
                let contained = match geometry {
                    SemanticExplicitGeometry::Radius(value)
                    | SemanticExplicitGeometry::Diameter(value)
                    | SemanticExplicitGeometry::Length(value)
                    | SemanticExplicitGeometry::Side(value) => value_within(value),
                    SemanticExplicitGeometry::WidthHeight { width, height } => {
                        value_within(width) && value_within(height)
                    }
                    SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => {
                        value_within(chord) && value_within(sagitta)
                    }
                };
                if contained {
                    ownership.insert(head.source().span, geometry.source().span);
                }
            }
            for position in &region.numeric_positions {
                if value_within(&position.x) && value_within(&position.y) {
                    ownership.insert(head.source().span, position.source().span);
                }
            }
        }
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
        .any(|parameter| parameter.owns_span(span))
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
            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
    let value = semantic_macro_parameter_value_from_bound(&parameter.value);
    let (source_asset_id, canonical_surface_ja) = match &parameter.value {
        BoundMacroParameterValue::Integer { .. }
        | BoundMacroParameterValue::ExactDecimal { .. }
        | BoundMacroParameterValue::Number { .. }
        | BoundMacroParameterValue::CoreModifier { .. } => (None, None),
        BoundMacroParameterValue::SemanticRef {
            source_asset_id,
            canonical_surface_ja,
            ..
        } => (
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

fn semantic_macro_parameter_value_from_bound(
    value: &BoundMacroParameterValue,
) -> SemanticMacroParameterValue {
    match value {
        BoundMacroParameterValue::ExactDecimal { value, .. } => {
            SemanticMacroParameterValue::ExactDecimal(*value)
        }
        BoundMacroParameterValue::CoreModifier { value, .. } => {
            SemanticMacroParameterValue::SemanticRef(SemanticIdentity {
                category: value.dimension().as_str().to_owned(),
                id: value.as_str().to_owned(),
            })
        }
        BoundMacroParameterValue::Integer { value, .. } => {
            SemanticMacroParameterValue::Integer(*value)
        }
        BoundMacroParameterValue::Number { value, .. } => {
            SemanticMacroParameterValue::Number(*value)
        }
        BoundMacroParameterValue::SemanticRef {
            category,
            canonical_id,
            ..
        } => SemanticMacroParameterValue::SemanticRef(SemanticIdentity {
            category: category.clone(),
            id: canonical_id.clone(),
        }),
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
        || !canonical_relation_identity_is_valid(
            relation_type,
            canonical_identity,
            &document.source()[span.start_byte..span.end_byte],
        )
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
        CanonicalRelationKind::Connected => SemanticRelationKind::Connected,
        CanonicalRelationKind::Mirrored => SemanticRelationKind::Mirrored,
    };
    let reference = match reference {
        CanonicalPreviousReference::PreviousOne => SemanticPreviousReference::PreviousOne,
        CanonicalPreviousReference::PreviousTwo => SemanticPreviousReference::PreviousTwo,
    };
    Ok(Some(ExplicitPreviousReferenceOccurrence {
        kind,
        target: canonical_identity.target,
        target_endpoint: canonical_identity.target_endpoint,
        target_path_selection: canonical_identity.target_path_selection,
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
                    .shape_constraints
                    .drain(..)
                    .map(OwnedSemanticOccurrence::ShapeConstraint),
            )
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
            .chain(
                region
                    .relative_scales
                    .drain(..)
                    .map(OwnedSemanticOccurrence::RelativeScale),
            )
            .chain(
                region
                    .explicit_geometries
                    .drain(..)
                    .map(OwnedSemanticOccurrence::ExplicitGeometry),
            )
            .chain(
                region
                    .numeric_positions
                    .drain(..)
                    .map(OwnedSemanticOccurrence::NumericPosition),
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
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
                    .shape_constraints
                    .drain(..)
                    .map(OwnedSemanticOccurrence::ShapeConstraint),
            )
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
            .chain(
                region
                    .relative_scales
                    .drain(..)
                    .map(OwnedSemanticOccurrence::RelativeScale),
            )
            .chain(
                region
                    .explicit_geometries
                    .drain(..)
                    .map(OwnedSemanticOccurrence::ExplicitGeometry),
            )
            .chain(
                region
                    .numeric_positions
                    .drain(..)
                    .map(OwnedSemanticOccurrence::NumericPosition),
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
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
                upstream_diagnostic: None,
            });
        }
        append_upstream_issues(region_index, region.diagnostics, issues);
        return;
    }

    let diagnostics = std::mem::take(&mut region.diagnostics);
    let head = region.heads.pop().expect("single head was checked");
    let mut owned_region = take_pre_head_region(&mut region, head, pre_head_ownership);
    owned_region
        .explicit_geometries
        .append(&mut region.explicit_geometries);
    owned_region
        .numeric_positions
        .append(&mut region.numeric_positions);
    let occurrences = take_all_modifier_occurrences(&mut region);
    if !occurrences.is_empty() {
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::AmbiguousEntityOwnership,
            region_index,
            occurrences,
            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            upstream_diagnostic: None,
        });
    }
    let head = owned_region
        .heads
        .pop()
        .expect("bounded phrase retains its head");
    let mut shape_constraint: Option<crate::SemanticShapeConstraint> = None;
    for constraint in owned_region.shape_constraints {
        if let Some(existing) = &mut shape_constraint {
            if existing.value.sides.is_some()
                && constraint.value.sides.is_some()
                && existing.value.sides != constraint.value.sides
            {
                issues.push(SemanticAssociationIssue {
                    kind: SemanticAssociationIssueKind::ConflictingShapeConstraints,
                    region_index,
                    occurrences: vec![OwnedSemanticOccurrence::ShapeConstraint(constraint)],
                    causal_provenance: SemanticIssueCausalProvenance::Unattributed,
                    upstream_diagnostic: None,
                });
            } else {
                existing.value.regular |= constraint.value.regular;
                existing.value.sides = existing.value.sides.or(constraint.value.sides);
                existing.additional_provenance.push(constraint.provenance);
            }
        } else {
            shape_constraint = Some(constraint);
        }
    }
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
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
                upstream_diagnostic: None,
            });
            None
        }
    };
    // Preserve all size owners for diagnostic recovery after canvas selection.
    let (relative_scale, additional_relative_scales) =
        take_size_candidates(owned_region.relative_scales);
    let (explicit_geometry, additional_explicit_geometries) =
        take_size_candidates(owned_region.explicit_geometries);
    let numeric_position = match owned_region.numeric_positions.len() {
        0 => None,
        1 => owned_region.numeric_positions.pop(),
        _ => {
            issues.push(SemanticAssociationIssue {
                kind: SemanticAssociationIssueKind::ConflictingNumericPositions,
                region_index,
                occurrences: owned_region
                    .numeric_positions
                    .into_iter()
                    .map(OwnedSemanticOccurrence::NumericPosition)
                    .collect(),
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
    let spread = select_term(
        owned_region.fluctuation_spreads,
        OwnedSemanticOccurrence::Fluctuation,
        SemanticAssociationIssueKind::ConflictingFluctuationSpreads,
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
            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
    let (width_extent, additional_width_extents) =
        take_size_candidates(owned_region.proportion_width_extents);
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
            causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            upstream_diagnostic: None,
        });
    }
    entities.push(SemanticEntity {
        shape_constraint,
        head,
        color,
        quantity,
        thinness,
        relative_scale,
        explicit_geometry,
        additional_relative_scales,
        additional_explicit_geometries,
        additional_width_extents,
        numeric_position,
        touch,
        continuity,
        angle,
        surface: SemanticSurface { quality, intensity },
        fluctuation: SemanticFluctuation {
            spread,
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
                .shape_constraints
                .drain(..)
                .map(OwnedSemanticOccurrence::ShapeConstraint),
        )
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
        .chain(
            region
                .relative_scales
                .drain(..)
                .map(OwnedSemanticOccurrence::RelativeScale),
        )
        .chain(
            region
                .explicit_geometries
                .drain(..)
                .map(OwnedSemanticOccurrence::ExplicitGeometry),
        )
        .chain(
            region
                .numeric_positions
                .drain(..)
                .map(OwnedSemanticOccurrence::NumericPosition),
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
        shape_constraints: {
            let (owned, remaining) = std::mem::take(&mut region.shape_constraints)
                .into_iter()
                .partition(|constraint| ownership.owns(&head, constraint.provenance.span));
            region.shape_constraints = remaining;
            owned
        },
        colors: take_owned_terms(&mut region.colors, &head, ownership),
        quantities: take_owned_quantities(&mut region.quantities, &head, ownership),
        thinnesses: take_owned_thinnesses(&mut region.thinnesses, &head, ownership),
        relative_scales: take_owned_relative_scales(&mut region.relative_scales, &head, ownership),
        explicit_geometries: {
            let (owned, remaining) = std::mem::take(&mut region.explicit_geometries)
                .into_iter()
                .partition(|geometry| ownership.owns(&head, geometry.source().span));
            region.explicit_geometries = remaining;
            owned
        },
        numeric_positions: {
            let (owned, remaining) = std::mem::take(&mut region.numeric_positions)
                .into_iter()
                .partition(|position| ownership.owns(&head, position.source().span));
            region.numeric_positions = remaining;
            owned
        },
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
        fluctuation_spreads: take_owned_terms(&mut region.fluctuation_spreads, &head, ownership),
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

fn take_owned_relative_scales(
    relative_scales: &mut Vec<SemanticRelativeScale>,
    head: &SemanticHead,
    ownership: &PreHeadPhraseOwnership,
) -> Vec<SemanticRelativeScale> {
    let (owned, remaining) = std::mem::take(relative_scales)
        .into_iter()
        .partition(|relative_scale| ownership.owns(head, relative_scale.provenance.span));
    *relative_scales = remaining;
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
        .chain(region.fluctuation_spreads.drain(..))
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

fn take_size_candidates<T>(values: Vec<T>) -> (Option<T>, Vec<T>) {
    let mut values = values.into_iter();
    (values.next(), values.collect())
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
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
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
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
                upstream_diagnostic: Some(diagnostic),
            }),
    );
}

fn attach_association_causal_provenance(
    clause_stream: &ClauseStream,
    entities: &[SemanticEntity],
    issues: &mut [SemanticAssociationIssue],
) {
    for issue in issues {
        let mut causes = Vec::new();
        match issue.kind {
            SemanticAssociationIssueKind::MissingEntityHead => {
                for occurrence in &issue.occurrences {
                    let source = occurrence.source();
                    let clause = &clause_stream.clauses[source.clause_index];
                    let clause_has_head = clause.atoms.iter().any(|atom| {
                        matches!(atom, ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive)
                    });
                    if !clause_has_head {
                        causes.extend(adjacent_diagnostic_causes(
                            clause_stream,
                            source,
                            SemanticUpstreamCausalRelation::MissingEntityHeadGap,
                        ));
                    }
                }
            }
            SemanticAssociationIssueKind::AmbiguousEntityOwnership => {
                let issue_region_index = issue.region_index;
                let heads = entities
                    .iter()
                    .map(|entity| entity.head.source())
                    .filter(|source| source.region_index == issue_region_index)
                    .collect::<Vec<_>>();
                if heads.len() == 1 {
                    for occurrence in &issue.occurrences {
                        let source = occurrence.source();
                        if source.clause_index == heads[0].clause_index {
                            causes.extend(diagnostic_causes_between(
                                clause_stream,
                                source.clause_index,
                                source.atom_index,
                                heads[0].atom_index,
                                SemanticUpstreamCausalRelation::EntityOwnershipPath,
                            ));
                        }
                    }
                }
            }
            _ => {}
        }
        issue.causal_provenance = causal_provenance(causes);
    }
}

fn adjacent_diagnostic_causes(
    clause_stream: &ClauseStream,
    occurrence: &SourceOccurrence,
    relation: SemanticUpstreamCausalRelation,
) -> Vec<SemanticUpstreamDiagnosticCause> {
    let clause = &clause_stream.clauses[occurrence.clause_index];
    clause
        .atoms
        .iter()
        .enumerate()
        .filter_map(|(atom_index, atom)| {
            let ClauseAtom::UnresolvedDiagnostic(diagnostic) = atom else {
                return None;
            };
            let lower = atom_index.min(occurrence.atom_index) + 1;
            let upper = atom_index.max(occurrence.atom_index);
            clause.atoms[lower..upper]
                .iter()
                .all(|between| {
                    matches!(
                        between,
                        ClauseAtom::GrammarMarker { .. }
                            | ClauseAtom::FunctionWord { .. }
                            | ClauseAtom::UnresolvedDiagnostic(_)
                    )
                })
                .then(|| {
                    diagnostic_cause(
                        clause_stream,
                        diagnostic,
                        occurrence.clause_index,
                        atom_index,
                        relation,
                    )
                })
        })
        .collect()
}

pub(crate) fn diagnostic_causes_between(
    clause_stream: &ClauseStream,
    clause_index: usize,
    left_atom_index: usize,
    right_atom_index: usize,
    relation: SemanticUpstreamCausalRelation,
) -> Vec<SemanticUpstreamDiagnosticCause> {
    let lower = left_atom_index.min(right_atom_index) + 1;
    let upper = left_atom_index.max(right_atom_index);
    clause_stream.clauses[clause_index].atoms[lower..upper]
        .iter()
        .enumerate()
        .filter_map(|(offset, atom)| {
            let ClauseAtom::UnresolvedDiagnostic(diagnostic) = atom else {
                return None;
            };
            Some(diagnostic_cause(
                clause_stream,
                diagnostic,
                clause_index,
                lower + offset,
                relation,
            ))
        })
        .collect()
}

pub(crate) fn diagnostic_causes_in_source_range(
    clause_stream: &ClauseStream,
    start_byte: usize,
    end_byte: usize,
    excluded_spans: &[SourceSpan],
    relation: SemanticUpstreamCausalRelation,
) -> Vec<SemanticUpstreamDiagnosticCause> {
    clause_stream
        .clauses
        .iter()
        .enumerate()
        .flat_map(|(clause_index, clause)| {
            clause
                .atoms
                .iter()
                .enumerate()
                .filter_map(move |(atom_index, atom)| {
                    let ClauseAtom::UnresolvedDiagnostic(diagnostic) = atom else {
                        return None;
                    };
                    (start_byte <= diagnostic.span.start_byte
                        && diagnostic.span.end_byte <= end_byte
                        && !excluded_spans.contains(&diagnostic.span))
                    .then(|| {
                        diagnostic_cause(
                            clause_stream,
                            diagnostic,
                            clause_index,
                            atom_index,
                            relation,
                        )
                    })
                })
        })
        .collect()
}

fn diagnostic_cause(
    clause_stream: &ClauseStream,
    diagnostic: &NeutralDiagnostic,
    clause_index: usize,
    atom_index: usize,
    relation: SemanticUpstreamCausalRelation,
) -> SemanticUpstreamDiagnosticCause {
    SemanticUpstreamDiagnosticCause {
        relation,
        diagnostic_kind: diagnostic.kind,
        recognized: diagnostic.recognized,
        span: diagnostic.span,
        region_index: sentence_region_index(clause_stream, diagnostic.span),
        clause_index,
        atom_index,
    }
}

pub(crate) fn causal_provenance(
    mut causes: Vec<SemanticUpstreamDiagnosticCause>,
) -> SemanticIssueCausalProvenance {
    causes.sort_by_key(|cause| {
        (
            cause.span.start_byte,
            cause.span.end_byte,
            cause.clause_index,
            cause.atom_index,
        )
    });
    causes.dedup_by_key(|cause| {
        (
            cause.span.start_byte,
            cause.span.end_byte,
            cause.clause_index,
            cause.atom_index,
        )
    });
    if causes.is_empty() {
        SemanticIssueCausalProvenance::Unattributed
    } else {
        SemanticIssueCausalProvenance::UpstreamDiagnostics(causes)
    }
}

fn entity_occurrence_count(entity: &SemanticEntity) -> usize {
    entity.head.occurrence_count()
        + entity.shape_constraint.as_ref().map_or(0, |constraint| {
            std::iter::once(&constraint.provenance)
                .chain(&constraint.additional_provenance)
                .filter(|source| source.span != entity.head.source().span)
                .count()
        })
        + usize::from(entity.color.is_some())
        + usize::from(entity.quantity.is_some())
        + usize::from(entity.thinness.is_some())
        + usize::from(entity.relative_scale.is_some())
        + usize::from(entity.explicit_geometry.is_some())
        + entity.additional_relative_scales.len()
        + entity.additional_explicit_geometries.len()
        + entity.additional_width_extents.len()
        + usize::from(entity.numeric_position.is_some())
        + usize::from(entity.touch.is_some())
        + usize::from(entity.continuity.is_some())
        + usize::from(entity.angle.is_some())
        + usize::from(entity.surface.quality.is_some())
        + usize::from(entity.surface.intensity.is_some())
        + usize::from(entity.fluctuation.amplitude.is_some())
        + usize::from(entity.fluctuation.frequency.is_some())
        + usize::from(entity.fluctuation.quality.is_some())
        + usize::from(entity.fluctuation.spread.is_some())
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
    if !ast.sequences.is_empty() {
        root.insert(
            "sequences".to_owned(),
            Value::Array(
                ast.sequences
                    .iter()
                    .map(|sequence| {
                        semantic_sequence_value(sequence.target_entity_index, &sequence.sequence)
                    })
                    .collect(),
            ),
        );
    }
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID.to_owned()),
    );
    serde_json::to_vec(&root).expect("closed semantic association AST serializes")
}

pub(crate) fn semantic_sequence_value(
    target_instruction_index: usize,
    sequence: &SemanticSequence,
) -> Value {
    match sequence.kind {
        SemanticSequenceKind::Color => serde_json::json!({
            "field": "color",
            "items": sequence
                .items
                .iter()
                .map(|item| semantic_identity_value(&item.identity))
                .collect::<Vec<_>>(),
            "kind": "cycle",
            "operator": semantic_identity_value(&sequence.operator.identity),
            "target_instruction_index": target_instruction_index,
        }),
        SemanticSequenceKind::Field(field) => serde_json::json!({
            "field": field.as_str(),
            "items": sequence
                .items
                .iter()
                .map(|item| semantic_identity_value(&item.identity))
                .collect::<Vec<_>>(),
            "kind": "member_cycle",
            "operator": semantic_identity_value(&sequence.operator.identity),
            "quantity": sequence.quantity.as_ref().map(|quantity| quantity.value),
            "target_instruction_index": target_instruction_index,
        }),
        SemanticSequenceKind::Units => serde_json::json!({
            "items": sequence
                .units
                .iter()
                .map(|unit| serde_json::json!({
                    "member_instruction_indices": unit.member_entity_indices,
                }))
                .collect::<Vec<_>>(),
            "kind": "member_cycle",
            "operator": semantic_identity_value(&sequence.operator.identity),
            "quantity": sequence.quantity.as_ref().map(|quantity| quantity.value),
            "target_instruction_index": target_instruction_index,
        }),
    }
}

pub(crate) fn semantic_entity_value(entity: &SemanticEntity) -> Value {
    let mut record = BTreeMap::new();
    if !entity.additional_relative_scales.is_empty() {
        record.insert(
            "additional_relative_scales".to_owned(),
            Value::Array(
                entity
                    .additional_relative_scales
                    .iter()
                    .map(|value| Value::String(value.value.as_str().to_owned()))
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
                    .map(semantic_explicit_geometry_value)
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
                    .map(|value| semantic_identity_value(&value.identity))
                    .collect(),
            ),
        );
    }

    if let Some(constraint) = &entity.shape_constraint {
        record.insert(
            "shape_constraint".to_owned(),
            serde_json::json!({
                "regular": constraint.value.regular, "sides": constraint.value.sides,
            }),
        );
    }
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
        "explicit_geometry".to_owned(),
        entity
            .explicit_geometry
            .as_ref()
            .map(semantic_explicit_geometry_value)
            .unwrap_or(Value::Null),
    );
    record.insert(
        "fluctuation".to_owned(),
        semantic_fluctuation_value(&entity.fluctuation),
    );
    record.insert("head".to_owned(), semantic_head_value(&entity.head));
    record.insert(
        "numeric_position".to_owned(),
        entity
            .numeric_position
            .as_ref()
            .map(semantic_numeric_position_value)
            .unwrap_or(Value::Null),
    );
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
        "relative_scale".to_owned(),
        entity
            .relative_scale
            .as_ref()
            .map(|relative_scale| Value::String(relative_scale.value.as_str().to_owned()))
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

pub(crate) fn semantic_explicit_geometry_value(geometry: &SemanticExplicitGeometry) -> Value {
    let mut record = BTreeMap::new();
    match geometry {
        SemanticExplicitGeometry::Radius(value) => {
            record.insert("dimension".to_owned(), Value::String("radius".to_owned()));
            record.insert(
                "value".to_owned(),
                semantic_decimal_value(value.decimal.value),
            );
        }
        SemanticExplicitGeometry::Diameter(value) => {
            record.insert("dimension".to_owned(), Value::String("diameter".to_owned()));
            record.insert(
                "value".to_owned(),
                semantic_decimal_value(value.decimal.value),
            );
        }
        SemanticExplicitGeometry::Length(value) => {
            record.insert("dimension".to_owned(), Value::String("length".to_owned()));
            record.insert(
                "value".to_owned(),
                semantic_decimal_value(value.decimal.value),
            );
        }
        SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => {
            record.insert(
                "dimension".to_owned(),
                Value::String("chord_sagitta".to_owned()),
            );
            record.insert(
                "chord".to_owned(),
                semantic_decimal_value(chord.decimal.value),
            );
            record.insert(
                "sagitta".to_owned(),
                semantic_decimal_value(sagitta.decimal.value),
            );
        }
        SemanticExplicitGeometry::WidthHeight { width, height } => {
            record.insert(
                "dimension".to_owned(),
                Value::String("width_height".to_owned()),
            );
            record.insert(
                "height".to_owned(),
                semantic_decimal_value(height.decimal.value),
            );
            record.insert(
                "width".to_owned(),
                semantic_decimal_value(width.decimal.value),
            );
        }
        SemanticExplicitGeometry::Side(value) => {
            record.insert("dimension".to_owned(), Value::String("side".to_owned()));
            record.insert(
                "value".to_owned(),
                semantic_decimal_value(value.decimal.value),
            );
        }
    }
    record.insert(
        "basis".to_owned(),
        Value::String("canvas_short_edge".to_owned()),
    );
    Value::Object(record.into_iter().collect())
}

pub(crate) fn semantic_numeric_position_value(position: &SemanticNumericPosition) -> Value {
    let mut record = BTreeMap::new();
    record.insert("basis".to_owned(), Value::String("canvas_axes".to_owned()));
    record.insert(
        "x".to_owned(),
        semantic_decimal_value(position.x.decimal.value),
    );
    record.insert(
        "y".to_owned(),
        semantic_decimal_value(position.y.decimal.value),
    );
    Value::Object(record.into_iter().collect())
}

fn semantic_decimal_value(decimal: crate::ExactDecimal) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "coefficient".to_owned(),
        Value::String(decimal.coefficient().to_string()),
    );
    record.insert("scale".to_owned(), Value::from(u64::from(decimal.scale())));
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
            SemanticMacroParameterValue::ExactDecimal(value) => semantic_decimal_value(*value),
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
    if let Some(spread) = &fluctuation.spread {
        record.insert(
            "spread".to_owned(),
            semantic_identity_value(&spread.identity),
        );
    }
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

    fn execution_owner_parameter(
        name: &str,
        schema: ParameterSchema,
        value: SemanticMacroParameterValue,
        span: SourceSpan,
    ) -> SemanticMacroParameterBinding {
        SemanticMacroParameterBinding {
            name: name.to_owned(),
            schema,
            value,
            provenance: SourceOccurrence {
                span,
                surface: format!("surface-{name}"),
                language: ResolvedInstructionLanguage::En,
                region_index: span.start_byte,
                clause_index: span.start_byte,
                atom_index: span.start_byte,
            },
            source_asset_id: Some(format!("asset-{name}")),
            canonical_surface_ja: Some(format!("表示-{name}")),
        }
    }

    #[test]
    fn execution_owner_parameter_meaning_is_typed_and_source_independent() {
        let original = vec![
            execution_owner_parameter(
                "count",
                ParameterSchema::Integer,
                SemanticMacroParameterValue::Integer(2),
                SourceSpan {
                    start_byte: 0,
                    end_byte: 1,
                },
            ),
            execution_owner_parameter(
                "ratio",
                ParameterSchema::Number,
                SemanticMacroParameterValue::Number(0.5),
                SourceSpan {
                    start_byte: 2,
                    end_byte: 3,
                },
            ),
            execution_owner_parameter(
                "tone",
                ParameterSchema::SemanticRef {
                    category: "color".to_owned(),
                    dimension: None,
                },
                SemanticMacroParameterValue::SemanticRef(SemanticIdentity {
                    category: "color".to_owned(),
                    id: "red".to_owned(),
                }),
                SourceSpan {
                    start_byte: 4,
                    end_byte: 5,
                },
            ),
        ];
        let mut source_only = original.clone();
        for (index, parameter) in source_only.iter_mut().enumerate() {
            parameter.provenance.span.start_byte += 10 + index;
            parameter.provenance.span.end_byte += 10 + index;
            parameter.provenance.surface.push('!');
            parameter.provenance.region_index += 1;
            parameter.provenance.clause_index += 1;
            parameter.provenance.atom_index += 1;
            parameter.source_asset_id = Some(format!("other-{index}"));
            parameter.canonical_surface_ja = Some(format!("別-{index}"));
        }
        let mut reordered = source_only.clone();
        reordered.reverse();
        let mut integer_difference = original.clone();
        integer_difference[0].value = SemanticMacroParameterValue::Integer(3);
        let mut number_difference = original.clone();
        number_difference[1].value = SemanticMacroParameterValue::Number(0.500_001);
        let mut semantic_ref_difference = original.clone();
        semantic_ref_difference[2].value =
            SemanticMacroParameterValue::SemanticRef(SemanticIdentity {
                category: "color".to_owned(),
                id: "blue".to_owned(),
            });
        let mut typed_difference = original.clone();
        typed_difference[0].value = SemanticMacroParameterValue::Number(2.0);
        let mut name_difference = original.clone();
        name_difference[0].name = "other".to_owned();
        let mut schema_difference = original.clone();
        schema_difference[2].schema = ParameterSchema::SemanticRef {
            category: "shape".to_owned(),
            dimension: None,
        };
        let mut duplicate_name = original.clone();
        duplicate_name[1].name = "count".to_owned();
        let mut fewer = original.clone();
        fewer.pop();

        for (label, candidate, expected) in [
            ("source-only", source_only, true),
            ("reordered", reordered, true),
            ("integer-value", integer_difference, false),
            ("number-value", number_difference, false),
            ("semantic-ref-value", semantic_ref_difference, false),
            ("typed-value", typed_difference, false),
            ("name", name_difference, false),
            ("schema", schema_difference, false),
            ("duplicate-name", duplicate_name, false),
            ("cardinality", fewer, false),
        ] {
            assert_eq!(
                semantic_macro_parameters_have_same_meaning(&original, &candidate),
                expected,
                "{label}"
            );
        }
    }

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
            Vec::new(),
            Vec::new(),
            BTreeSet::new(),
            BTreeSet::new(),
            BTreeSet::new(),
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
