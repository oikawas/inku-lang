//! Thin CPython binding for the platform-independent render core.

use pyo3::prelude::*;

#[pyfunction]
fn core_api_version() -> &'static str {
    inku_render::core_api_version()
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(core_api_version, module)?)?;
    Ok(())
}
