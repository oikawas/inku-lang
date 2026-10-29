package app.inku.mobile.pipeline

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PluginDiagnosticsDeviceTest {
    @Test fun packagedCoreExplainsV2Names() {
        val input = JSONObject().put("source", "｛若葉｝。｛花｝。｛未登録の語｝。").put("language", "ja")
            .put("definitions", JSONArray()).put("locks", JSONArray()).put("compiler", JSONObject.NULL)
            .put("plugin_names", JSONArray()
                .put(JSONObject().put("name", "若葉").put("qualified_name", "Nature.YoungLeaves").put("enabled", false))
                .put(JSONObject().put("name", "花").put("qualified_name", "Garden.Flower").put("enabled", true))
                .put(JSONObject().put("name", "花").put("qualified_name", "Sky.Flower").put("enabled", true)))
        val output = JSONObject(NativePipelineBridge.pluginCalls(input.toString().encodeToByteArray()).decodeToString())
        val calls = output.getJSONArray("calls")
        assertEquals(listOf("plugin_disabled", "plugin_name_ambiguous", "plugin_not_installed"),
            (0 until calls.length()).map { calls.getJSONObject(it).getString("status") })
    }
}
