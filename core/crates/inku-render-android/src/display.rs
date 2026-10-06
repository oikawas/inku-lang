//! Display JNI only transports the shared API and borrows its raster buffers.

use std::ptr::null_mut;
use std::sync::{Arc, Mutex, OnceLock};

use inku_pipeline_uniffi::{
    DisplayComposite, DisplayFailure, DisplayLayout, DisplayRect, DisplayRegion, DisplayScene,
    display_api_version, display_detail_region, display_layout, display_tiles,
    prepare_display_scene,
};
use jni::JNIEnv;
use jni::objects::{JObject, JString, JValue};
use jni::sys::{jdouble, jint, jlong, jobject, jstring};
use serde::de::DeserializeOwned;

use crate::bitmap::bitmap_from_raster;
use crate::handles::Handles;
use crate::{BindingError, java_string, jni_boundary, new_java_string};

enum Record {
    Scene(Arc<DisplayScene>),
    Composite {
        composite: Arc<DisplayComposite>,
        window: DisplayRegion,
    },
}
static HANDLES: OnceLock<Mutex<Handles<Record>>> = OnceLock::new();

fn table() -> &'static Mutex<Handles<Record>> {
    HANDLES.get_or_init(|| Mutex::new(Handles::default()))
}

fn failure(error: DisplayFailure) -> BindingError {
    let (kind, code, message) = match error {
        DisplayFailure::Unsupported { code, message } => ("unsupported", code, message),
        DisplayFailure::Refused { code, message } => ("refused", code, message),
        DisplayFailure::InternalInvariant => (
            "internal_invariant",
            "internal_invariant".into(),
            "the display core panicked".into(),
        ),
    };
    BindingError {
        exception_class: "app/inku/mobile/render/NativeDisplayException",
        message: serde_json::json!({"kind": kind, "code": code, "message": message}).to_string(),
    }
}

fn refused(code: &str) -> BindingError {
    failure(DisplayFailure::Refused {
        code: code.into(),
        message: code.into(),
    })
}

fn insert(record: Record) -> Result<i64, BindingError> {
    table()
        .lock()
        .map_err(|_| BindingError::state("display handle lock poisoned"))?
        .insert(record)
        .map_err(refused)
}

fn record(id: i64) -> Result<Arc<Record>, BindingError> {
    table()
        .lock()
        .map_err(|_| BindingError::state("display handle lock poisoned"))?
        .get(id)
        .ok_or_else(|| refused("closed_handle"))
}

fn scene(id: i64) -> Result<Arc<DisplayScene>, BindingError> {
    match record(id)?.as_ref() {
        Record::Scene(scene) => Ok(Arc::clone(scene)),
        _ => Err(refused("invalid_handle_kind")),
    }
}

fn composite(id: i64) -> Result<Arc<DisplayComposite>, BindingError> {
    match record(id)?.as_ref() {
        Record::Composite { composite, .. } => Ok(Arc::clone(composite)),
        _ => Err(refused("invalid_handle_kind")),
    }
}

fn json<T: DeserializeOwned>(env: &mut JNIEnv<'_>, value: JString<'_>) -> Result<T, BindingError> {
    serde_json::from_str(&java_string(env, value)?)
        .map_err(|error| BindingError::invalid(format!("invalid display request: {error}")))
}

fn dimension(value: jint) -> Result<u32, BindingError> {
    u32::try_from(value)
        .ok()
        .filter(|&n| n > 0)
        .ok_or_else(|| refused("invalid_target_dimension"))
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_apiVersion(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(env, &display_api_version())
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_layout(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        new_java_string(
            env,
            &serde_json::to_string(&display_layout())
                .map_err(|e| BindingError::state(e.to_string()))?,
        )
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_prepare(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    svg: JString<'_>,
) -> jobject {
    jni_boundary(env, null_mut(), |env| {
        let scene = prepare_display_scene(java_string(env, svg)?).map_err(failure)?;
        let (width, height, source, picture) = (
            scene.intrinsic_width(),
            scene.intrinsic_height(),
            scene.source_byte_count(),
            scene.picture_byte_count(),
        );
        let id = insert(Record::Scene(scene))?;
        let result = env
            .new_object(
                "app/inku/mobile/render/NativeDisplayScene",
                "(JDDJJ)V",
                &[
                    JValue::Long(id),
                    JValue::Double(width),
                    JValue::Double(height),
                    JValue::Long(source as i64),
                    JValue::Long(picture as i64),
                ],
            )
            .map(JObject::into_raw)
            .map_err(|error| {
                BindingError::state(format!("display scene construction failed: {error}"))
            });
        if result.is_err() {
            if let Ok(mut table) = table().lock() {
                table.remove(id);
            }
        }
        result
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_close(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    id: jlong,
) {
    jni_boundary(env, (), |_| {
        if table()
            .lock()
            .map_err(|_| BindingError::state("display handle lock poisoned"))?
            .remove(id)
        {
            Ok(())
        } else {
            Err(refused("closed_handle"))
        }
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_liveHandles(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jint {
    jni_boundary(env, -1, |_| {
        Ok(table()
            .lock()
            .map_err(|_| BindingError::state("display handle lock poisoned"))?
            .len() as i32)
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_whole(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    id: jlong,
    width: jint,
    height: jint,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let region = scene(id)?
            .whole(Some(dimension(width)?), Some(dimension(height)?))
            .map_err(failure)?;
        new_java_string(
            env,
            &serde_json::to_string(&region).map_err(|e| BindingError::state(e.to_string()))?,
        )
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_tiles(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    id: jlong,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let kept = record(id)?;
        // The shared composite constructor has already validated this window.
        let Record::Composite { window, .. } = kept.as_ref() else {
            return Err(refused("invalid_handle_kind"));
        };
        new_java_string(
            env,
            &serde_json::to_string(&display_tiles(*window, display_layout().tile_side))
                .map_err(|e| BindingError::state(e.to_string()))?,
        )
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_detailRegion(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    zoomed: JString<'_>,
    visible: JString<'_>,
    pixel_scale: jdouble,
    limits: JString<'_>,
) -> jstring {
    jni_boundary(env, null_mut(), |env| {
        let zoomed: DisplayRect = json(env, zoomed)?;
        let visible: DisplayRect = json(env, visible)?;
        let limits: DisplayLayout = json(env, limits)?;
        match display_detail_region(zoomed, visible, pixel_scale, limits) {
            Some(region) => new_java_string(
                env,
                &serde_json::to_string(&region).map_err(|e| BindingError::state(e.to_string()))?,
            ),
            None => Ok(null_mut()),
        }
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_begin(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    id: jlong,
    region: JString<'_>,
) -> jlong {
    jni_boundary(env, 0, |env| {
        let window = json(env, region)?;
        insert(Record::Composite {
            composite: scene(id)?.composite(window).map_err(failure)?,
            window,
        })
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_renderTile(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    id: jlong,
    region: JString<'_>,
) {
    jni_boundary(env, (), |env| {
        composite(id)?
            .render_tile(json(env, region)?)
            .map_err(failure)
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_snapshot(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    id: jlong,
) -> jobject {
    jni_boundary(env, null_mut(), |env| {
        bitmap_from_raster(env, composite(id)?.snapshot().map_err(failure)?.raster())
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_finish(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    id: jlong,
) -> jobject {
    jni_boundary(env, null_mut(), |env| {
        bitmap_from_raster(env, composite(id)?.finish().map_err(failure)?.raster())
    })
}

#[unsafe(no_mangle)]
#[allow(non_snake_case)]
pub extern "system" fn Java_app_inku_mobile_render_NativeDisplayBridge_rasterize(
    env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    id: jlong,
    width: jint,
    height: jint,
) -> jobject {
    jni_boundary(env, null_mut(), |env| {
        let frame = scene(id)?
            .rasterize(Some(dimension(width)?), Some(dimension(height)?))
            .map_err(failure)?;
        bitmap_from_raster(env, &frame)
    })
}
