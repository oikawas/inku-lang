package app.inku.mobile.pipeline

import androidx.test.ext.junit.runners.AndroidJUnit4
import app.inku.mobile.ui.i18n.InkuStringsJa
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The packaged shared explainer returns each of the four reasons, including
 * `plugin_version_mismatch`, which no ordinary Android operation produces: a
 * saved work carries its own definitions, so the digest mismatch is given here.
 */
@RunWith(AndroidJUnit4::class)
class PluginDiagnosticsDeviceTest {
    @Test
    fun packagedExplainerReturnsTheFourReasonsTheScreenWords() {
        val source = "紙。\nGarden.薔薇。\nNature.若菜。\nOld.Mark。\nNature.若葉。"
        fun span(sentence: String, reason: String): JSONObject {
            val start = source.substringBefore(sentence).encodeToByteArray().size
            return JSONObject()
                .put("reason", reason)
                .put("span", JSONObject().put("start_byte", start).put("end_byte", start + sentence.encodeToByteArray().size))
        }
        val input = JSONObject()
            .put("source", source)
            .put(
                "upstream_diagnostics",
                JSONArray()
                    .put(span("Garden.薔薇", "macro_resolution_missing_lock"))
                    .put(span("Nature.若菜", "macro_resolution_missing_lock"))
                    .put(span("Old.Mark", "macro_resolution_missing_lock"))
                    .put(span("Nature.若葉", "macro_resolution_digest_mismatch")),
            )
            .put("enabled", JSONArray(listOf("Nature.YoungLeaves", "Nature.若葉")))
            .put("disabled", JSONArray(listOf("Old.Mark")))

        val output = JSONObject(NativePipelineBridge.explainPluginDiagnostics(input.toString().encodeToByteArray()).decodeToString())
        assertEquals("inku.plugin-diagnostics.v1", output.getString("schema"))
        val plugins = output.getJSONArray("plugins")
        val reasons = (0 until plugins.length()).map { plugins.getJSONObject(it) }
            .associate { it.getString("name") to it.getString("reason") }
        assertEquals(
            mapOf(
                "Garden.薔薇" to "plugin_not_installed",
                "Nature.若菜" to "plugin_name_mismatch",
                "Old.Mark" to "plugin_disabled",
                "Nature.若葉" to "plugin_version_mismatch",
            ),
            reasons,
        )
        assertEquals(
            "プラグイン Nature.若葉 の中身が作品の保存時と違うため、この文は描かれていません。",
            InkuStringsJa.pipelinePluginDiagnostic("plugin_version_mismatch", "Nature.若葉", null),
        )
    }
}
