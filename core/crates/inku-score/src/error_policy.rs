//! Host-neutral checked execution policy shared by DDL and rendering.

use serde::{Deserialize, Serialize};

/// Closed author choice for an instruction that cannot be performed faithfully.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreErrorPolicy {
    #[default]
    Stop,
    OmitAndContinue,
}

#[must_use]
pub const fn is_stop(policy: &ScoreErrorPolicy) -> bool {
    matches!(policy, ScoreErrorPolicy::Stop)
}
