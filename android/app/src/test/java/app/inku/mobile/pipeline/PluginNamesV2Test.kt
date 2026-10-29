package app.inku.mobile.pipeline

import app.inku.mobile.data.db.SaijikiV1Migration
import app.inku.mobile.data.db.productFile
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PluginNamesV2Test {
    @Test fun bundledNamesAndEditorDiagnosticsUseRealCore() {
        val bundle = JSONObject(NativePipelineBridge.pluginPackage(JSONObject().put("action", "bundled_nature").toString().toByteArray()).decodeToString())
        assertEquals("ok", bundle.getString("outcome"))
        assertEquals(14, bundle.getJSONObject("pictures").length())
        assertEquals(7, JSONObject(bundle.getString("text")).getJSONArray("words").length())
        val builder = SharedPipelineConfigBuilder(NativePipelineBridge)
        val words = builder.bundledPluginWords("ja")
        assertEquals("Nature.YoungLeaves", words.first().qualifiedName)
        assertEquals("若葉", words.first().ja.first())
        assertEquals("young leaves", words.first().en.first())
        val old = JSONObject(productFile("core/crates/inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json").readText())
            .getJSONArray("entries").getJSONObject(0).getJSONObject("definition")
        val oldWord = builder.wordsForDefinitions(JSONArray().put(old), "ja").single()
        assertEquals("若葉", oldWord.ja.first())
        val normalized = pluginNameEntries(listOf(PluginWord("x.y", listOf(" ＹＯＵＮＧ　 𝐋𝐞𝐚𝐯𝐞𝐬 "), emptyList())), true)
        assertEquals("young leaves", normalized.single().getString("name"))
        val catalog = builder.editorCatalog("ja", true, emptyList())
        val entries = catalog.getJSONArray("entries")
        val definitions = JSONArray().also { out -> for (i in 0 until entries.length()) out.put(entries.getJSONObject(i).getJSONObject("definition")) }
        val input = JSONObject().put("source", "😀｛若葉｝。｛未登録の語｝。").put("language", "ja")
            .put("definitions", definitions).put("locks", SaijikiV1Migration.documentLocks(catalog.getJSONArray("locks")))
            .put("compiler", JSONObject.NULL).put("plugin_names", JSONArray(pluginNameEntries(words, true)))
            .put("enabled", JSONArray(words.map { it.qualifiedName }))
        val output = JSONObject(NativePipelineBridge.pluginCalls(input.toString().toByteArray()).decodeToString())
        val calls = output.getJSONArray("calls")
        assertEquals("resolved", calls.getJSONObject(0).getString("status"))
        assertEquals(2, calls.getJSONObject(0).getInt("start_utf16"))
        assertEquals("plugin_not_installed", calls.getJSONObject(1).getString("status"))
        assertTrue((0 until output.getJSONArray("entries").length()).any { output.getJSONArray("entries").getJSONObject(it).optString("written_ja") == "｛若葉｝" })
        val disabled = JSONObject().put("source", "｛若葉｝。").put("language", "ja")
            .put("definitions", JSONArray()).put("locks", JSONArray()).put("compiler", JSONObject.NULL)
            .put("plugin_names", JSONArray(pluginNameEntries(words, false)))
        val disabledResult = JSONObject(NativePipelineBridge.pluginCalls(disabled.toString().toByteArray()).decodeToString())
        assertEquals("plugin_disabled", disabledResult.getJSONArray("calls").getJSONObject(0).getString("status"))
    }
}
