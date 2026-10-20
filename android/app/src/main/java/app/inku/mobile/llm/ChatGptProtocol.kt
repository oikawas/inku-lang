package app.inku.mobile.llm

import android.util.Log
import java.io.ByteArrayOutputStream
import java.math.BigInteger
import java.net.URI
import java.net.URLDecoder
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
    if (request.pipelineAction !in CHATGPT_EFFECTS || request.imageJpeg != null || request.imagePng != null || tool == null) {
        throw ChatGptException("chatgpt_operation_not_supported")
    }
    // The schema's original member order matters when it has no propertyOrdering.
    // Keep that object raw on the trip to the core.
    val raw = "{\"action\":\"chatgpt_request\",\"model\":${JSONObject.quote(model)}," +
        "\"answer_limit\":$MAX_PROVIDER_RESPONSE_BYTES," +
        "\"prompt\":{\"system\":${JSONObject.quote(request.systemInstruction.orEmpty())}," +
        "\"message\":${JSONObject.quote(request.prompt)}," +
        "\"action_name\":${JSONObject.quote(request.pipelineAction)}," +
        "\"response_schema\":${tool.parametersJson}}}"
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
