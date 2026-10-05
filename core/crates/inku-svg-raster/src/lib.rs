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

/// A bounded tile on a larger export canvas. The original SVG remains intact.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RasterRegionOptions {
    pub full_width: u32,
    pub full_height: u32,
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
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

/// Immutable parsed SVG data owned by a host, with no global scene registry.
pub struct PreparedScene {
    tree: usvg::Tree,
    source_bytes: u64,
    cache_cost_bytes: u64,
}

impl PreparedScene {
    pub fn source_bytes(&self) -> u64 {
        self.source_bytes
    }
    pub fn intrinsic_width(&self) -> f64 {
        f64::from(self.tree.size().width())
    }
    pub fn intrinsic_height(&self) -> f64 {
        f64::from(self.tree.size().height())
    }

    /// Conservative cache admission weight, not allocator accounting or RSS.
    pub fn cache_cost_bytes(&self) -> u64 {
        self.cache_cost_bytes
    }

    pub fn rasterize(&self, options: RasterOptions) -> Result<RasterOutput, RasterError> {
        rasterize_tree(&self.tree, options)
    }

    pub fn region(&self, region: RasterRegionOptions) -> Result<RasterOutput, RasterError> {
        rasterize_tree_region(&self.tree, region)
    }
}

/// Reuse exactly the same parser options as the one-shot display/export calls.
pub fn prepare_scene(svg: &str) -> Result<PreparedScene, RasterError> {
    let tree = parse_tree(svg)?;
    let source_bytes = svg.len() as u64;
    // Count expanded geometry too: repeated <use> nodes can outgrow source text.
    let cache_cost_bytes = scene_cost(&tree).saturating_add(source_bytes.saturating_mul(16));
    Ok(PreparedScene {
        tree,
        source_bytes,
        cache_cost_bytes,
    })
}

fn validate_svg(svg: &str) -> Result<(), RasterError> {
    if svg.is_empty() {
        return Err(RasterError::EmptySvg);
    }
    if svg.len() > MAX_SVG_BYTES {
        return Err(RasterError::SvgTooLarge {
            actual: svg.len(),
            maximum: MAX_SVG_BYTES,
        });
    }
    Ok(())
}

fn parse_tree(svg: &str) -> Result<usvg::Tree, RasterError> {
    validate_svg(svg)?;
    usvg::Tree::from_str(
        svg,
        &usvg::Options {
            resources_dir: None,
            ..usvg::Options::default()
        },
    )
    .map_err(|error| RasterError::Parse(error.to_string()))
}

fn scene_cost(tree: &usvg::Tree) -> u64 {
    fn group_cost(group: &usvg::Group) -> u64 {
        let mut bytes = (std::mem::size_of::<usvg::Group>()
            + group.id().len()
            + group.children().len() * 2 * std::mem::size_of::<usvg::Node>())
            as u64;
        for node in group.children() {
            let cost = match node {
                usvg::Node::Group(group) => group_cost(group),
                usvg::Node::Path(path) => {
                    let dash = path
                        .stroke()
                        .and_then(|stroke| stroke.dasharray())
                        .map_or(0, |values| values.len() * 8);
                    (std::mem::size_of::<usvg::Path>()
                        + path.id().len()
                        + dash
                        + path.data().points().len() * 16
                        + path.data().verbs().len() * 2) as u64
                }
                usvg::Node::Image(image) => {
                    let data = match image.kind() {
                        usvg::ImageKind::SVG(svg) => scene_cost(svg),
                        usvg::ImageKind::JPEG(data)
                        | usvg::ImageKind::PNG(data)
                        | usvg::ImageKind::GIF(data)
                        | usvg::ImageKind::WEBP(data) => data.len() as u64,
                    };
                    data.saturating_add(std::mem::size_of::<usvg::Image>() as u64)
                }
                // Text is disabled in this crate. Source weight also covers metadata.
                usvg::Node::Text(_) => 2048,
            };
            bytes = bytes.saturating_add(cost);
        }
        bytes
    }
    let mut bytes = group_cost(tree.root());
    for pattern in tree.patterns() {
        bytes = bytes.saturating_add(group_cost(pattern.root()));
    }
    for clip in tree.clip_paths() {
        bytes = bytes.saturating_add(group_cost(clip.root()));
    }
    for mask in tree.masks() {
        bytes = bytes.saturating_add(group_cost(mask.root()));
    }
    for filter in tree.filters() {
        bytes = bytes.saturating_add(
            (std::mem::size_of::<usvg::filter::Filter>()
                + filter.primitives().len() * 2 * std::mem::size_of::<usvg::filter::Primitive>())
                as u64,
        );
    }
    bytes
}

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
    rasterize_tree(&parse_tree(svg)?, options)
}

fn rasterize_tree(tree: &usvg::Tree, options: RasterOptions) -> Result<RasterOutput, RasterError> {
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
        tree,
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

/// Render a tile from the original tree rather than wrapping or clipping its SVG.
/// Each output tile obeys the display raster budget; the full export canvas is
/// limited to 144 million pixels and 120,000 pixels on either side.
pub fn rasterize_region(
    svg: &str,
    region: RasterRegionOptions,
) -> Result<RasterOutput, RasterError> {
    validate_svg(svg)?;
    validate_region(region)?;
    rasterize_tree_region(&parse_tree(svg)?, region)
}

fn validate_region(region: RasterRegionOptions) -> Result<(), RasterError> {
    if region.full_width == 0
        || region.full_height == 0
        || region.full_width > 120_000
        || region.full_height > 120_000
        || region.width == 0
        || region.height == 0
        || region
            .x
            .checked_add(region.width)
            .is_none_or(|end| end > region.full_width)
        || region
            .y
            .checked_add(region.height)
            .is_none_or(|end| end > region.full_height)
    {
        return Err(RasterError::InvalidTargetDimension);
    }
    validate_requested_dimension(Some(region.width))?;
    validate_requested_dimension(Some(region.height))?;
    let full_pixels = u64::from(region.full_width) * u64::from(region.full_height);
    if full_pixels > 144_000_000 {
        return Err(RasterError::PixelCountTooLarge {
            actual: full_pixels,
            maximum: 144_000_000,
        });
    }
    let pixels = u64::from(region.width) * u64::from(region.height);
    if pixels > MAX_RASTER_PIXELS {
        return Err(RasterError::PixelCountTooLarge {
            actual: pixels,
            maximum: MAX_RASTER_PIXELS,
        });
    }
    Ok(())
}

fn rasterize_tree_region(
    tree: &usvg::Tree,
    region: RasterRegionOptions,
) -> Result<RasterOutput, RasterError> {
    validate_region(region)?;
    let intrinsic = tree.size();
    let scale = (region.full_width as f32 / intrinsic.width())
        .min(region.full_height as f32 / intrinsic.height());
    if !scale.is_finite() || scale <= 0.0 {
        return Err(RasterError::InvalidIntrinsicSize);
    }
    let stride = region
        .width
        .checked_mul(4)
        .ok_or(RasterError::ByteLengthOverflow)?;
    let mut pixmap =
        Pixmap::new(region.width, region.height).ok_or(RasterError::AllocationFailed)?;
    let transform =
        Transform::from_scale(scale, scale).post_translate(-(region.x as f32), -(region.y as f32));
    resvg::render(tree, transform, &mut pixmap.as_mut());
    Ok(RasterOutput {
        width: region.width,
        height: region.height,
        stride,
        pixel_format: PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
        pixels: pixmap.take(),
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
