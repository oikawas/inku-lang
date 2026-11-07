//! Owned presentation pixels without a JSON or base64 transport.

use std::fmt;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

use inku_svg_raster::{RasterError, RasterOptions};

#[cfg(feature = "display")]
use crate::display::DisplayImage;

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

/// Host-supplied fonts, loaded once and reused across prepared SVG scenes.
#[derive(uniffi::Object)]
pub struct RasterFonts {
    fonts: inku_svg_raster::PreparedFonts,
}

#[uniffi::export]
impl RasterFonts {
    pub fn prepare_scene(&self, svg: String) -> Result<Arc<RasterScene>, RasterFailure> {
        catch_unwind(AssertUnwindSafe(|| {
            Ok(Arc::new(RasterScene {
                scene: inku_svg_raster::prepare_scene_with_fonts(&svg, &self.fonts)?,
            }))
        }))
        .unwrap_or(Err(RasterFailure::InternalInvariant))
    }
}

/// Load explicit font files once for repeated scene preparation.
#[uniffi::export]
pub fn prepare_raster_fonts(font_files: Vec<String>) -> Result<Arc<RasterFonts>, RasterFailure> {
    catch_unwind(AssertUnwindSafe(|| {
        Ok(Arc::new(RasterFonts {
            fonts: inku_svg_raster::prepare_fonts(&font_files)?,
        }))
    }))
    .unwrap_or(Err(RasterFailure::InternalInvariant))
}

/// Prepare one scene with explicitly supplied font files.
#[uniffi::export]
pub fn prepare_raster_scene_with_fonts(
    svg: String,
    font_files: Vec<String>,
) -> Result<Arc<RasterScene>, RasterFailure> {
    prepare_raster_fonts(font_files)?.prepare_scene(svg)
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

/// The raster scene's images, which the display feature's image carries.
#[cfg(feature = "display")]
#[uniffi::export]
impl RasterScene {
    /// [`Self::rasterize`] as an image the host reads in place, without
    /// copying the pixels through a Record (I-732, 2026-11-07).
    pub fn rasterize_image(
        &self,
        target_width: Option<u32>,
        target_height: Option<u32>,
    ) -> Result<Arc<DisplayImage>, RasterFailure> {
        catch_unwind(AssertUnwindSafe(|| {
            self.scene
                .rasterize(RasterOptions {
                    target_width,
                    target_height,
                })
                .map(DisplayImage::of)
                .map_err(Into::into)
        }))
        .unwrap_or(Err(RasterFailure::InternalInvariant))
    }

    /// [`Self::region`] as an image the host reads in place.
    pub fn region_image(
        &self,
        full_width: u32,
        full_height: u32,
        x: u32,
        y: u32,
        width: u32,
        height: u32,
    ) -> Result<Arc<DisplayImage>, RasterFailure> {
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
                .map(DisplayImage::of)
                .map_err(Into::into)
        }))
        .unwrap_or(Err(RasterFailure::InternalInvariant))
    }
}

/// [`rasterize_svg`] as an image the host reads in place (I-732, 2026-11-07).
#[cfg(feature = "display")]
#[uniffi::export]
pub fn rasterize_svg_image(
    svg: String,
    target_width: Option<u32>,
    target_height: Option<u32>,
) -> Result<Arc<DisplayImage>, RasterFailure> {
    catch_unwind(AssertUnwindSafe(|| {
        inku_svg_raster::rasterize(
            &svg,
            RasterOptions {
                target_width,
                target_height,
            },
        )
        .map(DisplayImage::of)
        .map_err(Into::into)
    }))
    .unwrap_or(Err(RasterFailure::InternalInvariant))
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
            RasterError::FontFile { .. } => "font_file_unreadable",
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

#[cfg(test)]
mod font_tests {
    use super::*;

    fn noto_serif() -> String {
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../server/src/inku_server/fonts/NotoSerifJP-Variable.ttf")
            .to_string_lossy()
            .into_owned()
    }

    #[test]
    fn explicit_font_draws_text_and_can_be_reused_without_system_fonts() {
        let svg = r#"<svg xmlns="http://www.w3.org/2000/svg" width="200" height="80"><text x="4" y="55" font-size="36" font-family="Noto Serif JP">文字 Hello</text></svg>"#;
        let old = prepare_raster_scene(svg.to_owned())
            .unwrap()
            .rasterize(None, Some(80))
            .unwrap();
        let empty = prepare_raster_scene_with_fonts(svg.to_owned(), vec![])
            .unwrap()
            .rasterize(None, Some(80))
            .unwrap();
        assert_eq!(old.pixels, empty.pixels);
        assert!(
            old.pixels
                .as_chunks::<4>()
                .0
                .iter()
                .all(|pixel| pixel[3] == 0)
        );
        let font_files = vec![noto_serif()];
        let fonts = prepare_raster_fonts(font_files.clone()).unwrap();
        let first = fonts
            .prepare_scene(svg.to_owned())
            .unwrap()
            .rasterize(None, Some(80))
            .unwrap();
        let second = fonts
            .prepare_scene(svg.to_owned())
            .unwrap()
            .rasterize(None, Some(80))
            .unwrap();
        let direct = prepare_raster_scene_with_fonts(svg.to_owned(), font_files)
            .unwrap()
            .rasterize(None, Some(80))
            .unwrap();
        assert!(
            first
                .pixels
                .as_chunks::<4>()
                .0
                .iter()
                .any(|pixel| pixel[3] != 0)
        );
        assert_eq!(first.pixels, second.pixels);
        assert_eq!(first.pixels, direct.pixels);
    }

    #[test]
    fn unreadable_fonts_are_refused_and_plain_art_is_unchanged() {
        let missing = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("missing-font-file-for-raster-test.ttf")
            .to_string_lossy()
            .into_owned();
        assert!(matches!(
            prepare_raster_scene_with_fonts("<svg/>".to_owned(), vec![missing.clone()]),
            Err(RasterFailure::Refused { code, .. }) if code == "font_file_unreadable"
        ));
        assert!(
            matches!(prepare_raster_fonts(vec![missing]), Err(RasterFailure::Refused { code, .. }) if code == "font_file_unreadable")
        );
        let svg = r##"<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="#123456"/></svg>"##;
        let old = prepare_raster_scene(svg.to_owned())
            .unwrap()
            .rasterize(None, Some(20))
            .unwrap();
        let with_font = prepare_raster_scene_with_fonts(svg.to_owned(), vec![noto_serif()])
            .unwrap()
            .rasterize(None, Some(20))
            .unwrap();
        assert_eq!(old.pixels, with_font.pixels);
        assert_eq!(
            old.pixels,
            rasterize_svg(svg.to_owned(), None, Some(20))
                .unwrap()
                .pixels
        );
    }

    /// The images hold the very pixels the frames copy (I-732).
    #[cfg(feature = "display")]
    #[test]
    fn images_hold_the_frames_pixels() {
        let svg = r##"<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><rect width="12" height="10" fill="#123456"/></svg>"##;
        let scene = prepare_raster_scene(svg.to_owned()).unwrap();
        let frame = scene.rasterize(Some(40), None).unwrap();
        for image in [
            scene.rasterize_image(Some(40), None).unwrap(),
            rasterize_svg_image(svg.to_owned(), Some(40), None).unwrap(),
        ] {
            assert_eq!(
                (image.width(), image.height(), image.stride()),
                (frame.width, frame.height, frame.stride)
            );
            assert_eq!(image.pixel_format(), frame.pixel_format);
            assert_eq!(image.raster().pixels, frame.pixels);
        }
        let region = scene.region(40, 20, 8, 4, 16, 8).unwrap();
        let image = scene.region_image(40, 20, 8, 4, 16, 8).unwrap();
        assert_eq!(image.raster().pixels, region.pixels);
    }
}
