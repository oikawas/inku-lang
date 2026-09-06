//! Host-neutral error policy shared by ordinary and macro Score lowering.

/// Closed author choice for unsupported drawing meaning.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum ScoreErrorPolicy {
    /// Preserve the historical all-or-nothing result.
    #[default]
    Stop,
    /// Omit the smallest independently executable unit and continue in source order.
    OmitAndContinue,
}

/// Observable result state after applying one error policy.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScoreLoweringOutcome {
    Complete,
    CompleteWithOmissions,
    Stopped,
}
