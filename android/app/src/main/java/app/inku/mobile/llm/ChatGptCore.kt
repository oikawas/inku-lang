package app.inku.mobile.llm

import app.inku.mobile.data.catalogRequest
import java.math.BigDecimal
import org.json.JSONObject

internal data class ChatGptModelPolicy(val purposes: JSONObject = JSONObject(), val assessments: JSONObject = JSONObject())

/** Adapts the encrypted Android profile's millisecond timestamps to the shared policy. */
internal object ChatGptCore {
    fun call(action: String, fields: JSONObject = JSONObject()): JSONObject {
        val result = catalogRequest(action, fields)
        result.optString("error").takeIf(String::isNotEmpty)?.let { throw ChatGptException(it) }
        return result
    }

    fun toCore(profile: JSONObject, purposes: JSONObject? = null): JSONObject = JSONObject(profile.toString()).also { value ->
        for (key in listOf("expires_at", "earliest_refresh_at")) {
            if (value.opt(key) is Number) value.put(key, BigDecimal(value.get(key).toString()).movePointLeft(3))
        }
        value.optJSONObject("catalog")?.let { cache ->
            if (cache.opt("expires_at") is Number) cache.put("expires_at", BigDecimal(cache.get("expires_at").toString()).movePointLeft(3))
        }
        value.put("refresh_owner", "runtime")
        if (!value.has("issuer")) value.put("issuer", CHATGPT_ISSUER)
        if (purposes != null) value.put("model_purposes", purposes)
    }

    fun fromCore(profile: JSONObject): JSONObject = JSONObject(profile.toString()).also { value ->
        for (key in listOf("expires_at", "earliest_refresh_at")) {
            if (value.opt(key) is Number) value.put(key, BigDecimal(value.get(key).toString()).movePointRight(3).toLong())
        }
        value.optJSONObject("catalog")?.let { cache ->
            if (cache.opt("expires_at") is Number) cache.put("expires_at", BigDecimal(cache.get("expires_at").toString()).movePointRight(3).toLong())
        }
        value.remove("refresh_owner")
        value.remove("issuer")
    }
}
