//! Owned UTF-8 JSON boundary. Binding adapters copy bytes and do not branch on meaning.

use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::machine::{
    PipelineInput, PipelineSnapshot, StepOutput, advance, advance_with_svg_limit,
};
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
    match limits_for(snapshot_bytes, input_bytes) {
        Ok(limits) => {
            step(snapshot_bytes, input_bytes, limits).unwrap_or_else(crate::protocol::error_bytes)
        }
        Err(error) => crate::protocol::error_bytes(error),
    }
}

/// Server-only transport: render SVG bytes do not consume the JSON envelope cap.
/// A refusal returns no SVG; the host validates any returned SVG before saving.
pub fn step_owned_with_svg_limit(
    snapshot_bytes: &[u8],
    input_bytes: &[u8],
    max_svg_bytes: usize,
) -> (Vec<u8>, Option<String>) {
    limits_for(snapshot_bytes, input_bytes)
        .and_then(|limits| step_with_svg_limit(snapshot_bytes, input_bytes, limits, max_svg_bytes))
        .unwrap_or_else(|error| (crate::protocol::error_bytes(error), None))
}

fn limits_for(snapshot_bytes: &[u8], input_bytes: &[u8]) -> Result<EnvelopeLimits, ProtocolError> {
    let limits = if snapshot_bytes.is_empty() {
        serde_json::from_slice::<LimitInput>(input_bytes)
            .map(|input| input.payload.config.envelope_limits)
    } else {
        serde_json::from_slice::<LimitSnapshot>(snapshot_bytes)
            .map(|snapshot| snapshot.config.envelope_limits)
    };
    limits.map_err(|_| ProtocolError::MalformedPayload)
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
    step_impl(snapshot_bytes, input_bytes, limits, None).map(|(bytes, _)| bytes)
}

/// Keep input/snapshot limits and separate only a newly produced render SVG.
pub fn step_with_svg_limit(
    snapshot_bytes: &[u8],
    input_bytes: &[u8],
    limits: EnvelopeLimits,
    max_svg_bytes: usize,
) -> Result<(Vec<u8>, Option<String>), ProtocolError> {
    step_impl(snapshot_bytes, input_bytes, limits, Some(max_svg_bytes))
}

fn step_impl(
    snapshot_bytes: &[u8],
    input_bytes: &[u8],
    limits: EnvelopeLimits,
    max_svg_bytes: Option<usize>,
) -> Result<(Vec<u8>, Option<String>), ProtocolError> {
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
    let output = match max_svg_bytes {
        Some(maximum) => advance_with_svg_limit(snapshot, input, maximum),
        None => advance(snapshot, input),
    }?;
    encode_output(output, message_id, limits, max_svg_bytes.is_some())
}

fn encode_output(
    mut output: StepOutput,
    message_id: String,
    limits: EnvelopeLimits,
    separate_svg: bool,
) -> Result<(Vec<u8>, Option<String>), ProtocolError> {
    if serde_json::to_vec(&output.snapshot)
        .map_err(|_| ProtocolError::InternalInvariant)?
        .len()
        > limits.max_snapshot_bytes
    {
        return Err(ProtocolError::SchemaViolation);
    }
    let svg = if separate_svg {
        output
            .rendered
            .as_mut()
            .map(|rendered| std::mem::take(&mut rendered.svg))
    } else {
        None
    };
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
    Ok((bytes, svg))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn start_input() -> Vec<u8> {
        let mut config = crate::focused_flow::config();
        let definition = json!({
            "schema": "inku.macro-definition.v1", "namespace": "Example", "heading": "Circle",
            "version": "1.0.0", "parameters": {}, "components": {}, "body": [{
                "op": "emit", "binding": null, "fields": {
                    "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                    "color": {"expr": "semantic_ref", "category": "color", "id": "black"},
                    "position_x": {"expr": "exact_decimal", "value": "0.5"},
                    "position_y": {"expr": "exact_decimal", "value": "0.5"},
                    "count": {"expr": "integer", "value": 1}
                }
            }]
        });
        config.definitions =
            vec![inku_ddl::MacroDefinition::from_json(&definition.to_string()).unwrap()];
        config.macro_summaries = vec!["One black circle at the center".into()];
        serde_json::to_vec(&json!({
            "protocol": PROTOCOL_NAME, "version": PROTOCOL_VERSION, "kind": "input",
            "execution_id": "new", "sequence": "0", "message_id": "svg-limit-start",
            "payload": {"tag": "start", "version": 1, "variation_id": "svg-limit",
                "authoring_nonce": "svg-limit-1", "config": config,
                "authority": crate::authority::VariationAuthorityState::new_direct_ddl(),
                "authoring": {"tag": "direct_ddl", "source": "Example.Circle."}},
        }))
        .unwrap()
    }

    fn pending_output(input: &[u8]) -> StepOutput {
        let bytes = step_owned(&[], input);
        let envelope: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(envelope["kind"], "output", "{envelope}");
        serde_json::from_value(envelope["payload"]["result"].clone()).unwrap()
    }

    #[test]
    fn svg_limit_no_render_keeps_the_old_envelope_bytes_and_identity() {
        let input = start_input();
        let old = step_owned(&[], &input);
        let (separated, svg) = step_owned_with_svg_limit(&[], &input, 32 << 20);
        assert_eq!(separated, old);
        assert_eq!(svg, None);
    }

    #[test]
    fn svg_limit_separates_svg_before_the_json_output_budget() {
        let mut output = pending_output(&start_input());
        let score = serde_json::from_str(r#"{"instructions":[]}"#).unwrap();
        let raw = "<svg data-x=\"\\\">\n墨\u{0000}</svg>".repeat(32);
        output.rendered = Some(inku_render::types::RenderOutput {
            svg: raw.clone(),
            metadata: inku_render::render::build_render_metadata(
                &score,
                inku_render::types::SvgProfile::Display,
            ),
        });
        let mut limits = output.snapshot.config.envelope_limits;
        let (full, _) = encode_output(output.clone(), "render".into(), limits, false).unwrap();
        let (separated, svg) =
            encode_output(output.clone(), "render".into(), limits, true).unwrap();
        assert_eq!(svg.as_deref(), Some(raw.as_str()));
        assert!(full.len() > separated.len() + raw.len());
        limits.max_output_bytes = separated.len();
        assert!(matches!(
            encode_output(output.clone(), "render".into(), limits, false),
            Err(ProtocolError::SchemaViolation)
        ));
        let (bounded, svg) = encode_output(output, "render".into(), limits, true).unwrap();
        assert_eq!(bounded, separated);
        let mut restored: serde_json::Value = serde_json::from_slice(&bounded).unwrap();
        restored["payload"]["result"]["rendered"]["svg"] = json!(svg.unwrap());
        assert_eq!(serde_json::to_vec(&restored).unwrap(), full);
    }

    #[test]
    fn svg_limit_transport_keeps_input_snapshot_and_non_svg_caps() {
        let input = start_input();
        let output = pending_output(&input);
        let mut limits = output.snapshot.config.envelope_limits;
        limits.max_input_bytes = input.len() - 1;
        assert!(matches!(
            step_with_svg_limit(&[], &input, limits, 32 << 20),
            Err(ProtocolError::SchemaViolation)
        ));
        limits = output.snapshot.config.envelope_limits;
        limits.max_snapshot_bytes = serde_json::to_vec(&output.snapshot).unwrap().len() - 1;
        assert!(matches!(
            encode_output(output.clone(), "start".into(), limits, true),
            Err(ProtocolError::SchemaViolation)
        ));
        limits = output.snapshot.config.envelope_limits;
        let (bytes, _) = encode_output(output.clone(), "start".into(), limits, true).unwrap();
        limits.max_output_bytes = bytes.len() - 1;
        assert!(matches!(
            encode_output(output, "start".into(), limits, true),
            Err(ProtocolError::SchemaViolation)
        ));
        let (error, svg) = step_owned_with_svg_limit(&[], b"{", 32 << 20);
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&error).unwrap()["kind"],
            "error"
        );
        assert_eq!(svg, None);
    }
}
