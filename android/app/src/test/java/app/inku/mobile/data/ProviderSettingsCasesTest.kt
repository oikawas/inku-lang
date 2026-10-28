package app.inku.mobile.data

import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import app.inku.mobile.llm.RoutingModelProvider
import app.inku.mobile.llm.providerModelListRequest
import app.inku.mobile.llm.nextModelListQuery

/** The shared Server fixtures exercise the actual host JNI entry point. */
class ProviderSettingsCasesTest {
    private val cases = JSONObject(File(System.getProperty("inku.providerSettingsCases")).readText())
    private fun forEach(name: String, check: (JSONObject) -> Unit) {
        val rows = cases.getJSONArray(name)
        for (i in 0 until rows.length()) check(rows.getJSONObject(i))
    }
    private fun keys(obj: JSONObject?) = JSONArray(obj?.keys()?.asSequence()?.toList()?.sorted().orEmpty())
    private fun same(expected: Any, actual: Any) {
        fun canonical(value: Any?): Any? = when (value) {
            is JSONObject -> value.keys().asSequence().associateWith { canonical(value.get(it)) }
            is JSONArray -> (0 until value.length()).map { canonical(value.get(it)) }
            is Number -> value.toDouble()
            else -> value
        }
        val equal = canonical(expected) == canonical(actual)
        assertTrue("Expected $expected, got $actual", equal)
    }

    @Test fun normalizationAndUpdates() {
        forEach("normalization") { row ->
            val input = row.optJSONObject("input")
            val result = catalogRequest("normalize_settings", JSONObject().put("settings", row.get("input"))
                .put("order", keys(input?.optJSONObject("providers"))).put("env", JSONObject()))
            same(row.getJSONObject("result"), result.getJSONObject("settings"))
        }
        forEach("updates") { row ->
            val patch = row.getJSONObject("patch")
            val result = catalogRequest("update_settings", JSONObject().put("settings", row.get("input"))
                .put("patch", patch).put("order", JSONArray()).put("patch_order", keys(patch.optJSONObject("providers")))
                .put("env", JSONObject()))
            same(row.getJSONObject("result"), result.getJSONObject("settings"))
        }
    }

    @Test fun refreshAccessAndValidation() {
        forEach("refresh_cases") { row ->
            val finished = ProviderSettingsCodec.refresh(row.getString("provider"), row.getJSONArray("models"),
                row.getJSONObject("previous"), row.getString("today"))
            val actual = JSONObject().put("models", finished.get("models")).put("enabled_models", finished.get("enabled_models"))
            same(row.getJSONObject("result"), actual)
        }
        forEach("access_cases") { row ->
            val request = JSONObject().put("stage", row.get("stage")).put("status", row.get("status"))
                .put("text", row.optString("text")).put("today", row.optString("today"))
            same(row.getJSONObject("answer"), catalogRequest("access_probe", request).getJSONObject("answer"))
        }
        forEach("validation_cases") { row ->
            val result = catalogRequest("validate_settings", row.getJSONObject("input"))
            result.remove("schema"); result.remove("outcome")
            same(row.getJSONObject("result"), result)
        }
    }

    @Test fun referencesAndFetchPlans() {
        val providers = cases.getJSONObject("reference_settings").getJSONObject("providers")
        forEach("references") { row ->
            val request = JSONObject().put("providers", providers).put("ref", row.get("ref"))
            val split = catalogRequest("split_ref", request)
            same(row.getJSONArray("split"), JSONArray().put(split.get("provider")).put(split.get("model")))
            val resolved = catalogRequest("resolve_ref", request.put("default_provider", "nvidia")
                .put("default_model", "google/gemma-4-31b-it"))
            same(row.getJSONArray("stage1"), JSONArray().put(resolved.get("provider")).put(resolved.get("model")))
            same(row.getJSONArray("stage2"), JSONArray().put(resolved.get("provider")).put(resolved.get("model")))
            val rows = providers.keys().asSequence().map { ProviderSettingsCodec.fromCore(providers.getJSONObject(it)) }.toList()
            val available = providers.keys().asSequence().associateWith { id ->
                val models = providers.getJSONObject(id).getJSONArray("models")
                (0 until models.length()).map { models.getJSONObject(it).getString("id") }
            }
            same(row.getJSONArray("stage1").getString(0), RoutingModelProvider.resolveProviderForRouting(
                rows, row.getString("ref"), "nvidia", available)?.providerId ?: JSONObject.NULL)
        }
        forEach("resolution_cases") { row ->
            val settings = row.getJSONObject("settings")
            val answer = catalogRequest("resolve_ref", JSONObject().put("providers", settings.getJSONObject("providers"))
                .put("ref", row.get("ref")).put("default_provider", settings.get("stage1_provider"))
                .put("default_model", settings.get("stage1_model")))
            same(row.getJSONArray("result"), JSONArray().put(answer.get("provider")).put(answer.get("model")))
            val values = settings.getJSONObject("providers")
            val rows = values.keys().asSequence().map { ProviderSettingsCodec.fromCore(values.getJSONObject(it)) }.toList()
            val available = values.keys().asSequence().associateWith { id ->
                val models = values.getJSONObject(id).getJSONArray("models")
                (0 until models.length()).map { models.getJSONObject(it).getString("id") }
            }
            same(row.getJSONArray("result").getString(0), RoutingModelProvider.resolveProviderForRouting(
                rows, row.getString("ref"), settings.getString("stage1_provider"), available)?.providerId ?: JSONObject.NULL)
        }
        forEach("fetch_plan_cases") { row ->
            val answer = catalogRequest("model_list_start", JSONObject().put("kind", row.get("kind"))
                .put("base_url", row.get("base_url")).put("api_key", row.get("api_key")))
            listOf("url", "headers", "items_key", "query").forEach { same(row.get(it), answer.get(it)) }
            val next = catalogRequest("model_list_next", JSONObject().put("kind", row.get("kind")).put("page", row.get("next_page")))
            same(row.get("next_query"), next.get("query"))
            val actual = providerModelListRequest(row.getString("kind"), row.getString("base_url"), row.getString("api_key"))
            same(row.get("url"), actual.url)
            same(row.getJSONObject("headers"), JSONObject(actual.headers))
            same(row.optJSONObject("query") ?: JSONObject(), JSONObject(actual.firstQuery))
            val following = nextModelListQuery(row.getString("kind"), row.getJSONObject("next_page"))
            same(row.get("next_query"), following?.let(::JSONObject) ?: JSONObject.NULL)
        }
    }
}
