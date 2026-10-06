//! Where a picture is drawn: the whole work fitted to a box, a window on a larger
//! canvas, and the tiles a window is drawn in.
//!
//! The limits are the display raster's (`inku-svg-raster`), so a request the resvg
//! path accepts is accepted here too.

use inku_svg_raster::{
    MAX_RASTER_DIMENSION, MAX_RASTER_PIXELS, RasterOptions, RasterRegionOptions,
};

use crate::DisplayError;

/// Longest side of the first, coarse picture of a work (the author's decision,
/// 2026-10-06: a 256px whole first, then 512px tiles in parallel).
pub const COARSE_SIDE: u32 = 256;
/// Side of one tile.
pub const TILE_SIDE: u32 = 512;
/// Largest side of the full canvas a window is cut from (as the export tiles).
pub const MAX_CANVAS_SIDE: u32 = 120_000;
/// Largest full canvas a window is cut from (as the export tiles).
pub const MAX_CANVAS_PIXELS: u64 = 144_000_000;

/// A window on a canvas `full_width` × `full_height` pixels, with the scale that
/// maps the work's user units to those pixels.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Window {
    pub scale: f32,
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

/// The whole work, keeping its aspect, inside the box the options give.
pub fn fit(intrinsic: (f64, f64), options: RasterOptions) -> Result<Window, DisplayError> {
    check_dimension(options.target_width)?;
    check_dimension(options.target_height)?;
    let (width, height) = intrinsic;
    if !(width.is_finite() && height.is_finite() && width > 0.0 && height > 0.0) {
        return Err(DisplayError::InvalidIntrinsicSize);
    }
    let (scale, out_width, out_height) = match (options.target_width, options.target_height) {
        (Some(target_width), Some(target_height)) => {
            let scale = (f64::from(target_width) / width).min(f64::from(target_height) / height);
            (
                scale,
                rounded(width * scale)?.min(target_width),
                rounded(height * scale)?.min(target_height),
            )
        }
        (Some(target_width), None) => {
            let scale = f64::from(target_width) / width;
            (scale, target_width, rounded(height * scale)?)
        }
        (None, Some(target_height)) => {
            let scale = f64::from(target_height) / height;
            (scale, rounded(width * scale)?, target_height)
        }
        (None, None) => return Err(DisplayError::MissingTargetDimension),
    };
    check_pixels(out_width, out_height)?;
    let scale = scale as f32;
    if !(scale.is_finite() && scale > 0.0) {
        return Err(DisplayError::DerivedDimensionTooLarge);
    }
    Ok(Window {
        scale,
        x: 0,
        y: 0,
        width: out_width,
        height: out_height,
    })
}

/// The whole work fitted to the box, as a window covering its own canvas, so a host
/// can draw the whole in tiles of the same size [`fit`] gives.
pub fn whole(
    intrinsic: (f64, f64),
    options: RasterOptions,
) -> Result<RasterRegionOptions, DisplayError> {
    let fitted = fit(intrinsic, options)?;
    Ok(RasterRegionOptions {
        full_width: fitted.width,
        full_height: fitted.height,
        x: 0,
        y: 0,
        width: fitted.width,
        height: fitted.height,
    })
}

/// A window on a full canvas, as `inku_svg_raster::rasterize_region` takes it.
pub fn region(intrinsic: (f64, f64), region: RasterRegionOptions) -> Result<Window, DisplayError> {
    if region.full_width == 0
        || region.full_height == 0
        || region.full_width > MAX_CANVAS_SIDE
        || region.full_height > MAX_CANVAS_SIDE
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
        return Err(DisplayError::InvalidTargetDimension);
    }
    let full = u64::from(region.full_width) * u64::from(region.full_height);
    if full > MAX_CANVAS_PIXELS {
        return Err(DisplayError::PixelCountTooLarge {
            actual: full,
            maximum: MAX_CANVAS_PIXELS,
        });
    }
    check_dimension(Some(region.width))?;
    check_dimension(Some(region.height))?;
    check_pixels(region.width, region.height)?;
    let (width, height) = intrinsic;
    let scale =
        (region.full_width as f32 / width as f32).min(region.full_height as f32 / height as f32);
    if !(scale.is_finite() && scale > 0.0) {
        return Err(DisplayError::InvalidIntrinsicSize);
    }
    Ok(Window {
        scale,
        x: region.x,
        y: region.y,
        width: region.width,
        height: region.height,
    })
}

/// The tiles covering `window` on the same canvas, nearest to the window's centre first,
/// so what the viewer looks at comes first.
pub fn tiles(window: RasterRegionOptions, side: u32) -> Vec<RasterRegionOptions> {
    let side = side.max(1);
    let (center_x, center_y) = (
        f64::from(window.x) + f64::from(window.width) / 2.0,
        f64::from(window.y) + f64::from(window.height) / 2.0,
    );
    let mut tiles = Vec::new();
    let (right, bottom) = (window.x + window.width, window.y + window.height);
    let mut y = window.y;
    while y < bottom {
        let height = side.min(bottom - y);
        let mut x = window.x;
        while x < right {
            let width = side.min(right - x);
            tiles.push(RasterRegionOptions {
                width,
                height,
                x,
                y,
                ..window
            });
            x += width;
        }
        y += height;
    }
    let distance = |tile: &RasterRegionOptions| {
        let dx = f64::from(tile.x) + f64::from(tile.width) / 2.0 - center_x;
        let dy = f64::from(tile.y) + f64::from(tile.height) / 2.0 - center_y;
        dx * dx + dy * dy
    };
    tiles.sort_by(|a, b| {
        distance(a)
            .total_cmp(&distance(b))
            .then((a.y, a.x).cmp(&(b.y, b.x)))
    });
    tiles
}

fn check_dimension(dimension: Option<u32>) -> Result<(), DisplayError> {
    match dimension {
        Some(0) => Err(DisplayError::InvalidTargetDimension),
        Some(actual) if actual > MAX_RASTER_DIMENSION => {
            Err(DisplayError::TargetDimensionTooLarge {
                actual,
                maximum: MAX_RASTER_DIMENSION,
            })
        }
        _ => Ok(()),
    }
}

fn check_pixels(width: u32, height: u32) -> Result<(), DisplayError> {
    let pixels = u64::from(width) * u64::from(height);
    if pixels > MAX_RASTER_PIXELS {
        return Err(DisplayError::PixelCountTooLarge {
            actual: pixels,
            maximum: MAX_RASTER_PIXELS,
        });
    }
    Ok(())
}

fn rounded(value: f64) -> Result<u32, DisplayError> {
    if !(value.is_finite() && value > 0.0) {
        return Err(DisplayError::DerivedDimensionTooLarge);
    }
    let rounded = value.round().max(1.0);
    if rounded > f64::from(MAX_RASTER_DIMENSION) {
        return Err(DisplayError::DerivedDimensionTooLarge);
    }
    Ok(rounded as u32)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn window(x: u32, y: u32, width: u32, height: u32) -> RasterRegionOptions {
        RasterRegionOptions {
            full_width: 4000,
            full_height: 4000,
            x,
            y,
            width,
            height,
        }
    }

    #[test]
    fn tiles_cover_the_window_once_from_the_centre() {
        let tiles = tiles(window(100, 50, 1300, 700), TILE_SIDE);
        assert_eq!(tiles.len(), 3 * 2);
        let area: u64 = tiles
            .iter()
            .map(|t| u64::from(t.width) * u64::from(t.height))
            .sum();
        assert_eq!(area, 1300 * 700);
        // The middle column holds the centre (750, 400).
        assert_eq!((tiles[0].x, tiles[0].y), (612, 50));
        assert!(
            tiles
                .iter()
                .all(|t| t.full_width == 4000 && t.x + t.width <= 1400 && t.y + t.height <= 750)
        );
    }

    #[test]
    fn fit_keeps_the_aspect_and_the_raster_limits() {
        let coarse = fit(
            (707.0, 1000.0),
            RasterOptions {
                target_width: Some(COARSE_SIDE),
                target_height: Some(COARSE_SIDE),
            },
        )
        .unwrap();
        assert_eq!((coarse.width, coarse.height), (181, 256));
        assert!(matches!(
            fit(
                (1000.0, 1000.0),
                RasterOptions {
                    target_width: Some(8193),
                    target_height: None
                }
            ),
            Err(DisplayError::TargetDimensionTooLarge { .. })
        ));
        let options = RasterOptions {
            target_width: Some(640),
            target_height: Some(640),
        };
        let covering = whole((1000.0, 601.0), options).unwrap();
        assert_eq!((covering.full_width, covering.full_height), (640, 385));
        assert_eq!(
            (covering.x, covering.y, covering.width, covering.height),
            (0, 0, 640, 385)
        );
        assert_eq!(
            region((1000.0, 601.0), covering).unwrap().scale,
            fit((1000.0, 601.0), options).unwrap().scale
        );
        let large = RasterRegionOptions {
            full_width: 8000,
            full_height: 8000,
            ..window(0, 0, 4097, 4097)
        };
        assert!(matches!(
            region((1000.0, 1000.0), large),
            Err(DisplayError::PixelCountTooLarge { .. })
        ));
    }
}
