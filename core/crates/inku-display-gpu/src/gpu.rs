//! Graphite on Metal. One context and one recorder, used on the thread that made
//! them: the program reads, draws and answers one request at a time.

use std::ffi::{c_char, c_void};

use inku_display::{
    DisplayError, DisplayScene, PIXEL_FORMAT_RGBA8_PREMULTIPLIED, RasterOutput, RasterRegionOptions,
};
use skia_safe::gpu::{Mipmapped, graphite};
use skia_safe::{AlphaType, ColorType, ImageInfo};

#[link(name = "Metal", kind = "framework")]
unsafe extern "C" {
    /// Returns a retained device (`NS_RETURNS_RETAINED`), or null.
    fn MTLCreateSystemDefaultDevice() -> *mut c_void;
}

#[link(name = "objc")]
unsafe extern "C" {
    fn sel_registerName(name: *const c_char) -> *mut c_void;
    fn objc_msgSend();
    fn objc_release(object: *mut c_void);
}

/// `MTLGPUFamilyApple7`: M1 and every later Apple silicon Mac. Graphite also runs on
/// Intel Macs (`MTLGPUFamilyMac2`), which the app leaves on the CPU (author, 2026-10-11).
const MTL_GPU_FAMILY_APPLE7: isize = 1007;

/// Why a window was not drawn. `code` goes to the app's display failure log.
#[derive(Debug)]
pub struct GpuError {
    pub code: &'static str,
    pub message: String,
}

impl GpuError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

impl From<DisplayError> for GpuError {
    fn from(error: DisplayError) -> Self {
        Self::new(error.code(), error.to_string())
    }
}

/// Fields drop in order: the recorder before the context it records for.
pub struct GpuWindows {
    recorder: graphite::Recorder,
    context: graphite::Context,
    _backend: graphite::mtl::BackendContext,
}

impl GpuWindows {
    pub fn new() -> Result<Self, GpuError> {
        let backend = metal_backend()?;
        let mut context =
            graphite::mtl::context_factory::make_metal(&backend, None).ok_or_else(|| {
                GpuError::new("gpu_context", "Graphite could not make a Metal context")
            })?;
        let recorder = context
            .make_recorder(None)
            .ok_or_else(|| GpuError::new("gpu_recorder", "Graphite could not make a recorder"))?;
        Ok(Self {
            recorder,
            context,
            _backend: backend,
        })
    }

    /// The window `region` of the scene, drawn as the CPU draws it (`paint_region`)
    /// and read back as premultiplied RGBA8.
    pub fn draw(
        &mut self,
        scene: &DisplayScene,
        region: RasterRegionOptions,
    ) -> Result<RasterOutput, GpuError> {
        // Refuse a bad window before asking the GPU for a surface of its size.
        inku_display::geometry::region(
            (scene.intrinsic_width(), scene.intrinsic_height()),
            region,
        )?;
        let info = ImageInfo::new(
            (region.width as i32, region.height as i32),
            ColorType::RGBA8888,
            AlphaType::Premul,
            None,
        );
        let mut surface =
            graphite::surfaces::render_target(&mut self.recorder, &info, Mipmapped::No, None, None)
                .ok_or_else(|| {
                    GpuError::new(
                        "gpu_surface",
                        format!("no {}x{} surface", region.width, region.height),
                    )
                })?;
        scene.paint_region(surface.canvas(), region)?;
        let mut recording = self
            .recorder
            .snap()
            .ok_or_else(|| GpuError::new("gpu_snap", "the recorder gave no recording"))?;
        let status = self
            .context
            .insert_recording(&graphite::InsertRecordingInfo::new(&mut recording));
        if !matches!(status, graphite::InsertStatus::Success) {
            return Err(GpuError::new(
                "gpu_insert",
                format!("insert_recording: {status:?}"),
            ));
        }
        let stride = region.width as usize * 4;
        let length = stride * region.height as usize;
        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(length)
            .map_err(|_| DisplayError::AllocationFailed)?;
        pixels.resize(length, 0);
        if !self
            .context
            .read_pixels(&mut surface, &info, &mut pixels, stride, (0, 0))
        {
            return Err(GpuError::new("gpu_read", "reading the window back failed"));
        }
        Ok(RasterOutput {
            width: region.width,
            height: region.height,
            stride: stride as u32,
            pixel_format: PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
            pixels,
        })
    }
}

/// The system's Metal device and a command queue, when the device is Apple silicon.
fn metal_backend() -> Result<graphite::mtl::BackendContext, GpuError> {
    // SAFETY: `MTLCreateSystemDefaultDevice` and the two messages are Metal's public
    // API; `objc_msgSend` is called through the exact signature of each method
    // (`-supportsFamily:(MTLGPUFamily)` returns BOOL, `-newCommandQueue` returns a
    // retained queue). Both retained objects are released once the backend context,
    // which retains them itself, holds them.
    unsafe {
        let device = MTLCreateSystemDefaultDevice();
        if device.is_null() {
            return Err(GpuError::new("gpu_unavailable", "no Metal device"));
        }
        let message = objc_msgSend as unsafe extern "C" fn();
        let supports_family: unsafe extern "C" fn(*mut c_void, *mut c_void, isize) -> bool =
            std::mem::transmute(message);
        if !supports_family(
            device,
            sel_registerName(c"supportsFamily:".as_ptr()),
            MTL_GPU_FAMILY_APPLE7,
        ) {
            objc_release(device);
            return Err(GpuError::new(
                "gpu_unsupported",
                "the Metal device is not Apple silicon (MTLGPUFamilyApple7)",
            ));
        }
        let new_command_queue: unsafe extern "C" fn(*mut c_void, *mut c_void) -> *mut c_void =
            std::mem::transmute(message);
        let queue = new_command_queue(device, sel_registerName(c"newCommandQueue".as_ptr()));
        if queue.is_null() {
            objc_release(device);
            return Err(GpuError::new("gpu_queue", "Metal gave no command queue"));
        }
        let backend = graphite::mtl::BackendContext::new(device, queue);
        objc_release(queue);
        objc_release(device);
        Ok(backend)
    }
}
