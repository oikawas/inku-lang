//! Host-neutral raster presentation for canonical inku SVG artifacts.

#![forbid(unsafe_code)]

use std::fmt;

use resvg::tiny_skia::{Pixmap, Transform};
use resvg::usvg;
use serde::{Deserialize, Serialize};

/// Version of the host-neutral raster request/output boundary.
pub const RASTER_API_VERSION: &str = "0.1.0";
/// Byte layout returned by [`rasterize`].
pub const PIXEL_FORMAT_RGBA8_PREMULTIPLIED: &str = "rgba8-premultiplied";

/// Maximum accepted UTF-8 SVG payload size.
pub const MAX_SVG_BYTES: usize = 8 * 1024 * 1024;
/// Maximum accepted or derived output dimension.
pub const MAX_RASTER_DIMENSION: u32 = 8_192;
/// Maximum accepted output pixel allocation.
pub const MAX_RASTER_PIXELS: u64 = 16_777_216;

/// Fit request for one SVG artifact.
///
/// At least one dimension is required. Supplying both defines a containing box;
/// the output remains content-sized and preserves the SVG's intrinsic aspect.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RasterOptions {
    pub target_width: Option<u32>,
    pub target_height: Option<u32>,
}

/// Explicit host-neutral raster payload.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RasterOutput {
    pub width: u32,
    pub height: u32,
    pub stride: u32,
    pub pixel_format: &'static str,
    pub pixels: Vec<u8>,
}

/// Validation, parse, and allocation failures at the raster boundary.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RasterError {
    EmptySvg,
    SvgTooLarge { actual: usize, maximum: usize },
    MissingTargetDimension,
    InvalidTargetDimension,
    TargetDimensionTooLarge { actual: u32, maximum: u32 },
    InvalidIntrinsicSize,
    DerivedDimensionTooLarge,
    PixelCountTooLarge { actual: u64, maximum: u64 },
    ByteLengthOverflow,
    Parse(String),
    AllocationFailed,
}

impl fmt::Display for RasterError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptySvg => formatter.write_str("SVG input is empty"),
            Self::SvgTooLarge { actual, maximum } => {
                write!(
                    formatter,
                    "SVG input is {actual} bytes; maximum is {maximum}"
                )
            }
            Self::MissingTargetDimension => {
                formatter.write_str("target_width or target_height is required")
            }
            Self::InvalidTargetDimension => {
                formatter.write_str("target dimensions must be greater than zero")
            }
            Self::TargetDimensionTooLarge { actual, maximum } => write!(
                formatter,
                "target dimension {actual} exceeds maximum {maximum}"
            ),
            Self::InvalidIntrinsicSize => {
                formatter.write_str("SVG intrinsic dimensions are invalid")
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
            Self::ByteLengthOverflow => formatter.write_str("raster byte length overflow"),
            Self::Parse(message) => write!(formatter, "SVG parse failed: {message}"),
            Self::AllocationFailed => formatter.write_str("raster allocation failed"),
        }
    }
}

impl std::error::Error for RasterError {}

/// Report the raster boundary version independently from Render Engine identity.
#[must_use]
pub const fn raster_api_version() -> &'static str {
    RASTER_API_VERSION
}

fn validate_requested_dimension(dimension: Option<u32>) -> Result<(), RasterError> {
    let Some(dimension) = dimension else {
        return Ok(());
    };
    if dimension == 0 {
        return Err(RasterError::InvalidTargetDimension);
    }
    if dimension > MAX_RASTER_DIMENSION {
        return Err(RasterError::TargetDimensionTooLarge {
            actual: dimension,
            maximum: MAX_RASTER_DIMENSION,
        });
    }
    Ok(())
}

fn rounded_dimension(value: f64) -> Result<u32, RasterError> {
    if !value.is_finite() || value <= 0.0 || value > f64::from(u32::MAX) {
        return Err(RasterError::DerivedDimensionTooLarge);
    }
    let rounded = value.round().max(1.0);
    if rounded > f64::from(MAX_RASTER_DIMENSION) {
        return Err(RasterError::DerivedDimensionTooLarge);
    }
    Ok(rounded as u32)
}

fn output_geometry(
    intrinsic_width: f64,
    intrinsic_height: f64,
    options: RasterOptions,
) -> Result<(u32, u32, f32), RasterError> {
    validate_requested_dimension(options.target_width)?;
    validate_requested_dimension(options.target_height)?;
    if options.target_width.is_none() && options.target_height.is_none() {
        return Err(RasterError::MissingTargetDimension);
    }
    if !intrinsic_width.is_finite()
        || !intrinsic_height.is_finite()
        || intrinsic_width <= 0.0
        || intrinsic_height <= 0.0
    {
        return Err(RasterError::InvalidIntrinsicSize);
    }

    let (width, height, scale) = match (options.target_width, options.target_height) {
        (Some(target_width), Some(target_height)) => {
            let scale = (f64::from(target_width) / intrinsic_width)
                .min(f64::from(target_height) / intrinsic_height);
            let width = rounded_dimension(intrinsic_width * scale)?.min(target_width);
            let height = rounded_dimension(intrinsic_height * scale)?.min(target_height);
            (width, height, scale)
        }
        (Some(target_width), None) => {
            let scale = f64::from(target_width) / intrinsic_width;
            let height = rounded_dimension(intrinsic_height * scale)?;
            (target_width, height, scale)
        }
        (None, Some(target_height)) => {
            let scale = f64::from(target_height) / intrinsic_height;
            let width = rounded_dimension(intrinsic_width * scale)?;
            (width, target_height, scale)
        }
        (None, None) => unreachable!("missing dimensions rejected above"),
    };

    let pixel_count = u64::from(width)
        .checked_mul(u64::from(height))
        .ok_or(RasterError::ByteLengthOverflow)?;
    if pixel_count > MAX_RASTER_PIXELS {
        return Err(RasterError::PixelCountTooLarge {
            actual: pixel_count,
            maximum: MAX_RASTER_PIXELS,
        });
    }
    pixel_count
        .checked_mul(4)
        .and_then(|value| usize::try_from(value).ok())
        .ok_or(RasterError::ByteLengthOverflow)?;

    let scale = scale as f32;
    if !scale.is_finite() || scale <= 0.0 {
        return Err(RasterError::DerivedDimensionTooLarge);
    }
    Ok((width, height, scale))
}

/// Parse and rasterize one immutable SVG artifact into premultiplied RGBA8.
///
/// `resvg` is compiled without its default text, system-font, and raster-image
/// features. `resources_dir` remains unset, so this boundary neither discovers
/// host fonts nor resolves SVG resources from the filesystem or network.
pub fn rasterize(svg: &str, options: RasterOptions) -> Result<RasterOutput, RasterError> {
    if svg.is_empty() {
        return Err(RasterError::EmptySvg);
    }
    if svg.len() > MAX_SVG_BYTES {
        return Err(RasterError::SvgTooLarge {
            actual: svg.len(),
            maximum: MAX_SVG_BYTES,
        });
    }

    let parser_options = usvg::Options {
        resources_dir: None,
        ..usvg::Options::default()
    };
    let tree = usvg::Tree::from_str(svg, &parser_options)
        .map_err(|error| RasterError::Parse(error.to_string()))?;
    let intrinsic = tree.size();
    let (width, height, scale) = output_geometry(
        f64::from(intrinsic.width()),
        f64::from(intrinsic.height()),
        options,
    )?;
    let stride = width
        .checked_mul(4)
        .ok_or(RasterError::ByteLengthOverflow)?;
    let mut pixmap = Pixmap::new(width, height).ok_or(RasterError::AllocationFailed)?;
    resvg::render(
        &tree,
        Transform::from_scale(scale, scale),
        &mut pixmap.as_mut(),
    );
    let pixels = pixmap.take();
    debug_assert_eq!(pixels.len(), stride as usize * height as usize);
    Ok(RasterOutput {
        width,
        height,
        stride,
        pixel_format: PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
        pixels,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};

    const RED_RECT: &str = r##"<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><rect width="100" height="50" fill="#ff0000"/></svg>"##;

    #[test]
    fn boundary_and_pixel_format_are_explicit() {
        assert_eq!(raster_api_version(), "0.1.0");
        let output = rasterize(
            RED_RECT,
            RasterOptions {
                target_width: Some(2),
                target_height: None,
            },
        )
        .expect("raster");
        assert_eq!(output.pixel_format, "rgba8-premultiplied");
        assert_eq!((output.width, output.height, output.stride), (2, 1, 8));
        assert_eq!(output.pixels, vec![255, 0, 0, 255, 255, 0, 0, 255]);
    }

    #[test]
    fn containing_box_is_content_sized_and_preserves_aspect() {
        let output = rasterize(
            RED_RECT,
            RasterOptions {
                target_width: Some(200),
                target_height: Some(200),
            },
        )
        .expect("raster");
        assert_eq!((output.width, output.height), (200, 100));
    }

    #[test]
    fn one_dimension_derives_the_other_from_intrinsic_aspect() {
        let by_width = rasterize(
            RED_RECT,
            RasterOptions {
                target_width: Some(50),
                target_height: None,
            },
        )
        .expect("width raster");
        let by_height = rasterize(
            RED_RECT,
            RasterOptions {
                target_width: None,
                target_height: Some(20),
            },
        )
        .expect("height raster");
        assert_eq!((by_width.width, by_width.height), (50, 25));
        assert_eq!((by_height.width, by_height.height), (40, 20));
    }

    #[test]
    fn alpha_bytes_are_premultiplied_rgba() {
        let output = rasterize(
            r##"<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><rect width="1" height="1" fill="#00ff00" fill-opacity="0.5"/></svg>"##,
            RasterOptions {
                target_width: Some(1),
                target_height: None,
            },
        )
        .expect("raster");
        let [red, green, blue, alpha] = output.pixels[..] else {
            panic!("one RGBA pixel");
        };
        assert_eq!((red, blue, alpha), (0, 0, 128));
        assert!(green <= alpha && green >= 127);
    }

    #[test]
    fn clip_and_gradient_render_without_host_resources() {
        let svg = r##"<svg xmlns="http://www.w3.org/2000/svg" width="4" height="2"><defs><linearGradient id="g"><stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff"/></linearGradient><clipPath id="c"><rect width="2" height="2"/></clipPath></defs><rect width="4" height="2" fill="url(#g)" clip-path="url(#c)"/></svg>"##;
        let output = rasterize(
            svg,
            RasterOptions {
                target_width: Some(4),
                target_height: None,
            },
        )
        .expect("raster");
        for y in 0..2 {
            assert!(output.pixels[y * 16 + 3] > 0);
            assert!(output.pixels[y * 16 + 7] > 0);
            assert_eq!(output.pixels[y * 16 + 11], 0);
            assert_eq!(output.pixels[y * 16 + 15], 0);
        }
    }

    #[test]
    fn accepted_current_and_historical_svg_samples_rasterize_unchanged() {
        let samples = [
            include_str!(
                "../../../../server/reference/render-engine-41/C-filter-display-pencil.svg"
            ),
            include_str!("../../../../server/reference/render-engine-41/C-ground-washi.svg"),
            include_str!(
                "../../../../server/reference/render-engine-41/C-fill-circle-computer.svg"
            ),
            include_str!("../../../../server/reference/render-engine-21/G-scatter-edge.svg"),
        ];
        for svg in samples {
            let output = rasterize(
                svg,
                RasterOptions {
                    target_width: Some(64),
                    target_height: Some(64),
                },
            )
            .expect("accepted SVG sample");
            assert!(output.width <= 64);
            assert!(output.height <= 64);
            assert_eq!(
                output.pixels.len(),
                output.stride as usize * output.height as usize
            );
        }
    }

    #[test]
    fn parity_fixture_raw_pixel_digests_are_stable() {
        let samples = [
            (
                "A-pen-circle",
                include_str!("../../../../server/reference/render-engine-41/A-pen-circle.svg"),
                (64, 64, 256),
                "89f77c560b97e360ab740f1045da304c63df9ee55f44b111599f2484ef3d29a2",
            ),
            (
                "C-filter-display-pencil",
                include_str!(
                    "../../../../server/reference/render-engine-41/C-filter-display-pencil.svg"
                ),
                (64, 64, 256),
                "165e04ac91ff11bb05fcb99953d11100c9bdb63c9a2bf7e3144485cf130fa780",
            ),
            (
                "D-canvas-wide-region-single",
                include_str!(
                    "../../../../server/reference/render-engine-41/D-canvas-wide-region-single.svg"
                ),
                (64, 27, 256),
                "2912d5b6746b74b5f60b57d07c97b1b770b1443f33e18e9785b2037050eb88fe",
            ),
            (
                "engine21-scatter-edge",
                include_str!("../../../../server/reference/render-engine-21/G-scatter-edge.svg"),
                (64, 64, 256),
                "1bbb4da477413c3f65f1732cff3e03afaf3f5417736ea929f2bbd8c3de223368",
            ),
        ];
        for (name, svg, geometry, expected_digest) in samples {
            let output = rasterize(
                svg,
                RasterOptions {
                    target_width: Some(64),
                    target_height: Some(64),
                },
            )
            .expect("parity raster");
            let digest = Sha256::digest(&output.pixels)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>();
            assert_eq!(
                (output.width, output.height, output.stride),
                geometry,
                "{name}"
            );
            assert_eq!(digest, expected_digest, "{name}");
        }
    }

    #[test]
    fn invalid_and_oversize_requests_fail_before_allocation() {
        assert_eq!(
            rasterize(
                RED_RECT,
                RasterOptions {
                    target_width: None,
                    target_height: None,
                }
            ),
            Err(RasterError::MissingTargetDimension)
        );
        assert_eq!(
            rasterize(
                RED_RECT,
                RasterOptions {
                    target_width: Some(0),
                    target_height: None,
                }
            ),
            Err(RasterError::InvalidTargetDimension)
        );
        assert!(matches!(
            rasterize(
                RED_RECT,
                RasterOptions {
                    target_width: Some(MAX_RASTER_DIMENSION),
                    target_height: Some(MAX_RASTER_DIMENSION),
                }
            ),
            Err(RasterError::PixelCountTooLarge { .. })
        ));
    }

    #[test]
    fn svg_input_size_is_bounded() {
        let oversized = " ".repeat(MAX_SVG_BYTES + 1);
        assert!(matches!(
            rasterize(
                &oversized,
                RasterOptions {
                    target_width: Some(1),
                    target_height: None,
                }
            ),
            Err(RasterError::SvgTooLarge { .. })
        ));
    }
}
