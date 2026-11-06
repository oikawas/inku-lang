//! Thin CPython binding for the platform-independent render core.
//!
//! Every call that renders, compiles or advances the pipeline detaches from
//! the interpreter while Rust works. The server runs these calls on worker
//! threads; holding the GIL there stopped every other Python thread, including
//! the one serving HTTP, for the whole render. Shared font databases are
//! immutable after loading and their cache is synchronized across threads.

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use serde::Deserialize;

fn catch_python_panic<T>(action: impl FnOnce() -> PyResult<T>) -> PyResult<T> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(action)).unwrap_or_else(|_| {
        Err(PyRuntimeError::new_err(
            "native Rust panic at Python boundary",
        ))
    })
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RenderResources {
    hard_policy: inku_score::HardResourcePolicy,
    operational_budget: inku_score::OperationalResourceBudget,
    clip_policy: ClipPolicy,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ClipPolicy {
    tolerance_pixels: f64,
    max_nodes: usize,
    max_path_elements: usize,
    max_flattened_points: usize,
    max_work: usize,
    max_output_vertices: usize,
}

impl ClipPolicy {
    fn resolve(self) -> PyResult<inku_render::render::CompatFillClipPolicy> {
        if !self.tolerance_pixels.is_finite() || self.tolerance_pixels <= 0.0 {
            return Err(PyValueError::new_err(
                "invalid render resources: clip_policy tolerance_pixels must be finite and positive",
            ));
        }
        Ok(inku_render::render::CompatFillClipPolicy {
            tolerance_pixels: self.tolerance_pixels,
            limits: inku_render::compat_clip::ClipLimits {
                max_nodes: self.max_nodes,
                max_path_elements: self.max_path_elements,
                max_flattened_points: self.max_flattened_points,
                max_work: self.max_work,
                max_output_vertices: self.max_output_vertices,
            },
        })
    }
}

#[pyfunction]
fn score_version() -> PyResult<&'static str> {
    catch_python_panic(|| Ok(inku_score::ScoreEdition::LATEST.as_str()))
}

#[pyfunction]
fn render_engine_id() -> PyResult<&'static str> {
    catch_python_panic(|| Ok(inku_render::render_engine_identity().0))
}

#[pyfunction]
fn render_engine_version() -> PyResult<&'static str> {
    catch_python_panic(|| Ok(inku_render::render_engine_identity().1))
}

#[pyfunction]
fn default_color_map_json() -> PyResult<String> {
    catch_python_panic(|| {
        serde_json::to_string(&inku_render::palette::default_color_map()).map_err(|error| {
            PyValueError::new_err(format!("default color map serialization failed: {error}"))
        })
    })
}

#[pyfunction]
fn renderer_reference_json() -> PyResult<String> {
    catch_python_panic(|| {
        serde_json::to_string(&inku_render::reference::renderer_reference()).map_err(|error| {
            PyValueError::new_err(format!("renderer reference serialization failed: {error}"))
        })
    })
}

/// Derive word-touch seed text through the same portable boundary as Apple.
#[pyfunction]
fn render_seed_from_text(py: Python<'_>, seed_text: String) -> PyResult<Option<(String, String)>> {
    catch_python_panic(|| {
        Ok({
            py.detach(|| {
                inku_pipeline_uniffi::render_seed_from_text(seed_text)
                    .map(|derived| (derived.render_seed, derived.seed_text))
            })
        })
    })
}

/// Render one canonical coarse request and return SVG plus JSON metadata.
#[pyfunction]
fn render(py: Python<'_>, request_json: &str) -> PyResult<(String, String)> {
    catch_python_panic(|| {
        py.detach(|| {
            let request = serde_json::from_str(request_json).map_err(|error| {
                PyValueError::new_err(format!("invalid render request: {error}"))
            })?;
            let output = inku_render::render::render(request)
                .map_err(|error| PyValueError::new_err(format!("render failed: {error}")))?;
            let metadata = serde_json::to_string(&output.metadata).map_err(|error| {
                PyValueError::new_err(format!("metadata serialization failed: {error}"))
            })?;
            Ok((output.svg, metadata))
        })
    })
}

/// Server-only allowance; final SVG byte acceptance belongs to the host validator.
#[pyfunction]
fn render_with_svg_limit(
    py: Python<'_>,
    request_json: &str,
    max_svg_bytes: usize,
) -> PyResult<(String, String)> {
    catch_python_panic(|| {
        py.detach(|| {
            let request = serde_json::from_str(request_json).map_err(|error| {
                PyValueError::new_err(format!("invalid render request: {error}"))
            })?;
            let output = inku_render::render::render_with_svg_limit(request, max_svg_bytes)
                .map_err(|error| PyValueError::new_err(format!("render failed: {error}")))?;
            let metadata = serde_json::to_string(&output.metadata).map_err(|error| {
                PyValueError::new_err(format!("metadata serialization failed: {error}"))
            })?;
            Ok((output.svg, metadata))
        })
    })
}

/// Render one canonical coarse request under independent caller-owned resource authority.
#[pyfunction]
fn render_with_resources(
    py: Python<'_>,
    request_json: &str,
    resources_json: &str,
) -> PyResult<(String, String)> {
    catch_python_panic(|| {
        py.detach(|| {
            let request = serde_json::from_str(request_json).map_err(|error| {
                PyValueError::new_err(format!("invalid render request: {error}"))
            })?;
            let resources: RenderResources =
                serde_json::from_str(resources_json).map_err(|error| {
                    PyValueError::new_err(format!("invalid render resources: {error}"))
                })?;
            let clip_policy = resources.clip_policy.resolve()?;
            let output = inku_render::render::render_with_resources(
                request,
                &resources.hard_policy,
                resources.operational_budget,
                clip_policy,
            )
            .map_err(|error| PyValueError::new_err(format!("render failed: {error}")))?;
            let metadata = serde_json::to_string(&output.metadata).map_err(|error| {
                PyValueError::new_err(format!("metadata serialization failed: {error}"))
            })?;
            Ok((output.svg, metadata))
        })
    })
}

/// Report the shared pipeline binding and byte-protocol versions.
#[pyfunction]
fn pipeline_version_report() -> PyResult<String> {
    catch_python_panic(|| Ok(inku_pipeline_uniffi::version_report()))
}

/// Produce line animation frames through the same byte boundary as UniFFI.
#[pyfunction]
fn pipeline_line_animation<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::line_animation(input));
            PyBytes::new(py, &output)
        })
    })
}

/// Share the canonical canvas registry with the Python host.
#[pyfunction]
fn pipeline_canvas_registry() -> PyResult<String> {
    catch_python_panic(|| Ok(inku_pipeline_uniffi::canvas_registry()))
}

/// Advance one pipeline execution through the same owned byte boundary as Android.
#[pyfunction]
fn pipeline_step<'py>(
    py: Python<'py>,
    snapshot_bytes: &Bound<'py, PyBytes>,
    input_envelope_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let snapshot = snapshot_bytes.as_bytes().to_vec();
            let input_envelope = input_envelope_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::step(snapshot, input_envelope));
            PyBytes::new(py, &output)
        })
    })
}

/// Return bounded envelope JSON and any newly rendered SVG as separate values.
#[pyfunction]
fn pipeline_step_with_svg_limit<'py>(
    py: Python<'py>,
    snapshot_bytes: &Bound<'py, PyBytes>,
    input_bytes: &Bound<'py, PyBytes>,
    max_svg_bytes: usize,
) -> PyResult<(Bound<'py, PyBytes>, Option<String>)> {
    catch_python_panic(|| {
        Ok({
            let snapshot = snapshot_bytes.as_bytes().to_vec();
            let input = input_bytes.as_bytes().to_vec();
            let (output, svg) = py.detach(|| {
                inku_pipeline_uniffi::step_with_svg_limit(snapshot, input, max_svg_bytes)
            });
            (PyBytes::new(py, &output), svg)
        })
    })
}

/// Report the provider attempt in flight for a stored pipeline snapshot.
#[pyfunction]
fn pipeline_provider_attempt<'py>(
    py: Python<'py>,
    snapshot_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let snapshot = snapshot_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::provider_attempt(snapshot));
            PyBytes::new(py, &output)
        })
    })
}

/// Read structured progress for a saved pipeline snapshot.
#[pyfunction]
fn pipeline_run_progress<'py>(
    py: Python<'py>,
    snapshot_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let snapshot = snapshot_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::run_progress(snapshot));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_resolve_palette<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::resolve_palette(input));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_resolve_macro_catalog<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::resolve_macro_catalog(input));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_migrate_plugin_names<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::migrate_plugin_names(input));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_explain_plugin_diagnostics<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::explain_plugin_diagnostics(input));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_plugin_calls<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::plugin_calls(input));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_render_saved<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::render_saved(input));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_render_saved_with_svg_limit<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
    max_svg_bytes: usize,
) -> PyResult<(Bound<'py, PyBytes>, Option<String>)> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let (output, svg) = py
                .detach(|| inku_pipeline_uniffi::render_saved_with_svg_limit(input, max_svg_bytes));
            (PyBytes::new(py, &output), svg)
        })
    })
}

/// Migrate one saved Saijiki v1 unit (a document and its definitions) for a one-time host migration.
#[pyfunction]
fn pipeline_migrate_saijiki_v1<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::migrate_saijiki_v1(input));
            PyBytes::new(py, &output)
        })
    })
}

/// Migrate one saved Saijiki v2 unit (a document and its definitions) for a one-time host
/// migration (the touch reorganisation, 2026-10-31).
#[pyfunction]
fn pipeline_migrate_saijiki_v2<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::migrate_saijiki_v2(input));
            PyBytes::new(py, &output)
        })
    })
}

/// Another composition read from a work's visible instructions (draw-system05).
#[pyfunction]
fn pipeline_recompose<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::recompose(input));
            PyBytes::new(py, &output)
        })
    })
}

/// Another touch written into a work's visible instructions (the author, 2026-10-14).
#[pyfunction]
fn pipeline_retouch<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::retouch(input));
            PyBytes::new(py, &output)
        })
    })
}

/// The ranges the composition writes by name, for the host's display (draw-system05).
#[pyfunction]
fn pipeline_composition_ranges() -> PyResult<String> {
    catch_python_panic(|| Ok(inku_pipeline_uniffi::composition_ranges()))
}

/// The states of a work's completion ranges, for the instruction editor (A3).
#[pyfunction]
fn pipeline_completion_range_states<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::completion_range_states(input));
            PyBytes::new(py, &output)
        })
    })
}

/// The saved-Score refinements (touches, support, color arrangement) from the shared core.
#[pyfunction]
fn pipeline_saved_variants<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::saved_variants(input));
            PyBytes::new(py, &output)
        })
    })
}

/// The juxtaposition (取り合わせ) from the shared core: gather, prompt, check, join, same.
#[pyfunction]
fn pipeline_juxtaposition<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::juxtaposition(input));
            PyBytes::new(py, &output)
        })
    })
}

/// The chunk moves (まとまりの手) from the shared core: start, answer, drawn.
#[pyfunction]
fn pipeline_chunk_moves<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::chunk_moves(input));
            PyBytes::new(py, &output)
        })
    })
}

/// Inspect plugin packages through the shared host-neutral JSON boundary.
#[pyfunction]
fn pipeline_plugin_package(py: Python<'_>, input_bytes: &Bound<'_, PyBytes>) -> PyResult<String> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::plugin_package(input));
            String::from_utf8(output).expect("plugin package output is UTF-8 JSON")
        })
    })
}

/// The autonomous refinement (AI自動推敲) from the shared core: next, record, measure.
#[pyfunction]
fn pipeline_autonomous_refine<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::autonomous_refine(input));
            PyBytes::new(py, &output)
        })
    })
}

/// A provider request's bytes and what its answer says, from the shared core.
#[pyfunction]
fn pipeline_provider_wire<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::provider_wire(input));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_model_catalog<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::model_catalog(input));
            PyBytes::new(py, &output)
        })
    })
}

#[pyfunction]
fn pipeline_provider_admission<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::provider_admission(input));
            PyBytes::new(py, &output)
        })
    })
}

/// How a host prepares the image a work is written from (`inku.image-input-policy.v1`).
#[pyfunction]
fn pipeline_image_input_policy() -> PyResult<String> {
    catch_python_panic(|| Ok(inku_pipeline_uniffi::image_input_policy()))
}

/// The size to send an image at, the ratio its DDL declares and the nearest paper.
#[pyfunction]
fn pipeline_image_canvas<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let input = input_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::image_canvas(input));
            PyBytes::new(py, &output)
        })
    })
}

/// The SVG of the written DDL a host shows beside the image (`draw_image_review`).
#[pyfunction]
fn pipeline_image_review_svg<'py>(
    py: Python<'py>,
    snapshot_bytes: &Bound<'py, PyBytes>,
    request_bytes: &Bound<'py, PyBytes>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        Ok({
            let snapshot = snapshot_bytes.as_bytes().to_vec();
            let request = request_bytes.as_bytes().to_vec();
            let output = py.detach(|| inku_pipeline_uniffi::image_review_svg(snapshot, request));
            PyBytes::new(py, &output)
        })
    })
}

/// A description's identity `dh1` (`identity.description_hash`), from the shared core.
#[pyfunction]
fn pipeline_description_hash(text: &str) -> PyResult<String> {
    catch_python_panic(|| Ok(inku_pipeline_uniffi::description_hash(text.to_owned())))
}

/// A history item's render identity `rh3`, or `None` when the item JSON is not an object.
#[pyfunction]
fn pipeline_render_hash(item_json: &str) -> PyResult<Option<String>> {
    catch_python_panic(|| Ok(inku_pipeline_uniffi::render_hash(item_json.to_owned())))
}

/// The canonical JSON Server hashes, or `None` when the text is not JSON.
#[pyfunction]
fn pipeline_canonical_json(value_json: &str) -> PyResult<Option<String>> {
    catch_python_panic(|| Ok(inku_pipeline_uniffi::canonical_json(value_json.to_owned())))
}

/// The instruction language for `text`, or `None` for an unsupported request or fallback.
#[pyfunction]
#[pyo3(signature = (text, requested, fallback))]
fn pipeline_resolve_instruction_language(
    text: &str,
    requested: Option<&str>,
    fallback: &str,
) -> PyResult<Option<String>> {
    catch_python_panic(|| {
        Ok({
            inku_pipeline_uniffi::resolve_instruction_language(
                text.to_owned(),
                requested.map(str::to_owned),
                fallback.to_owned(),
            )
        })
    })
}

/// A requested language code normalized as Python's `(value or default).strip().lower()`.
#[pyfunction]
#[pyo3(signature = (value, default))]
fn pipeline_normalize_instruction_language(
    value: Option<&str>,
    default: &str,
) -> PyResult<Option<String>> {
    catch_python_panic(|| {
        Ok({
            inku_pipeline_uniffi::normalize_instruction_language(
                value.map(str::to_owned),
                default.to_owned(),
            )
        })
    })
}

/// The description with its labels removed, as every layer reads it.
#[pyfunction]
fn pipeline_description_without_labels(text: &str) -> PyResult<String> {
    catch_python_panic(|| {
        Ok(inku_pipeline_uniffi::description_without_labels(
            text.to_owned(),
        ))
    })
}

/// The labels' ranges as `[[start, end, kind], ...]` JSON, in Unicode scalar
/// offsets (Python's string indices): a host takes a read-and-draw run's
/// source labels from the `comment` ranges.
#[pyfunction]
fn pipeline_description_label_spans(text: &str) -> PyResult<String> {
    catch_python_panic(|| {
        Ok(inku_pipeline_uniffi::description_label_spans(
            text.to_owned(),
        ))
    })
}

/// How the PNG's size follows the request (resvg's command line, as resvg_py
/// does): no width or height keeps the SVG's size, one of them scales the
/// other with the aspect, both fit the picture inside them.
#[derive(Clone, Copy)]
enum FitTo {
    Original,
    Width(u32),
    Height(u32),
    Size(u32, u32),
}

impl FitTo {
    fn fit_to_size(self, size: resvg::tiny_skia::IntSize) -> Option<resvg::tiny_skia::IntSize> {
        match self {
            FitTo::Original => Some(size),
            FitTo::Width(width) => size.scale_to_width(width),
            FitTo::Height(height) => size.scale_to_height(height),
            FitTo::Size(width, height) => {
                resvg::tiny_skia::IntSize::from_wh(width, height).map(|fit| size.scale_to(fit))
            }
        }
    }

    fn fit_to_transform(self, size: resvg::tiny_skia::IntSize) -> resvg::tiny_skia::Transform {
        let from = size.to_size();
        let Some(to) = self.fit_to_size(size).map(|size| size.to_size()) else {
            return resvg::tiny_skia::Transform::default();
        };
        resvg::tiny_skia::Transform::from_scale(
            to.width() / from.width(),
            to.height() / from.height(),
        )
    }
}

#[derive(Eq, Hash, PartialEq)]
struct FontFileKey {
    path: String,
    size: u64,
    modified: std::time::SystemTime,
}

fn font_database(
    font_files: &[String],
) -> Result<std::sync::Arc<resvg::usvg::fontdb::Database>, String> {
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex, OnceLock};

    type FontCache = HashMap<Vec<FontFileKey>, Arc<resvg::usvg::fontdb::Database>>;
    static CACHE: OnceLock<Mutex<FontCache>> = OnceLock::new();

    let mut key = Vec::with_capacity(font_files.len());
    for (index, path) in font_files.iter().enumerate() {
        let metadata =
            std::fs::metadata(path).and_then(|metadata| Ok((metadata.len(), metadata.modified()?)));
        let (size, modified) = match metadata {
            Ok(values) => values,
            Err(error) => {
                // Preserve the first read error if an earlier path could not
                // have been read by the original sequential loader.
                for earlier in &font_files[..index] {
                    std::fs::read(earlier)
                        .map_err(|error| format!("font file {earlier}: {error}"))?;
                }
                return Err(format!("font file {path}: {error}"));
            }
        };
        key.push(FontFileKey {
            path: path.clone(),
            size,
            modified,
        });
    }
    let mut cache = CACHE
        .get_or_init(|| Mutex::new(HashMap::new()))
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    if let Some(fonts) = cache.get(&key) {
        return Ok(Arc::clone(fonts));
    }
    let mut fonts = resvg::usvg::fontdb::Database::new();
    let mut unchanged = true;
    for (path, expected) in font_files.iter().zip(&key) {
        let data = std::fs::read(path).map_err(|error| format!("font file {path}: {error}"))?;
        let metadata =
            std::fs::metadata(path).map_err(|error| format!("font file {path}: {error}"))?;
        let modified = metadata
            .modified()
            .map_err(|error| format!("font file {path}: {error}"))?;
        unchanged &= metadata.len() == expected.size && modified == expected.modified;
        fonts.load_font_data(data);
    }
    // resvg_py's names on Linux, where the Server runs.
    fonts.set_serif_family("Liberation Serif");
    fonts.set_sans_serif_family("Liberation Sans");
    fonts.set_cursive_family("Comic Neue");
    fonts.set_fantasy_family("Anton");
    fonts.set_monospace_family("Liberation Mono");
    let fonts = Arc::new(fonts);
    if unchanged {
        cache.insert(key, Arc::clone(&fonts));
    }
    Ok(fonts)
}

/// The PNG of `svg`, as resvg_py 0.5.0's `svg_to_bytes` drew it for the Server
/// and the CLI, by the core's vendored resvg (whose displacement follows the
/// specification, `core/vendor/resvg/INKU_PATCHES.md`).
fn png_of(
    svg: &str,
    width: Option<u32>,
    height: Option<u32>,
    font_files: &[String],
) -> Result<Vec<u8>, String> {
    use resvg::{tiny_skia, usvg};
    if svg.len() > inku_svg_raster::MAX_SVG_BYTES {
        return Err("SVG exceeds the byte limit".to_owned());
    }
    let positive = |value: u32, name: &str| {
        if value == 0 {
            Err(format!("{name} must be positive"))
        } else {
            Ok(value)
        }
    };
    let (fit, default_size) = match (width, height) {
        (Some(width), Some(height)) => (
            FitTo::Size(positive(width, "width")?, positive(height, "height")?),
            (width as f32, height as f32),
        ),
        (Some(width), None) => (
            FitTo::Width(positive(width, "width")?),
            (width as f32, 100.0),
        ),
        (None, Some(height)) => (
            FitTo::Height(positive(height, "height")?),
            (100.0, height as f32),
        ),
        (None, None) => (FitTo::Original, (100.0, 100.0)),
    };
    let fonts = font_database(font_files)?;
    let options = usvg::Options {
        dpi: 0.0,
        font_family: "Liberation Serif".to_owned(),
        font_size: 16.0,
        languages: Vec::new(),
        default_size: usvg::Size::from_wh(default_size.0, default_size.1)
            .ok_or_else(|| "invalid size".to_owned())?,
        fontdb: fonts,
        style_sheet: Some(String::new()),
        ..usvg::Options::default()
    };
    let tree =
        usvg::Tree::from_str(svg, &options).map_err(|error| format!("invalid SVG: {error}"))?;
    let size = fit
        .fit_to_size(tree.size().to_int_size())
        .ok_or_else(|| "target size is zero".to_owned())?;
    if u64::from(size.width()) * u64::from(size.height()) > 600_000_000 {
        return Err("raster exceeds the pixel limit".to_owned());
    }
    let mut pixmap = tiny_skia::Pixmap::new(size.width(), size.height())
        .ok_or_else(|| "cannot create pixmap".to_owned())?;
    resvg::render(
        &tree,
        fit.fit_to_transform(tree.size().to_int_size()),
        &mut pixmap.as_mut(),
    );
    pixmap.encode_png().map_err(|error| error.to_string())
}

/// SVG to PNG bytes for the Server and the CLI (`inku_analysis.rasterizer`),
/// drawn as Android's raster and the screens draw it (the core's vendored
/// resvg). The size follows resvg_py's `svg_to_bytes`: no `width` or `height`
/// keeps the SVG's own size, one of them scales the other with the aspect,
/// both fit the picture inside them. Text uses only `font_files` (the host's
/// bundled faces), never the machine's fonts. A raster image embedded in the
/// SVG (PNG, JPEG) is not decoded; an embedded SVG is drawn.
#[pyfunction]
#[pyo3(signature = (svg, width=None, height=None, font_files=Vec::new()))]
fn svg_to_png<'py>(
    py: Python<'py>,
    svg: &str,
    width: Option<u32>,
    height: Option<u32>,
    font_files: Vec<String>,
) -> PyResult<Bound<'py, PyBytes>> {
    catch_python_panic(|| {
        let svg = svg.to_owned();
        let png = py
            .detach(|| png_of(&svg, width, height, &font_files))
            .map_err(PyValueError::new_err)?;
        Ok(PyBytes::new(py, &png))
    })
}

/// The resvg `svg_to_png` draws with: the vendored crate's version and the
/// count of inku patches on it (`core/vendor/resvg/INKU_PATCHES.md`). Another
/// resvg draws other pixels from the same SVG, so a host records this beside
/// the PNGs it makes (the Server's and the CLI's `rasterizer_info`).
const RASTER_IDENTITY: (&str, &str) = ("resvg", "0.48.1+inku.2");

/// `{"backend": "resvg", "version": "<vendored version>+inku.<patches>"}`.
#[pyfunction]
fn raster_identity_json() -> PyResult<String> {
    catch_python_panic(|| {
        Ok({
            serde_json::json!({"backend": RASTER_IDENTITY.0, "version": RASTER_IDENTITY.1})
                .to_string()
        })
    })
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(svg_to_png, module)?)?;
    module.add_function(wrap_pyfunction!(raster_identity_json, module)?)?;
    module.add_function(wrap_pyfunction!(score_version, module)?)?;
    module.add_function(wrap_pyfunction!(render_engine_id, module)?)?;
    module.add_function(wrap_pyfunction!(render_engine_version, module)?)?;
    module.add_function(wrap_pyfunction!(default_color_map_json, module)?)?;
    module.add_function(wrap_pyfunction!(renderer_reference_json, module)?)?;
    module.add_function(wrap_pyfunction!(render_seed_from_text, module)?)?;
    module.add_function(wrap_pyfunction!(render, module)?)?;
    module.add_function(wrap_pyfunction!(render_with_svg_limit, module)?)?;
    module.add_function(wrap_pyfunction!(render_with_resources, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_version_report, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_line_animation, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_canvas_registry, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_step, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_step_with_svg_limit, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_provider_attempt, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_run_progress, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_resolve_palette, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_resolve_macro_catalog, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_migrate_plugin_names, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_plugin_calls, module)?)?;
    module.add_function(wrap_pyfunction!(
        pipeline_explain_plugin_diagnostics,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(pipeline_render_saved, module)?)?;
    module.add_function(wrap_pyfunction!(
        pipeline_render_saved_with_svg_limit,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(pipeline_migrate_saijiki_v1, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_migrate_saijiki_v2, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_recompose, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_retouch, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_composition_ranges, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_completion_range_states, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_canonical_json, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_saved_variants, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_juxtaposition, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_autonomous_refine, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_chunk_moves, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_plugin_package, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_provider_wire, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_model_catalog, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_provider_admission, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_image_input_policy, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_image_canvas, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_image_review_svg, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_description_hash, module)?)?;
    module.add_function(wrap_pyfunction!(
        pipeline_description_without_labels,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(pipeline_description_label_spans, module)?)?;
    module.add_function(wrap_pyfunction!(
        pipeline_normalize_instruction_language,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(pipeline_render_hash, module)?)?;
    module.add_function(wrap_pyfunction!(
        pipeline_resolve_instruction_language,
        module
    )?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn raster_reuses_font_database_and_keeps_png_bytes() {
        let font = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../../server/src/inku_server/fonts/NotoSerifJP-Variable.ttf"
        );
        let fonts = vec![font.to_owned()];
        let svg = r#"<svg xmlns="http://www.w3.org/2000/svg" width="160" height="48"><text x="4" y="30" font-family="Noto Serif JP" font-size="24">描画 test</text></svg>"#;
        let first_png = super::png_of(svg, None, None, &fonts).unwrap();
        let first_fonts = super::font_database(&fonts).unwrap();
        let second_png = super::png_of(svg, None, None, &fonts).unwrap();
        let second_fonts = super::font_database(&fonts).unwrap();
        assert_eq!(first_png, second_png);
        assert!(std::sync::Arc::ptr_eq(&first_fonts, &second_fonts));
    }

    #[test]
    fn p0_oversized_svg_is_rejected_before_rasterization() {
        let svg = format!(
            "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1\" height=\"1\"></svg>{}",
            " ".repeat(64 * 1024 * 1024)
        );
        let error = super::png_of(&svg, None, None, &[]).unwrap_err();
        assert!(error.contains("SVG"), "{error}");
    }
    #[test]
    fn score_version_names_the_latest_supported_edition() {
        assert_eq!(super::score_version().unwrap(), "0.24.0");
        assert_eq!(
            super::score_version().unwrap(),
            inku_score::ScoreEdition::LATEST.as_str()
        );
    }

    /// The identity follows the vendored crate: its version, and one `inku.N`
    /// per local patch that INKU_PATCHES.md counts.
    #[test]
    fn raster_identity_names_the_vendored_resvg_and_its_patches() {
        let manifest = include_str!("../../../vendor/resvg/Cargo.toml");
        let version = manifest
            .lines()
            .find_map(|line| line.strip_prefix("version = \""))
            .and_then(|rest| rest.strip_suffix('"'))
            .expect("the vendored resvg names its version");
        assert_eq!(super::RASTER_IDENTITY.1, format!("{version}+inku.2"));
        let patches = include_str!("../../../vendor/resvg/INKU_PATCHES.md");
        assert!(patches.contains("There are two local patches."));
        let identity: serde_json::Value =
            serde_json::from_str(&super::raster_identity_json().unwrap()).unwrap();
        assert_eq!(
            identity,
            serde_json::json!({"backend": "resvg", "version": "0.48.1+inku.2"})
        );
    }
}
