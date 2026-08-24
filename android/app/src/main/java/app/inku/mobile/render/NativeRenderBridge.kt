package app.inku.mobile.render

data class NativeRenderOutput(
    val svg: String,
    val metadataJson: String,
)

data class NativeRasterOutput(
    val width: Int,
    val height: Int,
    val stride: Int,
    val pixelFormat: String,
    val pixels: ByteArray,
)

/** One coarse, injectable transport boundary around the shared Rust libraries. */
interface RenderBridge {
    fun coreApiVersion(): String
    fun rasterApiVersion(): String
    fun renderEngineId(): String
    fun renderEngineVersion(): String
    fun defaultColorMapJson(): String
    fun rendererReferenceJson(): String
    fun render(requestJson: String): NativeRenderOutput
    fun rasterize(svg: String, rasterOptionsJson: String): NativeRasterOutput
}

/**
 * Direct JNI surface. Calls are synchronous by design; callers own background scheduling.
 * No Android component or JNI environment is retained between calls.
 */
object NativeRenderBridge : RenderBridge {
    init {
        System.loadLibrary(LIBRARY_NAME)
    }

    external override fun coreApiVersion(): String
    external override fun rasterApiVersion(): String
    external override fun renderEngineId(): String
    external override fun renderEngineVersion(): String
    external override fun defaultColorMapJson(): String
    external override fun rendererReferenceJson(): String
    external override fun render(requestJson: String): NativeRenderOutput
    external override fun rasterize(svg: String, rasterOptionsJson: String): NativeRasterOutput

    private const val LIBRARY_NAME = "inku_render_android"
}

internal const val EXPECTED_CORE_API_VERSION = "0.1.0"
internal const val EXPECTED_RASTER_API_VERSION = "0.1.0"

internal fun RenderBridge.requireCompatibleNativePackage() {
    check(coreApiVersion() == EXPECTED_CORE_API_VERSION) {
        "Rust render API mismatch: expected $EXPECTED_CORE_API_VERSION"
    }
    check(rasterApiVersion() == EXPECTED_RASTER_API_VERSION) {
        "Rust raster API mismatch: expected $EXPECTED_RASTER_API_VERSION"
    }
    check(renderEngineId().isNotBlank()) { "Rust render engine id is blank" }
    check(renderEngineVersion().isNotBlank()) { "Rust render engine version is blank" }
}
