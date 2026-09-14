//! Versioned effect envelopes, exact integers, and deterministic retry decisions.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const PROTOCOL_NAME: &str = "inku.pipeline";
pub const PROTOCOL_VERSION: &str = "1.0.0";

/// Language boundaries never round a seed, revision, or ordinal through a float.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct DecimalU64(u64);

impl DecimalU64 {
    pub const fn new(value: u64) -> Self {
        Self(value)
    }

    pub const fn get(self) -> u64 {
        self.0
    }

    pub fn checked_next(self) -> Result<Self, ProtocolError> {
        self.0
            .checked_add(1)
            .map(Self)
            .ok_or(ProtocolError::SequenceExhausted)
    }
}

impl From<DecimalU64> for String {
    fn from(value: DecimalU64) -> Self {
        value.0.to_string()
    }
}

impl TryFrom<String> for DecimalU64 {
    type Error = &'static str;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.is_empty()
            || !value.bytes().all(|byte| byte.is_ascii_digit())
            || (value.len() > 1 && value.starts_with('0'))
        {
            return Err("expected canonical unsigned decimal string");
        }
        value
            .parse::<u64>()
            .map(Self)
            .map_err(|_| "unsigned decimal overflow")
    }
}

/// Hash boundaries are explicit even when fields contain punctuation or NUL.
pub fn digest(domain: &str, fields: &[&[u8]]) -> String {
    let mut hash = Sha256::new();
    hash.update(domain.as_bytes());
    for field in fields {
        hash.update((field.len() as u64).to_be_bytes());
        hash.update(field);
    }
    hash.finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn value_digest<T: Serialize>(domain: &str, value: &T) -> Result<String, ProtocolError> {
    let bytes = serde_json::to_vec(value).map_err(|_| ProtocolError::SchemaViolation)?;
    Ok(digest(domain, &[&bytes]))
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope<T> {
    pub protocol: String,
    pub version: String,
    pub kind: String,
    pub execution_id: String,
    pub message_id: String,
    pub sequence: DecimalU64,
    pub payload: T,
}

impl<T> Envelope<T> {
    pub fn validate(&self, kind: &str) -> Result<(), ProtocolError> {
        if self.protocol != PROTOCOL_NAME || self.version != PROTOCOL_VERSION || self.kind != kind {
            return Err(ProtocolError::ProtocolMismatch);
        }
        if self.execution_id.is_empty() || self.message_id.is_empty() {
            return Err(ProtocolError::SchemaViolation);
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProtocolError {
    ProtocolMismatch,
    SchemaViolation,
    MalformedPayload,
    SemanticViolation,
    StaleResult,
    SequenceExhausted,
    InvalidState,
    InvalidPolicy,
    AuthorityConflict,
    DescriptionLocked,
    CompatibilityRequired,
    HostCommitFailed,
    Cancelled,
    InternalInvariant,
}

/// Stable pipeline failures are values, including at the generated-binding boundary.
pub fn error_bytes(error: ProtocolError) -> Vec<u8> {
    serde_json::to_vec(&serde_json::json!({
        "protocol": PROTOCOL_NAME, "version": PROTOCOL_VERSION, "kind": "error",
        "execution_id": null, "message_id": null, "sequence": null,
        "payload": { "tag": "error", "version": 1, "code": error },
    }))
    .expect("closed error enum and literal envelope serialize")
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderFailure {
    TransportUnavailable,
    TransportTimeout,
    RateLimited,
    ProviderRejected,
    MalformedPayload,
    SchemaViolation,
    SemanticViolation,
}

/// Values are caller-authorized. This crate supplies no shipping timeout/retry default.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetryPolicy {
    pub max_attempts: u32,
    pub attempt_timeout_ms: DecimalU64,
    pub total_timeout_ms: DecimalU64,
    pub retry_delay_ms: DecimalU64,
}

impl RetryPolicy {
    pub fn validate(self) -> Result<(), ProtocolError> {
        if self.max_attempts == 0
            || self.attempt_timeout_ms.get() == 0
            || self.total_timeout_ms.get() == 0
        {
            return Err(ProtocolError::InvalidPolicy);
        }
        Ok(())
    }

    pub fn next_attempt(
        self,
        attempt: u32,
        elapsed_ms: u64,
        failure: ProviderFailure,
    ) -> Option<u32> {
        if matches!(
            failure,
            ProviderFailure::ProviderRejected | ProviderFailure::SemanticViolation
        ) {
            return None;
        }
        self.next_budgeted_attempt(attempt, elapsed_ms)
    }

    pub(crate) fn next_budgeted_attempt(self, attempt: u32, elapsed_ms: u64) -> Option<u32> {
        if attempt >= self.max_attempts
            || elapsed_ms.checked_add(self.retry_delay_ms.get())? >= self.total_timeout_ms.get()
        {
            return None;
        }
        attempt.checked_add(1)
    }

    pub fn remaining_attempt_timeout(self, elapsed_ms: u64) -> u64 {
        self.attempt_timeout_ms
            .get()
            .min(self.total_timeout_ms.get().saturating_sub(elapsed_ms))
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ActionEcho {
    pub action_id: String,
    pub attempt: u32,
    pub request_digest: String,
}

/// One logical action keeps its ID through retries; only its attempt advances.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EffectAction {
    pub tag: String,
    pub version: u32,
    pub identity: ActionEcho,
    pub timeout_ms: DecimalU64,
    pub delay_ms: DecimalU64,
    pub payload: serde_json::Value,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "tag", rename_all = "snake_case", deny_unknown_fields)]
pub enum EffectResult {
    DescriptionCatalogSelected {
        identity: ActionEcho,
        response: String,
        elapsed_ms: DecimalU64,
    },
    NormalizedDdlGenerated {
        identity: ActionEcho,
        response: String,
        elapsed_ms: DecimalU64,
    },
    VisibleDdlHolePatchGenerated {
        identity: ActionEcho,
        response: String,
        elapsed_ms: DecimalU64,
    },
    ProviderFailed {
        identity: ActionEcho,
        failure: ProviderFailure,
        elapsed_ms: DecimalU64,
    },
    VisibleNormalizedDdlCommitted {
        identity: ActionEcho,
        ddl_digest: String,
        revision: DecimalU64,
        authority_digest: String,
    },
    HostCommitFailed {
        identity: ActionEcho,
        actual_revision: Option<DecimalU64>,
    },
}

impl EffectResult {
    pub fn identity(&self) -> &ActionEcho {
        match self {
            Self::DescriptionCatalogSelected { identity, .. }
            | Self::NormalizedDdlGenerated { identity, .. }
            | Self::VisibleDdlHolePatchGenerated { identity, .. }
            | Self::ProviderFailed { identity, .. }
            | Self::VisibleNormalizedDdlCommitted { identity, .. }
            | Self::HostCommitFailed { identity, .. } => identity,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PipelineEvent {
    pub tag: String,
    pub version: u32,
    pub sequence: DecimalU64,
    pub payload: serde_json::Value,
}
