//! Typed ownership and execution dispositions for Score lowering diagnostics.

use serde::Serialize;

use crate::{ExpansionPathSegment, SemanticPreviousReference, SemanticRelationKind, SourceSpan};

/// Closed gaps that preserve unsupported source meaning without a fallback or clamp.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "type", content = "value", rename_all = "snake_case")]
pub enum ScoreFieldGap {
    FillRegionHasNoArea,
    InvalidFillTarget,
    FillCountExceedsScoreRange,
    /// The resolved fill is symbolic until Step 11 supplies Score clip delivery.
    FillRequiresRegionMaterialization,
    ConflictingSizeSpecifications {
        candidate_extents: Vec<crate::score_lowering::Rational>,
        effective_extent: crate::score_lowering::Rational,
    },
    UnsupportedPrimitiveIdentity {
        category: String,
        id: String,
    },
    MacroInvocationHead,
    ExactCountZero {
        value: u64,
    },
    ExactCountExceedsScoreRange {
        value: u64,
    },
    UnsupportedRelativeScalePrimitive {
        primitive: inku_score::Primitive,
    },
    UnsupportedRelativeScaleValue {
        value: crate::CoreModifierValue,
    },
    MissingExactCount,
    RepeatedCountUnsupported {
        value: u32,
    },
    MissingExplicitGeometry,
    MissingNumericPosition,
    MissingColor,
    MissingResolvedPaletteContext,
    MissingTouch,
    MissingContinuity,
    MissingEmptySurface,
    MissingPlaceAction,
    UnsupportedPrimitiveForExplicitGeometry {
        primitive: inku_score::Primitive,
    },
    GeometryDimensionMismatch {
        primitive: inku_score::Primitive,
    },
    ShapeConstraintMismatch {
        primitive: inku_score::Primitive,
    },
    UnsupportedColorIdentity {
        category: String,
        id: String,
    },
    UnsupportedTouchIdentity {
        category: String,
        id: String,
    },
    UnsupportedContinuityIdentity {
        category: String,
        id: String,
    },
    UnsupportedSurfaceIdentity {
        category: String,
        id: String,
    },
    UnsupportedSurfaceIntensity {
        category: String,
        id: String,
    },
    UnsupportedActionIdentity {
        category: String,
        id: String,
    },
    UnsupportedAngleIdentity {
        category: String,
        id: String,
    },
    UnsupportedAngleForPrimitive {
        primitive: inku_score::Primitive,
    },
    NamedAndNumericPositionConflict,
    UnsupportedNamedPosition,
    UnsupportedInstructionMeaning,
    UnsupportedRelation {
        kind: SemanticRelationKind,
        reference: SemanticPreviousReference,
        dependency_instruction_indices: Vec<usize>,
    },
    UnavailableRelationReference {
        kind: SemanticRelationKind,
        reference: SemanticPreviousReference,
        dependency_instruction_indices: Vec<usize>,
    },
    UnsupportedGround,
    UnsupportedCoordinatedGroup,
    UnsupportedDocumentMeaning,
    UnboundMacroCallerMeaning,
    UnsupportedLayoutDirection {
        category: String,
        id: String,
    },
    MissingMacroExpansionOwner {
        invocation_ordinal: u64,
    },
    DuplicateMacroExpansionOwner {
        invocation_ordinal: u64,
    },
    UnsupportedMacroStructure,
    UnsupportedMacroRelation,
    UnavailableMacroRelationReference,
    MissingMacroEmitField {
        key: String,
    },
    UnknownMacroEmitField {
        key: String,
    },
    MacroEmitFieldTypeMismatch {
        key: String,
    },
    MacroEmitIntegerOutOfRange {
        key: String,
        value: i64,
    },
    MacroEmitFieldCategoryMismatch {
        key: String,
        expected: String,
        actual: String,
    },
    UnsupportedMacroEmitIdentity {
        key: String,
        category: String,
        id: String,
    },
    MissingMacroEmitFocusTarget {
        invocation_ordinal: u64,
        expansion_path: Vec<ExpansionPathSegment>,
        generated_ordinal: u64,
    },
    DuplicateMacroEmitFocusTarget {
        invocation_ordinal: u64,
        expansion_path: Vec<ExpansionPathSegment>,
        generated_ordinal: u64,
    },
    NonPositiveDimension,
    PositionOutOfRange,
    GeometryExtentOutOfBounds,
    GeometryRepresentationLimit,
}

impl ScoreFieldGap {
    pub const fn is_integrity_failure(&self) -> bool {
        matches!(
            self,
            Self::MissingMacroExpansionOwner { .. }
                | Self::DuplicateMacroExpansionOwner { .. }
                | Self::MissingMacroEmitFocusTarget { .. }
                | Self::DuplicateMacroEmitFocusTarget { .. }
        )
    }
}

/// One independently omittable appearance dimension.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreAppearanceField {
    Color,
    Touch,
    Continuity,
    SurfaceQuality,
    SurfaceIntensity,
}

/// Actual default or retained value used after one appearance omission.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreAppearanceResolution {
    ContrastColor,
    Pen,
    Solid,
    Filled,
    PreserveExplicitSurfaceQuality,
    PreserveGeneratedValue,
}

/// Exact source or generated owner for one lowering diagnostic.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ScoreDiagnosticOwner {
    SourceInstruction {
        instruction_index: usize,
        field: Option<ScoreAppearanceField>,
        spans: Vec<SourceSpan>,
    },
    MacroInvocation {
        source_instruction_index: usize,
        invocation_ordinal: u64,
        field: Option<ScoreAppearanceField>,
        spans: Vec<SourceSpan>,
    },
    GeneratedNode {
        source_instruction_index: usize,
        invocation_ordinal: u64,
        expansion_path: Vec<ExpansionPathSegment>,
        generated_ordinal: u64,
        key: Option<String>,
        spans: Vec<SourceSpan>,
    },
    Ground {
        spans: Vec<SourceSpan>,
    },
    CoordinatedGroup {
        group_index: usize,
        member_instruction_indices: Vec<usize>,
        spans: Vec<SourceSpan>,
    },
}

/// The smallest execution projection removed by OmitAndContinue.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ScoreOmissionUnit {
    AppearanceField {
        field: ScoreAppearanceField,
    },
    SourceInstruction {
        instruction_index: usize,
    },
    MacroEmit {
        source_instruction_index: usize,
        invocation_ordinal: u64,
        expansion_path: Vec<ExpansionPathSegment>,
        generated_ordinal: u64,
    },
    MacroStructuralSubtree {
        source_instruction_index: usize,
        invocation_ordinal: u64,
        expansion_path: Vec<ExpansionPathSegment>,
        generated_ordinal: u64,
    },
    MacroInvocation {
        source_instruction_index: usize,
        invocation_ordinal: u64,
    },
    Ground,
    CoordinatedGroup {
        group_index: usize,
        member_instruction_indices: Vec<usize>,
    },
    RelationInstruction {
        instruction_index: usize,
    },
}

/// Actual treatment of a diagnostic under the selected mode.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ScoreDiagnosticDisposition {
    /// The error is reported while the authorized smaller geometry is rendered.
    Recovered,
    /// The source geometry remains while its unsupported relation is removed.
    RelationOmitted,
    Stopped,
    Omitted {
        unit: ScoreOmissionUnit,
        appearance_resolution: Option<ScoreAppearanceResolution>,
    },
}

/// Stable reason, exact owner, and actual execution treatment.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ScoreLoweringDiagnostic {
    pub reason: ScoreFieldGap,
    pub owner: ScoreDiagnosticOwner,
    pub disposition: ScoreDiagnosticDisposition,
}
