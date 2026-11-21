//! Shared authoring decisions. Hosts perform network and atomic persistence effects.

#![forbid(unsafe_code)]

pub mod appearance;
pub mod authority;
pub mod byte_envelope;
pub mod catalog_reading;
mod catalog_reading_text;
pub mod chunk_moves;
pub mod colors;
pub mod completion_ranges;
pub mod composition;
pub mod composition_names;
pub mod composition_reading;
pub mod composition_rules;
pub mod composition_theses;
pub mod core_boundary;
pub mod ddl3d;
pub mod description_colors;
pub mod description_composition;
pub mod description_ddl;
pub mod description_laws;
pub mod draw_options;
mod hole_completion;
pub mod identity;
pub mod image_ddl;
pub mod laws;
pub mod laws_record;
pub mod machine;
pub mod model_catalog;
pub mod plugin_offer;
pub mod prompts;
pub mod protocol;
pub mod provider_admission;
mod provider_url;
pub mod provider_wire;
pub mod recompose;
pub mod replay;
pub mod retouch;
pub mod saved_variants;
pub mod workpack;

#[cfg(test)]
mod composition_server_cases;
#[cfg(test)]
mod focused_flow;
#[cfg(test)]
mod object_word_tests;
