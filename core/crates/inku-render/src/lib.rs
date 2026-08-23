//! Platform-independent render core for inku.
//!
//! Portability Boundary 2 starts with a deliberately small crate surface. Render
//! semantics move here in later stages; the crate must never depend on a host SDK.

#![forbid(unsafe_code)]

pub mod arc;
pub mod arrangement;
pub mod cloudform;
pub mod contact;
pub mod determinism;
pub mod fills;
pub mod geometry;
pub mod ground;
pub mod group;
pub mod layers;
pub mod marks;
pub mod materials;
pub mod palette;
pub mod performance;
pub mod placement;
pub mod planning;
pub mod render;
pub mod stroke;
pub mod support;
pub mod surfaces;
pub mod svg;
pub mod types;

/// Version of the Rust host boundary, independent from the Render Engine version.
pub const CORE_API_VERSION: &str = "0.1.0";

/// Candidate identity owned by the portable core and exposed by every host binding.
pub const RENDER_ENGINE_ID: &str = "default";
pub const RENDER_ENGINE_VERSION: &str = "41";

/// Report the host-boundary version for binding and packaging smoke tests.
#[must_use]
pub const fn core_api_version() -> &'static str {
    CORE_API_VERSION
}

/// Report the candidate identity without duplicating it in host adapters.
#[must_use]
pub const fn render_engine_identity() -> (&'static str, &'static str) {
    (RENDER_ENGINE_ID, RENDER_ENGINE_VERSION)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn boundary_version_is_explicit() {
        assert_eq!(core_api_version(), "0.1.0");
    }

    #[test]
    fn candidate_identity_is_owned_by_the_core() {
        assert_eq!(render_engine_identity(), ("default", "41"));
    }
}
