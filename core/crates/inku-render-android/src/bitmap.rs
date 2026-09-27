use inku_svg_raster::RasterOutput;

use crate::BindingError;

fn copy_rgba_rows(
    output: &RasterOutput,
    destination: &mut [u8],
    destination_stride: usize,
) -> Result<(), BindingError> {
    if output.pixel_format != inku_svg_raster::PIXEL_FORMAT_RGBA8_PREMULTIPLIED {
        return Err(BindingError::state("unsupported raster pixel format"));
    }
    let row_bytes = usize::try_from(output.width)
        .ok()
        .and_then(|width| width.checked_mul(4))
        .ok_or_else(|| BindingError::state("raster row length overflow"))?;
    let source_stride = output.stride as usize;
    let height = output.height as usize;
    if output.width == 0
        || output.height == 0
        || source_stride < row_bytes
        || destination_stride < row_bytes
        || source_stride
            .checked_mul(height)
            .is_none_or(|size| size > output.pixels.len())
        || destination_stride
            .checked_mul(height)
            .is_none_or(|size| size > destination.len())
    {
        return Err(BindingError::state("invalid raster or Bitmap row layout"));
    }

    for row in 0..height {
        let source = row * source_stride;
        let target = row * destination_stride;
        destination[target..target + row_bytes]
            .copy_from_slice(&output.pixels[source..source + row_bytes]);
    }
    Ok(())
}

#[cfg(target_os = "android")]
mod android {
    use super::*;
    use std::ffi::c_void;
    use std::ptr::null_mut;

    use jni::JNIEnv;
    use jni::objects::{JObject, JValue};
    use jni::sys::jobject;

    const ANDROID_BITMAP_FORMAT_RGBA_8888: i32 = 1;
    const ANDROID_BITMAP_FLAGS_IS_HARDWARE: u32 = 1 << 31;

    #[repr(C)]
    #[derive(Default)]
    struct AndroidBitmapInfo {
        width: u32,
        height: u32,
        stride: u32,
        format: i32,
        flags: u32,
    }

    #[link(name = "jnigraphics")]
    unsafe extern "C" {
        fn AndroidBitmap_getInfo(
            env: *mut jni::sys::JNIEnv,
            bitmap: jobject,
            info: *mut AndroidBitmapInfo,
        ) -> i32;
        fn AndroidBitmap_lockPixels(
            env: *mut jni::sys::JNIEnv,
            bitmap: jobject,
            pixels: *mut *mut c_void,
        ) -> i32;
        fn AndroidBitmap_unlockPixels(env: *mut jni::sys::JNIEnv, bitmap: jobject) -> i32;
    }

    struct LockedPixels {
        env: *mut jni::sys::JNIEnv,
        bitmap: jobject,
        pixels: *mut u8,
        locked: bool,
    }

    impl LockedPixels {
        fn lock(env: &JNIEnv<'_>, bitmap: &JObject<'_>) -> Result<Self, BindingError> {
            let mut pixels = null_mut();
            let native_env = env.get_native_interface();
            // SAFETY: Both JNI handles are live for this call; AndroidBitmap_lockPixels
            // initializes the pointer on success and requires one matching unlock.
            let status =
                unsafe { AndroidBitmap_lockPixels(native_env, bitmap.as_raw(), &mut pixels) };
            if status != 0 {
                return Err(BindingError::state(format!(
                    "Bitmap pixel lock failed: {status}"
                )));
            }
            let lock = Self {
                env: native_env,
                bitmap: bitmap.as_raw(),
                pixels: pixels.cast(),
                locked: true,
            };
            if lock.pixels.is_null() {
                return Err(BindingError::state(
                    "Bitmap pixel lock returned a null address",
                ));
            }
            Ok(lock)
        }

        fn unlock(mut self) -> Result<(), BindingError> {
            self.locked = false;
            // SAFETY: This balances the successful lock, once, before the JNI
            // bitmap reference and environment leave the current call.
            let status = unsafe { AndroidBitmap_unlockPixels(self.env, self.bitmap) };
            if status != 0 {
                return Err(BindingError::state(format!(
                    "Bitmap pixel unlock failed: {status}"
                )));
            }
            Ok(())
        }
    }

    impl Drop for LockedPixels {
        fn drop(&mut self) {
            if self.locked {
                // SAFETY: The guard only exists after a successful lock and its
                // JNI references remain live throughout this synchronous call.
                unsafe { AndroidBitmap_unlockPixels(self.env, self.bitmap) };
            }
        }
    }

    pub(crate) fn bitmap_from_raster(
        env: &mut JNIEnv<'_>,
        output: &RasterOutput,
    ) -> Result<jobject, BindingError> {
        let config = env
            .get_static_field(
                "android/graphics/Bitmap$Config",
                "ARGB_8888",
                "Landroid/graphics/Bitmap$Config;",
            )
            .and_then(|value| value.l())
            .map_err(|error| {
                BindingError::state(format!("Bitmap config lookup failed: {error}"))
            })?;
        let bitmap = env
            .call_static_method(
                "android/graphics/Bitmap",
                "createBitmap",
                "(IILandroid/graphics/Bitmap$Config;)Landroid/graphics/Bitmap;",
                &[
                    JValue::Int(output.width as i32),
                    JValue::Int(output.height as i32),
                    JValue::Object(&config),
                ],
            )
            .and_then(|value| value.l())
            .map_err(|error| BindingError::state(format!("Bitmap allocation failed: {error}")))?;

        let mut info = AndroidBitmapInfo::default();
        // SAFETY: JNI references and the output struct are live for the native call.
        let status = unsafe {
            AndroidBitmap_getInfo(env.get_native_interface(), bitmap.as_raw(), &mut info)
        };
        if status != 0 {
            return Err(BindingError::state(format!(
                "Bitmap info lookup failed: {status}"
            )));
        }
        if info.width != output.width
            || info.height != output.height
            || info.format != ANDROID_BITMAP_FORMAT_RGBA_8888
            || info.flags & ANDROID_BITMAP_FLAGS_IS_HARDWARE != 0
        {
            return Err(BindingError::state("Bitmap dimensions or format mismatch"));
        }
        let premultiplied = env
            .call_method(&bitmap, "isPremultiplied", "()Z", &[])
            .and_then(|value| value.z())
            .map_err(|error| {
                BindingError::state(format!("Bitmap alpha mode lookup failed: {error}"))
            })?;
        if !premultiplied {
            return Err(BindingError::state("Bitmap is not premultiplied"));
        }
        let destination_size = (info.stride as usize)
            .checked_mul(info.height as usize)
            .ok_or_else(|| BindingError::state("Bitmap byte length overflow"))?;
        let lock = LockedPixels::lock(env, &bitmap)?;
        // SAFETY: A successful lock keeps the allocation stationary. getInfo
        // supplies its row stride and height, and this slice ends before unlock.
        let destination = unsafe { std::slice::from_raw_parts_mut(lock.pixels, destination_size) };
        copy_rgba_rows(output, destination, info.stride as usize)?;
        lock.unlock()?;
        Ok(bitmap.into_raw())
    }
}

#[cfg(target_os = "android")]
pub(crate) use android::bitmap_from_raster;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn copies_premultiplied_rgba_by_row_without_touching_padding() {
        let raster = RasterOutput {
            width: 2,
            height: 2,
            stride: 12,
            pixel_format: inku_svg_raster::PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
            pixels: vec![
                128, 0, 0, 128, 0, 64, 0, 64, 91, 92, 93, 94, 0, 0, 255, 255, 64, 64, 64, 64, 95,
                96, 97, 98,
            ],
        };
        let mut destination = vec![42; 32];
        copy_rgba_rows(&raster, &mut destination, 16).expect("rows");
        assert_eq!(
            destination,
            vec![
                128, 0, 0, 128, 0, 64, 0, 64, 42, 42, 42, 42, 42, 42, 42, 42, 0, 0, 255, 255, 64,
                64, 64, 64, 42, 42, 42, 42, 42, 42, 42, 42
            ]
        );
    }
}
