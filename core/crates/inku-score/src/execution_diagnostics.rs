//! Shared checked-performance diagnostics without source or host dependencies.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreExecutionReason {
    InvalidCompactPerformance,
    InvalidFillTarget,
    MissingNotTouchingReference,
    NotTouchingReferenceOmitted,
    UnsupportedNotTouchingGeometry,
    NumericNotTouchingPositionConflict,
    MissingBetweenReference,
    BetweenReferenceOmitted,
    UnsupportedBetweenGeometry,
    NumericBetweenPositionConflict,
    MissingTouchingReference,
    TouchingReferenceOmitted,
    UnsupportedTouchingStructure,
    UnsupportedTouchingPrimitive,
    MissingTouchingPositionAuthority,
    MissingTouchingConstraints,
    TouchingGeometryConflict,
    TouchingDirectionConflict,
    NumericTouchingPositionConflict,
    NumericTouchingBoundsConflict,
    MissingConnectedReference,
    ConnectedReferenceOmitted,
    UnsupportedConnectedPrimitive,
    UnsupportedConnectedStructure,
    MissingConnectedPositionAuthority,
    NumericConnectedPositionConflict,
    CyclicConnectedDependency,
    ConflictingConnectedConstraints,
    ConflictingRelationConstraints,
    UnsupportedAnchorRelation,
    InvalidTransformGroup,
    UnsupportedTransformGroupRelation,
    NumericTransformGroupPositionConflict,
    MissingAlongReference,
    AlongReferenceOmitted,
    UnsupportedAlongPrimitive,
    UnsupportedAlongStructure,
    MissingAlongPositionAuthority,
    NumericAlongPositionConflict,
    AlongDirectionConflict,
    MissingCuttingReference,
    CuttingReferenceOmitted,
    UnsupportedCuttingPrimitive,
    UnsupportedCuttingStructure,
    MissingCuttingPositionAuthority,
    NumericCuttingPositionConflict,
    CuttingDirectionConflict,
    NoDrawableInstructions,
    FillClipUnsupported,
    FillClipLimitExceeded,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreExecutionDisposition {
    Stopped,
    Omitted,
    /// The source geometry remains rendered without the failed relation.
    RelationOmitted,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ScoreExecutionDiagnostic {
    pub instruction_index: usize,
    /// Non-drawing Anchor owner. When present, consumers must use this instead
    /// of `instruction_index`, which remains for legacy diagnostic compatibility.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub anchor_index: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dependency_instruction_index: Option<usize>,
    pub reason: ScoreExecutionReason,
    pub disposition: ScoreExecutionDisposition,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ScoreExecutionSummary {
    pub input_score_digest: String,
    pub diagnostics: Vec<ScoreExecutionDiagnostic>,
    pub rendered_instruction_indices: Vec<usize>,
}
