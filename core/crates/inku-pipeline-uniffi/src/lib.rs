//! UniFFI adapter for the pipeline's owned JSON byte boundary.

use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_pipeline::protocol::{ProtocolError, error_bytes};

mod description_labels;
#[cfg(not(target_os = "android"))]
mod description_meter;
#[cfg(feature = "display")]
mod display;
mod macro_catalog;
mod plugin_diagnostics;
mod raster;
mod saijiki_migration;
mod standalone;

pub use description_labels::pipeline_description;
#[cfg(not(target_os = "android"))]
pub use description_meter::count_description_meter;
#[cfg(feature = "display")]
pub use display::{
    DisplayComposite, DisplayFailure, DisplayImage, DisplayLayout, DisplayRect, DisplayRegion,
    DisplayRewrites, DisplayScene, display_api_version, display_detail_region, display_layout,
    display_tiles, prepare_display_scene,
};
pub use macro_catalog::resolve_macro_catalog;
pub use plugin_diagnostics::explain_plugin_diagnostics;
pub use raster::{
    RasterFailure, RasterFrame, RasterScene, prepare_raster_scene, raster_api_version,
    rasterize_svg, rasterize_svg_region,
};
pub use saijiki_migration::migrate_saijiki_v1;
pub use standalone::{compile_document, render_compiled, render_compiled_svg_limited};

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

/// Rust helper for the Server's CPython binding; existing UniFFI/JNI calls stay unchanged.
pub fn step_with_svg_limit(
    snapshot_bytes: Vec<u8>,
    input_envelope_bytes: Vec<u8>,
    max_svg_bytes: usize,
) -> (Vec<u8>, Option<String>) {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::byte_envelope::step_owned_with_svg_limit(
            &snapshot_bytes,
            &input_envelope_bytes,
            max_svg_bytes,
        )
    }))
    .unwrap_or_else(|_| (error_bytes(ProtocolError::InternalInvariant), None))
}

/// Native hosts receive raw SVG independently of bounded metadata JSON.
/// Validate its UTF-8 size before adopting the returned snapshot or result.
#[derive(uniffi::Record)]
pub struct NativeSvgOutput {
    pub json_bytes: Vec<u8>,
    pub svg: Option<String>,
}

impl From<(Vec<u8>, Option<String>)> for NativeSvgOutput {
    fn from((json_bytes, svg): (Vec<u8>, Option<String>)) -> Self {
        Self { json_bytes, svg }
    }
}

pub(crate) fn native_svg_limit(max_svg_bytes: u64) -> Result<usize, NativeSvgOutput> {
    // A host uses its 1–32 MiB generation setting, or the separate consumer
    // envelope when recreating a stored work's export profile.
    if max_svg_bytes == 0 || max_svg_bytes > inku_svg_raster::MAX_SVG_BYTES as u64 {
        return Err(NativeSvgOutput {
            json_bytes: saved_render_refusal("invalid_svg_limit", "invalid SVG byte allowance"),
            svg: None,
        });
    }
    Ok(max_svg_bytes as usize)
}

/// Advance without escaping the SVG into the output JSON envelope.
#[uniffi::export]
pub fn step_svg_limited(
    snapshot_bytes: Vec<u8>,
    input_envelope_bytes: Vec<u8>,
    max_svg_bytes: u64,
) -> NativeSvgOutput {
    match native_svg_limit(max_svg_bytes) {
        Ok(limit) => step_with_svg_limit(snapshot_bytes, input_envelope_bytes, limit).into(),
        Err(refusal) => refusal,
    }
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

/// Another touch written into a work's visible instructions (the author,
/// 2026-10-14): the request names the pipeline configuration, the source and the
/// tool asked for each sentence by its instruction index. The answer carries the
/// schema `inku.touch-change.v1`, the sentences whose tool can change, the tools,
/// and the rewritten source or the reason the work stays as it is; an unreadable
/// request is `{"error": "invalid_request"}` and a panic
/// `{"error": "internal_invariant"}`. The binding version is unchanged: this only
/// adds a call.
#[uniffi::export]
pub fn retouch(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::retouch::retouch_json(&input_bytes)
    }))
    .unwrap_or_else(|_| br#"{"error":"internal_invariant"}"#.to_vec())
}

/// The states of a work's completion ranges for the instruction editors (A3):
/// the request names the pipeline configuration, the editor's source and the
/// work's record (`completion_ranges`, schema `inku.completion-ranges.v1`). The
/// answer carries the schema `inku.completion-range-states.v1` and, for each
/// range the record knows, its place in UTF-8 and UTF-16 offsets and its state
/// (`completed`, `numbers_changed` or `words_changed`); an unreadable request is
/// `{"error": "invalid_request"}` and a panic `{"error": "internal_invariant"}`.
/// The binding version is unchanged: this only adds a call.
#[uniffi::export]
pub fn completion_range_states(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::completion_ranges::completion_range_states_json(&input_bytes)
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

/// The refinements that change one part of a saved Score (touches, support,
/// color arrangement): one JSON request with an `action`, one JSON answer
/// (`inku.saved-variants.v1`). A panic answers `{"error": "internal_invariant"}`.
#[uniffi::export]
pub fn saved_variants(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::saved_variants::saved_variants_json(&input_bytes)
    }))
    .unwrap_or_else(|_| br#"{"error":"internal_invariant"}"#.to_vec())
}

/// A provider request's bytes and what its answer says: one JSON request with
/// an `action` (`pipeline_request`, `pipeline_response`, `text_request`,
/// `text_response`), one JSON answer (`inku.provider-wire.v1`). The host adds
/// the key under the header the answer names, sends, and passes the status and
/// body back. A panic answers `{"error": "internal_invariant"}`.
#[uniffi::export]
pub fn provider_wire(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::provider_wire::provider_wire_json(&input_bytes)
    }))
    .unwrap_or_else(|_| br#"{"error":"internal_invariant"}"#.to_vec())
}

/// The experimental 3D viewer's input (`inku.ddl3d.v1`, Web `snapshot()`):
/// `{"score": "<stored Score text>", "metadata": "<stored render metadata
/// text>"}` in, `{"json": "<input>"}` or `{"error": "<reason>"}` out. A panic
/// answers `{"error": "internal_invariant"}`.
#[uniffi::export]
pub fn ddl3d_snapshot(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_pipeline::ddl3d::snapshot_json(&input_bytes)
    }))
    .unwrap_or_else(|_| br#"{"error":"internal_invariant"}"#.to_vec())
}

/// A description's identity `dh1`, as Server's `identity.description_hash`
/// computes it. Every host asks this one copy so stored identities agree.
#[uniffi::export]
pub fn description_hash(text: String) -> String {
    inku_pipeline::identity::description_hash(&text)
}

/// A history item's render identity `rh3`, or `None` when the item is not a
/// JSON object Python's `json.loads` would read.
#[uniffi::export]
pub fn render_hash(item_json: String) -> Option<String> {
    inku_pipeline::identity::render_hash(&item_json).ok()
}

/// The canonical JSON Server hashes (`json.dumps(sort_keys=True,
/// separators=(",", ":"), ensure_ascii=False)`), or `None` for invalid JSON.
#[uniffi::export]
pub fn canonical_json(value_json: String) -> Option<String> {
    inku_pipeline::identity::canonical_json(&value_json).ok()
}

/// The instruction language (`"ja"` or `"en"`) for `text`, or `None` when the
/// request or the fallback is not a supported code.
#[uniffi::export]
pub fn resolve_instruction_language(
    text: String,
    requested: Option<String>,
    fallback: String,
) -> Option<String> {
    inku_ddl::resolve_instruction_language(&text, requested.as_deref(), &fallback)
        .ok()
        .map(|language| language.as_str().to_owned())
}

/// A requested language code (`"auto"`, `"ja"` or `"en"`) normalized as
/// Python's `(value or default).strip().lower()`, or `None` when unsupported.
#[uniffi::export]
pub fn normalize_instruction_language(
    value: Option<String>,
    default_language: String,
) -> Option<String> {
    inku_ddl::normalize_instruction_language(value.as_deref(), &default_language)
        .ok()
        .map(|language| language.as_str().to_owned())
}

/// The description with its labels removed, as every layer reads it.
#[uniffi::export]
pub fn description_without_labels(text: String) -> String {
    description_labels::pipeline_description(&text)
}

/// The labels' ranges as `[[start, end, kind], ...]` JSON, in Unicode scalar offsets.
#[uniffi::export]
pub fn description_label_spans(text: String) -> String {
    description_labels::description_label_spans(&text)
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

const MAX_SAVED_RENDER_INPUT_BYTES: usize = 16 * 1024 * 1024;
// Only the added Server transport caps metadata JSON; the old ABI is unchanged.
const MAX_SAVED_RENDER_METADATA_BYTES: usize = 64 * 1024 * 1024;

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
        if input_bytes.len() > MAX_SAVED_RENDER_INPUT_BYTES {
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

fn saved_render_refusal(code: &str, message: &str) -> Vec<u8> {
    serde_json::to_vec(&serde_json::json!({ "error": code, "message": message }))
        .expect("two strings serialize")
}

fn separated_saved_output(
    mut output: inku_render::types::RenderOutput,
    max_metadata_bytes: usize,
) -> (Vec<u8>, Option<String>) {
    let svg = std::mem::take(&mut output.svg);
    match serde_json::to_vec(&output) {
        Ok(bytes) if bytes.len() <= max_metadata_bytes => (bytes, Some(svg)),
        Ok(_) => (
            saved_render_refusal(
                "invalid_saved_performance",
                "render metadata exceeds its byte limit",
            ),
            None,
        ),
        Err(error) => (
            saved_render_refusal("invalid_saved_performance", &error.to_string()),
            None,
        ),
    }
}

/// Server replay transport keeps raw SVG outside bounded non-SVG JSON.
/// The runtime value raises only intermediate allowance; the host checks final bytes.
pub fn render_saved_with_svg_limit(
    input_bytes: Vec<u8>,
    max_svg_bytes: usize,
) -> (Vec<u8>, Option<String>) {
    catch_unwind(AssertUnwindSafe(|| {
        if input_bytes.len() > MAX_SAVED_RENDER_INPUT_BYTES {
            return (
                saved_render_refusal("invalid_saved_performance", "input is larger than 16 MiB"),
                None,
            );
        }
        let input: SavedRenderInput = match serde_json::from_slice(&input_bytes) {
            Ok(input) => input,
            Err(error) => {
                return (
                    saved_render_refusal("invalid_saved_performance", &error.to_string()),
                    None,
                );
            }
        };
        match inku_pipeline::core_boundary::render_saved_score_with_svg_limit(
            input.request,
            &input.hard_policy,
            input.operational_budget,
            input.clip,
            max_svg_bytes,
        ) {
            Ok(output) => separated_saved_output(output, MAX_SAVED_RENDER_METADATA_BYTES),
            Err(error) => (
                saved_render_refusal(saved_render_error_code(&error), &error.to_string()),
                None,
            ),
        }
    }))
    .unwrap_or_else(|_| {
        (
            saved_render_refusal("internal_invariant", "the core panicked"),
            None,
        )
    })
}

/// Replay through the same separated transport used by native pipeline steps.
#[uniffi::export]
pub fn render_saved_svg_limited(input_bytes: Vec<u8>, max_svg_bytes: u64) -> NativeSvgOutput {
    match native_svg_limit(max_svg_bytes) {
        Ok(limit) => render_saved_with_svg_limit(input_bytes, limit).into(),
        Err(refusal) => refusal,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn small_saved_input() -> Vec<u8> {
        let budget = inku_score::ResourceBudget {
            maximum: inku_score::ResourceDemand {
                primitive_marks: 400,
                object_templates: 64,
                ..inku_score::ResourceDemand::default()
            },
        };
        serde_json::to_vec(&serde_json::json!({
            "request": {
                "score": {"version": "0.12.0", "instructions": [{"primitive": "circle",
                    "center": [0.5, 0.5], "radius": 0.05}]},
                "options": {"resolved_color_map": {}, "catalog_id": null,
                    "canvas": {"width": 1000.0, "height": 1000.0},
                    "canvas_aspect_id": "square", "svg_profile": "display",
                    "render_seed": 7, "composition_seed": null, "wild": false},
            },
            "hard_policy": inku_score::HardResourcePolicy { identity: "test".to_owned(), budget },
            "operational_budget": inku_score::OperationalResourceBudget(budget),
            "clip": {"tolerance_pixels": 0.1, "max_nodes": "1000", "max_path_elements": "1000",
                "max_flattened_points": "1000", "max_work": "1000", "max_output_vertices": "1000"},
        }))
        .unwrap()
    }

    #[test]
    fn svg_limit_saved_transport_keeps_old_svg_and_metadata() {
        let input = small_saved_input();
        let old = render_saved(input.clone());
        let old_value: serde_json::Value = serde_json::from_slice(&old).unwrap();
        assert!(old_value.get("error").is_none(), "{old_value}");
        let NativeSvgOutput {
            json_bytes: bytes,
            svg,
        } = render_saved_svg_limited(input, 32 << 20);
        let mut separated: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(separated["svg"], "");
        assert_eq!(svg.as_deref(), old_value["svg"].as_str());
        separated["svg"] = serde_json::json!(svg.unwrap());
        assert_eq!(separated, old_value);
    }

    #[test]
    fn svg_limit_native_entries_reject_unbounded_allowances_without_svg() {
        for limit in [0, inku_svg_raster::MAX_SVG_BYTES as u64 + 1, u64::MAX] {
            let outputs = [
                step_svg_limited(vec![], vec![], limit),
                render_saved_svg_limited(vec![], limit),
                render_compiled_svg_limited(vec![], limit),
            ];
            for output in outputs {
                assert!(output.svg.is_none());
                let value: serde_json::Value = serde_json::from_slice(&output.json_bytes).unwrap();
                assert_eq!(value["error"], "invalid_svg_limit");
            }
        }
        let output = render_compiled_svg_limited(b"{".to_vec(), 32 << 20);
        assert!(output.svg.is_none());
        let value: serde_json::Value = serde_json::from_slice(&output.json_bytes).unwrap();
        assert_eq!(value["error"], "invalid_render_input");
    }

    #[test]
    fn svg_limit_saved_metadata_cap_excludes_svg_and_still_refuses_metadata() {
        let old = render_saved(small_saved_input());
        let mut output: inku_render::types::RenderOutput = serde_json::from_slice(&old).unwrap();
        let raw = "<svg data-x=\"\\\">\n墨\u{0000}</svg>".repeat(32);
        output.svg = raw.clone();
        let (bytes, svg) = separated_saved_output(output.clone(), MAX_SAVED_RENDER_METADATA_BYTES);
        assert_eq!(svg.as_deref(), Some(raw.as_str()));
        assert!(serde_json::to_vec(&output).unwrap().len() > bytes.len() + raw.len());
        assert_eq!(
            separated_saved_output(output.clone(), bytes.len()).1,
            Some(raw)
        );
        let (error, svg) = separated_saved_output(output, bytes.len() - 1);
        assert_eq!(svg, None);
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&error).unwrap()["error"],
            "invalid_saved_performance"
        );
        let (error, svg) = render_saved_with_svg_limit(b"{".to_vec(), 32 << 20);
        assert_eq!(svg, None);
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&error).unwrap()["error"],
            "invalid_saved_performance"
        );
    }

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
