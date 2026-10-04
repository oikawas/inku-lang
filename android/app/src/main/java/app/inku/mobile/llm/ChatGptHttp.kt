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

internal data class ChatGptHttpResponse(val status: Int, val body: String)

internal interface ChatGptHttp {
    suspend fun request(url: String, method: String = "GET", token: String? = null,
                        body: String? = null, formBody: Boolean = false,
                        timeoutMs: Long = 30_000, check: () -> Unit = {},
                        onChunk: ((ByteArray) -> Unit)? = null): ChatGptHttpResponse
    fun cancelAll()
}

/** Fixed official origins; OAuth credentials cannot follow a redirect or provider URL. */
internal class UrlConnectionChatGptHttp : ChatGptHttp {
    private val connections = ConcurrentHashMap.newKeySet<HttpURLConnection>()

    override fun cancelAll() { connections.forEach { it.disconnect() } }

    override suspend fun request(url: String, method: String, token: String?, body: String?, formBody: Boolean,
                                 timeoutMs: Long, check: () -> Unit, onChunk: ((ByteArray) -> Unit)?): ChatGptHttpResponse =
        withContext(Dispatchers.IO) {
            coroutineScope {
                val uri = URI(url)
                if (uri.scheme != "https" || uri.host !in setOf("auth.openai.com", "api.openai.com") ||
                    uri.userInfo != null || uri.fragment != null || (uri.port != -1 && uri.port != 443)) {
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
                    connection.requestMethod = method
                    connection.connectTimeout = timeoutMs.coerceIn(1, Int.MAX_VALUE.toLong()).toInt()
                    connection.readTimeout = connection.connectTimeout
                    connection.setRequestProperty("Accept", if (onChunk == null) "application/json" else "text/event-stream")
                    token?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
                    body?.let {
                        val bytes = it.toByteArray(Charsets.UTF_8)
                        if (bytes.size > 2 * 1024 * 1024) throw ChatGptException("chatgpt_response_too_large")
                        connection.doOutput = true
                        connection.setRequestProperty("Content-Type", if (formBody) "application/x-www-form-urlencoded" else "application/json")
                        connection.setFixedLengthStreamingMode(bytes.size)
                        check()
                        connection.outputStream.use { stream -> stream.write(bytes) }
                    }
                    currentCoroutineContext().ensureActive(); check()
                    val status = connection.responseCode
                    check()
                    val output = ByteArrayOutputStream()
                    val streaming = status in 200..299 && onChunk != null
                    val limit = if (status in 200..299) 1024 * 1024 else 64 * 1024
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
                                if (output.size() + size > limit) throw ChatGptException("chatgpt_response_too_large")
                                output.write(buffer, 0, size)
                            }
                        }
                    }
                    currentCoroutineContext().ensureActive(); check()
                    ChatGptHttpResponse(status, output.toString(Charsets.UTF_8))
                } finally {
                    cancellation.cancel()
                    connections.remove(connection)
                    connection.disconnect()
                }
            }
        }
}
