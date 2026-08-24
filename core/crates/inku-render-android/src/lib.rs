//! Thin synchronous JNI transport for the shared render and raster cores.

use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr::null_mut;

use inku_render::types::RenderRequest;
use inku_svg_raster::RasterOptions;
use jni::JNIEnv;
use jni::objects::{JObject, JString, JValue};
use jni::sys::{jobject, jstring};

const RENDER_OUTPUT_CLASS: &str = "app/inku/mobile/render/NativeRenderOutput";
const RENDER_OUTPUT_SIGNATURE: &str = "(Ljava/lang/String;Ljava/lang/String;)V";
const RASTER_OUTPUT_CLASS: &str = "app/inku/mobile/render/NativeRasterOutput";
const RASTER_OUTPUT_SIGNATURE: &str = "(IIILjava/lang/String;[B)V";

#[derive(Debug)]
struct BindingError {
    exception_class: &'static str,
    message: String,
}

impl BindingError {
    fn invalid(message: impl Into<String>) -> Self {
        Self {
            exception_class: "java/lang/IllegalArgumentException",
            message: message.into(),
        }
    }

    fn state(message: impl Into<String>) -> Self {
        Self {
            exception_class: "java/lang/IllegalStateException",
            message: message.into(),
        }
    }
}

fn jni_boundary<T>(
    mut env: JNIEnv<'_>,
    failure_value: T,
    action: impl FnOnce(&mut JNIEnv<'_>) -> Result<T, BindingError>,
) -> T {
    match catch_unwind(AssertUnwindSafe(|| action(&mut env))) {
        Ok(Ok(value)) => value,
        Ok(Err(error)) => {
            let _ = env.throw_new(error.exception_class, error.message);
            failure_value
        }
        Err(_) => {
            let _ = env.throw_new(
                "java/lang/IllegalStateException",
                "native Rust panic at JNI boundary",
            );
            failure_value
        }
    }
}

fn java_string(env: &mut JNIEnv<'_>, value: JString<'_>) -> Result<String, BindingError> {
    env.get_string(&value)
        .map(Into::into)
        .map_err(|error| BindingError::invalid(format!("invalid Java string: {error}")))
}

fn new_java_string(env: &mut JNIEnv<'_>, value: &str) -> Result<jstring, BindingError> {
    env.new_string(value)
        .map(JString::into_raw)
        .map_err(|error| BindingError::state(format!("Java string allocation failed: {error}")))
}

fn parse_render_request(request_json: &str) -> Result<RenderRequest, BindingError> {
    serde_json::from_str(request_json)
        .map_err(|error| BindingError::invalid(format!("invalid render request: {error}")))
}

fn parse_raster_options(options_json: &str) -> Result<RasterOptions, BindingError> {
    serde_json::from_str(options_json)
        .map_err(|error| BindingError::invalid(format!("invalid raster options: {error}")))
}

/// Return the shared Render Core host-boundary version.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeRenderBridge_coreApiVersion(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(env, inku_render::core_api_version())
    })
}

/// Return the shared raster boundary version.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeRenderBridge_rasterApiVersion(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(env, inku_svg_raster::raster_api_version())
    })
}

/// Return the engine id from the canonical Rust owner.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeRenderBridge_renderEngineId(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(env, inku_render::render_engine_identity().0)
    })
}

/// Return the engine version from the canonical Rust owner.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeRenderBridge_renderEngineVersion(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(env, inku_render::render_engine_identity().1)
    })
}

/// Serialize the core-owned default color map for host freshness checks.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeRenderBridge_defaultColorMapJson(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let json =
            serde_json::to_string(&inku_render::palette::default_color_map()).map_err(|error| {
                BindingError::state(format!("default color map serialization failed: {error}"))
            })?;
        new_java_string(env, &json)
    })
}

/// Serialize renderer-owned reference data from the canonical Rust owner.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeRenderBridge_rendererReferenceJson(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let json = serde_json::to_string(&inku_render::reference::renderer_reference()).map_err(
            |error| {
                BindingError::state(format!("renderer reference serialization failed: {error}"))
            },
        )?;
        new_java_string(env, &json)
    })
}

/// Render one canonical request and return SVG plus metadata in one JNI call.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeRenderBridge_render(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    request_json: JString<'_>,
) -> jobject {
    jni_boundary(env, null_mut(), |env| {
        let request_json = java_string(env, request_json)?;
        let request = parse_render_request(&request_json)?;
        let output = inku_render::render::render(request)
            .map_err(|error| BindingError::state(format!("render failed: {error}")))?;
        let metadata_json = serde_json::to_string(&output.metadata).map_err(|error| {
            BindingError::state(format!("metadata serialization failed: {error}"))
        })?;

        let svg = env.new_string(output.svg).map_err(|error| {
            BindingError::state(format!("SVG Java string allocation failed: {error}"))
        })?;
        let metadata = env.new_string(metadata_json).map_err(|error| {
            BindingError::state(format!("metadata Java string allocation failed: {error}"))
        })?;
        let svg_object = JObject::from(svg);
        let metadata_object = JObject::from(metadata);
        env.new_object(
            RENDER_OUTPUT_CLASS,
            RENDER_OUTPUT_SIGNATURE,
            &[
                JValue::Object(&svg_object),
                JValue::Object(&metadata_object),
            ],
        )
        .map(JObject::into_raw)
        .map_err(|error| {
            BindingError::state(format!("NativeRenderOutput construction failed: {error}"))
        })
    })
}

/// Rasterize one immutable SVG artifact into one explicit raw-pixel result.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeRenderBridge_rasterize(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    svg: JString<'_>,
    raster_options_json: JString<'_>,
) -> jobject {
    jni_boundary(env, null_mut(), |env| {
        let svg = java_string(env, svg)?;
        let raster_options_json = java_string(env, raster_options_json)?;
        let options = parse_raster_options(&raster_options_json)?;
        let output = inku_svg_raster::rasterize(&svg, options)
            .map_err(|error| BindingError::invalid(format!("rasterize failed: {error}")))?;

        let pixel_format = env.new_string(output.pixel_format).map_err(|error| {
            BindingError::state(format!(
                "pixel format Java string allocation failed: {error}"
            ))
        })?;
        let pixels = env.byte_array_from_slice(&output.pixels).map_err(|error| {
            BindingError::state(format!("pixel byte array allocation failed: {error}"))
        })?;
        let pixel_format_object = JObject::from(pixel_format);
        let pixels_object = JObject::from(pixels);
        env.new_object(
            RASTER_OUTPUT_CLASS,
            RASTER_OUTPUT_SIGNATURE,
            &[
                JValue::Int(output.width as i32),
                JValue::Int(output.height as i32),
                JValue::Int(output.stride as i32),
                JValue::Object(&pixel_format_object),
                JValue::Object(&pixels_object),
            ],
        )
        .map(JObject::into_raw)
        .map_err(|error| {
            BindingError::state(format!("NativeRasterOutput construction failed: {error}"))
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request_json(render_seed: &str, composition_seed: &str) -> String {
        format!(
            r#"{{"score":{{"instructions":[]}},"options":{{"resolved_color_map":{{}},"catalog_id":null,"canvas":{{"width":1000.0,"height":1000.0}},"canvas_aspect_id":"square","svg_profile":"display","render_seed":{render_seed},"composition_seed":{composition_seed},"wild":true}}}}"#
        )
    }

    #[test]
    fn actual_json_parser_preserves_null_and_zero_seeds() {
        let null_request = parse_render_request(&request_json("null", "null")).expect("request");
        let zero_request = parse_render_request(&request_json("0", "0")).expect("request");
        assert_eq!(null_request.options.render_seed, None);
        assert_eq!(null_request.options.composition_seed, None);
        assert_eq!(zero_request.options.render_seed, Some(0));
        assert_eq!(zero_request.options.composition_seed, Some(0));
    }

    #[test]
    fn actual_json_parser_preserves_unsigned_u64_number_token() {
        let request = parse_render_request(&request_json("18446744073709551615", "0"))
            .expect("unsigned historical seed");
        assert_eq!(
            request.options.render_seed,
            Some(18_446_744_073_709_551_615_i128)
        );
        assert_eq!(request.options.composition_seed, Some(0));
        assert!(request.options.wild);
    }

    #[test]
    fn actual_json_parser_preserves_normal_and_signed_max_seeds() {
        let normal =
            parse_render_request(&request_json("9007199254740991", "null")).expect("normal seed");
        let signed_max = parse_render_request(&request_json("9223372036854775807", "null"))
            .expect("signed max seed");
        assert_eq!(normal.options.render_seed, Some(9_007_199_254_740_991));
        assert_eq!(signed_max.options.render_seed, Some(i128::from(i64::MAX)));
    }

    #[test]
    fn raster_options_use_the_frozen_optional_dimensions() {
        assert_eq!(
            parse_raster_options(r#"{"target_width":320,"target_height":null}"#).expect("options"),
            RasterOptions {
                target_width: Some(320),
                target_height: None,
            }
        );
    }
}
