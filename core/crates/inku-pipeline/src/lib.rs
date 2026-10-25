//! Shared authoring decisions. Hosts perform network and atomic persistence effects.

#![forbid(unsafe_code)]

pub mod appearance;
pub mod authority;
pub mod autonomous_refine;
pub mod byte_envelope;
pub mod colors;
pub mod completion_ranges;
pub mod composition;
pub mod composition_reading;
pub mod core_boundary;
pub mod ddl3d;
pub mod description_ddl;
mod hole_completion;
pub mod identity;
pub mod image_ddl;
pub mod juxtaposition;
pub mod laws;
pub mod laws_entry;
pub mod laws_record;
pub mod machine;
pub mod prompts;
pub mod protocol;
pub mod provider_wire;
pub mod recompose;
pub mod replay;
pub mod retouch;
pub mod saved_variants;

#[cfg(test)]
mod focused_flow;
