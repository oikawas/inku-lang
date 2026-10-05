//! Android transport for the same owned pipeline bytes used by the Python host.

use std::ptr::null_mut;

use jni::JNIEnv;
use jni::objects::{JByteArray, JObject, JString};
use jni::sys::{jbyteArray, jstring};

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
