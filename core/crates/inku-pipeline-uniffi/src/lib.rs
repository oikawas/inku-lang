//! UniFFI adapter for the pipeline's owned JSON byte boundary.

use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_pipeline::protocol::{ProtocolError, error_bytes};

#[cfg(not(target_os = "android"))]
mod description_meter;
mod macro_catalog;
mod plugin_diagnostics;
mod raster;
mod saijiki_migration;
mod standalone;

#[cfg(not(target_os = "android"))]
pub use description_meter::count_description_meter;
pub use macro_catalog::resolve_macro_catalog;
pub use plugin_diagnostics::explain_plugin_diagnostics;
pub use raster::{
    RasterFailure, RasterFrame, RasterScene, prepare_raster_scene, raster_api_version,
    rasterize_svg, rasterize_svg_region,
};
pub use saijiki_migration::migrate_saijiki_v1;
pub use standalone::{compile_document, render_compiled};

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

/// Report the provider attempt in flight for a stored snapshot, so a host can
/// show retry progress. The binding version is unchanged: this only adds a call.
#[uniffi::export]
pub fn provider_attempt(snapshot_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::byte_envelope::provider_attempt_owned(&snapshot_bytes)
    }))
    .unwrap_or_else(|_| br#"{"error":"invalid_snapshot"}"#.to_vec())
}

/// Another composition read from a work's visible instructions (draw-system05):
/// the request names the pipeline configuration, the source, the mode
/// (`principled` or `chance`), the seed and the work. The answer carries the
/// schema `inku.composition-recompose.v1` and either the recomposed source with
/// the moves or the reason the work stays as it is; an unreadable request is
/// `{"error": "invalid_request"}` and a panic `{"error": "internal_invariant"}`.
/// The binding version is unchanged: this only adds a call.
#[uniffi::export]
pub fn recompose(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::recompose::recompose_json(&input_bytes)
    }))
    .unwrap_or_else(|_| br#"{"error":"internal_invariant"}"#.to_vec())
}

/// The ranges the composition writes by name (schema `inku.composition-ranges.v1`):
/// the hosts fold a written range whose words and numbers are one of them, and
/// rename numbers the author edits. The binding version is unchanged: this only
/// adds a call.
#[uniffi::export]
pub fn composition_ranges() -> String {
    inku_pipeline::recompose::composition_ranges_json()
}

/// Report the fixed binding and byte-protocol versions as stable JSON.
#[uniffi::export]
pub fn version_report() -> String {
    format!(r#"{{"binding_version":"{BINDING_VERSION}","protocol_version":"{PROTOCOL_VERSION}"}}"#)
}

/// Exact word-touch identity, carried as decimal text across every host boundary.
#[derive(uniffi::Record)]
pub struct TextRenderSeed {
    pub render_seed: String,
    pub seed_text: String,
}

/// Derive a saved-Score performance seed without interpreting the words as DDL.
#[uniffi::export]
pub fn render_seed_from_text(seed_text: String) -> Option<TextRenderSeed> {
    inku_render::determinism::render_seed_from_text(&seed_text).map(|(seed, normalized)| {
        TextRenderSeed {
            render_seed: seed.to_string(),
            seed_text: normalized.to_owned(),
        }
    })
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

/// The stable code a host receives when the core does not draw a saved Score.
///
/// `invalid_saved_performance` stays the code for input the core cannot read
/// or authorize, so hosts that knew only that code keep working.
fn saved_render_error_code(error: &inku_pipeline::core_boundary::BoundaryError) -> &'static str {
    use inku_pipeline::core_boundary::BoundaryError;
    use inku_render::render::RenderError;
    let BoundaryError::Render(error) = error else {
        return "invalid_saved_performance";
    };
    match error {
        RenderError::ResourceAuthority(_) => "resource_authority",
        RenderError::CheckedPerformance(_) => "performance_stopped",
        RenderError::Mark(_) | RenderError::InvalidCanvas | RenderError::InvalidScore(_) => {
            "invalid_score"
        }
        RenderError::MarkTooLarge { .. } => "mark_too_large",
        RenderError::OutputTooLarge { .. } => "output_too_large",
        RenderError::NonFiniteSvg { .. } => "non_finite_value",
    }
}

/// Replay a saved Score using independently authorized host resource limits.
///
/// A refusal is `{"error": code, "message": reason}`: the code is stable, and
/// the message is the core's own reason, for logs. A panic becomes
/// `internal_invariant`. The binding version is unchanged: this only adds codes.
#[uniffi::export]
pub fn render_saved(input_bytes: Vec<u8>) -> Vec<u8> {
    fn refusal(code: &str, message: &str) -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({ "error": code, "message": message }))
            .expect("two strings serialize")
    }
    fn render(input_bytes: &[u8]) -> Vec<u8> {
        if input_bytes.len() > 16 * 1024 * 1024 {
            return refusal("invalid_saved_performance", "input is larger than 16 MiB");
        }
        let input: SavedRenderInput = match serde_json::from_slice(input_bytes) {
            Ok(input) => input,
            Err(error) => return refusal("invalid_saved_performance", &error.to_string()),
        };
        match inku_pipeline::core_boundary::render_saved_score(
            input.request,
            &input.hard_policy,
            input.operational_budget,
            input.clip,
        ) {
            Ok(output) => serde_json::to_vec(&output)
                .unwrap_or_else(|error| refusal("invalid_saved_performance", &error.to_string())),
            Err(error) => refusal(saved_render_error_code(&error), &error.to_string()),
        }
    }
    catch_unwind(AssertUnwindSafe(|| render(&input_bytes)))
        .unwrap_or_else(|_| refusal("internal_invariant", "the core panicked"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_saved_render_refusal_names_its_reason() {
        // One code for every refusal left the host unable to tell a mark too
        // large from a budget exceeded or unreadable input.
        let budget = inku_score::ResourceBudget {
            maximum: inku_score::ResourceDemand {
                primitive_marks: 400,
                object_templates: 64,
                ..inku_score::ResourceDemand::default()
            },
        };
        let input = serde_json::json!({
            "request": {
                "score": {"version": "0.12.0", "instructions": [{"primitive": "circle",
                    "center": [0.5, 0.5], "radius": 10, "surface": {"texture": "wash"}}]},
                "options": {"resolved_color_map": {}, "catalog_id": null,
                    "canvas": {"width": 1000.0, "height": 1000.0},
                    "canvas_aspect_id": "square", "svg_profile": "display",
                    "render_seed": 7, "composition_seed": null, "wild": false},
            },
            "hard_policy": inku_score::HardResourcePolicy { identity: "test".to_owned(), budget },
            "operational_budget": inku_score::OperationalResourceBudget(budget),
            "clip": {"tolerance_pixels": 0.1, "max_nodes": "1000", "max_path_elements": "1000",
                "max_flattened_points": "1000", "max_work": "1000", "max_output_vertices": "1000"},
        });
        let refusal = |bytes: Vec<u8>| {
            let value: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
            value["error"].as_str().unwrap_or("drawn").to_owned()
        };
        assert_eq!(
            refusal(render_saved(serde_json::to_vec(&input).unwrap())),
            "mark_too_large"
        );
        assert_eq!(
            refusal(render_saved(b"{".to_vec())),
            "invalid_saved_performance"
        );
    }
}
