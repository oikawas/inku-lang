package app.inku.mobile.data

import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.llm.ChatGptPlanView
import java.util.concurrent.ConcurrentHashMap
import org.json.JSONArray
import org.json.JSONObject

/**
 * The sign-in services of the core (`model_catalog_json`, actions
 * `sign_in_services` and `provider_groups`): connections where the author
 * signs in with their own account and its subscription allowance pays for the
 * models. For now only "Sign in with ChatGPT" (id `chatgpt`).
 *
 * The names, the abbreviation and the order of the groups come from the core
 * descriptor; this host keeps only the sign-in transport (`ChatGptPlanManager`).
 */
internal object SignInServices {
    private val byLanguage = ConcurrentHashMap<String, List<JSONObject>>()
    private val orders = ConcurrentHashMap<String, List<String>>()

    /** The core's public rows of every sign-in service, in the descriptor's order. */
    fun services(language: String): List<JSONObject> = byLanguage.getOrPut(language) {
        val rows = catalogRequest("sign_in_services", JSONObject().put("language", language)).getJSONArray("services")
        (0 until rows.length()).map { rows.getJSONObject(it) }
    }

    fun isSignIn(id: String): Boolean = services("en").any { it.getString("id") == id }

    /** The connection's name in [language] (`ja` or `en`), e.g. "ChatGPT でサインイン". */
    fun label(id: String, language: String): String =
        services(language).first { it.getString("id") == id }.getString("label")

    /**
     * [groups] in the core's `provider_groups` order: the signed-in services
     * first in the descriptor's order, then the others as given. A host that
     * puts some groups first (the on-device models) does so before calling.
     * Only the order is taken from the answer; each group is the host's own.
     */
    fun <T> order(groups: List<T>, id: (T) -> String): List<T> {
        val ids = groups.map(id)
        val ordered = orders.getOrPut(ids.joinToString("\u0000")) {
            val hostGroups = JSONArray()
            val signIn = JSONArray()
            ids.forEach { groupId ->
                if (isSignIn(groupId)) signIn.put(JSONObject().put("service", groupId).put("models", JSONArray()))
                else hostGroups.put(JSONObject().put("id", groupId))
            }
            val answer = catalogRequest("provider_groups", JSONObject().put("groups", hostGroups).put("sign_in", signIn))
                .getJSONArray("groups")
            (0 until answer.length()).map { answer.getJSONObject(it).getString("id") }
        }
        val byId = groups.associateBy(id)
        return ordered.map { byId.getValue(it) }
    }

    /**
     * The one provider row Sign in with ChatGPT is listed and routed by. The
     * connection is owned by `ChatGptPlanManager`, outside `provider_settings`.
     * The base URL is only there for the readiness check (`CameraDrawRoute`):
     * a request goes through the manager, and the core gives the transport in
     * step 4.
     */
    fun chatGptProviderSetting(plan: ChatGptPlanView): ProviderSettingEntity = ProviderSettingEntity(
        providerId = "chatgpt", displayName = label("chatgpt", "en"), kind = "chatgpt-responses",
        baseUrl = "https://api.openai.com/v1", encryptedApiKey = null,
        publishedModelsJson = JSONArray(plan.publishedModels).toString(),
        isEnabled = plan.canUsePlan, isDefaultLocal = false, updatedAt = 0,
    )
}
