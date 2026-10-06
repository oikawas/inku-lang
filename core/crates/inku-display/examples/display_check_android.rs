//! Development-only JNI bridge, packaged into Android's instrumentation APK.
//! It calls the same comparison module as tests/skia.rs, without enabling Skia.

#![cfg(target_os = "android")]

#[path = "../tests/common/difference.rs"]
mod comparison;

use std::io::Cursor;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr::null_mut;

use inku_display::{PIXEL_FORMAT_RGBA8_PREMULTIPLIED, RasterOutput};
use jni::JNIEnv;
use jni::objects::{JByteArray, JObject, JValue};
use jni::sys::{jint, jobject};

fn raw(
    env: &JNIEnv<'_>,
    width: jint,
    height: jint,
    stride: jint,
    bytes: JByteArray<'_>,
) -> Result<RasterOutput, String> {
    if width <= 0 || height <= 0 || stride < width.checked_mul(4).ok_or("row overflow")? {
        return Err("invalid raster dimensions".into());
    }
    let pixels = env
        .convert_byte_array(bytes)
        .map_err(|error| error.to_string())?;
    let length = (stride as usize)
        .checked_mul(height as usize)
        .ok_or("length overflow")?;
    if pixels.len() != length {
        return Err("invalid raster length".into());
    }
    Ok(RasterOutput {
        width: width as u32,
        height: height as u32,
        stride: stride as u32,
        pixel_format: PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
        pixels,
    })
}

fn png_white(bytes: &[u8]) -> Result<(usize, usize, Vec<[f64; 3]>), String> {
    let mut decoder = png::Decoder::new(Cursor::new(bytes));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder.read_info().map_err(|error| error.to_string())?;
    let mut data = vec![0; reader.output_buffer_size().ok_or("PNG size overflow")?];
    let info = reader
        .next_frame(&mut data)
        .map_err(|error| error.to_string())?;
    let channels = match info.color_type {
        png::ColorType::Rgb => 3,
        png::ColorType::Rgba => 4,
        _ => return Err("expected RGB/RGBA reference PNG".into()),
    };
    let pixels = data[..info.buffer_size()]
        .chunks_exact(channels)
        .map(|pixel| {
            let alpha = if channels == 4 {
                f64::from(pixel[3]) / 255.0
            } else {
                1.0
            };
            [0, 1, 2].map(|i| f64::from(pixel[i]) * alpha + 255.0 * (1.0 - alpha))
        })
        .collect();
    Ok((info.width as usize, info.height as usize, pixels))
}

fn boundary(
    mut env: JNIEnv<'_>,
    operation: impl FnOnce(&mut JNIEnv<'_>) -> Result<comparison::Difference, String>,
) -> jobject {
    let result = catch_unwind(AssertUnwindSafe(|| {
        let difference = operation(&mut env)?;
        env.new_object(
            "app/inku/mobile/render/NativeDisplayDifference",
            "(ZDD)V",
            &[
                JValue::Bool(u8::from(difference.passes())),
                JValue::Double(difference.worst_block),
                JValue::Double(difference.differing),
            ],
        )
        .map(JObject::into_raw)
        .map_err(|error| error.to_string())
    }));
    match result {
        Ok(Ok(value)) => value,
        failure => {
            let message = match failure {
                Ok(Err(message)) => message,
                _ => "display comparison panicked".into(),
            };
            let _ = env.throw_new("java/lang/IllegalArgumentException", message);
            null_mut()
        }
    }
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayChecks_comparePng(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    width: jint,
    height: jint,
    stride: jint,
    actual: JByteArray<'_>,
    reference: JByteArray<'_>,
) -> jobject {
    boundary(env, |env| {
        let actual = raw(env, width, height, stride, actual)?;
        let reference = env
            .convert_byte_array(reference)
            .map_err(|error| error.to_string())?;
        let (reference_width, reference_height, reference) = png_white(&reference)?;
        if (reference_width, reference_height) != (width as usize, height as usize) {
            return Err("reference dimensions differ".into());
        }
        Ok(comparison::difference(
            width as usize,
            height as usize,
            &comparison::over_white(&actual),
            &reference,
        ))
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayChecks_compareRaw(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    width: jint,
    height: jint,
    actual_stride: jint,
    actual: JByteArray<'_>,
    reference_stride: jint,
    reference: JByteArray<'_>,
) -> jobject {
    boundary(env, |env| {
        let actual = raw(env, width, height, actual_stride, actual)?;
        let reference = raw(env, width, height, reference_stride, reference)?;
        Ok(comparison::difference(
            width as usize,
            height as usize,
            &comparison::over_white(&actual),
            &comparison::over_white(&reference),
        ))
    })
}
