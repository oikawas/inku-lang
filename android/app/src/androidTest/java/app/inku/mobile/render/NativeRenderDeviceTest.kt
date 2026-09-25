package app.inku.mobile.render

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.model.WorkColorSnapshot
import app.inku.mobile.pipeline.RenderRequest
import java.security.MessageDigest
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NativeRenderDeviceTest {
    private val assets
        get() = InstrumentationRegistry.getInstrumentation().context.assets

    @Test
    fun packagedNativeLibraryMatchesTheHostCoreOfTheSameCommit() {
        assertEquals("0.1.0", NativeRenderBridge.coreApiVersion())
        assertEquals("0.1.0", NativeRenderBridge.rasterApiVersion())
        // Rendered at build time by `generateRustParityExpected` from the same
        // core sources, so the engine version is whatever this commit ships.
        val expected = JSONObject(assetText("render-parity/expected.json"))
        val engineId = expected.getString("render_engine_id")
        val engineVersion = expected.getString("render_engine_version")
        assertEquals(engineId, NativeRenderBridge.renderEngineId())
        assertEquals(engineVersion, NativeRenderBridge.renderEngineVersion())

        CASE_NAMES.forEach { name ->
            val output = NativeRenderBridge.render(assetText("render-parity/$name.request.json"))
            val metadata = JSONObject(output.metadataJson)

            assertEquals("SVG mismatch for $name", assetText("render-parity/$name.svg"), output.svg)
            assertEquals(engineId, metadata.getString("render_engine_id"))
            assertEquals(engineVersion, metadata.getString("render_engine_version"))
        }

        // The Kotlin host builds its own request from a Score; it must reach the
        // same bytes as the canonical request for the same work.
        val hostRequest = JSONObject(assetText("render-parity/A-pen-circle.request.json"))
        val hostScore = hostRequest.getJSONObject("score")
        val hostOptions = hostRequest.getJSONObject("options")
        val hostColorMap = hostOptions.getJSONObject("resolved_color_map")
        val hostResult = AndroidRenderHost().render(
            RenderRequest(
                scoreJson = hostScore.toString(),
                colorCatalogId = "default",
                canvasAspect = hostOptions.getString("canvas_aspect_id"),
                svgProfile = hostOptions.getString("svg_profile"),
                renderSeed = hostOptions.optNullableLong("render_seed"),
                compositionSeed = null,
                workColorSnapshot = WorkColorSnapshot(
                    catalogId = "default",
                    colorMap = hostColorMap.keys().asSequence()
                        .associateWith { hostColorMap.getString(it) },
                ),
                wild = hostOptions.getBoolean("wild"),
            ),
        )
        assertEquals(assetText("render-parity/A-pen-circle.svg"), hostResult.svg)

        assertEquals(
            JSONObject(assetText("render-parity/renderer_reference.json")).toString(),
            JSONObject(NativeRenderBridge.rendererReferenceJson()).toString(),
        )
    }

    @Test
    fun packagedRasterMatchesKnownPremultipliedRgbaAndHostDigests() {
        val known = NativeRenderBridge.rasterize(
            """<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><rect width="1" height="1" fill="#ff0000" fill-opacity="0.5"/></svg>""",
            """{"target_width":1,"target_height":null}""",
        )
        assertEquals("rgba8-premultiplied", known.pixelFormat)
        assertEquals(4, known.stride)
        assertArrayEquals(byteArrayOf(128.toByte(), 0, 0, 128.toByte()), known.pixels)

        RAW_CASES.forEach { case ->
            val output = NativeRenderBridge.rasterize(
                assetText(case.asset),
                """{"target_width":64,"target_height":64}""",
            )
            assertEquals(case.width, output.width)
            assertEquals(case.height, output.height)
            assertEquals(case.stride, output.stride)
            assertEquals(case.sha256, sha256(output.pixels))
        }
    }

    private fun JSONObject.optNullableLong(key: String): Long? =
        if (!has(key) || isNull(key)) null else getLong(key)

    private fun assetText(path: String): String = assets.open(path).bufferedReader().use { it.readText() }

    private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { "%02x".format(it) }

    private data class RawCase(
        val asset: String,
        val width: Int,
        val height: Int,
        val stride: Int,
        val sha256: String,
    )

    companion object {
        private val CASE_NAMES = listOf(
            "A-pen-circle",
            "B-wave-medium-line-brush_thick",
            "C-filter-display-pencil",
            "D-canvas-wide-region-single",
            "E-wild-surface-wash-pencil",
        )

        private val RAW_CASES = listOf(
            RawCase(
                "render-engine-41/A-pen-circle.svg",
                64,
                64,
                256,
                "89f77c560b97e360ab740f1045da304c63df9ee55f44b111599f2484ef3d29a2",
            ),
            RawCase(
                "render-engine-41/C-filter-display-pencil.svg",
                64,
                64,
                256,
                "165e04ac91ff11bb05fcb99953d11100c9bdb63c9a2bf7e3144485cf130fa780",
            ),
            RawCase(
                "render-engine-41/D-canvas-wide-region-single.svg",
                64,
                27,
                256,
                "2912d5b6746b74b5f60b57d07c97b1b770b1443f33e18e9785b2037050eb88fe",
            ),
            RawCase(
                "render-engine-21/G-scatter-edge.svg",
                64,
                64,
                256,
                "1bbb4da477413c3f65f1732cff3e03afaf3f5417736ea929f2bbd8c3de223368",
            ),
        )
    }
}
