//! Host-neutral checked execution policy shared by DDL and rendering.

use serde::{Deserialize, Serialize};

/// Legacy input preference for recovery reporting.
///
/// Recoverable failures retain every independently drawable unit under either
/// value. Only integrity failures stop execution.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreErrorPolicy {
    Stop,
    #[default]
    OmitAndContinue,
}

#[must_use]
pub const fn is_stop(policy: &ScoreErrorPolicy) -> bool {
    matches!(policy, ScoreErrorPolicy::Stop)
}
