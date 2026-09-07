//! Host-neutral error policy shared by ordinary and macro Score lowering.

pub use inku_score::ScoreErrorPolicy;

/// Observable result state after applying one error policy.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScoreLoweringOutcome {
    Complete,
    CompleteWithOmissions,
    Stopped,
}
