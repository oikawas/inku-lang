//! Host-neutral error policy shared by ordinary and macro Score lowering.

pub use inku_score::ScoreErrorPolicy;
use serde::{Deserialize, Serialize};

/// Observable result state after applying one error policy.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreLoweringOutcome {
    Complete,
    CompleteWithOmissions,
    Stopped,
}
