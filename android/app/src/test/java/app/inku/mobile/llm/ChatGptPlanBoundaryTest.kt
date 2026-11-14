package app.inku.mobile.llm

import java.net.HttpURLConnection
import java.net.URI
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.Signature
import java.security.interfaces.RSAPublicKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

// The values the core sends to (step 5 moved them out of the app); the fake server answers by them.
private const val CHATGPT_ISSUER = "https://auth.openai.com"
private const val CHATGPT_RESOURCE = "https://api.openai.com/v1"
private const val CHATGPT_TOKEN = "$CHATGPT_ISSUER/api/accounts/oauth/token"
private const val CHATGPT_SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"

private fun form(values: Map<String, String>): String = values.entries.joinToString("&") {
    java.net.URLEncoder.encode(it.key, Charsets.UTF_8) + "=" + java.net.URLEncoder.encode(it.value, Charsets.UTF_8)
}

class ChatGptPlanBoundaryTest {
    private class Store : ChatGptCredentialStore {
        var value = JSONObject().put("profiles", JSONObject())
        override fun read() = JSONObject(value.toString())
        override fun write(value: JSONObject) { this.value = JSONObject(value.toString()) }
    }

    private class Http : ChatGptHttp {
        val calls = java.util.Collections.synchronizedList(mutableListOf<String>())
        var chunkSize = 7
        /** Streamed instead of a 200 body's UTF-8, for bytes no String holds. */
        var streamBytes: ByteArray? = null
        var handler: (String, String?, String?) -> ChatGptHttpResponse = { _, _, _ -> error("Unexpected request") }
        /** What the core said for each request. */
        val sends = java.util.Collections.synchronizedList(mutableListOf<ChatGptSend>())
        override suspend fun request(send: ChatGptSend, token: String?, body: String?,
                                     timeoutMs: Long, check: () -> Unit, onChunk: ((ByteArray) -> Unit)?): ChatGptHttpResponse {
            val url = send.url
            check(); calls.add(url); sends.add(send)
            // A procedure's request carries its token in the core's headers.
            val result = handler(url, token ?: send.headers["Authorization"]?.removePrefix("Bearer "), body)
            check()
            if (onChunk != null && result.status == 200) {
                (streamBytes ?: result.body.toByteArray()).asList().chunked(chunkSize).forEach { check(); onChunk(it.toByteArray()) }
                return result.copy(body = "")
            }
            return result
        }
        override fun cancelAll() = Unit
    }

    private val now = 1_800_000_000_000L
    private val pair = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
    private val metadata = JSONObject().put("issuer", CHATGPT_ISSUER).put("jwks_uri", "$CHATGPT_ISSUER/jwks")
        .put("id_token_signing_alg_values_supported", JSONArray().put("RS256"))
    private val keys = (pair.public as RSAPublicKey).let { key ->
        fun number(value: java.math.BigInteger) = base64Url(value.toByteArray().dropWhile { it == 0.toByte() }.toByteArray())
        JSONObject().put("keys", JSONArray().put(JSONObject().put("kty", "RSA").put("kid", "test-key")
            .put("n", number(key.modulus)).put("e", number(key.publicExponent))))
    }

    private fun signedIdentity(nonce: String, client: String = "issued-client", subject: String = "person-a"): String {
        val header = base64Url(JSONObject().put("alg", "RS256").put("kid", "test-key").toString().toByteArray())
        val claims = base64Url(JSONObject().put("iss", CHATGPT_ISSUER).put("aud", client).put("sub", subject)
            .put("exp", now / 1000 + 3600).put("nonce", nonce).put("email", "test@example.invalid").toString().toByteArray())
        val input = "$header.$claims"
        val signature = Signature.getInstance("SHA256withRSA").apply { initSign(pair.private); update(input.toByteArray()) }.sign()
        return "$input.${base64Url(signature)}"
    }

    private fun query(url: String): Map<String, String> = URI(url).rawQuery.split('&').filter(String::isNotEmpty).associate { pair ->
        val (name, value) = pair.split('=', limit = 2).let { it[0] to it.getOrElse(1) { "" } }
        java.net.URLDecoder.decode(name, Charsets.UTF_8) to java.net.URLDecoder.decode(value, Charsets.UTF_8)
    }
    private fun tokens(nonce: String) = JSONObject().put("token_type", "Bearer").put("access_token", "test-access")
        .put("refresh_token", "test-refresh").put("expires_in", 3600).put("scope", CHATGPT_SCOPE)
        .put("id_token", signedIdentity(nonce))
    private fun profile(id: String) = JSONObject().put("id", id).put("client_id", "issued-$id").put("sub", "person-$id")
        .put("generation", 1).put("state", "connected").put("scopes", JSONArray(CHATGPT_SCOPE.split(' ')))
        .put("access_token", "access-$id").put("refresh_token", "refresh-$id").put("expires_at", now + 3_600_000)
        .put("published_models", JSONArray())
    private fun request(ref: ChatGptSessionRef) = ModelRequest("chatgpt:personal-model", "Draw a circle", 0.0, 2048,
        systemInstruction = "Pipeline instruction", tool = ModelTool("core-name", "core-description", "{\"type\":\"object\"}"),
        pipelineAction = "generate_normalized_ddl", chatGptSession = ref)
    private fun event(type: String, key: String, value: JSONObject) = JSONObject().put("type", type).put(key, value).let { "data: $it\r\n\r\n" }
    private fun function(arguments: String = "{\"ddl\":\"赤い円。\"}") = JSONObject().put("type", "function_call").put("namespace", "inku").put("name", "submit_pipeline_response")
        .put("id", "call-item").put("status", "completed").put("arguments", arguments)
    private fun completedStream(arguments: String = "{\"ddl\":\"赤い円。\"}"): String = event("response.output_item.added", "item", function().put("arguments", "")) +
        event("response.output_item.done", "item", function(arguments)) + event("response.completed", "response",
            JSONObject().put("status", "completed").put("output", JSONObject.NULL).put("usage", JSONObject().put("input_tokens", 10).put("output_tokens", 12)))

    /** A stream read as the plan manager reads it: received in pieces, then read once by the core. */
    private fun stream(mode: String = "pipeline"): ChatGptStream {
        val limit = if (mode == "text") 512 * 1024 else MAX_PROVIDER_RESPONSE_BYTES
        val wire = SharedProviderWire.call(JSONObject().put("action", "sign_in_limits").put("service", CHATGPT_PROVIDER)
            .put("answer_limit", limit)).getLong("wire_limit")
        // Only the stream is read here; where it would be sent does not matter.
        return ChatGptStream(ChatGptRequest("", mode, limit, wire,
            ChatGptSend("https://api.openai.com/v1/responses", "POST", emptyMap(), "Authorization", "Bearer ", limit, 65536, null)))
    }

    private fun rejected(code: String, block: () -> Unit) {
        try { block(); fail("Expected $code") } catch (error: ChatGptException) { assertEquals(code, error.code) }
    }

    private fun callbackResponse(start: Map<String, String>, client: String): Pair<Int, String> {
        val url = start.getValue("redirect_uri") + "?" + form(mapOf("state" to start.getValue("state"), "code" to "test-code", "client_id" to client))
        val connection = URI(url).toURL().openConnection() as HttpURLConnection
        connection.connectTimeout = 2000; connection.readTimeout = 3000
        return try {
            val status = connection.responseCode
            val body = (if (status >= 400) connection.errorStream else connection.inputStream).bufferedReader().use { it.readText() }
            status to body
        } finally { connection.disconnect() }
    }

    private fun completeCallback(start: Map<String, String>, client: String): Int = callbackResponse(start, client).first

    @Test
    fun failedLoginLogsOnlySafeDiagnosticFields() = runBlocking {
        val store = Store(); val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val logs = java.util.Collections.synchronizedList(mutableListOf<String>())
        val verifier = java.util.concurrent.atomic.AtomicReference<String>()
        val manager = ChatGptPlanManager(store, scope, http, diagnostic = { logs.add(it) }) { now }
        try {
            val start = query(manager.authorize())
            val sensitive = listOf("fake-secret-token-xyz", "https://secret.invalid/private", "person@example.invalid",
                "test-code", "issued-client", start.getValue("state"), start.getValue("nonce"), start.getValue("code_challenge"))
            http.handler = { url, _, body ->
                assertEquals(CHATGPT_TOKEN, url)
                verifier.set(query("https://test.invalid/?$body").getValue("code_verifier"))
                assertFalse(verifier.get().isEmpty())
                ChatGptHttpResponse(401, JSONObject().put("error", "invalid_grant")
                    .put("secret", sensitive.joinToString(" ") + " " + verifier.get()).toString())
            }
            val response = callbackResponse(start, "issued-client")
            assertEquals(200, response.first)
            // The core's received page (respond_before_exchange): answered before the code is exchanged.
            assertTrue(response.second.contains("ChatGPTでの許可を受け取りました"))
            assertTrue(response.second.contains("inkuへ戻ると接続を完了します。"))
            withTimeout(2000) { while (logs.isEmpty()) delay(5) }
            assertEquals(1, logs.size)
            val line = logs.single()
            assertTrue(line.contains("stage=token"))
            assertTrue(line.contains("code=chatgpt_reauthentication_required"))
            assertTrue(line.contains("status=401"))
            assertTrue(line.contains("class=app.inku.mobile.llm.ChatGptException"))
            assertTrue(Regex("frames=[A-Za-z0-9_]+\\.kt:[0-9]+").containsMatchIn(line))
            sensitive.forEach { assertFalse("Sensitive value entered the diagnostic", line.contains(it)) }
            assertFalse(line.contains(verifier.get()))
            assertFalse(line.contains("auth.openai.com"))
            assertFalse(line.contains("\n"))
            val injected = ChatGptException("fake-secret-token-xyz", "person@example.invalid")
            injected.stackTrace = arrayOf(StackTraceElement("app.inku.mobile.Fake", "execute", "secret-token-xyz.kt", 42))
            val safeLine = ChatGptDiagnostic.line("token", 401, injected)
            assertTrue(safeLine.contains("code=unrecognized"))
            sensitive.forEach { assertFalse(safeLine.contains(it)) }
            assertFalse(safeLine.contains("secret-token-xyz.kt"))
            val parseFailure = org.json.JSONException(sensitive.joinToString(" "))
            val parseLine = ChatGptDiagnostic.line("identity", null, parseFailure)
            sensitive.forEach { assertFalse(parseLine.contains(it)) }
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun callbackWaitsForForegroundBeforeTokenAndCatalog() = runBlocking {
        val store = Store(); val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val foreground = kotlinx.coroutines.flow.MutableStateFlow(false)
        val manager = ChatGptPlanManager(store, scope, http, foreground = foreground) { now }
        try {
            val start = query(manager.authorize(japanese = false))
            http.handler = { url, _, _ -> when {
                url == CHATGPT_TOKEN -> ChatGptHttpResponse(200, tokens(start.getValue("nonce")).toString())
                url.endsWith("openid-configuration") -> ChatGptHttpResponse(200, metadata.toString())
                url.endsWith("/jwks") -> ChatGptHttpResponse(200, keys.toString())
                url.endsWith("/models") -> ChatGptHttpResponse(200, "{\"models\":[]}")
                else -> error("Unexpected request")
            } }
            val response = callbackResponse(start, "issued-client")
            assertEquals(200, response.first)
            assertTrue(response.second.contains("ChatGPT authorization received"))
            assertTrue(response.second.contains("Return to inku to finish connecting."))
            assertTrue(manager.state.value.pending)
            delay(100)
            assertTrue(http.calls.isEmpty())
            foreground.value = true
            withTimeout(2000) { while (manager.state.value.pending || manager.state.value.models == null) delay(5) }
            assertEquals("connected", manager.state.value.active?.status)
            assertEquals(1, http.calls.count { it == CHATGPT_TOKEN })
            assertEquals(1, http.calls.count { it.endsWith("/models") })
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun callbackWhileBackgroundExpiresWithoutSendingToken() = runBlocking {
        val store = Store(); val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val foreground = kotlinx.coroutines.flow.MutableStateFlow(false)
        val manager = ChatGptPlanManager(store, scope, http, foreground = foreground, authorizationTimeoutMs = 500) { now }
        try {
            val start = query(manager.authorize())
            assertEquals(200, completeCallback(start, "issued-client"))
            withTimeout(2000) { while (manager.state.value.pending) delay(5) }
            assertEquals("chatgpt_cancelled", manager.state.value.errorCode)
            assertTrue(http.calls.isEmpty())
            foreground.value = true
            delay(100)
            assertTrue(http.calls.isEmpty())
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun reauthorizationReturnsBeforeFetchingAndRestoresPublishedCatalog() = runBlocking {
        val store = Store().apply {
            value.put("active", "a")
            value.getJSONObject("profiles").put("a", profile("a").put("published_models", JSONArray().put("personal-model"))
                .put("catalog", JSONObject().put("expires_at", now + 100_000).put("models", JSONArray().put(JSONObject().put("id", "old").put("label", "Old")))))
        }
        val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val gate = java.util.concurrent.CountDownLatch(1)
        val entered = java.util.concurrent.CountDownLatch(1)
        val manager = ChatGptPlanManager(store, scope, http) { now }
        try {
            assertTrue(http.calls.isEmpty())
            val start = query(manager.authorize())
            http.handler = { url, _, _ -> when {
                url == CHATGPT_TOKEN -> ChatGptHttpResponse(200, tokens(start.getValue("nonce"))
                    .put("id_token", signedIdentity(start.getValue("nonce"), "issued-a", "person-a")).toString())
                url.endsWith("openid-configuration") -> ChatGptHttpResponse(200, metadata.toString())
                url.endsWith("/jwks") -> ChatGptHttpResponse(200, keys.toString())
                url.endsWith("/models") -> {
                    entered.countDown()
                    check(gate.await(5, java.util.concurrent.TimeUnit.SECONDS))
                    ChatGptHttpResponse(200, "{\"models\":[{\"slug\":\"personal-model\",\"display_name\":\"Personal\",\"visibility\":\"list\"}]}")
                }
                else -> error("Unexpected request")
            } }
            assertEquals(200, completeCallback(start, "issued-a"))
            assertTrue(entered.await(2, java.util.concurrent.TimeUnit.SECONDS))
            withTimeout(2000) { while (manager.state.value.pending) delay(5) }
            assertEquals("connected", manager.state.value.active?.status)
            assertNull(manager.state.value.models)
            gate.countDown()
            withTimeout(2000) { while (manager.state.value.models == null) delay(5) }
            assertEquals(listOf("personal-model"), manager.state.value.models!!.map { it.id })
            assertEquals(listOf("personal-model"), manager.state.value.publishedModels)
            assertNotNull(store.read().getJSONObject("profiles").getJSONObject("a").optJSONObject("catalog"))
            assertEquals(1, http.calls.count { it == CHATGPT_TOKEN })
            assertEquals(1, http.calls.count { it.endsWith("/models") })
        } finally { gate.countDown(); manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun automaticCatalogFailureUsesTheManualRefreshFailureHandling() = runBlocking {
        val store = Store().apply { value.put("active", "a"); value.getJSONObject("profiles").put("a", profile("a")) }
        val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val logs = java.util.Collections.synchronizedList(mutableListOf<String>())
        val manager = ChatGptPlanManager(store, scope, http, diagnostic = { logs.add(it) }) { now }
        try {
            val start = query(manager.authorize())
            http.handler = { url, _, _ -> when {
                url == CHATGPT_TOKEN -> ChatGptHttpResponse(200, tokens(start.getValue("nonce"))
                    .put("id_token", signedIdentity(start.getValue("nonce"), "issued-a", "person-a")).toString())
                url.endsWith("openid-configuration") -> ChatGptHttpResponse(200, metadata.toString())
                url.endsWith("/jwks") -> ChatGptHttpResponse(200, keys.toString())
                url.endsWith("/models") -> ChatGptHttpResponse(503, "{}")
                else -> error("Unexpected request")
            } }
            assertEquals(200, completeCallback(start, "issued-a"))
            withTimeout(2000) { while (manager.state.value.errorCode == null) delay(5) }
            val automaticError = manager.state.value.errorCode
            assertEquals("chatgpt_transport_unavailable", automaticError)
            assertEquals("connected", manager.state.value.active?.status)
            assertFalse(manager.state.value.pending)
            assertEquals(1, logs.size)
            assertTrue(logs.single().contains("stage=catalog"))
            assertTrue(logs.single().contains("code=chatgpt_transport_unavailable"))
            assertEquals(1, http.calls.count { it.endsWith("/models") })
            try { manager.refreshModels(); fail("Manual refresh should fail") }
            catch (error: ChatGptException) { assertEquals(automaticError, error.code) }
            assertEquals(automaticError, manager.state.value.errorCode)
            assertEquals("connected", manager.state.value.active?.status)
            assertEquals(2, http.calls.count { it.endsWith("/models") })
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun loopbackRejectsWrongStateAndAdoptsOnlyTheVerifiedIssuedRegistration() = runBlocking {
        val store = Store(); val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val manager = ChatGptPlanManager(store, scope, http) { now }
        try {
            val start = query(manager.authorize())
            assertEquals("dynamic_agent_client", start["client_id"])
            assertEquals("inku", start["agent_name_hint"])
            assertEquals(CHATGPT_SCOPE, start["scope"])
            assertTrue(start.getValue("ext_agent_host_id").startsWith("urn:uuid:"))
            val verifierLength = java.util.concurrent.atomic.AtomicInteger()
            http.handler = { url, _, body -> when {
                url == CHATGPT_TOKEN -> {
                    val fields = query("https://test.invalid/?$body")
                    verifierLength.set(fields.getValue("code_verifier").length)
                    assertEquals("issued-client", fields["client_id"])
                    assertEquals(start["redirect_uri"], fields["redirect_uri"])
                    assertEquals(start["code_challenge"], base64Url(MessageDigest.getInstance("SHA-256").digest(fields.getValue("code_verifier").toByteArray())))
                    ChatGptHttpResponse(200, tokens(start.getValue("nonce")).toString())
                }
                url.endsWith("openid-configuration") -> ChatGptHttpResponse(200, metadata.toString())
                url.endsWith("/jwks") -> ChatGptHttpResponse(200, keys.toString())
                url.endsWith("/models") -> ChatGptHttpResponse(200, "{\"models\":[]}")
                else -> error("Unexpected auth endpoint")
            } }
            fun callback(state: String): Int {
                val connection = URI(start.getValue("redirect_uri") + "?" + form(mapOf("state" to state, "code" to "test-code", "client_id" to "issued-client")))
                    .toURL().openConnection() as HttpURLConnection
                connection.connectTimeout = 2000; connection.readTimeout = 3000
                return try { connection.responseCode } finally { connection.disconnect() }
            }
            fun rawCallback(target: String): String {
                val port = URI(start.getValue("redirect_uri")).port
                return java.net.Socket("127.0.0.1", port).use { socket ->
                    socket.soTimeout = 3000
                    socket.getOutputStream().write("GET $target HTTP/1.1\r\nHost: 127.0.0.1:$port\r\n\r\n".toByteArray())
                    socket.getInputStream().bufferedReader().readText()
                }
            }
            for (target in listOf("/other?state=${start.getValue("state")}", "/auth/callback?state=a&state=b")) {
                val response = rawCallback(target)
                assertTrue(response.startsWith("HTTP/1.1 400"))
                assertTrue(response.contains("ChatGPTの認証は完了していません"))
                assertTrue(manager.state.value.pending)
            }
            assertEquals(400, callback("wrong-state"))
            assertTrue(http.calls.isEmpty()); assertTrue(manager.state.value.pending)
            assertEquals(200, callback(start.getValue("state")))
            withTimeout(2000) { while (manager.state.value.pending) delay(5) }
            withTimeout(2000) { while (manager.state.value.models == null) delay(5) }
            assertTrue(manager.state.value.canUsePlan)
            assertEquals(emptyList<String>(), manager.state.value.publishedModels)
            // One registration: the next sign-in uses it (its client ID and id token as the hint), never a new one.
            val returning = query(manager.authorize(consent = true))
            assertEquals("issued-client", returning["client_id"])
            assertFalse(returning.containsKey("agent_name_hint"))
            assertTrue(returning.containsKey("id_token_hint"))
            assertEquals(start["ext_agent_host_id"], returning["ext_agent_host_id"])
            assertEquals("consent", returning["prompt"])
            assertNotEquals(start["state"], returning["state"])
            // Step 5: the verifier is 64 bytes, as Server's (the core's `random_bytes`).
            assertEquals(86, verifierLength.get())
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    /** One registration per device: `tidy` keeps the chosen one, and signing out keeps its client ID. */
    @Test fun publicationInputTidyAndSignOutKeepTheRegistration() = runBlocking {
        val store = Store().apply {
            value.put("active", "a")
            value.getJSONObject("profiles").put("a", profile("a").put("published_models", JSONArray().put("model")))
                .put("b", profile("b").put("published_models", JSONArray().put("other")))
        }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val manager = ChatGptPlanManager(store, scope, Http()) { now }
        try {
            val ref = ChatGptSessionRef("a", 1)
            rejected("chatgpt_model_not_offered") { manager.publishModels(ref, List(1025) { "m$it" }) }
            rejected("chatgpt_model_not_offered") { manager.publishModels(ref, listOf("x".repeat(257))) }
            rejected("chatgpt_model_not_offered") { manager.publishModels(ref, listOf("m"), JSONObject().put("m", JSONArray().put("other"))) }
            manager.tidy()
            assertFalse(store.read().getJSONObject("profiles").has("b"))
            assertEquals("a", store.read().getString("active"))
            manager.signOut("a")
            val kept = store.read().getJSONObject("profiles").getJSONObject("a")
            assertEquals("issued-a", kept.getString("client_id"))
            assertFalse(kept.has("refresh_token"))
            assertEquals(listOf("model"), kept.stringList("published_models"))
            assertEquals("a", manager.state.value.activeProfileId)
            assertTrue(manager.state.value.revocationUnconfirmed)
            // The one action after signing out is to sign in again (with the same registration).
            assertEquals("sign_in", manager.state.value.connection?.getJSONObject("primary")?.getString("action"))
        } finally { scope.cancel() }
    }

    /**
     * Step 5: the host checks only the signature (`verify`); the nonce, the
     * audience and the claims are the core's (`sign-in-flow-cases.json`).
     */
    @Test
    fun aSignatureIsCheckedWithTheAdvertisedKey() {
        val token = signedIdentity("expected")
        val key = keys.getJSONArray("keys").getJSONObject(0)
        val parts = token.split('.')
        assertTrue(verifyChatGptSignature("RS256", key, "${parts[0]}.${parts[1]}", parts[2]))
        val forged = base64Url(JSONObject(String(java.util.Base64.getUrlDecoder().decode(parts[1]))).put("sub", "forged-person").toString().toByteArray())
        assertFalse(verifyChatGptSignature("RS256", key, "${parts[0]}.$forged", parts[2]))
        assertFalse(verifyChatGptSignature("RS256", JSONObject(key.toString()).put("kty", "EC"), "${parts[0]}.${parts[1]}", parts[2]))
        assertFalse(verifyChatGptSignature("HS256", key, "${parts[0]}.${parts[1]}", parts[2]))
    }

    @Test
    fun splitUtf8AndAuxiliaryMessagesNeedACompletedFunctionAndNeverBecomeDrawingData() {
        val auxiliary = JSONObject().put("type", "message").put("role", "assistant").put("id", "message")
            .put("content", JSONArray().put(JSONObject().put("type", "output_text").put("text", "Do not draw this text")))
        val decoder = stream()
        (event("response.output_item.done", "item", auxiliary) + completedStream()).toByteArray().forEach { decoder.feed(byteArrayOf(it)) }
        assertEquals("赤い円。", JSONObject(decoder.finish()).getString("ddl"))
        assertEquals(12, decoder.usage?.getInt("output_tokens"))
        val added = event("response.output_item.added", "item", function().put("arguments", "")).toByteArray()
        val partial = stream()
        partial.feed(added)
        rejected("chatgpt_response_incomplete") { partial.finish() }
        val summary = stream()
        summary.feed(added)
        summary.feed(event("response.completed", "response", JSONObject().put("status", "completed").put("output", JSONArray())).toByteArray())
        rejected("chatgpt_unexpected_tool") { summary.finish() }
        rejected("chatgpt_unexpected_tool") { stream().apply { feed(event("response.output_item.done", "item", function().put("namespace", "other")).toByteArray()) }.finish() }
    }

    @Test
    fun personalPublicationAndPinnedGenerationPreventAccountSwitchAndApiFallback() = runBlocking {
        val store = Store().apply { value.getJSONObject("profiles").put("a", profile("a")).put("b", profile("b")); value.put("active", "a") }
        val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val manager = ChatGptPlanManager(store, scope, http) { now }
        try {
            http.handler = { url, token, body ->
                assertEquals("access-a", token)
                when {
                    url.endsWith("/models") -> ChatGptHttpResponse(200, "{\"models\":[{\"slug\":\"hidden\",\"display_name\":\"Hidden\",\"visibility\":\"hide\"},{\"slug\":\"personal-model\",\"display_name\":\"Personal model\",\"visibility\":\"list\"}]}")
                    url.endsWith("/responses") -> {
                        val json = JSONObject(body!!)
                        assertFalse(json.getBoolean("store")); assertTrue(json.getBoolean("stream"))
                        assertEquals("required", json.getString("tool_choice")); assertFalse(json.has("temperature")); assertFalse(json.has("max_output_tokens"))
                        assertEquals("inku", json.getJSONArray("tools").getJSONObject(0).getString("name"))
                        ChatGptHttpResponse(200, completedStream())
                    }
                    else -> error("Unexpected provider endpoint")
                }
            }
            val ref = manager.pinSession()
            assertEquals(listOf("personal-model"), manager.refreshModels())
            assertTrue(manager.state.value.publishedModels.isEmpty())
            manager.publishModels(ref, listOf("personal-model"))
            val response = manager.generate(request(ref))
            assertEquals("赤い円。", JSONObject(response.text).getString("ddl")); assertEquals(12, response.completionTokens)
            // Step 4: the core says where and how; the same URLs, headers and bounds as this client's constants before.
            // Step 5: the core's `catalog` puts the token in its headers; the bytes sent are the same.
            val models = http.sends.first { it.url.endsWith("/models") }
            assertEquals(ChatGptSend("$CHATGPT_RESOURCE/models", "GET", mapOf("Accept" to "application/json", "Authorization" to "Bearer access-a"),
                "Authorization", "", 1024 * 1024, 64 * 1024, "x-request-id"), models)
            // Step 6: a stream's answer gives no `answer_limit`; the host's 1 MiB default is gone and the
            // stream's own bound (the core's `wire_limit`) stands in. A 2xx stream never read that bound.
            val responses = http.sends.first { it.url.endsWith("/responses") }
            val wire = SharedProviderWire.call(JSONObject().put("action", "sign_in_limits").put("service", CHATGPT_PROVIDER)
                .put("answer_limit", MAX_PROVIDER_RESPONSE_BYTES)).getLong("wire_limit").toInt()
            assertEquals(ChatGptSend("$CHATGPT_RESOURCE/responses", "POST",
                mapOf("Accept" to "text/event-stream", "Content-Type" to "application/json"), "Authorization", "Bearer ",
                wire, 64 * 1024, "x-request-id"), responses)
            val calls = http.calls.size
            try { manager.generate(request(ref).copy(imageJpeg = byteArrayOf(1))); fail("Vision must not use this route") }
            catch (error: ChatGptException) { assertEquals("chatgpt_operation_not_supported", error.code) }
            assertEquals("赤い円。", JSONObject(manager.generate(request(ref)).text).getString("ddl"))
            assertEquals(calls + 1, http.calls.size)
            http.handler = { _, _, _ -> ChatGptHttpResponse(503, "{}") }
            manager.signOut("a")
            assertFalse(manager.state.value.canUsePlan); assertTrue(manager.state.value.revocationUnconfirmed)
            val saved = store.read().getJSONObject("profiles").getJSONObject("a")
            assertFalse(saved.has("access_token")); assertFalse(saved.has("refresh_token")); assertEquals(listOf("personal-model"), saved.stringList("published_models"))
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun aCameraImageIsNeverSentOnTheChatGptPlan() = runBlocking {
        withPlan({ "" }) { _, ref, _ ->
            rejected("chatgpt_operation_not_supported") {
                chatGptRequest(request(ref).copy(imageJpeg = byteArrayOf(1, 2, 3)))
            }
            rejected("chatgpt_operation_not_supported") {
                chatGptRequest(request(ref).copy(pipelineAction = null, imageJpeg = byteArrayOf(1, 2, 3)))
            }
        }
    }

    @Test
    fun visionStreamRejectsPartialTextAndFunctionCalls() {
        val partial = stream("text")
        partial.feed(("data: " + JSONObject().put("type", "response.output_text.delta")
            .put("delta", "partial") + "\r\n\r\n").toByteArray())
        rejected("chatgpt_response_incomplete") { partial.finish() }
        val tool = stream("text")
        tool.feed(event("response.output_item.done", "item", function()).toByteArray())
        rejected("chatgpt_unexpected_tool") { tool.finish() }
    }

    @Test
    fun providerAdmissionFailureLeavesTheRegistrationConnected() = runBlocking {
        val store = Store().apply { value.put("active", "a"); value.getJSONObject("profiles").put("a", profile("a")) }
        val http = Http().apply { handler = { _, _, _ -> ChatGptHttpResponse(401, "{\"error\":{\"message\":\"not copied to UI\"}}") } }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val manager = ChatGptPlanManager(store, scope, http) { now }
        try {
            val ref = manager.pinSession()
            try { manager.refreshModels(); fail("The provider rejected the request") }
            catch (error: ChatGptException) { assertEquals("chatgpt_admission_rejected", error.code) }
            assertEquals("connected", manager.state.value.active?.status)
            assertEquals("chatgpt_admission_rejected", manager.state.value.errorCode)
            assertTrue(store.read().getJSONObject("profiles").getJSONObject("a").has("refresh_token"))
            assertEquals(1, http.calls.size)
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun refreshedCredentialsWithoutPlanScopeCannotFetchModelsOrInfer() = runBlocking {
        val store = Store().apply { value.put("active", "a"); value.getJSONObject("profiles").put("a", profile("a").put("expires_at", now - 1)) }
        val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val manager = ChatGptPlanManager(store, scope, http) { now }
        try {
            http.handler = { url, _, body ->
                assertEquals(CHATGPT_TOKEN, url)
                val fields = query("https://test.invalid/?$body")
                assertEquals("issued-a", fields["client_id"]); assertEquals("refresh-a", fields["refresh_token"])
                assertEquals(CHATGPT_RESOURCE, fields["resource"]); assertFalse(fields.containsKey("scope"))
                ChatGptHttpResponse(200, JSONObject().put("token_type", "Bearer").put("access_token", "rotated-access")
                    .put("refresh_token", "rotated-refresh").put("expires_in", 3600).put("scope", "openid email").toString())
            }
            try { manager.refreshModels(); fail("Identity does not grant plan access") }
            catch (error: ChatGptException) { assertEquals("chatgpt_scope_required", error.code) }
            assertEquals(listOf(CHATGPT_TOKEN), http.calls)
            assertFalse(manager.state.value.canUsePlan)
            assertEquals("rotated-refresh", store.read().getJSONObject("profiles").getJSONObject("a").getString("refresh_token"))
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    /** Server `SSEDecoder`: `\r?\n\r?\n` ends an event, so LF followed by CRLF does too. */
    @Test
    fun aLineFeedThenCrlfBlankLineEndsAnEvent() {
        val decoder = stream()
        decoder.feed(completedStream().replace("\r\n\r\n", "\n\r\n").toByteArray())
        assertEquals("赤い円。", JSONObject(decoder.finish()).getString("ddl"))
    }

    /** Server pipeline: `SSEDecoder(max_response_bytes)`, the shared 1 MiB response bound. */
    @Test
    fun aSixHundredKibArgumentIsAcceptedAsTheServerAcceptsIt() = runBlocking {
        val ddl = "a".repeat(600 * 1024)
        val arguments = JSONObject().put("ddl", ddl).toString()
        withPlan({ completedStream(arguments) }) { manager, ref, http ->
            http.chunkSize = 64 * 1024
            assertEquals(ddl, JSONObject(manager.generate(request(ref)).text).getString("ddl"))
        }
    }

    /** Server `chatgpt_provider.py` / `chatgpt_store.py` failure classes, as the core receives them. */
    @Test
    fun streamFailuresAreClassedAsTheServerClassesThem() {
        fun decoded(vararg events: String) = runCatching {
            stream().apply { events.forEach { feed(it.toByteArray()) } }.finish()
        }.exceptionOrNull()!!
        val added = event("response.output_item.added", "item", function().put("arguments", ""))
        // An unfinished item or response is a refusal; a stream that stops is temporary.
        assertEquals("provider_rejected", failureOf(decoded(added, event("response.output_item.done", "item", function().put("status", "incomplete")))))
        assertEquals("provider_rejected", failureOf(decoded(added, event("response.output_item.done", "item", function()),
            event("response.completed", "response", JSONObject().put("status", "failed")))))
        assertEquals("transport_unavailable", failureOf(decoded(added, event("response.incomplete", "response", JSONObject()))))
        assertEquals("transport_unavailable", failureOf(decoded(added)))
    }

    @Test
    fun generationFailuresKeepTheirClassThroughThePlanManager() = runBlocking {
        suspend fun generated(stream: () -> String, bytes: ByteArray? = null): Throwable {
            var thrown: Throwable? = null
            withPlan(stream) { manager, ref, http ->
                http.streamBytes = bytes
                thrown = runCatching { manager.generate(request(ref)) }.exceptionOrNull()
            }
            return thrown!!
        }
        // Arguments that are not JSON are malformed; JSON that is not an object is refused.
        assertEquals("malformed_payload", failureOf(generated({ completedStream("{") })))
        assertEquals("provider_rejected", failureOf(generated({ completedStream("[1]") })))
        val timedOut = generated({ throw java.net.SocketTimeoutException("read timed out") }) as ChatGptException
        assertEquals("transport_timeout", failureOf(timedOut))
        // Step 4: the core's transport timeout, not an unavailable connection; it says to try again.
        assertEquals("chatgpt_transport_timeout", timedOut.code); assertEquals("retry", timedOut.action)
        val cut = generated({ throw java.io.IOException("connection reset") }) as ChatGptException
        assertEquals("chatgpt_transport_unavailable", cut.code); assertEquals("transport_unavailable", cut.failure)
        val badUtf8 = completedStream().toByteArray().let { it.copyOf(40) + byteArrayOf(0xC3.toByte(), 0x28) + it.copyOfRange(40, it.size) }
        val unreadable = generated({ completedStream() }, badUtf8) as ChatGptException
        assertEquals("provider_rejected", failureOf(unreadable))
        assertEquals("chatgpt_response_invalid", unreadable.code); assertEquals("diagnose", unreadable.action)
    }

    /** Step 4: an error body goes to the core as it came, with the request's ID; one that is not JSON is as none. */
    @Test
    fun anHttpErrorBodyAndItsRequestIdGoToTheCore() {
        val gateway = chatGptHttpError(ChatGptHttpResponse(502, "<html>Bad gateway</html>", "req_1"))
        assertEquals("chatgpt_transport_unavailable", gateway.code); assertEquals("retry", gateway.action)
        val limit = chatGptHttpError(ChatGptHttpResponse(429,
            "{\"error\": {\"code\": \"subscription_sharing_usage_limit_exceeded\", \"param\": \"model\"}}", "req_123"))
        assertEquals("subscription_sharing_usage_limit_exceeded", limit.code); assertEquals("usage", limit.action)
        assertEquals("chatgpt_transport_timeout", chatGptTransport("timeout").code)
        assertEquals("retry", ChatGptException("chatgpt_transport_unavailable").action)
    }

    @Test
    fun topLevelStreamErrorsPauseQuotaAndKeepTemporaryFailuresRetryable() = runBlocking {
        val limit = "subscription_sharing_usage_limit_exceeded"
        for (code in listOf(limit, "subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable")) {
            val errorEvent = JSONObject().put("type", "error").put("code", code).put("message", "Plan usage unavailable")
                .put("param", JSONObject.NULL).put("sequence_number", 3)
            withPlan({ "data: $errorEvent\n\n" }) { manager, ref, http ->
                val error = runCatching { manager.generate(request(ref)) }.exceptionOrNull() as ChatGptException
                assertEquals(code, error.code)
                assertEquals(if (code == limit) "provider_rejected" else "transport_unavailable", failureOf(error))
                assertEquals(code, manager.state.value.errorCode)
                if (code == limit) {
                    assertEquals("quota", manager.state.value.active?.status)
                    assertFalse(manager.state.value.canUsePlan)
                    val calls = http.calls.size
                    assertTrue(runCatching { manager.generate(request(ref)) }.isFailure)
                    assertEquals(calls, http.calls.size)
                } else {
                    assertEquals("connected", manager.state.value.active?.status)
                    assertTrue(manager.state.value.canUsePlan)
                    http.handler = { url, token, _ ->
                        check(url.endsWith("/responses"))
                        assertEquals("access-a", token)
                        ChatGptHttpResponse(200, completedStream())
                    }
                    assertEquals("赤い円。", JSONObject(manager.generate(request(ref)).text).getString("ddl"))
                }
            }
        }
    }

    /**
     * Step 6 (the author's answer): the host keeps its own list of the hosts a
     * token may go to, beside the core's answer; it names the hosts of the
     * core's issuer and resource, no more and no fewer.
     */
    @Test
    fun theAllowedHostsAreTheCoresIssuerAndResource() {
        val constants = ChatGptCore.call("sign_in_auth_constants")
        val described = listOf("issuer", "resource").map { URI(constants.getString(it)) }
        described.forEach { assertEquals("https", it.scheme) }
        assertEquals(described.map { it.host }.toSet(), UrlConnectionChatGptHttp.ALLOWED_HOSTS)
    }

    @Test
    fun planWritesSchemaPropertiesInDeclaredOrderAndKeepsOtherRequestsByteForByte() = runBlocking {
        withPlan({ completedStream() }) { manager, ref, http ->
            var wire = ""
            http.handler = { url, _, body ->
                check(url.endsWith("/responses"))
                wire = body!!
                ChatGptHttpResponse(200, completedStream())
            }
            val cases = listOf("read_composition" to SchemaOrderFixtures.reading) + SchemaOrderFixtures.plain
            for ((action, schema) in cases) {
                val request = SchemaOrderFixtures.request("chatgpt:personal-model", action, schema).copy(chatGptSession = ref)
                val before = chatGptRequest(request).body
                manager.generate(request)
                if (action == "read_composition") {
                    val sentSchema = JSONObject(wire).getJSONArray("tools").getJSONObject(0)
                        .getJSONArray("tools").getJSONObject(0).getJSONObject("parameters")
                    SchemaOrderFixtures.assertOrdered(wire, sentSchema)
                } else {
                    SchemaOrderFixtures.assertBytes(before, wire)
                    assertTrue("$action keeps its schema byte for byte", wire.contains("\"parameters\":$schema,"))
                }
            }
        }
    }

    private fun failureOf(error: Throwable): String = runBlocking {
        val provider = object : ModelProvider {
            override val providerId = "chatgpt"
            override suspend fun generate(request: ModelRequest): ModelResponse = throw error
        }
        val action = JSONObject().put("tag", "generate_normalized_ddl")
            .put("identity", JSONObject().put("action_id", "a").put("attempt", 1).put("request_digest", "b"))
            .put("timeout_ms", "5000")
            .put("payload", JSONObject().put("prompt", JSONObject().put("action_name", "generate_normalized_ddl")
                .put("system", "system").put("message", "message").put("response_schema", JSONObject().put("type", "object"))))
        JSONObject(app.inku.mobile.pipeline.SingleAttemptModelEffectProvider(provider)
            .perform(action.toString(), app.inku.mobile.pipeline.PipelineModelSelection("chatgpt:m", "chatgpt:m"))).getString("failure")
    }

    /** A published personal model on profile "a", answering /responses with [stream]. */
    private suspend fun withPlan(stream: () -> String, block: suspend (ChatGptPlanManager, ChatGptSessionRef, Http) -> Unit) {
        val store = Store().apply { value.getJSONObject("profiles").put("a", profile("a")); value.put("active", "a") }
        val http = Http(); val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val manager = ChatGptPlanManager(store, scope, http) { now }
        try {
            http.handler = { url, _, _ ->
                when {
                    url.endsWith("/models") -> ChatGptHttpResponse(200, "{\"models\":[{\"slug\":\"personal-model\",\"display_name\":\"Personal model\",\"visibility\":\"list\"}]}")
                    url.endsWith("/responses") -> ChatGptHttpResponse(200, stream())
                    else -> error("Unexpected provider endpoint")
                }
            }
            val ref = manager.pinSession()
            manager.refreshModels()
            manager.publishModels(ref, listOf("personal-model"))
            block(manager, ref, http)
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }
}
