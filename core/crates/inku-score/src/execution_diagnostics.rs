//! Shared checked-performance diagnostics without source or host dependencies.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreExecutionReason {
    MissingConnectedReference,
    ConnectedReferenceOmitted,
    UnsupportedConnectedPrimitive,
    UnsupportedConnectedStructure,
    MissingConnectedPositionAuthority,
    NumericConnectedPositionConflict,
    NoDrawableInstructions,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreExecutionDisposition {
    Stopped,
    Omitted,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ScoreExecutionDiagnostic {
    pub instruction_index: usize,
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
