//! Thin CPython binding for the platform-independent render core.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

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

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(core_api_version, module)?)?;
    module.add_function(wrap_pyfunction!(render_engine_id, module)?)?;
    module.add_function(wrap_pyfunction!(render_engine_version, module)?)?;
    module.add_function(wrap_pyfunction!(default_color_map_json, module)?)?;
    module.add_function(wrap_pyfunction!(renderer_reference_json, module)?)?;
    module.add_function(wrap_pyfunction!(render, module)?)?;
    Ok(())
}
