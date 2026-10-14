//! Shared authoring decisions. Hosts perform network and atomic persistence effects.

#![forbid(unsafe_code)]

pub mod authority;
pub mod byte_envelope;
pub mod completion_ranges;
pub mod composition;
pub mod composition_reading;
pub mod core_boundary;
mod hole_completion;
pub mod machine;
pub mod prompts;
pub mod protocol;
pub mod recompose;
pub mod replay;
pub mod retouch;

#[cfg(test)]
mod focused_flow;
