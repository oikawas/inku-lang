//! Platform-independent render core for inku.
//!
//! Portability Boundary 2 starts with a deliberately small crate surface. Render
//! semantics move here in later stages; the crate must never depend on a host SDK.

#![forbid(unsafe_code)]

pub mod arc;
pub mod contact;
pub mod determinism;
pub mod geometry;
pub mod group;
pub mod placement;
pub mod planning;
pub mod stroke;
pub mod support;
pub mod types;

/// Version of the Rust host boundary, independent from the Render Engine version.
pub const CORE_API_VERSION: &str = "0.1.0";

/// Report the host-boundary version for binding and packaging smoke tests.
#[must_use]
pub const fn core_api_version() -> &'static str {
    CORE_API_VERSION
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn boundary_version_is_explicit() {
        assert_eq!(core_api_version(), "0.1.0");
    }
}
