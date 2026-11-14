package app.inku.mobile.llm

import app.inku.mobile.data.SignInServices
import app.inku.mobile.data.catalogRequest
import java.math.BigDecimal
import org.json.JSONArray
import org.json.JSONObject

/** The person's purposes for each ChatGPT model, and each model's assessment. */
internal data class ChatGptModelPolicy(val purposes: JSONObject = JSONObject(), val assessments: JSONObject = JSONObject()) {
    companion object {
        /** The measured [records] over the bundled catalog's rows: the one layering, for drawing and for the settings alike. */
        fun of(purposes: JSONObject, records: Map<String, JSONObject>): ChatGptModelPolicy =
            ChatGptModelPolicy(purposes, SignInServices.chatGptAssessments(records))
    }
}

/** Adapts the encrypted Android profile's millisecond timestamps to the shared policy. */
internal object ChatGptCore {
    /** A sign-in action (`sign_in_<name>`), sent for the ChatGPT service (step 6). */
    fun call(action: String, fields: JSONObject = JSONObject()): JSONObject {
        val result = catalogRequest(action, fields.put("service", CHATGPT_PROVIDER))
        result.optString("error").takeIf(String::isNotEmpty)?.let { throw ChatGptException(it) }
        return result
    }

    /**
     * The core's `sign_in_publication` for a registration (in the core's
     * units) under [policy]: each model's assessment, selectability and
     * purposes. The one place it is asked (step 6), for the check before and
     * during a drawing and for the drawing choices and the publishing picker.
     */
    fun publication(profile: JSONObject, policy: ChatGptModelPolicy, models: JSONArray? = null): JSONObject =
        call("sign_in_publication", JSONObject().put("profile", JSONObject(profile.toString()).put("model_purposes", policy.purposes))
            .put("models", models ?: JSONObject.NULL).put("assessments", policy.assessments)).getJSONObject("publication")

    fun toCore(profile: JSONObject, purposes: JSONObject? = null): JSONObject = JSONObject(profile.toString()).also { value ->
        for (key in listOf("expires_at", "earliest_refresh_at")) {
            if (value.opt(key) is Number) value.put(key, BigDecimal(value.get(key).toString()).movePointLeft(3))
        }
        value.optJSONObject("catalog")?.let { cache ->
            if (cache.opt("expires_at") is Number) cache.put("expires_at", BigDecimal(cache.get("expires_at").toString()).movePointLeft(3))
        }
        // As saved (step 5). A registration saved before step 5 has neither:
        // Android has always refreshed its own tokens, at the core's issuer.
        if (!value.has("refresh_owner")) value.put("refresh_owner", "runtime")
        if (!value.has("issuer")) value.put("issuer", issuer)
        if (purposes != null) value.put("model_purposes", purposes)
    }

    private val issuer: String by lazy { call("sign_in_auth_constants").getString("issuer") }

    fun fromCore(profile: JSONObject): JSONObject = JSONObject(profile.toString()).also { value ->
        for (key in listOf("expires_at", "earliest_refresh_at")) {
            if (value.opt(key) is Number) value.put(key, BigDecimal(value.get(key).toString()).movePointRight(3).toLong())
        }
        value.optJSONObject("catalog")?.let { cache ->
            if (cache.opt("expires_at") is Number) cache.put("expires_at", BigDecimal(cache.get("expires_at").toString()).movePointRight(3).toLong())
        }
    }
}
