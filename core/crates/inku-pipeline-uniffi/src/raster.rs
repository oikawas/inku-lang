//! Owned presentation pixels without a JSON or base64 transport.

use std::fmt;
use std::panic::{AssertUnwindSafe, catch_unwind};

use inku_svg_raster::{RasterError, RasterOptions};

/// One independent premultiplied RGBA8 buffer, owned by the calling host.
#[derive(uniffi::Record)]
pub struct RasterFrame {
    pub width: u32,
    pub height: u32,
    pub stride: u32,
    pub pixel_format: String,
    pub pixels: Vec<u8>,
}

/// Stable refusal codes and the shared raster implementation's reason.
#[derive(Debug, uniffi::Error)]
pub enum RasterFailure {
    Refused { code: String, message: String },
    InternalInvariant,
}

impl fmt::Display for RasterFailure {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Refused { code, message } => write!(formatter, "{code}: {message}"),
            Self::InternalInvariant => formatter.write_str("the raster core panicked"),
        }
    }
}

impl std::error::Error for RasterFailure {}

impl From<RasterError> for RasterFailure {
    fn from(error: RasterError) -> Self {
        let code = match &error {
            RasterError::EmptySvg => "empty_svg",
            RasterError::SvgTooLarge { .. } => "svg_too_large",
            RasterError::MissingTargetDimension => "missing_target_dimension",
            RasterError::InvalidTargetDimension => "invalid_target_dimension",
            RasterError::TargetDimensionTooLarge { .. } => "target_dimension_too_large",
            RasterError::InvalidIntrinsicSize => "invalid_intrinsic_size",
            RasterError::DerivedDimensionTooLarge => "derived_dimension_too_large",
            RasterError::PixelCountTooLarge { .. } => "pixel_count_too_large",
            RasterError::ByteLengthOverflow => "byte_length_overflow",
            RasterError::Parse(_) => "invalid_svg",
            RasterError::AllocationFailed => "allocation_failed",
        };
        Self::Refused {
            code: code.to_owned(),
            message: error.to_string(),
        }
    }
}

#[uniffi::export]
pub fn raster_api_version() -> String {
    inku_svg_raster::raster_api_version().to_owned()
}

/// Reuse the host-neutral renderer and contain unwinding at the FFI boundary.
#[uniffi::export]
pub fn rasterize_svg(
    svg: String,
    target_width: Option<u32>,
    target_height: Option<u32>,
) -> Result<RasterFrame, RasterFailure> {
    catch_unwind(AssertUnwindSafe(|| {
        let output = inku_svg_raster::rasterize(
            &svg,
            RasterOptions {
                target_width,
                target_height,
            },
        )?;
        Ok(RasterFrame {
            width: output.width,
            height: output.height,
            stride: output.stride,
            pixel_format: output.pixel_format.to_owned(),
            pixels: output.pixels,
        })
    }))
    .unwrap_or(Err(RasterFailure::InternalInvariant))
}
