//! Versioned, host-neutral variation authoring-authority transitions.
//!
//! This module decides whether an authoring write may be committed and proposes
//! the next compare-and-set value. It does not save the proposal or claim that a
//! host transaction succeeded.

use std::fmt;

use serde::{Deserialize, Deserializer, Serialize, Serializer, de};

use crate::protocol::DecimalU64;

/// Stable wire identity for the first authority protocol.
pub const VARIATION_AUTHORITY_PROTOCOL_ID: &str = "inku.variation-authority.v1";

/// Version of every state and transition outcome in this module.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub enum AuthorityProtocolVersion {
    #[serde(rename = "inku.variation-authority.v1")]
    V1,
}

impl AuthorityProtocolVersion {
    pub const fn id(self) -> &'static str {
        match self {
            Self::V1 => VARIATION_AUTHORITY_PROTOCOL_ID,
        }
    }
}

/// How the variation was first created. This value never changes in-place.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VariationOrigin {
    Stage1Generated,
    UserAuthoredDdl,
}

/// Which visible authoring surface may currently replace the variation source.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuthoringAuthority {
    DescriptionAuthoritative,
    DdlAuthoritative,
    LegacyUnknown,
}

/// A persisted authority sidecar that has passed protocol and pair validation.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct VariationAuthorityState {
    protocol_version: AuthorityProtocolVersion,
    #[serde(with = "decimal_u64")]
    revision: u64,
    origin: VariationOrigin,
    authority: AuthoringAuthority,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UnvalidatedAuthorityState {
    protocol_version: AuthorityProtocolVersion,
    #[serde(with = "decimal_u64")]
    revision: u64,
    origin: VariationOrigin,
    authority: AuthoringAuthority,
}

impl VariationAuthorityState {
    /// Initial state for a variation created from a description and Stage 1.
    pub const fn new_description() -> Self {
        Self {
            protocol_version: AuthorityProtocolVersion::V1,
            revision: 0,
            origin: VariationOrigin::Stage1Generated,
            authority: AuthoringAuthority::DescriptionAuthoritative,
        }
    }

    /// Initial state for a variation created directly from authored DDL.
    pub const fn new_direct_ddl() -> Self {
        Self {
            protocol_version: AuthorityProtocolVersion::V1,
            revision: 0,
            origin: VariationOrigin::UserAuthoredDdl,
            authority: AuthoringAuthority::DdlAuthoritative,
        }
    }

    /// Validate a state loaded from host persistence without inferring migration.
    pub fn from_loaded(
        protocol_version: AuthorityProtocolVersion,
        revision: u64,
        origin: VariationOrigin,
        authority: AuthoringAuthority,
    ) -> Result<Self, AuthorityStateValidationError> {
        if matches!(
            (origin, authority),
            (
                VariationOrigin::UserAuthoredDdl,
                AuthoringAuthority::DescriptionAuthoritative
            )
        ) {
            return Err(AuthorityStateValidationError::IllegalOriginAuthorityPair {
                origin,
                authority,
            });
        }

        Ok(Self {
            protocol_version,
            revision,
            origin,
            authority,
        })
    }

    pub const fn protocol_version(&self) -> AuthorityProtocolVersion {
        self.protocol_version
    }

    pub const fn revision(&self) -> u64 {
        self.revision
    }

    pub const fn origin(&self) -> VariationOrigin {
        self.origin
    }

    pub const fn authority(&self) -> AuthoringAuthority {
        self.authority
    }

    /// Propose one committed user edit after the host compares exact source bytes.
    ///
    /// `source_bytes_changed = false` is a no-op and cannot acquire the DDL lock.
    /// A later edit that restores older bytes is still a mutation and cannot
    /// restore description authority.
    pub fn propose_committed_user_ddl_mutation(
        &self,
        expected_revision: u64,
        source_bytes_changed: bool,
    ) -> AuthorityTransitionOutcome {
        let action = AuthorityAction::CommitUserDdlMutation;
        if let Some(conflict) = self.revision_conflict(expected_revision) {
            return conflict;
        }
        if !source_bytes_changed {
            return AuthorityTransitionOutcome::no_change(action, self.clone());
        }
        if self.authority == AuthoringAuthority::LegacyUnknown {
            return AuthorityTransitionOutcome::compatibility_required(action, self);
        }

        self.propose_advance(
            action,
            expected_revision,
            AuthoringAuthority::DdlAuthoritative,
        )
    }

    /// Propose committing a description edit while description remains authoritative.
    pub fn propose_description_edit(&self, expected_revision: u64) -> AuthorityTransitionOutcome {
        self.propose_description_write(AuthorityAction::CommitDescriptionEdit, expected_revision)
    }

    /// Propose committing visible DDL produced by an explicit Stage 1 regeneration.
    pub fn propose_stage1_result_commit(
        &self,
        expected_revision: u64,
    ) -> AuthorityTransitionOutcome {
        self.propose_description_write(AuthorityAction::CommitStage1Result, expected_revision)
    }

    fn propose_description_write(
        &self,
        action: AuthorityAction,
        expected_revision: u64,
    ) -> AuthorityTransitionOutcome {
        if let Some(conflict) = self.revision_conflict(expected_revision) {
            return conflict;
        }

        match self.authority {
            AuthoringAuthority::DescriptionAuthoritative => self.propose_advance(
                action,
                expected_revision,
                AuthoringAuthority::DescriptionAuthoritative,
            ),
            AuthoringAuthority::DdlAuthoritative => {
                AuthorityTransitionOutcome::forbidden(action, self)
            }
            AuthoringAuthority::LegacyUnknown => {
                AuthorityTransitionOutcome::compatibility_required(action, self)
            }
        }
    }

    fn revision_conflict(&self, expected_revision: u64) -> Option<AuthorityTransitionOutcome> {
        (expected_revision != self.revision).then(|| AuthorityTransitionOutcome {
            protocol_version: self.protocol_version,
            result: AuthorityTransitionResult::Conflict {
                expected_revision,
                actual_revision: self.revision,
            },
        })
    }

    fn propose_advance(
        &self,
        action: AuthorityAction,
        expected_revision: u64,
        next_authority: AuthoringAuthority,
    ) -> AuthorityTransitionOutcome {
        let Some(next_revision) = self.revision.checked_add(1) else {
            return AuthorityTransitionOutcome {
                protocol_version: self.protocol_version,
                result: AuthorityTransitionResult::RevisionExhausted {
                    action,
                    revision: self.revision,
                },
            };
        };

        let next_state = Self {
            protocol_version: self.protocol_version,
            revision: next_revision,
            origin: self.origin,
            authority: next_authority,
        };
        AuthorityTransitionOutcome {
            protocol_version: self.protocol_version,
            result: AuthorityTransitionResult::Proposed {
                proposal: AuthorityTransitionProposal {
                    expected_revision,
                    next_state,
                },
            },
        }
    }
}

impl<'de> Deserialize<'de> for VariationAuthorityState {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let state = UnvalidatedAuthorityState::deserialize(deserializer)?;
        Self::from_loaded(
            state.protocol_version,
            state.revision,
            state.origin,
            state.authority,
        )
        .map_err(de::Error::custom)
    }
}

/// Failure to load an authority sidecar as a valid protocol state.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuthorityStateValidationError {
    IllegalOriginAuthorityPair {
        origin: VariationOrigin,
        authority: AuthoringAuthority,
    },
}

impl fmt::Display for AuthorityStateValidationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::IllegalOriginAuthorityPair { origin, authority } => write!(
                formatter,
                "illegal variation origin/authority pair: {origin:?}/{authority:?}"
            ),
        }
    }
}

impl std::error::Error for AuthorityStateValidationError {}

/// Host action whose authority effect is being evaluated.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuthorityAction {
    CommitUserDdlMutation,
    CommitDescriptionEdit,
    CommitStage1Result,
}

/// A compare-and-set value for the host to persist atomically with its content.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthorityTransitionProposal {
    #[serde(with = "decimal_u64")]
    pub expected_revision: u64,
    pub next_state: VariationAuthorityState,
}

/// Versioned decision returned to Web, server, Android, or a future host.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct AuthorityTransitionOutcome {
    pub protocol_version: AuthorityProtocolVersion,
    #[serde(flatten)]
    pub result: AuthorityTransitionResult,
}

impl AuthorityTransitionOutcome {
    fn no_change(action: AuthorityAction, current_state: VariationAuthorityState) -> Self {
        Self {
            protocol_version: current_state.protocol_version,
            result: AuthorityTransitionResult::NoChange {
                action,
                current_state,
            },
        }
    }

    fn forbidden(action: AuthorityAction, state: &VariationAuthorityState) -> Self {
        Self {
            protocol_version: state.protocol_version,
            result: AuthorityTransitionResult::Forbidden {
                action,
                authority: state.authority,
                revision: state.revision,
            },
        }
    }

    fn compatibility_required(action: AuthorityAction, state: &VariationAuthorityState) -> Self {
        Self {
            protocol_version: state.protocol_version,
            result: AuthorityTransitionResult::CompatibilityRequired {
                action,
                origin: state.origin,
                revision: state.revision,
            },
        }
    }
}

/// Exhaustive transition disposition. Only `Proposed` authorizes a host CAS write.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum AuthorityTransitionResult {
    Proposed {
        proposal: AuthorityTransitionProposal,
    },
    NoChange {
        action: AuthorityAction,
        current_state: VariationAuthorityState,
    },
    Conflict {
        #[serde(with = "decimal_u64")]
        expected_revision: u64,
        #[serde(with = "decimal_u64")]
        actual_revision: u64,
    },
    Forbidden {
        action: AuthorityAction,
        authority: AuthoringAuthority,
        #[serde(with = "decimal_u64")]
        revision: u64,
    },
    CompatibilityRequired {
        action: AuthorityAction,
        origin: VariationOrigin,
        #[serde(with = "decimal_u64")]
        revision: u64,
    },
    RevisionExhausted {
        action: AuthorityAction,
        #[serde(with = "decimal_u64")]
        revision: u64,
    },
}

mod decimal_u64 {
    use super::*;

    pub fn serialize<S>(value: &u64, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        DecimalU64::new(*value).serialize(serializer)
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<u64, D::Error>
    where
        D: Deserializer<'de>,
    {
        DecimalU64::deserialize(deserializer).map(DecimalU64::get)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn first_edit_locks_monotonically_and_legacy_requires_compatibility() {
        let described = VariationAuthorityState::new_description();
        let no_op = described.propose_committed_user_ddl_mutation(0, false);
        assert!(matches!(
            no_op.result,
            AuthorityTransitionResult::NoChange { current_state, .. }
                if current_state == described
        ));

        let first_edit = described.propose_committed_user_ddl_mutation(0, true);
        let AuthorityTransitionResult::Proposed { proposal } = first_edit.result else {
            panic!("first changed edit must propose the DDL lock");
        };
        assert_eq!(proposal.expected_revision, 0);
        assert_eq!(proposal.next_state.revision(), 1);
        assert_eq!(
            proposal.next_state.origin(),
            VariationOrigin::Stage1Generated
        );
        assert_eq!(
            proposal.next_state.authority(),
            AuthoringAuthority::DdlAuthoritative
        );

        let undo = proposal
            .next_state
            .propose_committed_user_ddl_mutation(1, true);
        let AuthorityTransitionResult::Proposed { proposal: undo } = undo.result else {
            panic!("undo is another mutation after the lock was committed");
        };
        assert_eq!(undo.next_state.revision(), 2);
        assert_eq!(
            undo.next_state.authority(),
            AuthoringAuthority::DdlAuthoritative
        );

        let stale = undo.next_state.propose_committed_user_ddl_mutation(1, true);
        assert!(matches!(
            stale.result,
            AuthorityTransitionResult::Conflict {
                expected_revision: 1,
                actual_revision: 2
            }
        ));

        let description = undo.next_state.propose_description_edit(2);
        assert!(matches!(
            description.result,
            AuthorityTransitionResult::Forbidden {
                action: AuthorityAction::CommitDescriptionEdit,
                authority: AuthoringAuthority::DdlAuthoritative,
                revision: 2
            }
        ));

        let legacy = VariationAuthorityState::from_loaded(
            AuthorityProtocolVersion::V1,
            7,
            VariationOrigin::Stage1Generated,
            AuthoringAuthority::LegacyUnknown,
        )
        .expect("legacy_unknown is preserved for an explicit compatibility gate");
        let legacy_write = legacy.propose_stage1_result_commit(7);
        assert!(matches!(
            legacy_write.result,
            AuthorityTransitionResult::CompatibilityRequired {
                action: AuthorityAction::CommitStage1Result,
                origin: VariationOrigin::Stage1Generated,
                revision: 7
            }
        ));

        assert!(matches!(
            VariationAuthorityState::from_loaded(
                AuthorityProtocolVersion::V1,
                0,
                VariationOrigin::UserAuthoredDdl,
                AuthoringAuthority::DescriptionAuthoritative,
            ),
            Err(AuthorityStateValidationError::IllegalOriginAuthorityPair { .. })
        ));
    }
}
