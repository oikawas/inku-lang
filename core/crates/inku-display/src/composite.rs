//! A shared joined pixel allocation. Drawing never holds the pixel lock.

#[cfg(feature = "skia")]
use std::sync::Arc;
use std::sync::Mutex;

use crate::{DisplayError, PIXEL_FORMAT_RGBA8_PREMULTIPLIED, RasterOutput, RasterRegionOptions};

struct CompositePixels {
    window: RasterRegionOptions,
    pixels: Mutex<Option<RasterOutput>>,
}

impl CompositePixels {
    fn new(window: RasterRegionOptions) -> Result<Self, DisplayError> {
        // Validate before calculating lengths or allocating the joined window.
        crate::geometry::region((1.0, 1.0), window)?;
        let stride = window.width * 4;
        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(stride as usize * window.height as usize)
            .map_err(|_| DisplayError::AllocationFailed)?;
        pixels.resize(stride as usize * window.height as usize, 0);
        Ok(Self {
            window,
            pixels: Mutex::new(Some(RasterOutput {
                width: window.width,
                height: window.height,
                stride,
                pixel_format: PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
                pixels,
            })),
        })
    }

    fn check_tile(&self, tile: RasterRegionOptions) -> Result<(), DisplayError> {
        let window = self.window;
        if tile.full_width != window.full_width
            || tile.full_height != window.full_height
            || tile.width == 0
            || tile.height == 0
            || tile.x < window.x
            || tile.y < window.y
            || tile
                .x
                .checked_add(tile.width)
                .is_none_or(|end| end > window.x + window.width)
            || tile
                .y
                .checked_add(tile.height)
                .is_none_or(|end| end > window.y + window.height)
        {
            return Err(DisplayError::InvalidTargetDimension);
        }
        Ok(())
    }

    fn write(&self, tile: RasterRegionOptions, drawn: &RasterOutput) -> Result<(), DisplayError> {
        self.check_tile(tile)?;
        let row_bytes = tile.width as usize * 4;
        if drawn.width != tile.width
            || drawn.height != tile.height
            || drawn.pixel_format != PIXEL_FORMAT_RGBA8_PREMULTIPLIED
            || (drawn.stride as usize) < row_bytes
            || drawn.pixels.len() < drawn.stride as usize * drawn.height as usize
        {
            return Err(DisplayError::InvalidTargetDimension);
        }
        let mut joined = self
            .pixels
            .lock()
            .expect("display composite pixel lock poisoned");
        let joined = joined.as_mut().ok_or(DisplayError::CompositeFinished)?;
        for row in 0..tile.height as usize {
            let at = (tile.y as usize - self.window.y as usize + row) * joined.stride as usize
                + (tile.x as usize - self.window.x as usize) * 4;
            let from = row * drawn.stride as usize;
            joined.pixels[at..at + row_bytes]
                .copy_from_slice(&drawn.pixels[from..from + row_bytes]);
        }
        Ok(())
    }

    fn snapshot(&self) -> Result<RasterOutput, DisplayError> {
        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(self.window.width as usize * 4 * self.window.height as usize)
            .map_err(|_| DisplayError::AllocationFailed)?;
        let joined = self
            .pixels
            .lock()
            .expect("display composite pixel lock poisoned");
        let joined = joined.as_ref().ok_or(DisplayError::CompositeFinished)?;
        pixels.extend_from_slice(&joined.pixels);
        Ok(RasterOutput {
            width: joined.width,
            height: joined.height,
            stride: joined.stride,
            pixel_format: joined.pixel_format,
            pixels,
        })
    }

    fn finish(&self) -> Result<RasterOutput, DisplayError> {
        self.pixels
            .lock()
            .expect("display composite pixel lock poisoned")
            .take()
            .ok_or(DisplayError::CompositeFinished)
    }
}

/// One scene and one window allocation, shared by the host's tile workers. The
/// host owns cancellation and must join all workers before `finish`. It may take
/// immutable snapshots between tiles. Finished pixels no longer own the scene.
#[cfg(feature = "skia")]
pub struct DisplayComposite {
    scene: Arc<crate::DisplayScene>,
    joined: CompositePixels,
}

#[cfg(feature = "skia")]
impl DisplayComposite {
    pub fn new(
        scene: Arc<crate::DisplayScene>,
        window: RasterRegionOptions,
    ) -> Result<Self, DisplayError> {
        crate::geometry::region((scene.intrinsic_width(), scene.intrinsic_height()), window)?;
        Ok(Self {
            scene,
            joined: CompositePixels::new(window)?,
        })
    }

    /// Draw first, outside the lock, then copy just this tile into the window.
    /// Tile pixels never travel through the host or through binding serialization.
    pub fn render_tile(&self, tile: RasterRegionOptions) -> Result<(), DisplayError> {
        self.joined.check_tile(tile)?;
        let drawn = self.scene.region(tile)?;
        self.joined.write(tile, &drawn)
    }

    pub fn snapshot(&self) -> Result<RasterOutput, DisplayError> {
        self.joined.snapshot()
    }

    /// Move the original allocation to the image, once. Late writes are refused.
    pub fn finish(&self) -> Result<RasterOutput, DisplayError> {
        self.joined.finish()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // The new shared buffer must keep stride/placement right across workers,
    // isolate snapshots and move (not copy) the finished allocation.
    #[test]
    fn shared_display_parallel_tiles_snapshot_and_finished_allocation() {
        let window = RasterRegionOptions {
            full_width: 10,
            full_height: 10,
            x: 3,
            y: 4,
            width: 3,
            height: 2,
        };
        let joined = CompositePixels::new(window).unwrap();
        let address = joined
            .pixels
            .lock()
            .unwrap()
            .as_ref()
            .unwrap()
            .pixels
            .as_ptr();
        let snapshot = joined.snapshot().unwrap();
        std::thread::scope(|scope| {
            for (x, width, color) in [(3, 2, [128, 0, 0, 128]), (5, 1, [0, 0, 255, 255])] {
                let joined = &joined;
                scope.spawn(move || {
                    let tile = RasterRegionOptions { x, width, ..window };
                    let mut pixels = Vec::new();
                    for _ in 0..2 {
                        for _ in 0..width {
                            pixels.extend_from_slice(&color);
                        }
                        pixels.extend_from_slice(&[99; 4]); // source row padding
                    }
                    let drawn = RasterOutput {
                        width,
                        height: 2,
                        stride: (width + 1) * 4,
                        pixel_format: PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
                        pixels,
                    };
                    joined.write(tile, &drawn).unwrap();
                });
            }
        });
        let image = joined.finish().unwrap();
        assert_eq!(image.pixels.as_ptr(), address);
        assert!(snapshot.pixels.iter().all(|&byte| byte == 0));
        assert_ne!(snapshot.pixels.as_ptr(), address);
        for row in image.pixels.chunks(image.stride as usize) {
            assert_eq!(row, [128, 0, 0, 128, 128, 0, 0, 128, 0, 0, 255, 255]);
        }
        assert!(matches!(
            joined.write(window, &image),
            Err(DisplayError::CompositeFinished)
        ));
        assert!(matches!(
            joined.finish(),
            Err(DisplayError::CompositeFinished)
        ));
        drop(joined);
        assert_eq!(image.pixels.len(), 24); // image owns the allocation after the composer leaves
    }
}
