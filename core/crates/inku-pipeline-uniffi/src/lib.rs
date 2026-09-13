//! UniFFI adapter for the pipeline's owned JSON byte boundary.

use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_pipeline::protocol::{ProtocolError, error_bytes};

const BINDING_VERSION: &str = "1.0.0";
const PROTOCOL_VERSION: &str = "1.0.0";

uniffi::setup_scaffolding!();

/// Advance one pipeline execution using only owned byte envelopes.
#[uniffi::export]
pub fn step(snapshot_bytes: Vec<u8>, input_envelope_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::byte_envelope::step_owned(&snapshot_bytes, &input_envelope_bytes)
    }))
    .unwrap_or_else(|_| error_bytes(ProtocolError::InternalInvariant))
}

/// Report the fixed binding and byte-protocol versions as stable JSON.
#[uniffi::export]
pub fn version_report() -> String {
    format!(r#"{{"binding_version":"{BINDING_VERSION}","protocol_version":"{PROTOCOL_VERSION}"}}"#)
}
