//! Source-owned diagnostics for the compile-once Score execution facade.

use serde::Serialize;

use crate::SourceSpan;

/// The original typed compiler bucket that produced an execution diagnostic.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CompilerExecutionIssueKind {
    Hole,
    Conflict,
    BlockingDiagnostic,
    Dependency,
}

/// A typed source unit removed from the internal recovery projection.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum CompilerExecutionOmissionUnit {
    /// An undelivered field or grammar occurrence, separate from accepted drawables.
    SourceOccurrence {
        span: SourceSpan,
    },
    SourceInstructions {
        instruction_indices: Vec<usize>,
    },
    Clause {
        clause_index: usize,
    },
    CoordinatedGroup {
        group_index: usize,
        member_instruction_indices: Vec<usize>,
    },
    AcceptedContinuationTarget {
        target_instruction_index: usize,
    },
    RelationInstruction {
        instruction_index: usize,
        dependency_instruction_indices: Vec<usize>,
    },
    GroundCandidates,
    BackgroundCandidates,
    MacroInvocation {
        source_instruction_index: usize,
        invocation_ordinal: u64,
    },
}

/// Actual treatment of one original compiler issue.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum CompilerExecutionDisposition {
    Stopped,
    /// The source instruction remains after its unresolved relation is removed.
    RelationOmitted {
        unit: CompilerExecutionOmissionUnit,
    },
    Omitted {
        unit: CompilerExecutionOmissionUnit,
    },
}

/// Original compiler identity plus the exact execution treatment.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct CompilerExecutionDiagnostic {
    pub issue_kind: CompilerExecutionIssueKind,
    pub issue_id: String,
    pub reason: String,
    pub span: Option<SourceSpan>,
    pub disposition: CompilerExecutionDisposition,
}
