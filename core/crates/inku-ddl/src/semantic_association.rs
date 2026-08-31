//! Single-head semantic association over the accepted source-preserving clause stream.

use std::collections::BTreeMap;

use serde_json::{Number, Value};

use crate::{
    ClauseAtom, ClauseSeparatorKind, ClauseStream, ClauseStreamError, CoreRoleKind,
    NeutralDiagnostic, NeutralDiagnosticKind, NormalizedDdlDocument, RemainingRoleKind,
    ResolvedInstructionLanguage, SAIJIKI_ASSET_ID, SourceSpan, parse_clause_stream,
    project_macro_semantic_ref, saijiki_asset,
};

/// Stable identity for the runtime-disconnected single-head semantic AST.
pub const SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID: &str = "inku.semantic-entity-association.v6";

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

/// One single-head entity. A field is absent only when it was not explicitly and uniquely stated.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticEntity {
    pub head: SemanticTerm,
    pub color: Option<SemanticTerm>,
    pub quantity: Option<SemanticQuantity>,
    pub touch: Option<SemanticTerm>,
    pub continuity: Option<SemanticTerm>,
    pub angle: Option<SemanticTerm>,
    pub surface: SemanticSurface,
    pub fluctuation: SemanticFluctuation,
    pub proportion: SemanticProportion,
}

/// Partial or complete semantic entity sequence in sentence-region source order.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticEntityAssociationAst {
    pub entities: Vec<SemanticEntity>,
    pub complete: bool,
}

/// An association-owned occurrence delivered to a typed issue rather than an AST field.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum OwnedSemanticOccurrence {
    Head(SemanticTerm),
    Color(SemanticTerm),
    Quantity(SemanticQuantity),
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
            Self::Head(term)
            | Self::Color(term)
            | Self::Touch(term)
            | Self::Continuity(term)
            | Self::Angle(term)
            | Self::Surface(term)
            | Self::Fluctuation(term)
            | Self::Proportion(term) => &term.provenance.source,
            Self::Quantity(quantity) => &quantity.provenance,
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
}

impl SemanticAssociationIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::AmbiguousEntityOwnership => "ambiguous_entity_ownership",
            Self::MissingEntityHead => "missing_entity_head",
            Self::ConflictingColors => "conflicting_colors",
            Self::ConflictingQuantities => "conflicting_quantities",
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
        }
    }
}

/// One typed issue with either its owned occurrences or its unchanged upstream diagnostic.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticAssociationIssue {
    pub kind: SemanticAssociationIssueKind,
    pub region_index: usize,
    pub occurrences: Vec<OwnedSemanticOccurrence>,
    pub upstream_diagnostic: Option<NeutralDiagnostic>,
}

/// Source-preserving association result. Entity counts and compound-reference counts remain
/// separate so the accepted I-592 occurrence accounting is not recounted by this slice.
#[derive(Clone, Debug, Eq, PartialEq)]
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
}

#[derive(Default)]
struct AssociationRegion {
    heads: Vec<SemanticTerm>,
    colors: Vec<SemanticTerm>,
    quantities: Vec<SemanticQuantity>,
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

/// Associate the closed single-entity roles and explicit numeric quantity within sentence regions.
///
/// The accepted clause parser is invoked exactly once. Sentence endings close a region, while line
/// breaks only create source-formatting clause boundaries inside the same region.
pub fn associate_semantic_entities(
    document: &NormalizedDdlDocument,
) -> Result<SemanticAssociationResult, ClauseStreamError> {
    let clause_stream = parse_clause_stream(document)?;
    let mut regions = BTreeMap::<usize, AssociationRegion>::new();
    let mut owned_occurrence_count = 0;
    let mut explicit_previous_references = Vec::new();

    for (clause_index, clause) in clause_stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let region_index = sentence_region_index(&clause_stream, atom.span());
            let region = regions.entry(region_index).or_default();
            match atom {
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive => {
                    region.heads.push(project_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
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
                ClauseAtom::UnresolvedDiagnostic(diagnostic) => {
                    region.diagnostics.push(diagnostic.clone());
                }
                ClauseAtom::SaijikiRelation {
                    asset_id,
                    relation_type,
                    surface,
                    span,
                } => {
                    if let Some(occurrence) = explicit_previous_reference_occurrence(
                        document,
                        asset_id,
                        relation_type,
                        surface,
                        *span,
                        region_index,
                        clause_index,
                        atom_index,
                    ) {
                        explicit_previous_references.push(occurrence);
                    }
                }
                ClauseAtom::CoreRole(_)
                | ClauseAtom::RemainingRole(_)
                | ClauseAtom::FunctionWord { .. } => {}
            }
        }
    }

    let mut entities = Vec::new();
    let mut issues = Vec::new();
    for (region_index, region) in regions {
        associate_region(region_index, region, &mut entities, &mut issues);
    }

    let delivered_occurrence_count = entities.iter().map(entity_occurrence_count).sum::<usize>()
        + issues
            .iter()
            .map(|issue| issue.occurrences.len())
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

    Ok(SemanticAssociationResult {
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
    })
}

#[allow(clippy::too_many_arguments)]
fn explicit_previous_reference_occurrence(
    document: &NormalizedDdlDocument,
    asset_id: &str,
    relation_type: &str,
    surface: &str,
    span: SourceSpan,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> Option<ExplicitPreviousReferenceOccurrence> {
    if asset_id != SAIJIKI_ASSET_ID {
        return None;
    }
    let relation = saijiki_asset()
        .relations
        .iter()
        .find(|relation| relation.relation_type == relation_type)?;
    let literals = match document.language() {
        ResolvedInstructionLanguage::Ja => &relation.literals_ja,
        ResolvedInstructionLanguage::En => &relation.literals_en,
    };
    let accepted = literals.iter().any(|literal| match document.language() {
        ResolvedInstructionLanguage::Ja => surface == literal,
        ResolvedInstructionLanguage::En => surface.eq_ignore_ascii_case(literal),
    });
    if !accepted {
        return None;
    }

    let kind = match relation_type {
        "along" => SemanticRelationKind::Along,
        "not_touching" => SemanticRelationKind::NotTouching,
        "cutting" => SemanticRelationKind::Cutting,
        "between" => SemanticRelationKind::Between,
        "touching" => SemanticRelationKind::Touching,
        _ => return None,
    };
    let reference = match kind {
        SemanticRelationKind::Between => SemanticPreviousReference::PreviousTwo,
        SemanticRelationKind::Along
        | SemanticRelationKind::NotTouching
        | SemanticRelationKind::Cutting
        | SemanticRelationKind::Touching => SemanticPreviousReference::PreviousOne,
    };
    Some(ExplicitPreviousReferenceOccurrence {
        kind,
        reference,
        provenance: source_occurrence(document, span, region_index, clause_index, atom_index),
        asset_id: asset_id.to_owned(),
        relation_type: relation_type.to_owned(),
    })
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
    entities: &mut Vec<SemanticEntity>,
    issues: &mut Vec<SemanticAssociationIssue>,
) {
    if region.heads.len() > 1 {
        let surface_occurrences = take_surface_occurrences(&mut region);
        let fluctuation_occurrences = take_fluctuation_occurrences(&mut region);
        let proportion_occurrences = take_proportion_occurrences(&mut region);
        let mut occurrences = region
            .heads
            .drain(..)
            .map(OwnedSemanticOccurrence::Head)
            .chain(region.colors.drain(..).map(OwnedSemanticOccurrence::Color))
            .chain(
                region
                    .quantities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Quantity),
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
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::AmbiguousEntityOwnership,
            region_index,
            occurrences,
            upstream_diagnostic: None,
        });
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

    let head = region.heads.pop().expect("single head was checked");
    let color = select_term(
        region.colors,
        OwnedSemanticOccurrence::Color,
        SemanticAssociationIssueKind::ConflictingColors,
        region_index,
        issues,
    );
    let quantity = match region.quantities.len() {
        0 => None,
        1 => region.quantities.pop(),
        _ => {
            let occurrences = region
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
    let touch = select_term(
        region.touches,
        OwnedSemanticOccurrence::Touch,
        SemanticAssociationIssueKind::ConflictingTouches,
        region_index,
        issues,
    );
    let continuity = select_term(
        region.continuities,
        OwnedSemanticOccurrence::Continuity,
        SemanticAssociationIssueKind::ConflictingContinuities,
        region_index,
        issues,
    );
    let angle = select_term(
        region.angles,
        OwnedSemanticOccurrence::Angle,
        SemanticAssociationIssueKind::ConflictingAngles,
        region_index,
        issues,
    );
    let quality = select_term(
        region.surface_qualities,
        OwnedSemanticOccurrence::Surface,
        SemanticAssociationIssueKind::ConflictingSurfaceQualities,
        region_index,
        issues,
    );
    let intensity = select_term(
        region.surface_intensities,
        OwnedSemanticOccurrence::Surface,
        SemanticAssociationIssueKind::ConflictingSurfaceIntensities,
        region_index,
        issues,
    );
    if !region.unclassified_surfaces.is_empty() {
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::UnknownSurfaceDimension,
            region_index,
            occurrences: region
                .unclassified_surfaces
                .into_iter()
                .map(OwnedSemanticOccurrence::Surface)
                .collect(),
            upstream_diagnostic: None,
        });
    }
    let amplitude = select_term(
        region.fluctuation_amplitudes,
        OwnedSemanticOccurrence::Fluctuation,
        SemanticAssociationIssueKind::ConflictingFluctuationAmplitudes,
        region_index,
        issues,
    );
    let frequency = select_term(
        region.fluctuation_frequencies,
        OwnedSemanticOccurrence::Fluctuation,
        SemanticAssociationIssueKind::ConflictingFluctuationFrequencies,
        region_index,
        issues,
    );
    let fluctuation_quality = select_term(
        region.fluctuation_qualities,
        OwnedSemanticOccurrence::Fluctuation,
        SemanticAssociationIssueKind::ConflictingFluctuationQualities,
        region_index,
        issues,
    );
    if !region.unclassified_fluctuations.is_empty() {
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::UnknownFluctuationDimension,
            region_index,
            occurrences: region
                .unclassified_fluctuations
                .into_iter()
                .map(OwnedSemanticOccurrence::Fluctuation)
                .collect(),
            upstream_diagnostic: None,
        });
    }
    let aspect = select_term(
        region.proportion_aspects,
        OwnedSemanticOccurrence::Proportion,
        SemanticAssociationIssueKind::ConflictingProportionAspects,
        region_index,
        issues,
    );
    let width_extent = select_term(
        region.proportion_width_extents,
        OwnedSemanticOccurrence::Proportion,
        SemanticAssociationIssueKind::ConflictingProportionWidthExtents,
        region_index,
        issues,
    );
    let arc_form = select_term(
        region.proportion_arc_forms,
        OwnedSemanticOccurrence::Proportion,
        SemanticAssociationIssueKind::ConflictingProportionArcForms,
        region_index,
        issues,
    );
    if !region.unclassified_proportions.is_empty() {
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::UnknownProportionDimension,
            region_index,
            occurrences: region
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
    append_upstream_issues(region_index, region.diagnostics, issues);
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
    1 + usize::from(entity.color.is_some())
        + usize::from(entity.quantity.is_some())
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
    record.insert(
        "head".to_owned(),
        semantic_identity_value(&entity.head.identity),
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
        "quantity".to_owned(),
        entity
            .quantity
            .as_ref()
            .map(|quantity| Value::Number(Number::from(quantity.value)))
            .unwrap_or(Value::Null),
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
