package app.inku.mobile.llm

import android.util.Log
import java.io.ByteArrayOutputStream
import java.util.Base64
import org.json.JSONArray
import org.json.JSONObject

internal fun base64Url(bytes: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
internal fun chatGptPurpose(action: String?): String {
    val effects = ChatGptCore.call("sign_in_auth_constants").getJSONArray("image_effects")
    return if ((0 until effects.length()).any { effects.getString(it) == action }) "vision" else "llm"
}


/** What the shared core wrote for one request, where it goes, and the bounds its stream is read to. */
internal class ChatGptRequest(val body: String, val mode: String, val answerLimit: Int, val wireLimit: Long, val send: ChatGptSend)

/** An HTTP error answer as it came: the core reads the [body] (one that is not JSON is as none) and keeps the [requestId]. */
internal fun chatGptHttpError(response: ChatGptHttpResponse): ChatGptException =
    chatGptFailure(SharedProviderWire.call(JSONObject().put("action", "sign_in_error").put("service", CHATGPT_PROVIDER)
        .put("body", response.body).put("status", response.status).put("request_id", response.requestId ?: JSONObject.NULL)))

/**
 * A failure of the connection itself, as the core names it (`sign_in_transport`):
 * `timeout` (a read, a connection or the whole deadline ran out),
 * `unavailable` (it failed or was cut) or `too_large` (an answer passed its bound).
 */
internal fun chatGptTransport(kind: String): ChatGptException =
    chatGptFailure(SharedProviderWire.call(JSONObject().put("action", "sign_in_transport").put("service", CHATGPT_PROVIDER).put("kind", kind)))

/** The core's code, failure class and next action. */
internal fun chatGptFailure(answer: JSONObject): ChatGptException =
    ChatGptException(answer.getString("code"), answer.getString("failure"), answer.optString("action").takeIf(String::isNotEmpty))

/** The operation is checked here; the body is the shared core's (`provider_wire`). */
internal fun chatGptRequest(request: ModelRequest): ChatGptRequest {
    if (!request.modelId.startsWith("chatgpt:")) {
        throw ChatGptException("chatgpt_operation_not_supported")
    }
    val model = request.modelId.removePrefix("chatgpt:")
    val purpose = chatGptPurpose(request.pipelineAction)
    ChatGptCore.call("sign_in_auth_operation", JSONObject().put("purpose", purpose)
        .put("tag", request.pipelineAction ?: JSONObject.NULL))
    val tool = request.tool
    if (request.imageJpeg != null || tool == null) {
        throw ChatGptException("chatgpt_operation_not_supported")
    }
    // The schema's original member order matters when it has no propertyOrdering.
    // Keep that object raw on the trip to the core.
    val images = request.pipelineImages
    val raw = "{\"action\":\"sign_in_request\",\"service\":\"$CHATGPT_PROVIDER\",\"model\":${JSONObject.quote(model)}," +
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
    return ChatGptRequest(answer.getString("body"), mode, answerLimit, answer.getLong("wire_limit"), ChatGptSend.of(answer))
}

/**
 * The stream, received whole and read once by the shared core (`provider_wire`).
 * Only the wire as a whole is bounded here, as it arrives; the core holds each
 * event and the answer to their limits and reads the events in order, so the
 * answer is the one an incremental reader gave however the bytes came.
 */
internal class ChatGptStream(private val request: ChatGptRequest, private val onReceivedBytes: ((Long) -> Unit)? = null) {
    private val wire = ByteArrayOutputStream()
    var usage: JSONObject? = null
        private set

    fun feed(chunk: ByteArray) {
        if (wire.size().toLong() + chunk.size > request.wireLimit) throw chatGptTransport("too_large")
        wire.write(chunk)
        runCatching { onReceivedBytes?.invoke(wire.size().toLong()) }
    }

    fun finish(): String {
        val answer = SharedProviderWire.call(JSONObject().put("action", "sign_in_stream").put("service", CHATGPT_PROVIDER).put("mode", request.mode)
            .put("answer_limit", request.answerLimit)
            .put("wire_base64", Base64.getEncoder().encodeToString(wire.toByteArray())))
        usage = answer.optJSONObject("terminal")?.optJSONObject("usage")
        when (answer.getString("outcome")) {
            "answer" -> return answer.getString("text")
            // The core names it: bytes that are not UTF-8 are refused; events and
            // arguments of the wrong shape are malformed_payload, asked again for.
            "malformed" -> throw chatGptFailure(answer)
        }
        answer.optJSONArray("tool_shapes")?.let { shapes ->
            // Tool metadata explains protocol failures without logging text or arguments.
            Log.w("InkuProvider", "chatgpt_tool_shape $shapes streamed_calls=${answer.optInt("streamed_calls")} " +
                "finalized_calls=${answer.optInt("finalized_calls")}")
        }
        throw chatGptFailure(answer)
    }
}
