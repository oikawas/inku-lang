package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URI
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONObject

internal data class ChatGptHttpResponse(val status: Int, val body: String, val requestId: String? = null)

/**
 * Where and how a request to the ChatGPT API is sent, as the shared core
 * answers it (`sign_in_request`, and the sign-in procedure's `http`): the URL, the
 * method, the headers that are not secret, where the token goes, the bounds of
 * an answer and of an error body, and the header that names the request.
 */
internal data class ChatGptSend(
    val url: String,
    val method: String,
    val headers: Map<String, String>,
    val authHeader: String,
    val authPrefix: String,
    val answerLimit: Int,
    val errorLimit: Int,
    val requestIdHeader: String?,
) {
    companion object {
        /** The fields of a core answer; a stream's answer gives no `answer_limit` and is bounded by its `wire_limit`. */
        fun of(answer: JSONObject): ChatGptSend {
            val headers = answer.getJSONObject("headers")
            val auth = answer.getJSONObject("auth")
            return ChatGptSend(answer.getString("url"), answer.getString("method"),
                headers.keys().asSequence().associateWith(headers::getString), auth.getString("header"), auth.getString("prefix"),
                if (answer.has("answer_limit")) answer.getInt("answer_limit") else answer.getLong("wire_limit").coerceAtMost(Int.MAX_VALUE.toLong()).toInt(),
                answer.getInt("error_limit"),
                answer.optString("request_id_header").takeIf(String::isNotEmpty))
        }
    }
}

internal interface ChatGptHttp {
    /** The URL, the method, the headers, the token's header, the bounds and the request ID are the core's [send]. */
    suspend fun request(send: ChatGptSend, token: String? = null, body: String? = null,
                        timeoutMs: Long = 30_000, check: () -> Unit = {},
                        onChunk: ((ByteArray) -> Unit)? = null): ChatGptHttpResponse
    fun cancelAll()
}

/** Fixed official origins; OAuth credentials cannot follow a redirect or provider URL. */
internal class UrlConnectionChatGptHttp : ChatGptHttp {
    private val connections = ConcurrentHashMap.newKeySet<HttpURLConnection>()

    override fun cancelAll() { connections.forEach { it.disconnect() } }

    override suspend fun request(send: ChatGptSend, token: String?, body: String?,
                                 timeoutMs: Long, check: () -> Unit, onChunk: ((ByteArray) -> Unit)?): ChatGptHttpResponse =
        withContext(Dispatchers.IO) {
            coroutineScope {
                val uri = URI(send.url)
                // A guard kept beside the core's answer (the author, step 6);
                // a test holds it to the core's issuer and resource.
                if (!uri.scheme.equals("https", ignoreCase = true) || uri.host !in ALLOWED_HOSTS ||
                    uri.userInfo != null || !uri.fragment.isNullOrEmpty() || (uri.port != -1 && uri.port != 443)) {
                    throw ChatGptException("chatgpt_identity_invalid")
                }
                check()
                val connection = uri.toURL().openConnection() as HttpURLConnection
                connections.add(connection)
                val cancellation = launch(start = CoroutineStart.UNDISPATCHED) {
                    suspendCancellableCoroutine<Unit> { continuation ->
                        continuation.invokeOnCancellation { connection.disconnect() }
                    }
                }
                try {
                    connection.instanceFollowRedirects = false
                    connection.requestMethod = send.method
                    connection.connectTimeout = timeoutMs.coerceIn(1, Int.MAX_VALUE.toLong()).toInt()
                    connection.readTimeout = connection.connectTimeout
                    send.headers.forEach { (name, value) -> connection.setRequestProperty(name, value) }
                    token?.let { connection.setRequestProperty(send.authHeader, send.authPrefix + it) }
                    body?.let {
                        val bytes = it.toByteArray(Charsets.UTF_8)
                        connection.doOutput = true
                        connection.setFixedLengthStreamingMode(bytes.size)
                        check()
                        connection.outputStream.use { stream -> stream.write(bytes) }
                    }
                    currentCoroutineContext().ensureActive(); check()
                    val status = connection.responseCode
                    check()
                    val output = ByteArrayOutputStream()
                    val streaming = status in 200..299 && onChunk != null
                    val limit = if (status in 200..299) send.answerLimit else send.errorLimit
                    val requestId = send.requestIdHeader?.let(connection::getHeaderField)
                    val source = if (status in 200..299) connection.inputStream else connection.errorStream
                    source?.use { stream ->
                        val buffer = ByteArray(8192)
                        while (true) {
                            currentCoroutineContext().ensureActive(); check()
                            val size = stream.read(buffer)
                            if (size == -1) break
                            check()
                            if (streaming) onChunk(buffer.copyOf(size))
                            else {
                                if (output.size() + size > limit) throw chatGptTransport("too_large")
                                output.write(buffer, 0, size)
                            }
                        }
                    }
                    currentCoroutineContext().ensureActive(); check()
                    ChatGptHttpResponse(status, output.toString(Charsets.UTF_8), requestId)
                } finally {
                    cancellation.cancel()
                    connections.remove(connection)
                    connection.disconnect()
                }
            }
        }

    internal companion object {
        /** The official origins a token may go to: the core's issuer and resource hosts. */
        val ALLOWED_HOSTS = setOf("auth.openai.com", "api.openai.com")
    }
}
