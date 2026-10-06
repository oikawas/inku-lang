//! Shared screen display with Skia (opt-in feature `display`, Apple and Android).
//! The core classifies failures; each host owns its fallback policy.

use std::fmt;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

use inku_display::{DisplayError, RasterOptions, RasterOutput, RasterRegionOptions};

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
#[derive(Clone, Copy, Debug, serde::Serialize, serde::Deserialize, uniffi::Record)]
pub struct DisplayRegion {
    pub full_width: u32,
    pub full_height: u32,
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

/// The sides the display is drawn in (a coarse whole first, then tiles), and the
/// largest window and full canvas a window is cut from.
#[derive(Clone, Copy, Debug, serde::Serialize, serde::Deserialize, uniffi::Record)]
pub struct DisplayLayout {
    pub coarse_side: u32,
    pub tile_side: u32,
    pub max_window_side: u32,
    pub max_window_pixels: u64,
    pub max_canvas_side: u32,
}

/// Host screen rectangles in one unit system, after its fit/zoom/rotation and
/// viewport intersection. No platform coordinate type crosses the core boundary.
#[derive(Clone, Copy, Debug, serde::Serialize, serde::Deserialize, uniffi::Record)]
pub struct DisplayRect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// One recorded work. Its windows may be drawn on several threads at once.
#[derive(uniffi::Object)]
pub struct DisplayScene {
    scene: Arc<inku_display::DisplayScene>,
}

/// The scene and joined window allocation used by the host's tile workers.
#[derive(uniffi::Object)]
pub struct DisplayComposite {
    composite: inku_display::DisplayComposite,
}

/// An immutable pixel lease. `finish` moves the joined allocation here; a snapshot
/// has one separate allocation. Images retain pixels, never the source scene.
#[derive(uniffi::Object)]
pub struct DisplayImage {
    raster: RasterOutput,
}

#[uniffi::export]
impl DisplayImage {
    pub fn width(&self) -> u32 {
        self.raster.width
    }
    pub fn height(&self) -> u32 {
        self.raster.height
    }
    pub fn stride(&self) -> u32 {
        self.raster.stride
    }
    pub fn byte_count(&self) -> u64 {
        self.raster.pixels.len() as u64
    }
    pub fn pixel_format(&self) -> String {
        self.raster.pixel_format.to_owned()
    }

    /// For the Apple native-image bridge only. The allocation is immutable and
    /// stationary. Its CGDataProvider must retain this DisplayImage until the
    /// provider's release callback, including when CGImage creation fails. The
    /// address must never escape that bridge or outlive this object.
    pub fn pixel_buffer_address(&self) -> u64 {
        self.raster.pixels.as_ptr() as usize as u64
    }
}

impl DisplayImage {
    /// Borrow the same allocation for Android's NDK Bitmap writer; no binding
    /// serialization and no intermediate Vec or Java byte array.
    pub fn raster(&self) -> &RasterOutput {
        &self.raster
    }
}

#[uniffi::export]
impl DisplayComposite {
    pub fn render_tile(&self, tile: DisplayRegion) -> Result<(), DisplayFailure> {
        guarded(|| self.composite.render_tile(tile.into()).map_err(refused))
    }

    pub fn snapshot(&self) -> Result<Arc<DisplayImage>, DisplayFailure> {
        guarded(|| {
            self.composite
                .snapshot()
                .map(|raster| Arc::new(DisplayImage { raster }))
                .map_err(refused)
        })
    }

    /// Host joins all workers first. Late writes and repeated finish are refused.
    pub fn finish(&self) -> Result<Arc<DisplayImage>, DisplayFailure> {
        guarded(|| {
            self.composite
                .finish()
                .map(|raster| Arc::new(DisplayImage { raster }))
                .map_err(refused)
        })
    }
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

    /// The whole work fitted to the box, as a window to draw in tiles.
    pub fn whole(
        &self,
        target_width: Option<u32>,
        target_height: Option<u32>,
    ) -> Result<DisplayRegion, DisplayFailure> {
        guarded(|| {
            self.scene
                .whole(RasterOptions {
                    target_width,
                    target_height,
                })
                .map(DisplayRegion::from)
                .map_err(refused)
        })
    }

    pub fn region(&self, region: DisplayRegion) -> Result<RasterFrame, DisplayFailure> {
        guarded(|| self.scene.region(region.into()).map(frame).map_err(refused))
    }

    pub fn composite(
        &self,
        window: DisplayRegion,
    ) -> Result<Arc<DisplayComposite>, DisplayFailure> {
        guarded(|| {
            inku_display::DisplayComposite::new(Arc::clone(&self.scene), window.into())
                .map(|composite| Arc::new(DisplayComposite { composite }))
                .map_err(refused)
        })
    }
}

/// Check, rewrite, read and record one stored SVG for display.
#[uniffi::export]
pub fn prepare_display_scene(svg: String) -> Result<Arc<DisplayScene>, DisplayFailure> {
    guarded(|| {
        let scene = inku_display::prepare_scene(&svg).map_err(classified)?;
        Ok(Arc::new(DisplayScene {
            scene: Arc::new(scene),
        }))
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
        max_window_side: inku_display::MAX_RASTER_DIMENSION,
        max_window_pixels: inku_display::MAX_RASTER_PIXELS,
        max_canvas_side: inku_display::geometry::MAX_CANVAS_SIDE,
    }
}

#[uniffi::export]
pub fn display_api_version() -> String {
    inku_display::display_api_version().to_owned()
}

/// Shared density limiting and outward rounding; the host owns the zoom threshold
/// and passes rectangles already transformed into the original picture's axes.
#[uniffi::export]
pub fn display_detail_region(
    zoomed: DisplayRect,
    visible: DisplayRect,
    pixel_scale: f64,
    limits: DisplayLayout,
) -> Option<DisplayRegion> {
    inku_display::geometry::detail_region(
        zoomed.into(),
        visible.into(),
        pixel_scale,
        inku_display::geometry::DetailLimits {
            max_window_side: limits.max_window_side,
            max_window_pixels: limits.max_window_pixels,
            max_canvas_side: limits.max_canvas_side,
        },
    )
    .map(DisplayRegion::from)
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

fn classified(error: DisplayError) -> DisplayFailure {
    match error {
        DisplayError::EmptySvg
        | DisplayError::Parse(_)
        | DisplayError::Unsupported(_)
        | DisplayError::SkiaLoad => DisplayFailure::Unsupported {
            code: error.code().to_owned(),
            message: error.to_string(),
        },
        _ => refused(error),
    }
}

impl From<DisplayRect> for inku_display::geometry::Rect {
    fn from(rect: DisplayRect) -> Self {
        Self {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
        }
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
