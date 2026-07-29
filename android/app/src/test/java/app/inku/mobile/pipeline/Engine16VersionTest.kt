package app.inku.mobile.pipeline

import app.inku.mobile.render.DefaultSvgRenderer
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class Engine16VersionTest {
    @Test
    fun testRendererMetadataDeclaresEngine16() {
        val result = DefaultSvgRenderer().render(
            app.inku.mobile.pipeline.RenderRequest(
                scoreJson = """{"instructions":[]}""",
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
            )
        )
        assertEquals("16", JSONObject(result.metadataJson).getString("render_engine_version"))
    }

    @Test
    fun testRenderHashDefaultsMissingAndBlankMetadataToEngine16() {
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

        val explicit16 = hash(JSONObject().put("render_engine_version", "16"))
        assertEquals(explicit16, hash(JSONObject()))
        assertEquals(explicit16, hash(JSONObject().put("render_engine_version", "")))
    }
}
