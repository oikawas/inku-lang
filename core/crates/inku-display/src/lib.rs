//! Screen display of inku SVG artifacts with Skia, so a host shows a work as the
//! Web's Chrome does (Skia display plan, 2026-10-06).
//!
//! The pure part is always built: the support check (a work outside it is shown
//! with resvg, as before), the display-time compatibility rewrite, and the window
//! and tile geometry. The `skia` feature adds the scene: Skia reads the rewritten
//! SVG once, records a `Picture`, and replays it into premultiplied RGBA8 windows
//! from any thread.
//!
//! Nothing here changes the stored SVG, the core's render output, or the resvg
//! paths (export, thumbnails, the Server).

#![forbid(unsafe_code)]

use std::fmt;

use roxmltree::{Document, ParsingOptions};

mod check;
pub mod geometry;
mod rewrite;
#[cfg(feature = "skia")]
mod scene;

pub use check::Unsupported;
pub use inku_svg_raster::{
    MAX_RASTER_DIMENSION, MAX_RASTER_PIXELS, MAX_SVG_BYTES, PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
    RasterOptions, RasterOutput, RasterRegionOptions,
};
pub use rewrite::Rewrites;
#[cfg(feature = "skia")]
pub use scene::{DisplayScene, prepare_scene};

/// Version of the display boundary, independent of the Render Engine.
pub const DISPLAY_API_VERSION: &str = "0.1.0";

/// The SVG Skia reads, and the work's size in user units.
#[derive(Clone, Debug, PartialEq)]
pub struct DisplaySvg {
    pub svg: String,
    pub width: f64,
    pub height: f64,
    pub rewrites: Rewrites,
}

/// Why a work is not drawn here. `Unsupported` and `Parse` mean "show it with resvg".
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DisplayError {
    EmptySvg,
    SvgTooLarge {
        actual: usize,
        maximum: usize,
    },
    Parse(String),
    Unsupported(Unsupported),
    InvalidIntrinsicSize,
    MissingTargetDimension,
    InvalidTargetDimension,
    TargetDimensionTooLarge {
        actual: u32,
        maximum: u32,
    },
    DerivedDimensionTooLarge,
    PixelCountTooLarge {
        actual: u64,
        maximum: u64,
    },
    /// Skia could not read the rewritten SVG or record it.
    SkiaLoad,
    AllocationFailed,
}

impl DisplayError {
    /// Stable code for the host's diagnostics.
    pub fn code(&self) -> &'static str {
        match self {
            Self::EmptySvg => "empty_svg",
            Self::SvgTooLarge { .. } => "svg_too_large",
            Self::Parse(_) => "invalid_svg",
            Self::Unsupported(unsupported) => unsupported.code,
            Self::InvalidIntrinsicSize => "invalid_intrinsic_size",
            Self::MissingTargetDimension => "missing_target_dimension",
            Self::InvalidTargetDimension => "invalid_target_dimension",
            Self::TargetDimensionTooLarge { .. } => "target_dimension_too_large",
            Self::DerivedDimensionTooLarge => "derived_dimension_too_large",
            Self::PixelCountTooLarge { .. } => "pixel_count_too_large",
            Self::SkiaLoad => "skia_load",
            Self::AllocationFailed => "allocation_failed",
        }
    }
}

impl fmt::Display for DisplayError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptySvg => formatter.write_str("SVG input is empty"),
            Self::SvgTooLarge { actual, maximum } => {
                write!(
                    formatter,
                    "SVG input is {actual} bytes; maximum is {maximum}"
                )
            }
            Self::Parse(message) => write!(formatter, "SVG parse failed: {message}"),
            Self::Unsupported(unsupported) => write!(
                formatter,
                "outside the display support table ({}): {}",
                unsupported.code, unsupported.detail
            ),
            Self::InvalidIntrinsicSize => {
                formatter.write_str("SVG intrinsic dimensions are invalid")
            }
            Self::MissingTargetDimension => {
                formatter.write_str("target_width or target_height is required")
            }
            Self::InvalidTargetDimension => formatter
                .write_str("target dimensions must be greater than zero and inside the canvas"),
            Self::TargetDimensionTooLarge { actual, maximum } => {
                write!(
                    formatter,
                    "target dimension {actual} exceeds maximum {maximum}"
                )
            }
            Self::DerivedDimensionTooLarge => {
                formatter.write_str("aspect-preserving output dimension is out of range")
            }
            Self::PixelCountTooLarge { actual, maximum } => {
                write!(
                    formatter,
                    "raster has {actual} pixels; maximum is {maximum}"
                )
            }
            Self::SkiaLoad => formatter.write_str("Skia could not read the SVG"),
            Self::AllocationFailed => formatter.write_str("raster allocation failed"),
        }
    }
}

impl std::error::Error for DisplayError {}

impl From<Unsupported> for DisplayError {
    fn from(unsupported: Unsupported) -> Self {
        Self::Unsupported(unsupported)
    }
}

/// Check a stored SVG against the support table and rewrite it for Skia.
pub fn display_svg(svg: &str) -> Result<DisplaySvg, DisplayError> {
    if svg.is_empty() {
        return Err(DisplayError::EmptySvg);
    }
    if svg.len() > MAX_SVG_BYTES {
        return Err(DisplayError::SvgTooLarge {
            actual: svg.len(),
            maximum: MAX_SVG_BYTES,
        });
    }
    let document = Document::parse_with_options(svg, ParsingOptions::default())
        .map_err(|error| DisplayError::Parse(error.to_string()))?;
    check::check(&document, svg)?;
    let (width, height) = intrinsic_size(document.root_element())?;
    let (svg, rewrites) = rewrite::rewrite(&document, svg)?;
    Ok(DisplaySvg {
        svg,
        width,
        height,
        rewrites,
    })
}

/// The root's `width` and `height` in px (as the core writes them), else its viewBox.
fn intrinsic_size(root: roxmltree::Node<'_, '_>) -> Result<(f64, f64), DisplayError> {
    if root.tag_name().name() != "svg" || root.tag_name().namespace() != Some(check::SVG_NAMESPACE)
    {
        return Err(Unsupported::new("element", "root is not svg").into());
    }
    let length = |name: &str| {
        root.attribute(name)
            .map(|value| value.trim().trim_end_matches("px").parse::<f64>().ok())
    };
    let size = match (length("width"), length("height")) {
        (Some(Some(width)), Some(Some(height))) => (width, height),
        (None, None) => {
            let view_box: Vec<f64> = root
                .attribute("viewBox")
                .unwrap_or_default()
                .split([' ', ','])
                .filter(|part| !part.is_empty())
                .map(|part| part.parse::<f64>().unwrap_or(f64::NAN))
                .collect();
            match view_box[..] {
                [_, _, width, height] => (width, height),
                _ => (f64::NAN, f64::NAN),
            }
        }
        _ => return Err(Unsupported::new("root_size", "width or height is not in px").into()),
    };
    if size.0.is_finite() && size.1.is_finite() && size.0 > 0.0 && size.1 > 0.0 {
        Ok(size)
    } else {
        Err(DisplayError::InvalidIntrinsicSize)
    }
}

#[must_use]
pub const fn display_api_version() -> &'static str {
    DISPLAY_API_VERSION
}
