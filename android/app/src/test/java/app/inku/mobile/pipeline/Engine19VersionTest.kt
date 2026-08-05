package app.inku.mobile.pipeline

import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.render.DefaultSvgRenderer
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class Engine19VersionTest {
    @Test
    fun testRendererMetadataDeclaresEngine21() {
        val result = DefaultSvgRenderer().render(
            app.inku.mobile.pipeline.RenderRequest(
                scoreJson = """{"instructions":[]}""",
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
            )
        )
        assertEquals("21", JSONObject(result.metadataJson).getString("render_engine_version"))
    }

    @Test
    fun testRenderHashPreservesNullEngineVersionWhenMissingInMetadata() {
        val pipeline = LocalFallbackPipeline()
        val method = LocalFallbackPipeline::class.java.getDeclaredMethod(
            "renderHash",
            String::class.java,
            String::class.java,
            String::class.java,
            String::class.java,
            String::class.java,
            String::class.java,
        ).apply { isAccessible = true }

        fun hash(metadata: JSONObject): String =
            method.invoke(
                pipeline,
                "input",
                "ddl",
                """{"instructions":[]}""",
                "<svg/>",
                metadata.toString(),
                "default",
            ) as String

        val missing = hash(JSONObject())
        val blank = hash(JSONObject().put("render_engine_version", ""))
        assertEquals(missing, blank)
        org.junit.Assert.assertNotEquals(hash(JSONObject().put("render_engine_version", "21")), missing)
    }

    // The version the UI shows is pinned to a literal so that leaving it stale fails here.
    @Test
    fun testCompatibilityConstantsDeclareEngine21() {
        assertEquals("21", CompatibilityConstants.renderEngineVersion)
        assertEquals("default", CompatibilityConstants.renderEngineId)
    }

    // The label the UI shows and the metadata the renderer emits must never drift apart again.
    @Test
    fun testUiConstantsMatchRendererMetadata() {
        val metadata = JSONObject(
            DefaultSvgRenderer().render(
                RenderRequest(
                    scoreJson = """{"instructions":[]}""",
                    colorCatalogId = "default",
                    canvasAspect = "square",
                    svgProfile = "editable",
                )
            ).metadataJson
        )
        assertEquals(metadata.getString("render_engine_version"), CompatibilityConstants.renderEngineVersion)
        assertEquals(metadata.getString("render_engine_id"), CompatibilityConstants.renderEngineId)
    }
}
