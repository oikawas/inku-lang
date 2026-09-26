//! Owned UTF-8 JSON boundary. Binding adapters copy bytes and do not branch on meaning.

use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::machine::{PipelineInput, PipelineSnapshot, advance};
use crate::protocol::{Envelope, PROTOCOL_NAME, PROTOCOL_VERSION, ProtocolError};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EnvelopeLimits {
    pub max_input_bytes: usize,
    pub max_snapshot_bytes: usize,
    pub max_output_bytes: usize,
}

impl EnvelopeLimits {
    pub fn validate(self) -> Result<(), ProtocolError> {
        if self.max_input_bytes == 0 || self.max_snapshot_bytes == 0 || self.max_output_bytes == 0 {
            return Err(ProtocolError::InvalidPolicy);
        }
        Ok(())
    }
}

// These projections skip unrelated fields without allocating their contents.
// The complete input and snapshot are validated by `step` after the size check.
#[derive(Deserialize)]
struct LimitConfig {
    envelope_limits: EnvelopeLimits,
}

#[derive(Deserialize)]
struct LimitStart {
    config: LimitConfig,
}

#[derive(Deserialize)]
struct LimitInput {
    payload: LimitStart,
}

#[derive(Deserialize)]
struct LimitSnapshot {
    config: LimitConfig,
}

/// The two-byte-buffer ABI uses explicit limits in the start configuration and
/// retains them in its snapshot. Hosts must enforce their transport byte cap
/// before allocating an ABI input buffer.
pub fn step_owned(snapshot_bytes: &[u8], input_bytes: &[u8]) -> Vec<u8> {
    let limits = if snapshot_bytes.is_empty() {
        serde_json::from_slice::<LimitInput>(input_bytes)
            .map(|input| input.payload.config.envelope_limits)
    } else {
        serde_json::from_slice::<LimitSnapshot>(snapshot_bytes)
            .map(|snapshot| snapshot.config.envelope_limits)
    };
    match limits {
        Ok(limits) => {
            step(snapshot_bytes, input_bytes, limits).unwrap_or_else(crate::protocol::error_bytes)
        }
        Err(_) => crate::protocol::error_bytes(ProtocolError::MalformedPayload),
    }
}

/// The provider attempt in flight for a stored snapshot, as
/// `{"provider_attempt": {...}}` or `{"provider_attempt": null}`, or
/// `{"error": "invalid_snapshot"}` for a snapshot that `step` would refuse.
pub fn provider_attempt_owned(snapshot_bytes: &[u8]) -> Vec<u8> {
    let attempt = serde_json::from_slice::<LimitSnapshot>(snapshot_bytes)
        .ok()
        .filter(|limits| {
            let limits = limits.config.envelope_limits;
            limits.validate().is_ok() && snapshot_bytes.len() <= limits.max_snapshot_bytes
        })
        .and_then(|_| serde_json::from_slice::<PipelineSnapshot>(snapshot_bytes).ok())
        .and_then(|snapshot| snapshot.provider_attempt().ok());
    match attempt {
        Some(attempt) => serde_json::to_vec(&json!({ "provider_attempt": attempt }))
            .expect("provider attempt serializes"),
        None => br#"{"error":"invalid_snapshot"}"#.to_vec(),
    }
}

/// Empty snapshot bytes create an execution. A start reply assigns the execution
/// identity; subsequent inputs must echo it and advance the returned sequence.
/// The host must serialize calls per execution and store the returned snapshot.
pub fn step(
    snapshot_bytes: &[u8],
    input_bytes: &[u8],
    limits: EnvelopeLimits,
) -> Result<Vec<u8>, ProtocolError> {
    limits.validate()?;
    if input_bytes.len() > limits.max_input_bytes
        || snapshot_bytes.len() > limits.max_snapshot_bytes
    {
        return Err(ProtocolError::SchemaViolation);
    }
    let snapshot = if snapshot_bytes.is_empty() {
        None
    } else {
        Some(
            serde_json::from_slice::<PipelineSnapshot>(snapshot_bytes)
                .map_err(|_| ProtocolError::SchemaViolation)?,
        )
    };
    let mut input: serde_json::Value =
        serde_json::from_slice(input_bytes).map_err(|_| ProtocolError::MalformedPayload)?;
    let payload = input
        .get_mut("payload")
        .and_then(serde_json::Value::as_object_mut)
        .ok_or(ProtocolError::SchemaViolation)?;
    if payload.remove("version") != Some(json!(1)) {
        return Err(ProtocolError::ProtocolMismatch);
    }
    let input: Envelope<PipelineInput> =
        serde_json::from_value(input).map_err(|_| ProtocolError::SchemaViolation)?;
    let message_id = input.message_id.clone();
    let output = advance(snapshot, input)?;
    if serde_json::to_vec(&output.snapshot)
        .map_err(|_| ProtocolError::InternalInvariant)?
        .len()
        > limits.max_snapshot_bytes
    {
        return Err(ProtocolError::SchemaViolation);
    }
    let result = json!({
        "protocol": PROTOCOL_NAME, "version": PROTOCOL_VERSION, "kind": "output",
        "execution_id": output.snapshot.execution_id, "message_id": message_id,
        "sequence": output.snapshot.sequence,
        "payload": { "tag": "step_result", "version": 1, "result": output },
    });
    let bytes = serde_json::to_vec(&result).map_err(|_| ProtocolError::InternalInvariant)?;
    if bytes.len() > limits.max_output_bytes {
        return Err(ProtocolError::SchemaViolation);
    }
    Ok(bytes)
}
