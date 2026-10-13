package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ModelAccessProbeTest {
    @Test fun oneTokenProbeUsesTheKeyAndOnlyDefiniteStatusesChangeAccess() = runBlocking {
        listOf(200 to true, 402 to false, 403 to false, 401 to null, 429 to null, 500 to null).forEach { (status, expected) ->
            val connection = object : HttpURLConnection(URL("https://ollama.com/v1/chat/completions")) {
                val body = ByteArrayOutputStream()
                var closed = false
                override fun getOutputStream() = body
                override fun getResponseCode() = status
                override fun disconnect() { closed = true }
                override fun connect() {}
                override fun usingProxy() = false
            }
            assertEquals(expected, ModelAccessProbe.check("https://ollama.com/v1", "fixture-key", "gpt-oss:20b") { url ->
                assertEquals(connection.url, url)
                connection
            })
            assertEquals("Bearer fixture-key", connection.getRequestProperty("Authorization"))
            assertEquals("POST", connection.requestMethod)
            val body = JSONObject(connection.body.toString("UTF-8"))
            assertEquals(1, body.getInt("max_tokens"))
            assertEquals("gpt-oss:20b", body.getString("model"))
            assertEquals(".", body.getJSONArray("messages").getJSONObject(0).getString("content"))
            assertTrue(connection.closed)
        }
    }
}
