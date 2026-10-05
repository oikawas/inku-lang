package app.inku.mobile.llm

import android.content.Context
import android.util.AtomicFile
import app.inku.mobile.data.AndroidSecretBox
import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject

/** Only these non-secret values are saved with a pipeline execution. */
data class ChatGptSessionRef(val profileId: String, val generation: Long)

data class ChatGptModel(val id: String, val label: String)

data class ChatGptProfileView(val id: String, val label: String, val status: String, val planAllowed: Boolean)

data class ChatGptPlanView(
    val profiles: List<ChatGptProfileView> = emptyList(),
    val activeProfileId: String? = null,
    val pending: Boolean = false,
    val errorCode: String? = null,
    val revocationUnconfirmed: Boolean = false,
    val models: List<ChatGptModel>? = null,
    val publishedModels: List<String> = emptyList(),
    val activeSession: ChatGptSessionRef? = null,
    val showPlanNotice: Boolean = false,
) {
    val active: ChatGptProfileView? get() = profiles.firstOrNull { it.id == activeProfileId }
    val canUsePlan: Boolean get() = active?.let { it.status == "connected" && it.planAllowed } == true
}

/** Messages contain public codes only, never a response body or credential. */
class ChatGptException(
    val code: String,
    /**
     * The failure class the shared core receives, as the server's
     * `ChatGPTError.failure`: by default the one the server gives [code], set
     * where the same code is a refusal in one place and temporary in another.
     */
    val failure: String = chatGptFailureFor(code),
) : IllegalArgumentException(code)

/** The server's temporary ChatGPT failures; every other code is `provider_rejected`. */
internal fun chatGptFailureFor(code: String): String = when (code) {
    "chatgpt_transport_unavailable", "chatgpt_auth_unavailable", "chatgpt_response_incomplete",
    "subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable", "chatgpt_refresh_not_ready",
    -> "transport_unavailable"
    else -> "provider_rejected"
}

internal const val CHATGPT_PROVIDER = "chatgpt"
internal const val CHATGPT_ISSUER = "https://auth.openai.com"
internal const val CHATGPT_RESOURCE = "https://api.openai.com/v1"
internal const val CHATGPT_TOKEN = "$CHATGPT_ISSUER/api/accounts/oauth/token"
internal const val CHATGPT_USAGE = "https://chatgpt.com/settings/usage"
internal const val CHATGPT_SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"

/** A store's monitor serializes adoption, sign-out and generation checks. */
internal interface ChatGptCredentialStore {
    fun read(): JSONObject
    fun write(value: JSONObject)
}

internal class AndroidChatGptCredentialStore(context: Context) : ChatGptCredentialStore {
    private val file = AtomicFile(context.noBackupFilesDir.resolve("chatgpt-plan.enc"))

    override fun read(): JSONObject {
        if (!file.baseFile.exists()) return JSONObject().put("profiles", JSONObject())
        return try {
            val encrypted = file.openRead().use {
                val bytes = it.readNBytes(4 * 1024 * 1024 + 1)
                if (bytes.size > 4 * 1024 * 1024) throw ChatGptException("chatgpt_storage_unavailable")
                bytes.toString(Charsets.UTF_8)
            }
            if (!AndroidSecretBox.isEncrypted(encrypted)) throw ChatGptException("chatgpt_storage_unavailable")
            val plain = AndroidSecretBox.decryptOrPlain(encrypted) ?: throw ChatGptException("chatgpt_storage_unavailable")
            JSONObject(plain).also { it.getJSONObject("profiles") }
        } catch (_: Exception) {
            throw ChatGptException("chatgpt_storage_unavailable")
        }
    }

    override fun write(value: JSONObject) {
        var stream: java.io.FileOutputStream? = null
        try {
            val bytes = AndroidSecretBox.encrypt(value.toString()).toByteArray(Charsets.UTF_8)
            if (bytes.size > 4 * 1024 * 1024) throw ChatGptException("chatgpt_storage_unavailable")
            stream = file.startWrite()
            stream.write(bytes)
            file.finishWrite(stream)
        } catch (_: Exception) {
            stream?.let(file::failWrite)
            throw ChatGptException("chatgpt_storage_unavailable")
        }
    }
}

internal fun ChatGptCredentialStore.hostId(): String = synchronized(this) {
    val value = read()
    value.optString("host_id").takeIf { it.startsWith("urn:uuid:") } ?: ("urn:uuid:" + UUID.randomUUID()).also {
        write(value.put("host_id", it))
    }
}

internal fun JSONObject.stringList(key: String): List<String> = optJSONArray(key)?.let { array ->
    (0 until array.length()).map { array.getString(it) }
} ?: emptyList()

internal fun JSONObject.planAllowed(): Boolean =
    stringList("scopes").containsAll(listOf("resource.invoke", "chatgpt.tokens.use.direct"))

internal fun JSONObject.sessionRef(): ChatGptSessionRef = ChatGptSessionRef(getString("id"), getLong("generation"))

internal fun modelArray(models: List<ChatGptModel>): JSONArray = JSONArray().apply {
    models.forEach { put(JSONObject().put("id", it.id).put("label", it.label)) }
}
