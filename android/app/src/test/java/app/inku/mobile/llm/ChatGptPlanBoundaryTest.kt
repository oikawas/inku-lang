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

class ChatGptPlanBoundaryTest {
    private class Store : ChatGptCredentialStore {
        var value = JSONObject().put("profiles", JSONObject())
        override fun read() = JSONObject(value.toString())
        override fun write(value: JSONObject) { this.value = JSONObject(value.toString()) }
    }

    private class Http : ChatGptHttp {
        val calls = mutableListOf<String>()
        var chunkSize = 7
        /** Streamed instead of a 200 body's UTF-8, for bytes no String holds. */
        var streamBytes: ByteArray? = null
        var handler: (String, String?, String?) -> ChatGptHttpResponse = { _, _, _ -> error("Unexpected request") }
        override suspend fun request(url: String, method: String, token: String?, body: String?, formBody: Boolean,
                                     timeoutMs: Long, check: () -> Unit, onChunk: ((ByteArray) -> Unit)?): ChatGptHttpResponse {
            check(); calls.add(url)
            val result = handler(url, token, body)
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

    private fun query(url: String) = callbackParameters("/auth/callback?" + URI(url).rawQuery)
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
    private fun completedVisionStream(text: String): String {
        val item = JSONObject().put("type", "message").put("role", "assistant").put("id", "vision-item")
            .put("status", "completed")
            .put("content", JSONArray().put(JSONObject().put("type", "output_text").put("text", text)))
        return event("response.output_item.done", "item", item) + event("response.completed", "response",
            JSONObject().put("status", "completed").put("output", JSONObject.NULL)
                .put("usage", JSONObject().put("input_tokens", 15).put("output_tokens", 28)))
    }

    private fun rejected(code: String, block: () -> Unit) {
        try { block(); fail("Expected $code") } catch (error: ChatGptException) { assertEquals(code, error.code) }
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
            http.handler = { url, _, body -> when {
                url == CHATGPT_TOKEN -> {
                    val fields = query("https://test.invalid/?$body")
                    assertEquals("issued-client", fields["client_id"])
                    assertEquals(start["redirect_uri"], fields["redirect_uri"])
                    assertEquals(start["code_challenge"], base64Url(MessageDigest.getInstance("SHA-256").digest(fields.getValue("code_verifier").toByteArray())))
                    ChatGptHttpResponse(200, tokens(start.getValue("nonce")).toString())
                }
                url.endsWith("openid-configuration") -> ChatGptHttpResponse(200, metadata.toString())
                url.endsWith("/jwks") -> ChatGptHttpResponse(200, keys.toString())
                else -> error("Unexpected auth endpoint")
            } }
            fun callback(state: String): Int {
                val connection = URI(start.getValue("redirect_uri") + "?" + form(mapOf("state" to state, "code" to "test-code", "client_id" to "issued-client")))
                    .toURL().openConnection() as HttpURLConnection
                connection.connectTimeout = 2000; connection.readTimeout = 3000
                return try { connection.responseCode } finally { connection.disconnect() }
            }
            assertEquals(400, callback("wrong-state"))
            assertTrue(http.calls.isEmpty()); assertTrue(manager.state.value.pending)
            assertEquals(200, callback(start.getValue("state")))
            withTimeout(2000) { while (manager.state.value.pending) delay(5) }
            assertTrue(manager.state.value.canUsePlan)
            assertTrue(manager.state.value.showPlanNotice)
            assertEquals(emptyList<String>(), manager.state.value.publishedModels)
            val ref = manager.pinSession()
            val returning = query(manager.authorize(ref.profileId, consent = true))
            assertEquals("issued-client", returning["client_id"])
            assertFalse(returning.containsKey("agent_name_hint"))
            assertEquals(start["ext_agent_host_id"], returning["ext_agent_host_id"])
            assertEquals("consent", returning["prompt"])
            assertNotEquals(start["state"], returning["state"])
            rejected("chatgpt_registration_incomplete") { issuedClientId(mapOf("client_id" to "another-client", "code" to "x"), store.read().getJSONObject("profiles").getJSONObject(ref.profileId)) }
            rejected("chatgpt_callback_invalid") { callbackParameters("/auth/callback?state=a&state=b") }
            rejected("chatgpt_callback_invalid") { callbackParameters("//other.invalid/auth/callback?state=a") }
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun aSignedIdentityStillNeedsTheCurrentNonceAndAudience() {
        val token = signedIdentity("expected")
        assertEquals("person-a", validateChatGptIdentity(token, "issued-client", "expected", metadata, keys, now / 1000).getString("sub"))
        rejected("chatgpt_identity_invalid") { validateChatGptIdentity(token, "issued-client", "old-attempt", metadata, keys, now / 1000) }
        rejected("chatgpt_identity_invalid") { validateChatGptIdentity(token, "other-client", "expected", metadata, keys, now / 1000) }
        val parts = token.split('.').toMutableList()
        parts[1] = base64Url(JSONObject(String(java.util.Base64.getUrlDecoder().decode(parts[1]))).put("sub", "forged-person").toString().toByteArray())
        rejected("chatgpt_identity_invalid") { validateChatGptIdentity(parts.joinToString("."), "issued-client", "expected", metadata, keys, now / 1000) }
    }

    @Test
    fun splitUtf8AndAuxiliaryMessagesNeedACompletedFunctionAndNeverBecomeDrawingData() {
        val auxiliary = JSONObject().put("type", "message").put("role", "assistant").put("id", "message")
            .put("content", JSONArray().put(JSONObject().put("type", "output_text").put("text", "Do not draw this text")))
        val decoder = ChatGptSseDecoder()
        (event("response.output_item.done", "item", auxiliary) + completedStream()).toByteArray().forEach { decoder.feed(byteArrayOf(it)) }
        assertEquals("赤い円。", JSONObject(decoder.finish()).getString("ddl"))
        assertEquals(12, decoder.usage?.getInt("output_tokens"))
        val partial = ChatGptSseDecoder()
        partial.feed(event("response.output_item.added", "item", function().put("arguments", "")).toByteArray())
        rejected("chatgpt_response_incomplete") { partial.finish() }
        rejected("chatgpt_unexpected_tool") { partial.feed(event("response.completed", "response", JSONObject().put("status", "completed").put("output", JSONArray())).toByteArray()) }
        rejected("chatgpt_unexpected_tool") { ChatGptSseDecoder().feed(event("response.output_item.done", "item", function().put("namespace", "other")).toByteArray()) }
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
            val calls = http.calls.size
            try { manager.generate(request(ref).copy(imageJpeg = byteArrayOf(1))); fail("Vision must not use this route") }
            catch (error: ChatGptException) { assertEquals("chatgpt_operation_not_supported", error.code) }
            manager.selectProfile("b"); manager.selectProfile("a")
            try { manager.generate(request(ref)); fail("An old run must not resume after switching back") }
            catch (error: ChatGptException) { assertEquals("chatgpt_session_changed", error.code) }
            assertEquals(calls, http.calls.size)
            http.handler = { _, _, _ -> ChatGptHttpResponse(503, "{}") }
            manager.signOut("a")
            assertFalse(manager.state.value.canUsePlan); assertTrue(manager.state.value.revocationUnconfirmed)
            val saved = store.read().getJSONObject("profiles").getJSONObject("a")
            assertFalse(saved.has("access_token")); assertFalse(saved.has("refresh_token")); assertEquals(listOf("personal-model"), saved.stringList("published_models"))
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    @Test
    fun onlyPinnedRefinementVisionAdviceSendsAnImageAndReadsCompletedAssistantText() = runBlocking {
        val text = """{"observation":"A circle sits low.","next_direction":"Move it up.","suggested_kind":"layout_change"}"""
        withPlan({ completedVisionStream(text) }) { manager, ref, http ->
            var wire = ""
            http.handler = { url, token, body ->
                assertEquals("access-a", token)
                when {
                    url.endsWith("/models") -> ChatGptHttpResponse(200,
                        """{"models":[{"slug":"personal-model","display_name":"Personal model","visibility":"list"}]}""")
                    url.endsWith("/responses") -> {
                        wire = body!!
                        ChatGptHttpResponse(200, completedVisionStream(text))
                    }
                    else -> error("Unexpected provider endpoint")
                }
            }
            val visionRequest = RefinementVisionRequest(
                modelId = "chatgpt:personal-model", instruction = "a circle", direction = "leave space",
                enabledKinds = listOf("layout_change"), languageCode = "en", imageJpeg = byteArrayOf(1, 2, 3),
            )
            val advice = RefinementVisionAdviser(manager, ref).advise(visionRequest)
            assertEquals("A circle sits low.", advice.observation)
            assertEquals("Move it up.", advice.nextDirection)
            val sent = JSONObject(wire)
            assertFalse(sent.getBoolean("store"))
            assertTrue(sent.getBoolean("stream"))
            assertFalse(sent.has("tools"))
            assertFalse(sent.has("tool_choice"))
            assertFalse(sent.has("max_output_tokens"))
            val content = sent.getJSONArray("input").getJSONObject(0).getJSONArray("content")
            assertEquals("input_text", content.getJSONObject(0).getString("type"))
            assertEquals("input_image", content.getJSONObject(1).getString("type"))
            assertEquals("data:image/jpeg;base64,AQID", content.getJSONObject(1).getString("image_url"))
            val calls = http.calls.size
            rejected("chatgpt_operation_not_supported") {
                chatGptRequestBody(request(ref).copy(imageJpeg = byteArrayOf(1, 2, 3)))
            }
            rejected("chatgpt_operation_not_supported") {
                chatGptRequestBody(request(ref).copy(pipelineAction = null, imageJpeg = byteArrayOf(1, 2, 3)))
            }
            rejected("chatgpt_operation_not_supported") {
                chatGptRequestBody(request(ref).copy(pipelineAction = REFINEMENT_VISION_ACTION, imageJpeg = byteArrayOf(1)))
            }
            try {
                RefinementVisionAdviser(manager, ref.copy(generation = ref.generation - 1)).advise(visionRequest)
                fail("An old profile generation must not advise")
            } catch (error: ChatGptException) {
                assertEquals("chatgpt_session_changed", error.code)
            }
            assertEquals(calls, http.calls.size)
        }
    }

    @Test
    fun visionStreamRejectsPartialTextAndFunctionCalls() {
        val partial = ChatGptVisionSseDecoder()
        partial.feed(("data: " + JSONObject().put("type", "response.output_text.delta")
            .put("delta", "partial") + "\r\n\r\n").toByteArray())
        rejected("chatgpt_response_incomplete") { partial.finish() }
        val tool = ChatGptVisionSseDecoder()
        rejected("chatgpt_unexpected_tool") {
            tool.feed(event("response.output_item.done", "item", function()).toByteArray())
        }
    }

    @Test
    fun rejectedAuthorizationDropsLocalCredentialsAndStopsThePinnedRun() = runBlocking {
        val store = Store().apply { value.put("active", "a"); value.getJSONObject("profiles").put("a", profile("a")) }
        val http = Http().apply { handler = { _, _, _ -> ChatGptHttpResponse(401, "{\"error\":{\"message\":\"not copied to UI\"}}") } }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val manager = ChatGptPlanManager(store, scope, http) { now }
        try {
            val ref = manager.pinSession()
            try { manager.refreshModels(); fail("Rejected credentials must not remain connected") }
            catch (error: ChatGptException) { assertEquals("chatgpt_admission_rejected", error.code) }
            assertEquals("reauthentication_required", manager.state.value.active?.status)
            assertEquals("chatgpt_admission_rejected", manager.state.value.errorCode)
            assertFalse(store.read().getJSONObject("profiles").getJSONObject("a").has("refresh_token"))
            try { manager.generate(request(ref)); fail("The previous run must stop") }
            catch (error: ChatGptException) { assertEquals("chatgpt_session_changed", error.code) }
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
            catch (error: ChatGptException) { assertEquals("chatgpt_plan_not_authorized", error.code) }
            assertEquals(listOf(CHATGPT_TOKEN), http.calls)
            assertFalse(manager.state.value.canUsePlan)
            assertEquals("rotated-refresh", store.read().getJSONObject("profiles").getJSONObject("a").getString("refresh_token"))
        } finally { manager.cancelAuthorization(); scope.cancel() }
    }

    /** Server `SSEDecoder`: `\r?\n\r?\n` ends an event, so LF followed by CRLF does too. */
    @Test
    fun aLineFeedThenCrlfBlankLineEndsAnEvent() {
        val decoder = ChatGptSseDecoder()
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
            ChatGptSseDecoder().apply { events.forEach { feed(it.toByteArray()) } }.finish()
        }.exceptionOrNull()!!
        val added = event("response.output_item.added", "item", function().put("arguments", ""))
        // An unfinished item or response is a refusal; a stream that stops is temporary.
        assertEquals("provider_rejected", failureOf(decoded(added, event("response.output_item.done", "item", function().put("status", "incomplete")))))
        assertEquals("provider_rejected", failureOf(decoded(added, event("response.output_item.done", "item", function()),
            event("response.completed", "response", JSONObject().put("status", "failed")))))
        assertEquals("transport_unavailable", failureOf(decoded(added, event("response.incomplete", "response", JSONObject()))))
        assertEquals("transport_unavailable", failureOf(decoded(added)))
        // A public code that arrives with a 5xx is temporary.
        val ineligible = JSONObject().put("error", JSONObject().put("code", "subscription_sharing_user_not_eligible"))
        assertEquals("transport_unavailable", failureOf(chatGptResponseError(ineligible, 503)))
        assertEquals("provider_rejected", failureOf(chatGptResponseError(ineligible, 403)))
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
        assertEquals("transport_timeout", failureOf(generated({ throw java.net.SocketTimeoutException("read timed out") })))
        val badUtf8 = completedStream().toByteArray().let { it.copyOf(40) + byteArrayOf(0xC3.toByte(), 0x28) + it.copyOfRange(40, it.size) }
        assertEquals("provider_rejected", failureOf(generated({ completedStream() }, badUtf8)))
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

    @Test
    fun responseErrorsKeepNestedPrecedenceAndRequireAnErrorEventForTopLevelCodes() {
        val limit = "subscription_sharing_usage_limit_exceeded"
        val temporary = "subscription_sharing_usage_unavailable"
        val nested = JSONObject().put("code", "subscription_sharing_user_not_eligible")
        val top = JSONObject().put("type", "error").put("code", limit)
            .put("error", nested).put("response", JSONObject().put("error", JSONObject().put("code", temporary)))
        assertEquals("subscription_sharing_user_not_eligible", chatGptResponseError(top).code)
        top.remove("error")
        assertEquals(temporary, chatGptResponseError(top).code)
        top.put("response", "not an object")
        assertEquals(limit, chatGptResponseError(top).code)
        top.remove("type")
        assertEquals("chatgpt_response_failed", chatGptResponseError(top).code)
        val http = chatGptResponseError(JSONObject().put("error", JSONObject().put("code", limit)), 429)
        assertEquals(limit, http.code)
        assertEquals("provider_rejected", http.failure)
        val failed = chatGptResponseError(JSONObject().put("type", "response.failed")
            .put("response", JSONObject().put("error", JSONObject().put("code", temporary))))
        assertEquals(temporary, failed.code)
        assertEquals("transport_unavailable", failed.failure)
        for (value in listOf(null, "not an object", JSONArray())) {
            assertEquals("chatgpt_response_failed", chatGptResponseError(value).code)
        }
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
                val before = chatGptRequestBody(request).toString()
                manager.generate(request)
                if (action == "read_composition") {
                    val sentSchema = JSONObject(wire).getJSONArray("tools").getJSONObject(0)
                        .getJSONArray("tools").getJSONObject(0).getJSONObject("parameters")
                    SchemaOrderFixtures.assertOrdered(wire, sentSchema)
                } else SchemaOrderFixtures.assertBytes(before, wire)
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
