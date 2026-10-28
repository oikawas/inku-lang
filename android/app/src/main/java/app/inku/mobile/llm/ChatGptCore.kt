package app.inku.mobile.llm

import app.inku.mobile.data.catalogRequest
import org.json.JSONObject

/** Adapts the encrypted Android profile's millisecond timestamps to the shared policy. */
internal object ChatGptCore {
    fun call(action: String, fields: JSONObject = JSONObject()): JSONObject {
        val result = catalogRequest(action, fields)
        result.optString("error").takeIf(String::isNotEmpty)?.let { throw ChatGptException(it) }
        return result
    }

    fun toCore(profile: JSONObject): JSONObject = JSONObject(profile.toString()).also { value ->
        for (key in listOf("expires_at", "earliest_refresh_at")) {
            if (value.opt(key) is Number) value.put(key, value.getDouble(key) / 1000.0)
        }
        value.optJSONObject("catalog")?.let { cache ->
            if (cache.opt("expires_at") is Number) cache.put("expires_at", cache.getDouble("expires_at") / 1000.0)
        }
        value.put("refresh_owner", "runtime")
    }

    fun fromCore(profile: JSONObject): JSONObject = JSONObject(profile.toString()).also { value ->
        for (key in listOf("expires_at", "earliest_refresh_at")) {
            if (value.opt(key) is Number) value.put(key, (value.getDouble(key) * 1000).toLong())
        }
        value.optJSONObject("catalog")?.let { cache ->
            if (cache.opt("expires_at") is Number) cache.put("expires_at", (cache.getDouble("expires_at") * 1000).toLong())
        }
        value.remove("refresh_owner")
    }
}
