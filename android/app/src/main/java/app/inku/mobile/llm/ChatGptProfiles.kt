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

data class ChatGptProfileView(
    val id: String, val label: String, val status: String, val planAllowed: Boolean,
    val scopes: List<String> = emptyList(),
)

/** A registration whose sign-in never finished (no `sub`): listed apart, to be reconnected (Web `pending_registrations`). */
data class ChatGptPendingRegistration(val id: String, val clientId: String?)

data class ChatGptPlanView(
    /** The finished registrations only. */
    val profiles: List<ChatGptProfileView> = emptyList(),
    val pendingRegistrations: List<ChatGptPendingRegistration> = emptyList(),
    val activeProfileId: String? = null,
    val pending: Boolean = false,
    val errorCode: String? = null,
    val revocationUnconfirmed: Boolean = false,
    val models: List<ChatGptModel>? = null,
    val publishedModels: List<String> = emptyList(),
    val activeSession: ChatGptSessionRef? = null,
    /**
     * The core's `sign_in_connection_view` answer: the status line, the
     * actions and each registration's status, as the Web's settings show them.
     */
    val connection: JSONObject? = null,
) {
    val active: ChatGptProfileView? get() = profiles.firstOrNull { it.id == activeProfileId }

    /** The chosen registration is connected and allowed the plan: the core's `guide`. */
    val canUsePlan: Boolean get() = connection?.optBoolean("guide") == true
}

/** The request for the core's `sign_in_connection_view` (Web `ChatGPTSettings.svelte`). */
internal fun chatGptConnectionRequest(
    profiles: List<ChatGptProfileView>, pendingRegistrations: List<ChatGptPendingRegistration>, activeProfileId: String?,
    pending: Boolean, errorCode: String?, revocationUnconfirmed: Boolean,
): JSONObject = JSONObject()
    .put("service", CHATGPT_PROVIDER)
    .put("connection", JSONObject()
        .put("active_profile_id", activeProfileId ?: JSONObject.NULL)
        .put("profiles", JSONArray().apply { profiles.forEach { profile ->
            put(JSONObject().put("id", profile.id).put("label", profile.label).put("state", profile.status).put("scopes", JSONArray(profile.scopes)))
        } })
        .put("pending_registrations", JSONArray().apply { pendingRegistrations.forEach { row ->
            put(JSONObject().put("id", row.id).put("client_id", row.clientId ?: JSONObject.NULL))
        } }))
    // Android opens Chrome once and cannot open the same page again; nothing to reopen.
    .put("attempt", JSONObject().put("active", pending).put("can_reopen", false).put("helper", false))
    // While Chrome is signing in, nothing else is pressed (as before; Android has no other busy state).
    .put("busy", pending)
    .put("code", errorCode ?: JSONObject.NULL)
    .put("last_operation", if (revocationUnconfirmed) "sign_out" else JSONObject.NULL)
    .put("revocation_confirmed", !revocationUnconfirmed)

/** Messages contain public codes only, never a response body or credential. */
class ChatGptException(
    val code: String,
    /**
     * The failure class the shared core receives, as the server's
     * `ChatGPTError.failure`: by default the one the server gives [code], set
     * where the same code is a refusal in one place and temporary in another.
     */
    failure: String? = null,
    /** What to do next (`retry`, `diagnose`, `usage`, …): the core's answer, by default its table's for [code]. */
    action: String? = null,
) : IllegalArgumentException(code) {
    val failure: String
    val action: String

    init {
        val row = if (failure == null || action == null) chatGptFailureRow(code) else null
        this.failure = failure ?: row!!.getString("failure")
        this.action = action ?: row!!.getString("action")
    }
}

/** The shared core's failure table (`chatgpt_failure`); a code it does not know is `provider_rejected`. */
internal fun chatGptFailureFor(code: String): String = chatGptFailureRow(code).getString("failure")

private fun chatGptFailureRow(code: String): JSONObject =
    SharedProviderWire.call(JSONObject().put("action", "chatgpt_failure").put("code", code))

internal const val CHATGPT_PROVIDER = "chatgpt"

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
    runCatching { ChatGptCore.call("chatgpt_auth_session", JSONObject().put("profile", ChatGptCore.toCore(this).put("state", "connected"))
        .put("generation", optLong("generation"))); true }.getOrDefault(false)

internal fun JSONObject.sessionRef(): ChatGptSessionRef = ChatGptSessionRef(getString("id"), getLong("generation"))

internal fun modelArray(models: List<ChatGptModel>): JSONArray = JSONArray().apply {
    models.forEach { put(JSONObject().put("id", it.id).put("label", it.label)) }
}
