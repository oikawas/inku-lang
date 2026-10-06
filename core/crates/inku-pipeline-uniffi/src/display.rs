//! Screen display with Skia (feature `display`, enabled only by the Apple build).
//!
//! A work the display cannot take (`DisplayFailure::Unsupported`) is shown with the
//! resvg `RasterScene`, as before; the host counts the code.

use std::fmt;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

use inku_display::{DisplayError, RasterOptions, RasterRegionOptions};

use crate::raster::{RasterFrame, frame};

/// Why a work was not prepared (show it with resvg) or a window was refused.
#[derive(Debug, uniffi::Error)]
pub enum DisplayFailure {
    Unsupported { code: String, message: String },
    Refused { code: String, message: String },
    InternalInvariant,
}

/// How many places each display-time compatibility rewrite changed.
#[derive(uniffi::Record)]
pub struct DisplayRewrites {
    pub href: u64,
    pub ellipse: u64,
    pub seed: u64,
}

/// A window on a canvas `full_width` × `full_height` pixels.
#[derive(Clone, Copy, uniffi::Record)]
pub struct DisplayRegion {
    pub full_width: u32,
    pub full_height: u32,
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

/// The sides the display is drawn in: a coarse whole first, then tiles.
#[derive(uniffi::Record)]
pub struct DisplayLayout {
    pub coarse_side: u32,
    pub tile_side: u32,
}

/// One recorded work. Its windows may be drawn on several threads at once.
#[derive(uniffi::Object)]
pub struct DisplayScene {
    scene: inku_display::DisplayScene,
}

#[uniffi::export]
impl DisplayScene {
    pub fn source_byte_count(&self) -> u64 {
        self.scene.source_bytes()
    }
    pub fn picture_byte_count(&self) -> u64 {
        self.scene.picture_bytes()
    }
    pub fn intrinsic_width(&self) -> f64 {
        self.scene.intrinsic_width()
    }
    pub fn intrinsic_height(&self) -> f64 {
        self.scene.intrinsic_height()
    }
    pub fn rewrites(&self) -> DisplayRewrites {
        let rewrites = self.scene.rewrites();
        DisplayRewrites {
            href: rewrites.href as u64,
            ellipse: rewrites.ellipse as u64,
            seed: rewrites.seed as u64,
        }
    }

    pub fn rasterize(
        &self,
        target_width: Option<u32>,
        target_height: Option<u32>,
    ) -> Result<RasterFrame, DisplayFailure> {
        guarded(|| {
            self.scene
                .rasterize(RasterOptions {
                    target_width,
                    target_height,
                })
                .map(frame)
                .map_err(refused)
        })
    }

    pub fn region(&self, region: DisplayRegion) -> Result<RasterFrame, DisplayFailure> {
        guarded(|| self.scene.region(region.into()).map(frame).map_err(refused))
    }
}

/// Check, rewrite, read and record one stored SVG for display.
#[uniffi::export]
pub fn prepare_display_scene(svg: String) -> Result<Arc<DisplayScene>, DisplayFailure> {
    guarded(|| {
        let scene =
            inku_display::prepare_scene(&svg).map_err(|error| DisplayFailure::Unsupported {
                code: error.code().to_owned(),
                message: error.to_string(),
            })?;
        Ok(Arc::new(DisplayScene { scene }))
    })
}

/// The tiles covering a window, nearest to its centre first.
#[uniffi::export]
pub fn display_tiles(window: DisplayRegion, side: u32) -> Vec<DisplayRegion> {
    inku_display::geometry::tiles(window.into(), side)
        .into_iter()
        .map(DisplayRegion::from)
        .collect()
}

#[uniffi::export]
pub fn display_layout() -> DisplayLayout {
    DisplayLayout {
        coarse_side: inku_display::geometry::COARSE_SIDE,
        tile_side: inku_display::geometry::TILE_SIDE,
    }
}

#[uniffi::export]
pub fn display_api_version() -> String {
    inku_display::display_api_version().to_owned()
}

fn guarded<T>(operation: impl FnOnce() -> Result<T, DisplayFailure>) -> Result<T, DisplayFailure> {
    catch_unwind(AssertUnwindSafe(operation)).unwrap_or(Err(DisplayFailure::InternalInvariant))
}

fn refused(error: DisplayError) -> DisplayFailure {
    DisplayFailure::Refused {
        code: error.code().to_owned(),
        message: error.to_string(),
    }
}

impl From<DisplayRegion> for RasterRegionOptions {
    fn from(region: DisplayRegion) -> Self {
        Self {
            full_width: region.full_width,
            full_height: region.full_height,
            x: region.x,
            y: region.y,
            width: region.width,
            height: region.height,
        }
    }
}

impl From<RasterRegionOptions> for DisplayRegion {
    fn from(region: RasterRegionOptions) -> Self {
        Self {
            full_width: region.full_width,
            full_height: region.full_height,
            x: region.x,
            y: region.y,
            width: region.width,
            height: region.height,
        }
    }
}

impl fmt::Display for DisplayFailure {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Unsupported { code, message } | Self::Refused { code, message } => {
                write!(formatter, "{code}: {message}")
            }
            Self::InternalInvariant => formatter.write_str("the display core panicked"),
        }
    }
}

impl std::error::Error for DisplayFailure {}
