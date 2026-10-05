package app.inku.mobile.llm

import java.math.BigInteger
import java.net.URI
import java.net.URLDecoder
import java.net.URLEncoder
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import java.security.spec.RSAPublicKeySpec
import java.util.Base64
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import org.json.JSONTokener

internal fun base64Url(bytes: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
internal fun randomOAuthValue(): String = base64Url(ByteArray(32).also(SecureRandom()::nextBytes))
internal fun form(values: Map<String, String>): String = values.entries.joinToString("&") {
    URLEncoder.encode(it.key, Charsets.UTF_8) + "=" + URLEncoder.encode(it.value, Charsets.UTF_8)
}

internal fun authorizationUrl(hostId: String, redirectUri: String, state: String, nonce: String,
                              verifier: String, previous: JSONObject?, consent: Boolean): String {
    val values = linkedMapOf(
        "client_id" to (previous?.getString("client_id") ?: "dynamic_agent_client"),
        "ext_agent_host_id" to hostId, "response_type" to "code", "redirect_uri" to redirectUri,
        "scope" to CHATGPT_SCOPE, "resource" to CHATGPT_RESOURCE, "state" to state, "nonce" to nonce,
        "code_challenge_method" to "S256",
        "code_challenge" to base64Url(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII))),
    )
    if (previous == null) values["agent_name_hint"] = "inku"
    previous?.optString("id_token")?.takeIf(String::isNotEmpty)?.let { values["id_token_hint"] = it }
    previous?.optString("email")?.takeIf(String::isNotEmpty)?.let { values["login_hint"] = it }
    if (consent) values["prompt"] = "consent"
    return "$CHATGPT_ISSUER/api/accounts/authorize?" + form(values)
}

internal fun callbackParameters(target: String): Map<String, String> {
    if (target.length > 16_384) throw ChatGptException("chatgpt_callback_invalid")
    val uri = URI(target)
    if (uri.isAbsolute || uri.rawAuthority != null || uri.rawPath != "/auth/callback" || uri.fragment != null) {
        throw ChatGptException("chatgpt_callback_invalid")
    }
    val result = linkedMapOf<String, String>()
    uri.rawQuery.orEmpty().split('&').filter(String::isNotEmpty).forEach { field ->
        val pair = field.split('=', limit = 2)
        val key = URLDecoder.decode(pair[0], Charsets.UTF_8)
        val value = URLDecoder.decode(pair.getOrElse(1) { "" }, Charsets.UTF_8)
        if (result.put(key, value) != null) throw ChatGptException("chatgpt_callback_invalid")
    }
    return result
}

internal fun callbackStateMatches(query: Map<String, String>, expected: String): Boolean =
    MessageDigest.isEqual(query["state"].orEmpty().toByteArray(Charsets.UTF_8), expected.toByteArray(Charsets.UTF_8))

internal fun issuedClientId(query: Map<String, String>, previous: JSONObject?): String {
    if (query.containsKey("error")) throw ChatGptException("chatgpt_consent_declined")
    val expected = previous?.getString("client_id")
    val issued = query["client_id"] ?: expected.orEmpty()
    if (!issued.matches(Regex("[A-Za-z0-9_.:-]{1,256}")) || issued == "dynamic_agent_client" ||
        (expected != null && expected != issued) || query["code"].isNullOrEmpty()) {
        throw ChatGptException("chatgpt_registration_incomplete")
    }
    return issued
}

/** JCA verifies only advertised RSA/P-256 signatures; no unsigned claims are adopted. */
internal fun validateChatGptIdentity(token: String, clientId: String, nonce: String?, metadata: JSONObject,
                                     jwks: JSONObject, nowSeconds: Long): JSONObject {
    try {
        require(token.length <= 65_536 && metadata.getString("issuer") == CHATGPT_ISSUER)
        val parts = token.split('.')
        require(parts.size == 3 && parts.all { it.matches(Regex("[A-Za-z0-9_-]+")) })
        val decoder = Base64.getUrlDecoder()
        val header = JSONObject(decoder.decode(parts[0]).toString(Charsets.UTF_8))
        val algorithm = header.getString("alg")
        val advertised = metadata.optJSONArray("id_token_signing_alg_values_supported") ?: JSONArray().put("RS256")
        require(algorithm in listOf("RS256", "ES256") && (0 until advertised.length()).any { advertised.getString(it) == algorithm })
        val kid = header.getString("kid")
        val keys = jwks.getJSONArray("keys")
        val matching = (0 until keys.length()).map { keys.getJSONObject(it) }.filter {
            it.optString("kid") == kid && it.optString("use", "sig") == "sig" &&
                (!it.has("alg") || it.getString("alg") == algorithm)
        }
        require(matching.size == 1)
        val key = matching.single()
        val signature = Signature.getInstance(if (algorithm == "RS256") "SHA256withRSA" else "SHA256withECDSA")
        val publicKey = if (algorithm == "RS256") {
            require(key.getString("kty") == "RSA")
            val n = BigInteger(1, decoder.decode(key.getString("n")))
            val e = BigInteger(1, decoder.decode(key.getString("e")))
            require(n.bitLength() in 2048..8192 && e >= BigInteger.valueOf(3) && e.bitLength() <= 32)
            KeyFactory.getInstance("RSA").generatePublic(RSAPublicKeySpec(n, e))
        } else {
            require(key.getString("kty") == "EC" && key.getString("crv") == "P-256")
            val parameters = AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }
                .getParameterSpec(ECParameterSpec::class.java)
            val x = decoder.decode(key.getString("x")); val y = decoder.decode(key.getString("y"))
            require(x.size == 32 && y.size == 32)
            KeyFactory.getInstance("EC").generatePublic(ECPublicKeySpec(ECPoint(BigInteger(1, x), BigInteger(1, y)), parameters))
        }
        signature.initVerify(publicKey)
        signature.update((parts[0] + "." + parts[1]).toByteArray(Charsets.US_ASCII))
        val rawSignature = decoder.decode(parts[2])
        require(signature.verify(if (algorithm == "ES256") ecdsaDer(rawSignature) else rawSignature))
        val claims = JSONObject(decoder.decode(parts[1]).toString(Charsets.UTF_8))
        require(claims.getString("iss") == CHATGPT_ISSUER)
        val aud = claims.get("aud")
        require(aud == clientId || (aud is JSONArray && (0 until aud.length()).any { aud.getString(it) == clientId }))
        if (aud is JSONArray && aud.length() > 1) require(claims.optString("azp") == clientId)
        require(claims.get("exp") is Number && claims.getDouble("exp").isFinite() && claims.getDouble("exp") > nowSeconds)
        require(!claims.has("nbf") || claims.getDouble("nbf") <= nowSeconds + 30)
        require(claims.getString("sub").isNotEmpty())
        if (nonce != null) require(MessageDigest.isEqual(claims.optString("nonce").toByteArray(Charsets.UTF_8), nonce.toByteArray(Charsets.UTF_8)))
        return claims
    } catch (_: Exception) {
        throw ChatGptException("chatgpt_identity_invalid")
    }
}

private fun ecdsaDer(raw: ByteArray): ByteArray {
    require(raw.size == 64)
    fun integer(bytes: ByteArray): ByteArray {
        val first = bytes.indexOfFirst { it != 0.toByte() }.let { if (it < 0) bytes.lastIndex else it }
        val value = bytes.copyOfRange(first, bytes.size)
        return if (value[0].toInt() and 128 != 0) byteArrayOf(0) + value else value
    }
    val r = integer(raw.copyOfRange(0, 32)); val s = integer(raw.copyOfRange(32, 64))
    return byteArrayOf(0x30, (r.size + s.size + 4).toByte(), 0x02, r.size.toByte()) + r + byteArrayOf(0x02, s.size.toByte()) + s
}

internal val CHATGPT_EFFECTS = setOf("generate_sketch", "select_description_catalog", "generate_normalized_ddl", "read_composition", "complete_visible_ddl_holes")
private val PUBLIC_CHATGPT_CODES = setOf(
    "subscription_sharing_usage_limit_exceeded", "subscription_sharing_user_not_eligible",
    "subscription_sharing_unsupported_capability", "subscription_sharing_route_not_supported",
    "subscription_sharing_invalid_user", "chatpass_v2_scope_not_authorized",
    "chatpass_v2_invalid_authorization_context", "subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable",
)

internal fun chatGptResponseError(value: JSONObject, status: Int? = null): ChatGptException {
    val error = value.optJSONObject("error") ?: value.optJSONObject("response")?.optJSONObject("error")
    val code = error?.optString("code")
    val public = if (code in PUBLIC_CHATGPT_CODES) code!! else when {
        status == 401 || status == 403 -> "chatgpt_admission_rejected"
        status != null && status >= 500 -> "chatgpt_transport_unavailable"
        else -> "chatgpt_response_failed"
    }
    // Server `ResponseFailure`: a 5xx is temporary whatever code it carries.
    val temporary = public in TEMPORARY_CHATGPT_CODES || (status != null && status >= 500)
    return ChatGptException(public, if (temporary) "transport_unavailable" else "provider_rejected")
}

private val TEMPORARY_CHATGPT_CODES = setOf("subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable")

internal fun chatGptRequestBody(request: ModelRequest): JSONObject {
    if (!request.modelId.startsWith("chatgpt:") || request.pipelineAction !in CHATGPT_EFFECTS || request.imageJpeg != null || request.tool == null) {
        throw ChatGptException("chatgpt_operation_not_supported")
    }
    return JSONObject().put("model", request.modelId.removePrefix("chatgpt:")).put("store", false).put("stream", true)
        .put("instructions", request.systemInstruction.orEmpty())
        .put("input", JSONArray().put(JSONObject().put("role", "user").put("content", request.prompt)))
        .put("tools", JSONArray().put(JSONObject().put("type", "namespace").put("name", "inku")
            .put("description", "Return data for the inku drawing pipeline.")
            .put("tools", JSONArray().put(JSONObject().put("type", "function").put("name", "submit_pipeline_response")
                .put("description", "Return the requested drawing data.").put("parameters", JSONObject(request.tool.parametersJson)).put("strict", false)))))
        .put("tool_choice", "required").put("parallel_tool_calls", false)
}

/** Byte-framed SSE; only a completed, sole namespace function can become drawing data. */
internal class ChatGptSseDecoder(private val argumentLimit: Int = 512 * 1024) {
    private var buffer = ByteArray(0)
    private var wireBytes = 0
    private val items = linkedMapOf<String, JSONObject>()
    private val finalized = linkedMapOf<String, JSONObject>()
    private val arguments = mutableMapOf<String, String>()
    private var completed: String? = null
    private var terminal: JSONObject? = null
    val usage: JSONObject? get() = terminal?.optJSONObject("usage")

    fun feed(chunk: ByteArray) {
        wireBytes += chunk.size
        if (wireBytes > maxOf(1024 * 1024, argumentLimit * 6 + 512 * 1024)) fail("chatgpt_response_too_large")
        buffer += chunk
        while (true) {
            var end = -1; var separator = 0
            for (i in buffer.indices) {
                val length = blankLineAt(i)
                if (length > 0) { end = i; separator = length; break }
            }
            if ((if (end < 0) buffer.size else end) > maxOf(64 * 1024, argumentLimit * 2 + 64 * 1024)) fail("chatgpt_response_too_large")
            if (end < 0) break
            val text = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(buffer.copyOfRange(0, end))).toString()
            buffer = buffer.copyOfRange(end + separator, buffer.size)
            val data = text.lines().filter { it.startsWith("data:") }.joinToString("\n") { it.substring(5).trimStart(' ') }
            if (data.isNotEmpty() && data != "[DONE]") event(JSONObject(data))
        }
    }

    /**
     * The length of the server's `\r?\n\r?\n` match starting at [start], or 0.
     * CRLF and LF are both line ends, so LF then CRLF ends an event too; a CR
     * at the end of the buffer waits for the byte after it.
     */
    private fun blankLineAt(start: Int): Int {
        fun lineEnd(at: Int): Int = when {
            at < buffer.size && buffer[at] == LF -> 1
            at + 1 < buffer.size && buffer[at] == CR && buffer[at + 1] == LF -> 2
            else -> 0
        }
        val first = lineEnd(start)
        if (first == 0) return 0
        val second = lineEnd(start + first)
        return if (second == 0) 0 else first + second
    }

    private fun function(item: JSONObject) {
        if (item.optString("type") != "function_call" || item.optString("name") != "submit_pipeline_response" || item.optString("namespace") != "inku") fail("chatgpt_unexpected_tool")
    }

    private fun auxiliary(item: JSONObject) {
        if (item.optString("type") == "reasoning") return
        if (item.optString("type") != "message" || item.optString("role") != "assistant") fail("chatgpt_unexpected_tool")
        val content = item.optJSONArray("content") ?: JSONArray()
        for (i in 0 until content.length()) {
            val type = content.getJSONObject(i).optString("type")
            if (type == "refusal") fail("chatgpt_refused")
            if (type != "output_text") fail("chatgpt_unexpected_tool")
        }
    }

    private fun checkArguments(text: String): String {
        if (text.toByteArray(Charsets.UTF_8).size > argumentLimit) fail("chatgpt_response_too_large")
        return text
    }

    private fun event(event: JSONObject) {
        val type = event.optString("type")
        if (type == "error" || type == "response.failed") throw chatGptResponseError(event)
        if (type == "response.incomplete") fail("chatgpt_response_incomplete")
        if (type.contains("refusal")) fail("chatgpt_refused")
        if (terminal != null) fail("chatgpt_response_invalid")
        when (type) {
            "response.output_item.added", "response.output_item.done" -> {
                val item = event.getJSONObject("item")
                if (item.optString("type") != "function_call") { auxiliary(item); return }
                function(item)
                val id = item.getString("id")
                if (id !in items && items.isNotEmpty()) fail("chatgpt_unexpected_tool")
                items[id] = item
                if (type.endsWith(".done")) {
                    if (item.has("status") && !item.isNull("status") && item.getString("status") != "completed") {
                        // Server: an item that did not complete is refused, not retried.
                        throw ChatGptException("chatgpt_response_incomplete", "provider_rejected")
                    }
                    val text = checkArguments(item.getString("arguments"))
                    if (arguments[id]?.let { it != text } == true) fail("chatgpt_response_invalid")
                    finalized[id] = item
                }
            }
            "response.function_call_arguments.delta", "response.function_call_arguments.done" -> {
                val id = event.getString("item_id")
                if (id !in items) fail("chatgpt_response_invalid")
                if (type.endsWith(".delta")) arguments[id] = checkArguments(arguments[id].orEmpty() + event.getString("delta"))
                else {
                    val text = checkArguments(event.getString("arguments"))
                    if (arguments[id]?.let { it != text } == true) fail("chatgpt_response_invalid")
                    arguments[id] = text
                }
            }
            "response.completed" -> {
                val response = event.getJSONObject("response")
                if (response.optString("status") != "completed") {
                    throw ChatGptException("chatgpt_response_incomplete", "provider_rejected")
                }
                val output = if (!response.has("output") || response.isNull("output") || response.optJSONArray("output")?.length() == 0) {
                    finalized.values.toList()
                } else {
                    val array = response.getJSONArray("output")
                    (0 until array.length()).map { array.getJSONObject(it) }
                }
                val calls = output.filter { it.optString("type") == "function_call" }
                output.filter { it.optString("type") != "function_call" }.forEach(::auxiliary)
                if (calls.size != 1) fail("chatgpt_unexpected_tool")
                val item = calls.single(); function(item)
                val id = item.getString("id"); val text = checkArguments(item.getString("arguments"))
                if (id !in items || arguments[id]?.let { it != text } == true || finalized[id]?.getString("arguments")?.let { it != text } == true) fail("chatgpt_response_invalid")
                requireObject(text)
                completed = text; terminal = response
            }
        }
    }

    /**
     * Server `json.loads(arguments)` then `isinstance(..., dict)`: text that is
     * not JSON stays a JSONException (`malformed_payload`); JSON that is not
     * an object is `chatgpt_response_invalid` (`provider_rejected`).
     */
    private fun requireObject(text: String) {
        try {
            JSONObject(text)
        } catch (notObject: JSONException) {
            val value = text.trim()
            val otherJson = runCatching { JSONArray(value) }.isSuccess ||
                value.matches(JSON_SCALAR) ||
                (value.startsWith('"') && runCatching { JSONTokener(value).nextValue() is String }.getOrDefault(false))
            if (otherJson) fail("chatgpt_response_invalid")
            throw notObject
        }
    }

    fun finish(): String {
        if (buffer.any { !it.toInt().toChar().isWhitespace() } || completed == null) fail("chatgpt_response_incomplete")
        return completed!!
    }

    private fun fail(code: String): Nothing = throw ChatGptException(code)

    private companion object {
        const val LF: Byte = 10
        const val CR: Byte = 13
        val JSON_SCALAR = Regex("true|false|null|-?(0|[1-9]\\d*)(\\.\\d+)?([eE][+-]?\\d+)?")
    }
}
