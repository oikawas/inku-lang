//! Owned presentation pixels without a JSON or base64 transport.

use std::fmt;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

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

/// Reference-counted immutable scene; the last host reference frees the tree.
#[derive(uniffi::Object)]
pub struct RasterScene {
    scene: inku_svg_raster::PreparedScene,
}

#[uniffi::export]
impl RasterScene {
    pub fn source_byte_count(&self) -> u64 {
        self.scene.source_bytes()
    }
    pub fn cache_cost_bytes(&self) -> u64 {
        self.scene.cache_cost_bytes()
    }
    pub fn intrinsic_width(&self) -> f64 {
        self.scene.intrinsic_width()
    }
    pub fn intrinsic_height(&self) -> f64 {
        self.scene.intrinsic_height()
    }

    pub fn rasterize(
        &self,
        target_width: Option<u32>,
        target_height: Option<u32>,
    ) -> Result<RasterFrame, RasterFailure> {
        catch_unwind(AssertUnwindSafe(|| {
            self.scene
                .rasterize(RasterOptions {
                    target_width,
                    target_height,
                })
                .map(frame)
                .map_err(Into::into)
        }))
        .unwrap_or(Err(RasterFailure::InternalInvariant))
    }

    pub fn region(
        &self,
        full_width: u32,
        full_height: u32,
        x: u32,
        y: u32,
        width: u32,
        height: u32,
    ) -> Result<RasterFrame, RasterFailure> {
        catch_unwind(AssertUnwindSafe(|| {
            self.scene
                .region(inku_svg_raster::RasterRegionOptions {
                    full_width,
                    full_height,
                    x,
                    y,
                    width,
                    height,
                })
                .map(frame)
                .map_err(Into::into)
        }))
        .unwrap_or(Err(RasterFailure::InternalInvariant))
    }
}

#[uniffi::export]
pub fn prepare_raster_scene(svg: String) -> Result<Arc<RasterScene>, RasterFailure> {
    catch_unwind(AssertUnwindSafe(|| {
        Ok(Arc::new(RasterScene {
            scene: inku_svg_raster::prepare_scene(&svg)?,
        }))
    }))
    .unwrap_or(Err(RasterFailure::InternalInvariant))
}

pub(crate) fn frame(output: inku_svg_raster::RasterOutput) -> RasterFrame {
    RasterFrame {
        width: output.width,
        height: output.height,
        stride: output.stride,
        pixel_format: output.pixel_format.to_owned(),
        pixels: output.pixels,
    }
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

/// Export tiles reuse the original SVG tree with an explicit canvas transform.
#[uniffi::export]
pub fn rasterize_svg_region(
    svg: String,
    full_width: u32,
    full_height: u32,
    x: u32,
    y: u32,
    width: u32,
    height: u32,
) -> Result<RasterFrame, RasterFailure> {
    catch_unwind(AssertUnwindSafe(|| {
        let output = inku_svg_raster::rasterize_region(
            &svg,
            inku_svg_raster::RasterRegionOptions {
                full_width,
                full_height,
                x,
                y,
                width,
                height,
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

/// `measure` of the autonomous refinement (the visible-difference gate), or
/// `None` for its other actions, which the pipeline answers. Both drawings are
/// made here, with the shared rasterizer, so that the three apps count the
/// same pixels.
pub(crate) fn measure_visible_difference(input: &[u8]) -> Option<Vec<u8>> {
    use inku_pipeline::autonomous_refine::{
        GATE_SIZE, gate_square, measure_answer, measure_refusal, visible_count,
    };

    #[derive(serde::Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Measure {
        #[allow(dead_code)]
        action: String,
        before: String,
        after: String,
    }

    let request: serde_json::Value = serde_json::from_slice(input).ok()?;
    if request.get("action").and_then(serde_json::Value::as_str) != Some("measure") {
        return None;
    }
    let Ok(measure) = serde_json::from_value::<Measure>(request) else {
        return Some(br#"{"error":"invalid_request"}"#.to_vec());
    };
    let draw = |svg: &str, which: &str| {
        let output = inku_svg_raster::rasterize(
            svg,
            RasterOptions {
                target_width: Some(GATE_SIZE),
                target_height: Some(GATE_SIZE),
            },
        )
        .map_err(|error| format!("{which}: {error}"))?;
        gate_square(
            output.width,
            output.height,
            output.stride,
            &output.pixels,
            GATE_SIZE,
        )
        .ok_or_else(|| format!("{which}: the drawing does not fit the gate's square"))
    };
    Some(
        match (
            draw(&measure.before, "before"),
            draw(&measure.after, "after"),
        ) {
            (Ok(before), Ok(after)) => match visible_count(&before, &after, GATE_SIZE) {
                Some(count) => measure_answer(count),
                None => measure_refusal(
                    "not_drawable",
                    "the drawings do not fill the gate's square".to_owned(),
                ),
            },
            (Err(detail), _) | (_, Err(detail)) => measure_refusal("not_drawable", detail),
        },
    )
}
