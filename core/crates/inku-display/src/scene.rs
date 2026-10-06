//! The Skia scene: read once, record a `Picture`, replay windows from any thread.
//!
//! Stage 1 found a replayed picture byte-identical to drawing the SVG directly, and
//! eight threads replaying one picture at once identical to one thread. Skia's SVG
//! DOM is neither `Send` nor `Sync`, so it lives only inside `prepare_scene`.

use skia_safe::svg::Dom;
use skia_safe::{
    AlphaType, Canvas, Color, ColorType, FontMgr, ImageInfo, Picture, PictureRecorder, Rect,
};

use crate::geometry::{self, Window};
use crate::{
    DisplayError, PIXEL_FORMAT_RGBA8_PREMULTIPLIED, RasterOptions, RasterOutput,
    RasterRegionOptions, Rewrites, display_svg,
};

/// One recorded work. `Send + Sync`: hosts draw its tiles on several threads.
pub struct DisplayScene {
    picture: Picture,
    width: f64,
    height: f64,
    source_bytes: u64,
    rewrites: Rewrites,
}

/// Check, rewrite, read and record one stored SVG.
pub fn prepare_scene(svg: &str) -> Result<DisplayScene, DisplayError> {
    let display = display_svg(svg)?;
    let size = (display.width as f32, display.height as f32);
    // No fonts: the support table has no text, and nothing is looked up on the host.
    let mut dom =
        Dom::from_str(&display.svg, FontMgr::empty()).map_err(|_| DisplayError::SkiaLoad)?;
    dom.set_container_size(size);
    let mut recorder = PictureRecorder::new();
    let canvas = recorder.begin_recording(Rect::from_wh(size.0, size.1), false);
    dom.render(canvas);
    let picture = recorder
        .finish_recording_as_picture(None)
        .ok_or(DisplayError::SkiaLoad)?;
    Ok(DisplayScene {
        picture,
        width: display.width,
        height: display.height,
        source_bytes: svg.len() as u64,
        rewrites: display.rewrites,
    })
}

impl DisplayScene {
    pub fn intrinsic_width(&self) -> f64 {
        self.width
    }
    pub fn intrinsic_height(&self) -> f64 {
        self.height
    }
    pub fn source_bytes(&self) -> u64 {
        self.source_bytes
    }
    pub fn rewrites(&self) -> Rewrites {
        self.rewrites
    }
    /// Skia's estimate of the recorded picture, for a host's cache weight.
    pub fn picture_bytes(&self) -> u64 {
        self.picture.approximate_bytes_used() as u64
    }

    /// The whole work fitted to the box.
    pub fn rasterize(&self, options: RasterOptions) -> Result<RasterOutput, DisplayError> {
        self.draw(geometry::fit((self.width, self.height), options)?)
    }

    /// The whole work fitted to the box, as a window to draw in tiles.
    pub fn whole(&self, options: RasterOptions) -> Result<RasterRegionOptions, DisplayError> {
        geometry::whole((self.width, self.height), options)
    }

    /// A window on a canvas `full_width` × `full_height` pixels.
    pub fn region(&self, region: RasterRegionOptions) -> Result<RasterOutput, DisplayError> {
        self.draw(geometry::region((self.width, self.height), region)?)
    }

    fn draw(&self, window: Window) -> Result<RasterOutput, DisplayError> {
        let stride = window.width as usize * 4;
        let length = stride * window.height as usize;
        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(length)
            .map_err(|_| DisplayError::AllocationFailed)?;
        pixels.resize(length, 0);
        let info = ImageInfo::new(
            (window.width as i32, window.height as i32),
            ColorType::RGBA8888,
            AlphaType::Premul,
            None,
        );
        {
            let canvas = Canvas::from_raster_direct(&info, &mut pixels, stride, None)
                .ok_or(DisplayError::AllocationFailed)?;
            canvas.clear(Color::TRANSPARENT);
            canvas.translate((-(window.x as f32), -(window.y as f32)));
            canvas.scale((window.scale, window.scale));
            canvas.draw_picture(&self.picture, None, None);
        }
        Ok(RasterOutput {
            width: window.width,
            height: window.height,
            stride: stride as u32,
            pixel_format: PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
            pixels,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_scene_is_shared_across_threads() {
        fn shared<T: Send + Sync>() {}
        shared::<DisplayScene>();
    }
}
