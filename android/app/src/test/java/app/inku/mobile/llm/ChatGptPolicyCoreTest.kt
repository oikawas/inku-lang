package app.inku.mobile.llm

import app.inku.mobile.pipeline.CoreIdentityJson
import app.inku.mobile.pipeline.NativePipelineBridge
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class ChatGptPolicyCoreTest {
    private fun canonical(value: Any?): Any? = when (value) {
        is JSONObject -> value.keys().asSequence().associateWith { canonical(value.get(it)) }
        is JSONArray -> (0 until value.length()).map { canonical(value.get(it)) }
        is Number -> java.math.BigDecimal(value.toString()).stripTrailingZeros()
        else -> value
    }

    @Test fun sharedPolicyCasesUseTheActualJniCore() {
        val directory = requireNotNull(File(requireNotNull(System.getProperty("inku.identityCases"))).parentFile)
        val wire = JSONObject(directory.resolve("provider-wire-cases.json").readText()).getJSONArray("chatgpt")
        val addendum = JSONArray(directory.resolve("chatgpt-auth-addendum-cases.json").readText())
        val rows = (0 until wire.length()).map { wire.getJSONObject(it) }
            .filter { it.getJSONObject("request").optString("schema") == "inku.model-catalog-request.v1" }
        assertEquals(59, rows.size)
        assertEquals(37, addendum.length())
        for (row in rows + (0 until addendum.length()).map { addendum.getJSONObject(it) }) {
            val request = row.getJSONObject("request").put("schema", "inku.model-catalog-request.v1")
            val result = JSONObject(NativePipelineBridge.modelCatalog(CoreIdentityJson.encode(request).toByteArray()).toString(Charsets.UTF_8))
            val expected = row.getJSONObject("expect")
            for (key in expected.keys()) {
                assertEquals(row.optString("why", row.optString("name")) + ": " + key,
                    canonical(expected.get(key)), canonical(result.get(key)))
            }
        }
    }
}
