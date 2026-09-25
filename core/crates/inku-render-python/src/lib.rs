//! Thin CPython binding for the platform-independent render core.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use serde::Deserialize;

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
fn core_api_version() -> &'static str {
    inku_render::core_api_version()
}

#[pyfunction]
fn render_engine_id() -> &'static str {
    inku_render::render_engine_identity().0
}

#[pyfunction]
fn render_engine_version() -> &'static str {
    inku_render::render_engine_identity().1
}

#[pyfunction]
fn default_color_map_json() -> PyResult<String> {
    serde_json::to_string(&inku_render::palette::default_color_map()).map_err(|error| {
        PyValueError::new_err(format!("default color map serialization failed: {error}"))
    })
}

#[pyfunction]
fn renderer_reference_json() -> PyResult<String> {
    serde_json::to_string(&inku_render::reference::renderer_reference()).map_err(|error| {
        PyValueError::new_err(format!("renderer reference serialization failed: {error}"))
    })
}

/// Render one canonical coarse request and return SVG plus JSON metadata.
#[pyfunction]
fn render(request_json: &str) -> PyResult<(String, String)> {
    let request = serde_json::from_str(request_json)
        .map_err(|error| PyValueError::new_err(format!("invalid render request: {error}")))?;
    let output = inku_render::render::render(request)
        .map_err(|error| PyValueError::new_err(format!("render failed: {error}")))?;
    let metadata = serde_json::to_string(&output.metadata).map_err(|error| {
        PyValueError::new_err(format!("metadata serialization failed: {error}"))
    })?;
    Ok((output.svg, metadata))
}

/// Render one canonical coarse request under independent caller-owned resource authority.
#[pyfunction]
fn render_with_resources(request_json: &str, resources_json: &str) -> PyResult<(String, String)> {
    let request = serde_json::from_str(request_json)
        .map_err(|error| PyValueError::new_err(format!("invalid render request: {error}")))?;
    let resources: RenderResources = serde_json::from_str(resources_json)
        .map_err(|error| PyValueError::new_err(format!("invalid render resources: {error}")))?;
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
}

/// Report the shared pipeline binding and byte-protocol versions.
#[pyfunction]
fn pipeline_version_report() -> String {
    inku_pipeline_uniffi::version_report()
}

/// Share the canonical canvas registry with the Python host.
#[pyfunction]
fn pipeline_canvas_registry() -> String {
    inku_pipeline_uniffi::canvas_registry()
}

/// Project the shared Stage 1 grammar for host input and prompt displays.
#[pyfunction]
fn pipeline_stage1_system_projection(language_code: String) -> String {
    inku_pipeline_uniffi::stage1_system_projection(language_code)
}

/// Advance one pipeline execution through the same owned byte boundary as Android.
#[pyfunction]
fn pipeline_step<'py>(
    py: Python<'py>,
    snapshot_bytes: &Bound<'py, PyBytes>,
    input_envelope_bytes: &Bound<'py, PyBytes>,
) -> Bound<'py, PyBytes> {
    let output = inku_pipeline_uniffi::step(
        snapshot_bytes.as_bytes().to_vec(),
        input_envelope_bytes.as_bytes().to_vec(),
    );
    PyBytes::new(py, &output)
}

#[pyfunction]
fn pipeline_resolve_palette<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> Bound<'py, PyBytes> {
    let output = inku_pipeline_uniffi::resolve_palette(input_bytes.as_bytes().to_vec());
    PyBytes::new(py, &output)
}

#[pyfunction]
fn pipeline_resolve_macro_catalog<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> Bound<'py, PyBytes> {
    let output = inku_pipeline_uniffi::resolve_macro_catalog(input_bytes.as_bytes().to_vec());
    PyBytes::new(py, &output)
}

#[pyfunction]
fn pipeline_explain_plugin_diagnostics<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> Bound<'py, PyBytes> {
    let output = inku_pipeline_uniffi::explain_plugin_diagnostics(input_bytes.as_bytes().to_vec());
    PyBytes::new(py, &output)
}

#[pyfunction]
fn pipeline_render_saved<'py>(
    py: Python<'py>,
    input_bytes: &Bound<'py, PyBytes>,
) -> Bound<'py, PyBytes> {
    let output = inku_pipeline_uniffi::render_saved(input_bytes.as_bytes().to_vec());
    PyBytes::new(py, &output)
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(core_api_version, module)?)?;
    module.add_function(wrap_pyfunction!(render_engine_id, module)?)?;
    module.add_function(wrap_pyfunction!(render_engine_version, module)?)?;
    module.add_function(wrap_pyfunction!(default_color_map_json, module)?)?;
    module.add_function(wrap_pyfunction!(renderer_reference_json, module)?)?;
    module.add_function(wrap_pyfunction!(render, module)?)?;
    module.add_function(wrap_pyfunction!(render_with_resources, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_version_report, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_canvas_registry, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_stage1_system_projection, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_step, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_resolve_palette, module)?)?;
    module.add_function(wrap_pyfunction!(pipeline_resolve_macro_catalog, module)?)?;
    module.add_function(wrap_pyfunction!(
        pipeline_explain_plugin_diagnostics,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(pipeline_render_saved, module)?)?;
    Ok(())
}
