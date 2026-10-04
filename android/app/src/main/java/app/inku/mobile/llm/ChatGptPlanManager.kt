package app.inku.mobile.llm

import java.net.InetAddress
import java.net.ServerSocket
import java.net.SocketTimeoutException
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject

/** One locally hosted Android user. Profiles remain separate by verified sub and client ID. */
class ChatGptPlanManager internal constructor(
    private val store: ChatGptCredentialStore,
    private val scope: CoroutineScope,
    private val http: ChatGptHttp = UrlConnectionChatGptHttp(),
    private val now: () -> Long = System::currentTimeMillis,
) : ModelProvider {
    override val providerId: String = CHATGPT_PROVIDER
    private val mutableState = MutableStateFlow(ChatGptPlanView())
    val state: StateFlow<ChatGptPlanView> = mutableState.asStateFlow()
    private val refreshMutex = Mutex()
    private val wireMutex = Mutex()
    private var authorization: Authorization? = null

    private class Authorization(val profileId: String, val previous: JSONObject?, val listener: ServerSocket,
                                val japanese: Boolean, val deadline: Long) {
        val state = randomOAuthValue()
        val nonce = randomOAuthValue()
        val verifier = randomOAuthValue()
        val redirectUri = "http://127.0.0.1:${listener.localPort}/auth/callback"
        @Volatile var cancelled = false
        @Volatile var used = false
        var job: Job? = null
    }

    init { updateView() }

    private fun updateView(errorCode: String? = null, revocationUnconfirmed: Boolean = false): Unit = synchronized(store) {
        try {
            val saved = store.read()
            val profiles = saved.getJSONObject("profiles")
            val activeId = saved.optString("active").takeIf(String::isNotEmpty)
            val active = activeId?.let(profiles::optJSONObject)
            val cache = active?.optJSONObject("catalog")?.optJSONArray("models")
            mutableState.value = ChatGptPlanView(
                profiles = profiles.keys().asSequence().map { id ->
                    val item = profiles.getJSONObject(id)
                    ChatGptProfileView(id, item.optString("label", "ChatGPT / " + item.optString("client_id").takeLast(8)),
                        item.optString("state", "reauthentication_required"), item.planAllowed())
                }.toList(),
                activeProfileId = activeId, pending = authorization != null,
                errorCode = errorCode, revocationUnconfirmed = revocationUnconfirmed,
                models = cache?.let { (0 until it.length()).map { i -> it.getJSONObject(i).let { model -> ChatGptModel(model.getString("id"), model.getString("label")) } } },
                publishedModels = active?.stringList("published_models") ?: emptyList(),
                activeSession = active?.sessionRef(),
                showPlanNotice = active?.let { it.optString("state") == "connected" && it.planAllowed() && !it.optBoolean("plan_notice_seen") } == true,
            )
        } catch (_: Exception) {
            mutableState.value = ChatGptPlanView(errorCode = "chatgpt_storage_unavailable")
        }
    }

    fun cancelAuthorization(): Unit = synchronized(store) {
        authorization?.let { it.cancelled = true; it.listener.close(); it.job?.cancel() }
        authorization = null
        updateView()
    }

    suspend fun authorize(profileId: String? = null, consent: Boolean = false, japanese: Boolean = true): String {
        val attempt = synchronized(store) {
            if (authorization != null) throw ChatGptException("chatgpt_attempt_busy")
            val profiles = store.read().getJSONObject("profiles")
            val previous = profileId?.let { profiles.optJSONObject(it) ?: throw ChatGptException("chatgpt_not_connected") }
            if (previous == null && profiles.length() >= 8) throw ChatGptException("chatgpt_profile_limit")
            Authorization(profileId ?: UUID.randomUUID().toString(), previous, ServerSocket(0, 4, InetAddress.getByName("127.0.0.1")), japanese, now() + 300_000)
                .also { authorization = it; updateView() }
        }
        val url = try {
            authorizationUrl(store.hostId(), attempt.redirectUri, attempt.state, attempt.nonce, attempt.verifier, attempt.previous, consent)
        } catch (error: Exception) { cancelAuthorization(); throw error }
        attempt.job = scope.launch(Dispatchers.IO) { listen(attempt) }
        return url
    }

    private fun checkAttempt(attempt: Authorization): Unit = synchronized(store) {
        if (attempt.cancelled || authorization !== attempt || now() >= attempt.deadline) throw ChatGptException("chatgpt_cancelled")
        val current = store.read().getJSONObject("profiles").optJSONObject(attempt.profileId)
        if (attempt.previous != null && current?.optLong("generation") != attempt.previous.optLong("generation")) throw ChatGptException("chatgpt_session_changed")
        if (attempt.previous == null && current != null && (current.optLong("generation") != 0L || current.optString("state") != "reauthentication_required")) throw ChatGptException("chatgpt_session_changed")
    }

    private suspend fun listen(attempt: Authorization) {
        try {
            attempt.listener.soTimeout = 1000
            while (!attempt.used) {
                checkAttempt(attempt)
                val socket = try { attempt.listener.accept() } catch (_: SocketTimeoutException) { continue }
                socket.use {
                    socket.soTimeout = 1000
                    var consumed = false
                    var success = false
                    var code: String? = null
                    try {
                        val input = socket.getInputStream()
                        val request = readLine(input, 16_384).split(' ')
                        if (request.size != 3 || request[0] != "GET") throw ChatGptException("chatgpt_callback_invalid")
                        var headerBytes = 0; var host: String? = null
                        while (true) {
                            val line = readLine(input, 4096)
                            headerBytes += line.length
                            if (headerBytes > 16_384) throw ChatGptException("chatgpt_callback_invalid")
                            if (line.isEmpty()) break
                            if (line.substringBefore(':').equals("host", ignoreCase = true)) {
                                if (host != null) throw ChatGptException("chatgpt_callback_invalid")
                                host = line.substringAfter(':').trim()
                            }
                        }
                        if (host != "127.0.0.1:${attempt.listener.localPort}") throw ChatGptException("chatgpt_callback_invalid")
                        val query = callbackParameters(request[1])
                        if (!callbackStateMatches(query, attempt.state)) throw ChatGptException("chatgpt_callback_invalid")
                        synchronized(store) {
                            checkAttempt(attempt)
                            if (attempt.used) throw ChatGptException("chatgpt_callback_invalid")
                            attempt.used = true; consumed = true
                        }
                        val client = issuedClientId(query, attempt.previous)
                        withTimeout((attempt.deadline - now()).coerceAtLeast(1)) { exchange(attempt, client, query.getValue("code")) }
                        success = true
                    } catch (cancelled: CancellationException) { throw cancelled }
                    catch (error: Exception) { code = (error as? ChatGptException)?.code ?: "chatgpt_auth_unavailable" }
                    val text = if (attempt.japanese) {
                        if (success) "ChatGPTの認証が完了しました。このタブを閉じ、inkuへ戻ってモデル設定を開いてください。"
                        else "ChatGPTの認証は完了していません。inkuへ戻り、接続の案内を確認してください。"
                    } else {
                        if (success) "ChatGPT authorization completed. Close this tab, return to inku and open Model settings."
                        else "ChatGPT authorization did not complete. Return to inku and check the connection message."
                    }
                    val body = ("<!doctype html><html lang=\"${if (attempt.japanese) "ja" else "en"}\"><meta charset=\"utf-8\"><title>inku</title><p>$text</p></html>").toByteArray(Charsets.UTF_8)
                    runCatching { socket.getOutputStream().apply {
                        write(("HTTP/1.1 ${if (success) "200 OK" else "400 Bad Request"}\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\nContent-Length: ${body.size}\r\n\r\n").toByteArray(Charsets.US_ASCII)); write(body); flush()
                    } }
                    if (consumed) synchronized(store) {
                        if (authorization === attempt) { authorization = null; updateView(code) }
                    }
                }
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) { synchronized(store) {
            if (authorization === attempt) { authorization = null; updateView((error as? ChatGptException)?.code ?: "chatgpt_auth_unavailable") }
        } } finally { attempt.listener.close() }
    }

    private suspend fun exchange(attempt: Authorization, client: String, code: String) {
        val check = { checkAttempt(attempt) }
        // Retain the issued ID on a failed code exchange; it is never an authorized profile.
        if (attempt.previous == null) synchronized(store) {
            check()
            val value = store.read()
            value.getJSONObject("profiles").put(attempt.profileId, JSONObject().put("id", attempt.profileId).put("client_id", client)
                .put("generation", 0).put("state", "reauthentication_required"))
            store.write(value)
        }
        val tokens = authJson(CHATGPT_TOKEN, "POST", form(mapOf("grant_type" to "authorization_code", "client_id" to client,
            "code" to code, "code_verifier" to attempt.verifier, "redirect_uri" to attempt.redirectUri, "resource" to CHATGPT_RESOURCE)), check)
        val claims = identity(tokens.getString("id_token"), client, attempt.nonce, check)
        if (attempt.previous?.has("sub") == true && claims.getString("sub") != attempt.previous.getString("sub")) throw ChatGptException("chatgpt_identity_mismatch")
        val profile = tokenFields(tokens, null).put("id", attempt.profileId).put("client_id", client)
            .put("sub", claims.getString("sub")).put("generation", (attempt.previous?.optLong("generation") ?: 0) + 1)
            .put("label", claims.optString("email", "ChatGPT").take(254) + " / " + client.takeLast(8)).put("state", "connected")
            .put("email", claims.optString("email").take(254)).put("plan_notice_seen", attempt.previous?.optBoolean("plan_notice_seen") ?: false)
            .put("published_models", attempt.previous?.optJSONArray("published_models") ?: JSONArray())
        synchronized(store) {
            check()
            val value = store.read()
            value.getJSONObject("profiles").put(attempt.profileId, profile)
            value.put("active", attempt.profileId)
            store.write(value)
            http.cancelAll()
        }
    }

    fun selectProfile(id: String): Unit = synchronized(store) {
        cancelAuthorization()
        val value = store.read()
        val profiles = value.getJSONObject("profiles")
        if (!profiles.has(id)) throw ChatGptException("chatgpt_not_connected")
        if (value.optString("active") == id) return@synchronized
        profiles.optJSONObject(value.optString("active"))?.let { it.put("generation", it.getLong("generation") + 1) }
        profiles.getJSONObject(id).let { it.put("generation", it.getLong("generation") + 1) }
        store.write(value.put("active", id)); http.cancelAll(); updateView()
    }

    fun pinSession(): ChatGptSessionRef = synchronized(store) {
        val value = store.read()
        val profile = value.getJSONObject("profiles").optJSONObject(value.optString("active")) ?: throw ChatGptException("chatgpt_not_connected")
        checkSession(profile.sessionRef())
        profile.sessionRef()
    }

    internal fun checkSession(ref: ChatGptSessionRef): JSONObject = synchronized(store) {
        val value = store.read()
        val profile = value.getJSONObject("profiles").optJSONObject(ref.profileId) ?: throw ChatGptException("chatgpt_not_connected")
        if (value.optString("active") != ref.profileId || profile.getLong("generation") != ref.generation) throw ChatGptException("chatgpt_session_changed")
        when (profile.optString("state")) {
            "connected" -> Unit
            "quota" -> throw ChatGptException("subscription_sharing_usage_limit_exceeded")
            else -> throw ChatGptException("chatgpt_reauthentication_required")
        }
        if (!profile.planAllowed()) throw ChatGptException("chatgpt_plan_not_authorized")
        profile
    }

    suspend fun refreshModels(): List<String> {
        val ref = synchronized(store) {
            val value = store.read()
            val profile = value.getJSONObject("profiles").optJSONObject(value.optString("active")) ?: throw ChatGptException("chatgpt_not_connected")
            // A deliberate refresh can check whether the usage window has reopened.
            if (profile.optString("state") == "quota") {
                profile.put("state", "connected").put("generation", profile.getLong("generation") + 1)
                store.write(value); updateView()
            }
            pinSession()
        }
        try {
            return withTimeout(30_000) { wireMutex.withLock { catalog(ref, force = true).map { it.id } } }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) {
            val safe = error as? ChatGptException ?: ChatGptException("chatgpt_transport_unavailable")
            invalidateForFailure(ref, safe.code)
            reportFailure(ref, safe.code); throw safe
        }
    }

    fun acknowledgePlanNotice(): Unit = synchronized(store) {
        val value = store.read()
        value.getJSONObject("profiles").optJSONObject(value.optString("active"))?.put("plan_notice_seen", true)
        store.write(value); updateView()
    }

    fun browserUnavailable() { cancelAuthorization(); updateView("chatgpt_browser_unavailable") }

    fun publishModels(ref: ChatGptSessionRef, models: List<String>): Unit = synchronized(store) {
        val profile = checkSession(ref)
        val offered = profile.optJSONObject("catalog")?.getJSONArray("models") ?: throw ChatGptException("chatgpt_catalog_required")
        val ids = (0 until offered.length()).map { offered.getJSONObject(it).getString("id") }.toSet()
        if (models.any { it !in ids }) throw ChatGptException("chatgpt_model_unavailable")
        val value = store.read()
        profile.put("published_models", JSONArray(models.distinct()))
        value.getJSONObject("profiles").put(ref.profileId, profile)
        store.write(value); http.cancelAll(); updateView()
    }

    private suspend fun catalog(ref: ChatGptSessionRef, force: Boolean = false): List<ChatGptModel> {
        val profile = checkSession(ref)
        val cache = profile.optJSONObject("catalog")
        val entries = if (!force && cache != null && cache.optLong("expires_at") > now()) cache.getJSONArray("models") else {
            val token = accessToken(ref)
            val response = http.request("$CHATGPT_RESOURCE/models", token = token, check = { checkSession(ref); Unit })
            val json = JSONObject(response.body)
            if (response.status !in 200..299) throw chatGptResponseError(json, response.status)
            val raw = json.getJSONArray("models")
            val models = (0 until raw.length()).map { raw.getJSONObject(it) }.filter { it.optString("visibility") == "list" }
                .map { ChatGptModel(it.getString("slug"), it.getString("display_name")) }
            if (models.any { it.id.isBlank() || it.id.length > 256 || it.label.length > 512 }) throw ChatGptException("chatgpt_response_invalid")
            val result = modelArray(models.distinctBy { it.id })
            synchronized(store) {
                val current = checkSession(ref)
                current.put("catalog", JSONObject().put("expires_at", now() + 300_000).put("models", result))
                val value = store.read(); value.getJSONObject("profiles").put(ref.profileId, current); store.write(value); updateView()
            }
            result
        }
        return (0 until entries.length()).map { entries.getJSONObject(it).let { model -> ChatGptModel(model.getString("id"), model.getString("label")) } }
    }

    private suspend fun accessToken(ref: ChatGptSessionRef): String = refreshMutex.withLock {
        val profile = checkSession(ref)
        if (profile.getLong("expires_at") > now() + 60_000) return@withLock profile.getString("access_token")
        if (now() < profile.optLong("earliest_refresh_at")) {
            if (profile.getLong("expires_at") > now()) return@withLock profile.getString("access_token")
            throw ChatGptException("chatgpt_refresh_not_ready")
        }
        val check = { checkSession(ref); Unit }
        try {
            val tokens = authJson(CHATGPT_TOKEN, "POST", form(mapOf("grant_type" to "refresh_token", "client_id" to profile.getString("client_id"),
                "refresh_token" to profile.getString("refresh_token"), "resource" to CHATGPT_RESOURCE)), check)
            tokens.optString("id_token").takeIf(String::isNotEmpty)?.let {
                if (identity(it, profile.getString("client_id"), null, check).getString("sub") != profile.getString("sub")) throw ChatGptException("chatgpt_identity_mismatch")
            }
            val fields = tokenFields(tokens, profile)
            synchronized(store) {
                val current = checkSession(ref)
                fields.keys().forEach { current.put(it, fields.get(it)) }
                current.remove("catalog")
                val value = store.read(); value.getJSONObject("profiles").put(ref.profileId, current); store.write(value); updateView()
            }
            fields.getString("access_token")
        } catch (error: ChatGptException) {
            if (error.code == "chatgpt_reauthentication_required") invalidate(ref, "reauthentication_required")
            throw error
        }
    }

    override suspend fun generate(request: ModelRequest): ModelResponse {
        // Validate the operation before opening any connection, including catalog retrieval.
        val body = chatGptRequestBody(request)
        val ref = request.chatGptSession ?: throw ChatGptException("chatgpt_session_required")
        val started = System.nanoTime()
        try {
            return withTimeout(request.timeoutMs ?: 60_000) { wireMutex.withLock {
                val slug = request.modelId.removePrefix("chatgpt:")
                val offered = catalog(ref)
                fun check() {
                    val profile = checkSession(ref)
                    if (slug !in profile.stringList("published_models") || offered.none { it.id == slug }) throw ChatGptException("chatgpt_model_unavailable")
                }
                check()
                val token = accessToken(ref)
                val decoder = ChatGptSseDecoder()
                val response = http.request("$CHATGPT_RESOURCE/responses", "POST", token, body.toString(), timeoutMs = request.timeoutMs ?: 60_000,
                    check = ::check, onChunk = decoder::feed)
                if (response.status !in 200..299) throw chatGptResponseError(runCatching { JSONObject(response.body) }.getOrDefault(JSONObject()), response.status)
                val text = decoder.finish(); check()
                ModelResponse(text, request.modelId, decoder.usage?.optInt("input_tokens")?.takeIf { it > 0 },
                    decoder.usage?.optInt("output_tokens")?.takeIf { it > 0 }, (System.nanoTime() - started) / 1_000_000)
            } }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) {
            val safe = (error as? ChatGptException) ?: ChatGptException("chatgpt_transport_unavailable")
            invalidateForFailure(ref, safe.code)
            reportFailure(ref, safe.code)
            throw safe
        }
    }

    private fun reportFailure(ref: ChatGptSessionRef, code: String): Unit = synchronized(store) {
        val value = store.read()
        val profile = value.getJSONObject("profiles").optJSONObject(ref.profileId)
        if (value.optString("active") == ref.profileId && profile != null &&
            (profile.optLong("generation") == ref.generation || profile.optLong("generation") == ref.generation + 1 &&
                profile.optString("state") in setOf("quota", "reauthentication_required"))) updateView(code)
    }

    private fun invalidateForFailure(ref: ChatGptSessionRef, code: String) {
        when (code) {
            "subscription_sharing_usage_limit_exceeded" -> invalidate(ref, "quota", removeTokens = false)
            "chatgpt_admission_rejected", "subscription_sharing_invalid_user", "chatpass_v2_invalid_authorization_context",
            "chatpass_v2_scope_not_authorized" -> invalidate(ref, "reauthentication_required")
        }
    }

    private fun invalidate(ref: ChatGptSessionRef, status: String, removeTokens: Boolean = true): Unit = synchronized(store) {
        val value = store.read()
        val profile = value.getJSONObject("profiles").optJSONObject(ref.profileId) ?: return@synchronized
        if (profile.optLong("generation") != ref.generation) return@synchronized
        profile.put("state", status).put("generation", ref.generation + 1).remove("catalog")
        if (removeTokens) listOf("access_token", "refresh_token", "id_token", "scopes").forEach(profile::remove)
        store.write(value); http.cancelAll(); updateView()
    }

    suspend fun signOut(id: String) {
        val old = synchronized(store) {
            cancelAuthorization()
            val profile = store.read().getJSONObject("profiles").optJSONObject(id) ?: throw ChatGptException("chatgpt_not_connected")
            val copy = JSONObject(profile.toString())
            invalidate(profile.sessionRef(), "signed_out")
            copy
        }
        var confirmed = false
        try {
            withTimeout(10_000) {
                if (old.has("refresh_token")) {
                    val metadata = discovery()
                    val endpoint = metadata.getString("revocation_endpoint"); validateAuthEndpoint(endpoint)
                    val response = http.request(endpoint, "POST", body = form(mapOf("token" to old.getString("refresh_token"),
                        "token_type_hint" to "refresh_token", "client_id" to old.getString("client_id"))), formBody = true, timeoutMs = 10_000)
                    confirmed = response.status == 200
                }
            }
        } catch (cancelled: CancellationException) { updateView(revocationUnconfirmed = true); throw cancelled }
        catch (_: Exception) { /* Local tokens were removed before the network operation. */ }
        updateView(revocationUnconfirmed = !confirmed)
    }

    private suspend fun authJson(url: String, method: String = "GET", body: String? = null, check: () -> Unit = {}): JSONObject {
        validateAuthEndpoint(url)
        val response = http.request(url, method, body = body, formBody = body != null, check = check)
        val value = runCatching { JSONObject(response.body) }.getOrElse { throw ChatGptException("chatgpt_auth_unavailable") }
        if (response.status !in 200..299) {
            val error = value.opt("error").let { if (it is JSONObject) it.optString("code") else it as? String }
            val expired = setOf("invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused")
            throw ChatGptException(if (error in expired) "chatgpt_reauthentication_required" else if (response.status >= 500) "chatgpt_auth_unavailable" else "chatgpt_auth_rejected")
        }
        return value
    }

    private suspend fun discovery(check: () -> Unit = {}): JSONObject = authJson("$CHATGPT_ISSUER/.well-known/openid-configuration", check = check).also {
        if (it.getString("issuer") != CHATGPT_ISSUER) throw ChatGptException("chatgpt_identity_invalid")
        validateAuthEndpoint(it.getString("jwks_uri"))
    }

    private suspend fun identity(token: String, client: String, nonce: String?, check: () -> Unit): JSONObject {
        val metadata = discovery(check)
        val keys = authJson(metadata.getString("jwks_uri"), check = check)
        check()
        return validateChatGptIdentity(token, client, nonce, metadata, keys, now() / 1000)
    }

    private fun tokenFields(value: JSONObject, previous: JSONObject?): JSONObject {
        if (!value.optString("token_type").equals("Bearer", ignoreCase = true)) throw ChatGptException("chatgpt_identity_invalid")
        for (key in listOf("access_token", "refresh_token")) {
            val token = value.opt(key)
            if (token !is String || token.length !in 1..65_536) throw ChatGptException("chatgpt_identity_invalid")
        }
        val expiry = value.getDouble("expires_in")
        if (!expiry.isFinite() || expiry <= 0 || expiry > 86_400) throw ChatGptException("chatgpt_identity_invalid")
        val earliest = when (val item = value.opt("earliest_refresh_at")) {
            is String -> Instant.parse(item).toEpochMilli()
            is Number -> { if (!item.toDouble().isFinite()) throw ChatGptException("chatgpt_identity_invalid"); (item.toDouble() * 1000).toLong() }
            else -> 0L
        }
        if (value.has("scope") && value.opt("scope") !is String) throw ChatGptException("chatgpt_identity_invalid")
        return JSONObject().put("access_token", value.getString("access_token")).put("refresh_token", value.getString("refresh_token"))
            .put("id_token", value.optString("id_token", previous?.optString("id_token").orEmpty()))
            .put("expires_at", now() + (expiry * 1000).toLong()).put("earliest_refresh_at", earliest)
            .put("scopes", if (value.has("scope")) JSONArray(value.getString("scope").split(' ').filter(String::isNotEmpty)) else previous?.optJSONArray("scopes") ?: JSONArray())
    }

    private fun validateAuthEndpoint(url: String) {
        val uri = java.net.URI(url)
        if (uri.scheme != "https" || uri.rawAuthority != "auth.openai.com" || uri.fragment != null) throw ChatGptException("chatgpt_identity_invalid")
    }

    private fun readLine(input: java.io.InputStream, limit: Int): String {
        val result = StringBuilder()
        while (result.length < limit) {
            val value = input.read()
            if (value == -1) throw ChatGptException("chatgpt_callback_invalid")
            if (value == 10) return result.toString().removeSuffix("\r")
            if (value != 13 && value !in 32..126) throw ChatGptException("chatgpt_callback_invalid")
            result.append(value.toChar())
        }
        throw ChatGptException("chatgpt_callback_invalid")
    }
}
