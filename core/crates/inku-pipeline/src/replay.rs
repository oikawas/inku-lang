//! Deterministic replay of commands and final effect results, without host effects.

use crate::machine::{PipelineInput, PipelineSnapshot, StepOutput, advance};
use crate::protocol::{Envelope, ProtocolError};

/// A transcript contains input envelopes, never output-only progress events.
pub fn replay(
    mut snapshot: Option<PipelineSnapshot>,
    inputs: &[Envelope<PipelineInput>],
) -> Result<Vec<StepOutput>, ProtocolError> {
    let mut outputs = Vec::with_capacity(inputs.len());
    for input in inputs {
        let output = advance(snapshot, input.clone())?;
        snapshot = Some(output.snapshot.clone());
        outputs.push(output);
    }
    Ok(outputs)
}
