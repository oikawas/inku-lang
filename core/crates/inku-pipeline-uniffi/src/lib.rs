//! UniFFI adapter for the pipeline's owned JSON byte boundary.

use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_pipeline::protocol::{ProtocolError, error_bytes};

mod macro_catalog;

pub use macro_catalog::resolve_macro_catalog;

const BINDING_VERSION: &str = "1.1.0";
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

/// Share the canonical registry with host settings and compatibility adapters.
#[uniffi::export]
pub fn canvas_registry() -> String {
    let bytes = inku_score::canvas_format_registry_canonical_json_bytes()
        .expect("static canvas registry serializes");
    let registry = String::from_utf8(bytes).expect("canonical JSON is UTF-8");
    let digest =
        inku_score::canvas_format_registry_digest().expect("static canvas registry has a digest");
    format!(r#"{{"registry":{registry},"digest":"{digest}"}}"#)
}

/// Project the shared Stage 1 grammar and vocabulary before a host has an authoring input.
#[uniffi::export]
pub fn stage1_system_projection(language_code: String) -> String {
    let language = if language_code == "en" {
        inku_ddl::ResolvedInstructionLanguage::En
    } else {
        inku_ddl::ResolvedInstructionLanguage::Ja
    };
    inku_pipeline::prompts::stage1_system_projection(language)
        .expect("static Stage 1 projection is valid")
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct PaletteInput {
    color_map: std::collections::BTreeMap<String, String>,
    catalog_id: String,
    render_seed: Option<String>,
    background: inku_score::Color,
}

/// Resolve host catalog data through the existing shared palette algorithm.
#[uniffi::export]
pub fn resolve_palette(input_bytes: Vec<u8>) -> Vec<u8> {
    fn resolve(input_bytes: &[u8]) -> Option<Vec<u8>> {
        if input_bytes.len() > 65_536 {
            return None;
        }
        let input: PaletteInput = serde_json::from_slice(input_bytes).ok()?;
        let seed = input
            .render_seed
            .map(|seed| seed.parse::<i128>())
            .transpose()
            .ok()?;
        let palette = inku_render::palette::work_palette_context(
            &input.color_map,
            seed,
            Some(&input.catalog_id),
            input.background,
        )
        .ok()?;
        let dto = |color: inku_score::ResolvedPaletteColor| {
            inku_pipeline::core_boundary::ResolvedPaletteColorDto {
                abstract_color: color.abstract_color(),
                concrete_rgb: color.concrete_rgb(),
                oklch_lightness: color.oklch_lightness(),
            }
        };
        serde_json::to_vec(&inku_pipeline::core_boundary::ResolvedPaletteDto {
            background: dto(palette.background()),
            black: dto(palette.black()),
            white: dto(palette.white()),
            observations: palette.observations().map(|colors| colors.map(dto)),
        })
        .ok()
    }
    catch_unwind(AssertUnwindSafe(|| resolve(&input_bytes)))
        .ok()
        .flatten()
        .unwrap_or_else(|| br#"{"error":"invalid_palette_input"}"#.to_vec())
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SavedRenderInput {
    request: inku_render::types::RenderRequest,
    hard_policy: inku_score::HardResourcePolicy,
    operational_budget: inku_score::OperationalResourceBudget,
    clip: inku_pipeline::core_boundary::ClipPolicy,
}

/// Replay a saved Score using independently authorized host resource limits.
#[uniffi::export]
pub fn render_saved(input_bytes: Vec<u8>) -> Vec<u8> {
    fn render(input_bytes: &[u8]) -> Option<Vec<u8>> {
        if input_bytes.len() > 16 * 1024 * 1024 {
            return None;
        }
        let input: SavedRenderInput = serde_json::from_slice(input_bytes).ok()?;
        let output = inku_pipeline::core_boundary::render_saved_score(
            input.request,
            &input.hard_policy,
            input.operational_budget,
            input.clip,
        )
        .ok()?;
        serde_json::to_vec(&output).ok()
    }
    catch_unwind(AssertUnwindSafe(|| render(&input_bytes)))
        .ok()
        .flatten()
        .unwrap_or_else(|| br#"{"error":"invalid_saved_performance"}"#.to_vec())
}
