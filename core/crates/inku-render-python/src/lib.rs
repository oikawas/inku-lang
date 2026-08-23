//! Thin CPython binding for the platform-independent render core.

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

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(core_api_version, module)?)?;
    module.add_function(wrap_pyfunction!(render_engine_id, module)?)?;
    module.add_function(wrap_pyfunction!(render_engine_version, module)?)?;
    Ok(())
}
