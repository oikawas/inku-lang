package app.inku.mobile.llm

import android.util.Log
import java.io.ByteArrayOutputStream
import java.math.BigInteger
import java.net.URI
import java.net.URLEncoder
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

internal fun base64Url(bytes: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
internal fun randomOAuthValue(): String = base64Url(ByteArray(32).also(SecureRandom()::nextBytes))
internal fun form(values: Map<String, String>): String = values.entries.joinToString("&") {
    URLEncoder.encode(it.key, Charsets.UTF_8) + "=" + URLEncoder.encode(it.value, Charsets.UTF_8)
}

internal fun authorizationUrl(hostId: String, redirectUri: String, state: String, nonce: String,
                              verifier: String, previous: JSONObject?, consent: Boolean): String {
    return ChatGptCore.call("chatgpt_auth_url", JSONObject().put("host_id", hostId).put("redirect_uri", redirectUri)
        .put("state", state).put("nonce", nonce).put("verifier", verifier)
        .put("previous", previous ?: JSONObject.NULL).put("consent", consent)).getString("url")
}

internal fun callbackParameters(target: String): Map<String, String> {
    if (target.length > 16_384) throw ChatGptException("chatgpt_callback_invalid")
    val query = ChatGptCore.call("chatgpt_auth_callback_query", JSONObject().put("target", target)).getJSONObject("query")
    return query.keys().asSequence().associateWith { query.getJSONArray(it).getString(0) }
}

internal fun callbackStateMatches(query: Map<String, String>, expected: String): Boolean =
    runCatching { ChatGptCore.call("chatgpt_auth_callback", JSONObject().put("state", query["state"].orEmpty())
        .put("expected_state", expected).put("code", "state-check")); true }.getOrDefault(false)

internal fun issuedClientId(query: Map<String, String>, previous: JSONObject?): String {
    ChatGptCore.call("chatgpt_auth_callback", JSONObject().put("state", "ok").put("expected_state", "ok")
        .put("error", query["error"] ?: JSONObject.NULL).put("code", query["code"] ?: JSONObject.NULL))
    val issued = query["client_id"] ?: previous?.optString("client_id").orEmpty()
    return ChatGptCore.call("chatgpt_auth_callback_client", JSONObject().put("issued", issued)
        .put("previous", previous ?: JSONObject.NULL)).getString("client_id")
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
        val selected = ChatGptCore.call("chatgpt_auth_key", JSONObject().put("header", header).put("discovery", metadata).put("keys", jwks))
        val algorithm = selected.getString("alg")
        val key = selected.getJSONObject("key")
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
        ChatGptCore.call("chatgpt_auth_claims", JSONObject().put("claims", claims).put("client_id", clientId)
            .put("nonce", nonce ?: JSONObject.NULL).put("now", nowSeconds))
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

internal fun chatGptPurpose(action: String?): String {
    if (isVisionTextAction(action)) return "vision"
    val effects = ChatGptCore.call("chatgpt_auth_constants").getJSONArray("image_effects")
    return if ((0 until effects.length()).any { effects.getString(it) == action }) "vision" else "llm"
}

/** Server `request_vision`: the assistant text read up to 512 KiB. */
private const val CHATGPT_VISION_ANSWER_LIMIT = 512 * 1024

/** What the shared core wrote for one request, and the bounds its stream is read to. */
internal class ChatGptRequest(val body: String, val mode: String, val answerLimit: Int, val wireLimit: Long)

/**
 * The shared core reads an HTTP error body, a `response.failed` event and a
 * stream's `error` event alike, so a usage limit sent any of those ways is the same code.
 */
internal fun chatGptResponseError(value: Any?, status: Int? = null): ChatGptException =
    chatGptFailure(SharedProviderWire.call(JSONObject().put("action", "chatgpt_error")
        .put("value", value ?: JSONObject.NULL).put("status", status ?: JSONObject.NULL).put("request_id", JSONObject.NULL)))

private fun chatGptFailure(answer: JSONObject): ChatGptException =
    ChatGptException(answer.getString("code"), answer.getString("failure"))

/** The operation is checked here; the body is the shared core's (`provider_wire`). */
internal fun chatGptRequest(request: ModelRequest): ChatGptRequest {
    if (!request.modelId.startsWith("chatgpt:")) {
        throw ChatGptException("chatgpt_operation_not_supported")
    }
    val model = request.modelId.removePrefix("chatgpt:")
    val purpose = chatGptPurpose(request.pipelineAction)
    ChatGptCore.call("chatgpt_auth_operation", JSONObject().put("purpose", purpose)
        .put("tag", if (isVisionTextAction(request.pipelineAction)) "vision" else request.pipelineAction ?: JSONObject.NULL))
    if (isVisionTextAction(request.pipelineAction)) {
        val image = request.imagePng
        if (image == null || image.isEmpty() || request.imageJpeg != null || request.tool != null) {
            throw ChatGptException("chatgpt_operation_not_supported")
        }
        RefinementVisionImage.requirePng768(image)
        // Server request_vision: bounded assistant text with one input_image,
        // never a pipeline function call or the generic camera route.
        val built = SharedProviderWire.call(JSONObject().put("action", "chatgpt_vision_request").put("model", model)
            .put("system", request.systemInstruction.orEmpty()).put("text", request.prompt)
            .put("images", JSONArray().put("data:image/png;base64," + Base64.getEncoder().encodeToString(image)))
            .put("answer_limit", CHATGPT_VISION_ANSWER_LIMIT))
        return built(built, "text", CHATGPT_VISION_ANSWER_LIMIT)
    }
    val tool = request.tool
    if (request.imageJpeg != null || request.imagePng != null || tool == null) {
        throw ChatGptException("chatgpt_operation_not_supported")
    }
    // The schema's original member order matters when it has no propertyOrdering.
    // Keep that object raw on the trip to the core.
    val images = request.pipelineImages
    val raw = "{\"action\":\"chatgpt_request\",\"model\":${JSONObject.quote(model)}," +
        "\"answer_limit\":$MAX_PROVIDER_RESPONSE_BYTES," +
        "\"prompt\":{\"system\":${JSONObject.quote(request.systemInstruction.orEmpty())}," +
        "\"message\":${JSONObject.quote(request.prompt)}," +
        "\"action_name\":${JSONObject.quote(request.pipelineAction)}," +
        "\"response_schema\":${tool.parametersJson}" +
        (images?.let { ",\"images\":${it.referencesJson}" } ?: "") + "}" +
        (images?.let { ",\"images\":${JSONArray(it.dataUrls)}" } ?: "") + "}"
    return built(SharedProviderWire.call(raw), "pipeline", MAX_PROVIDER_RESPONSE_BYTES)
}

private fun built(answer: JSONObject, mode: String, answerLimit: Int): ChatGptRequest {
    if (answer.optString("outcome") == "refused") throw IllegalArgumentException(answer.getString("detail"))
    check(answer.optString("outcome") == "ok") { "chatgpt request outcome missing" }
    return ChatGptRequest(answer.getString("body"), mode, answerLimit, answer.getLong("wire_limit"))
}

/**
 * The stream, received whole and read once by the shared core (`provider_wire`).
 * Only the wire as a whole is bounded here, as it arrives; the core holds each
 * event and the answer to their limits and reads the events in order, so the
 * answer is the one an incremental reader gave however the bytes came.
 */
internal class ChatGptStream(private val request: ChatGptRequest) {
    private val wire = ByteArrayOutputStream()
    var usage: JSONObject? = null
        private set

    fun feed(chunk: ByteArray) {
        if (wire.size().toLong() + chunk.size > request.wireLimit) throw ChatGptException("chatgpt_response_too_large")
        wire.write(chunk)
    }

    fun finish(): String {
        val answer = SharedProviderWire.call(JSONObject().put("action", "chatgpt_stream").put("mode", request.mode)
            .put("answer_limit", request.answerLimit)
            .put("wire_base64", Base64.getEncoder().encodeToString(wire.toByteArray())))
        usage = answer.optJSONObject("terminal")?.optJSONObject("usage")
        when (answer.getString("outcome")) {
            "answer" -> return answer.getString("text")
            "malformed" -> {
                // As Server reads it: bytes that are not UTF-8 are refused;
                // events and arguments of the wrong shape are malformed_payload.
                val kind = answer.getString("kind")
                if (kind == "utf8") throw ChatGptException("chatgpt_response_invalid", "provider_rejected")
                throw JSONException("chatgpt stream is malformed: $kind")
            }
        }
        answer.optJSONArray("tool_shapes")?.let { shapes ->
            // Tool metadata explains protocol failures without logging text or arguments.
            Log.w("InkuProvider", "chatgpt_tool_shape $shapes streamed_calls=${answer.optInt("streamed_calls")} " +
                "finalized_calls=${answer.optInt("finalized_calls")}")
        }
        throw chatGptFailure(answer)
    }
}
