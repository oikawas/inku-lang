package app.inku.mobile.llm

import androidx.room.withTransaction
import app.inku.mobile.data.db.AppSettingEntity
import app.inku.mobile.data.db.InkuDatabase
import org.json.JSONArray
import org.json.JSONObject
import app.inku.mobile.pipeline.CoreIdentityJson

internal fun encodeProviderRateState(state: JSONObject): String {
    fun ordered(value: JSONObject, first: List<String>): String {
        val rest = value.keys().asSequence().filter { it !in first }.toList().sorted()
        return (first.filter(value::has) + rest).joinToString(",", "{", "}") { key ->
            val encoded = if (key == "events") {
                val events = value.getJSONArray(key)
                (0 until events.length()).joinToString(",", "[", "]") { ordered(events.getJSONObject(it), listOf("id", "at", "tokens")) }
            } else CoreIdentityJson.encode(value.get(key))
            JSONObject.quote(key) + ":" + encoded
        }
    }
    return ordered(state, listOf("events", "day", "daily", "not_before"))
}

internal fun interface ProviderRateTransitions {
    suspend fun transition(providerId: String, request: JSONObject): JSONObject
}

internal fun transitionStoredProviderRateState(raw: String?, request: JSONObject): JSONObject {
    val state = if (raw == null) JSONObject().put("events", JSONArray()).put("day", "")
        .put("daily", 0).put("not_before", 0) else try {
        JSONObject(raw)
    } catch (_: Exception) {
        return JSONObject().put("error", "corrupt_state")
    }
    return SharedProviderAdmission.call(JSONObject(request.toString()).put("state", state))
}

/** Room owns the transaction; core owns every transition of the stored JSON. */
internal class ProviderRateState(private val database: InkuDatabase) : ProviderRateTransitions {
    override suspend fun transition(providerId: String, request: JSONObject): JSONObject = database.withTransaction {
        val key = "provider_rate_usage:$providerId"
        val raw = database.settingsDao().get(key)?.valueJson
        val answer = transitionStoredProviderRateState(raw, request)
        answer.optJSONObject("state")?.let { next ->
            database.settingsDao().upsert(AppSettingEntity(key,
                encodeProviderRateState(next), System.currentTimeMillis()))
        }
        answer
    }
}
