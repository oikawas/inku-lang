package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class RenderEngineVersionTest {
    @Test
    fun renderHashPreservesNullEngineVersionWhenMissingInMetadata() {
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

        fun hash(metadata: JSONObject): String = method.invoke(
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
        assertNotEquals(hash(JSONObject().put("render_engine_version", "41")), missing)
    }
}
