//! Android transport for the same owned pipeline bytes used by the Python host.

use std::ptr::null_mut;

use jni::JNIEnv;
use jni::objects::{JByteArray, JObject, JString, JValue};
use jni::sys::{jbyteArray, jlong, jobject, jstring};

use super::{BindingError, java_string, jni_boundary, new_java_string};

fn read_bytes(env: &JNIEnv<'_>, value: JByteArray<'_>) -> Result<Vec<u8>, BindingError> {
    env.convert_byte_array(value)
        .map_err(|error| BindingError::invalid(format!("invalid pipeline bytes: {error}")))
}

fn write_bytes(env: &JNIEnv<'_>, value: &[u8]) -> Result<jbyteArray, BindingError> {
    env.byte_array_from_slice(value)
        .map(JByteArray::into_raw)
        .map_err(|error| BindingError::state(format!("pipeline byte allocation failed: {error}")))
}

fn optional_java_string(
    env: &mut JNIEnv<'_>,
    value: JString<'_>,
) -> Result<Option<String>, BindingError> {
    if value.is_null() {
        Ok(None)
    } else {
        java_string(env, value).map(Some)
    }
}

fn optional_jstring(env: &mut JNIEnv<'_>, value: Option<String>) -> Result<jstring, BindingError> {
    match value {
        Some(value) => new_java_string(env, &value),
        None => Ok(null_mut()),
    }
}

fn native_svg_output(
    env: &mut JNIEnv<'_>,
    output: inku_pipeline_uniffi::NativeSvgOutput,
) -> Result<jobject, BindingError> {
    let json = env
        .byte_array_from_slice(&output.json_bytes)
        .map_err(|error| {
            BindingError::state(format!("pipeline byte allocation failed: {error}"))
        })?;
    let json_object = JObject::from(json);
    let svg_object = match output.svg {
        Some(svg) => JObject::from(
            env.new_string(svg)
                .map_err(|error| BindingError::state(format!("SVG allocation failed: {error}")))?,
        ),
        None => JObject::null(),
    };
    env.new_object(
        "app/inku/mobile/pipeline/NativeSvgOutput",
        "([BLjava/lang/String;)V",
        &[JValue::Object(&json_object), JValue::Object(&svg_object)],
    )
    .map(JObject::into_raw)
    .map_err(|error| BindingError::state(format!("NativeSvgOutput construction failed: {error}")))
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_stepSvgLimited(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    snapshot: JByteArray<'_>,
    input: JByteArray<'_>,
    max_svg_bytes: jlong,
) -> jobject {
    jni_boundary(env, null_mut(), |env| {
        let snapshot = read_bytes(env, snapshot)?;
        let input = read_bytes(env, input)?;
        let output = inku_pipeline_uniffi::step_svg_limited(snapshot, input, max_svg_bytes as u64);
        native_svg_output(env, output)
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_renderSavedSvgLimited(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
    max_svg_bytes: jlong,
) -> jobject {
    jni_boundary(env, null_mut(), |env| {
        let input = read_bytes(env, input)?;
        let output = inku_pipeline_uniffi::render_saved_svg_limited(input, max_svg_bytes as u64);
        native_svg_output(env, output)
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_versionReport(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(env, &inku_pipeline_uniffi::version_report())
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_canvasRegistry(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(env, &inku_pipeline_uniffi::canvas_registry())
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_compositionRanges(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(env, &inku_pipeline_uniffi::composition_ranges())
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_step(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    snapshot: JByteArray<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    jni_boundary(env, null_mut(), |env| {
        let snapshot = read_bytes(env, snapshot)?;
        let input = read_bytes(env, input)?;
        write_bytes(env, &inku_pipeline_uniffi::step(snapshot, input))
    })
}

fn unary_bytes(
    env: JNIEnv<'_>,
    input: JByteArray<'_>,
    operation: fn(Vec<u8>) -> Vec<u8>,
) -> jbyteArray {
    jni_boundary(env, null_mut(), |env| {
        let input = read_bytes(env, input)?;
        write_bytes(env, &operation(input))
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_resolvePalette(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, input, inku_pipeline_uniffi::resolve_palette)
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_resolveMacroCatalog(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, input, inku_pipeline_uniffi::resolve_macro_catalog)
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_explainPluginDiagnostics(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, input, inku_pipeline_uniffi::explain_plugin_diagnostics)
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_recompose(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, input, inku_pipeline_uniffi::recompose)
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_retouch(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, input, inku_pipeline_uniffi::retouch)
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_completionRangeStates(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, input, inku_pipeline_uniffi::completion_range_states)
}

/// The one-time Saijiki v1 migration of one saved unit, for the startup migration.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_migrateSaijikiV1(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, input, inku_pipeline_uniffi::migrate_saijiki_v1)
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_renderSaved(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    input: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, input, inku_pipeline_uniffi::render_saved)
}

/// The provider attempt in flight for a stored snapshot, for the running row.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_providerAttempt(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    snapshot: JByteArray<'_>,
) -> jbyteArray {
    unary_bytes(env, snapshot, inku_pipeline_uniffi::provider_attempt)
}

/// The description every layer reads: Server's label cut, from the one shared copy.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_pipelineDescription(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    text: JString<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let text = java_string(env, text)?;
        new_java_string(env, &inku_pipeline_uniffi::pipeline_description(&text))
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_descriptionHash(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    text: JString<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let text = java_string(env, text)?;
        new_java_string(env, &inku_pipeline_uniffi::description_hash(text))
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_renderHash(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    item_json: JString<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let item_json = java_string(env, item_json)?;
        optional_jstring(env, inku_pipeline_uniffi::render_hash(item_json))
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_canonicalJson(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    value_json: JString<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let value_json = java_string(env, value_json)?;
        optional_jstring(env, inku_pipeline_uniffi::canonical_json(value_json))
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_resolveInstructionLanguage(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    text: JString<'_>,
    requested: JString<'_>,
    fallback: JString<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let text = java_string(env, text)?;
        let requested = optional_java_string(env, requested)?;
        let fallback = java_string(env, fallback)?;
        optional_jstring(
            env,
            inku_pipeline_uniffi::resolve_instruction_language(text, requested, fallback),
        )
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_normalizeInstructionLanguage(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    value: JString<'_>,
    default: JString<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let value = optional_java_string(env, value)?;
        let default = java_string(env, default)?;
        optional_jstring(
            env,
            inku_pipeline_uniffi::normalize_instruction_language(value, default),
        )
    })
}

/// A word-touch seed as Server derives it; null when the words carry no seed.
#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_pipeline_NativePipelineBridge_renderSeedFromText(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    seed_text: JString<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let seed_text = java_string(env, seed_text)?;
        match inku_pipeline_uniffi::render_seed_from_text(seed_text) {
            None => Ok(null_mut()),
            Some(seed) => new_java_string(
                env,
                &serde_json::json!({
                    "render_seed": seed.render_seed,
                    "seed_text": seed.seed_text,
                })
                .to_string(),
            ),
        }
    })
}
