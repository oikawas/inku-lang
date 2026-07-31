package app.inku.mobile.pipeline

import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.render.DefaultSvgRenderer
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class Engine17VersionTest {
    @Test
    fun testRendererMetadataDeclaresEngine17() {
        val result = DefaultSvgRenderer().render(
            app.inku.mobile.pipeline.RenderRequest(
                scoreJson = """{"instructions":[]}""",
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
            )
        )
        assertEquals("17", JSONObject(result.metadataJson).getString("render_engine_version"))
    }

    @Test
    fun testRenderHashDefaultsMissingAndBlankMetadataToEngine17() {
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

        val explicit17 = hash(JSONObject().put("render_engine_version", "17"))
        assertEquals(explicit17, hash(JSONObject()))
        assertEquals(explicit17, hash(JSONObject().put("render_engine_version", "")))
    }

    // The version the UI shows is pinned to a literal so that leaving it stale fails here.
    @Test
    fun testCompatibilityConstantsDeclareEngine17() {
        assertEquals("17", CompatibilityConstants.renderEngineVersion)
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
