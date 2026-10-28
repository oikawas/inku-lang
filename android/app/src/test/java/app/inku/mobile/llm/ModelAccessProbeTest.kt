package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.io.ByteArrayInputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import java.io.File
import org.junit.Assert.*
import org.junit.Test

class ModelAccessProbeTest {
    @Test fun fixtureAccessAnswersMatchThroughTheHttpAdapter() = runBlocking {
        val cases = JSONObject(File(System.getProperty("inku.providerSettingsCases")).readText()).getJSONArray("access_cases")
        for (index in 0 until cases.length()) {
            val row = cases.getJSONObject(index)
            val answer = ModelAccessProbe.checkDetailed("https://example.test/v1", "fixture-key", "fixture-model", row.optString("today")) { url ->
                val show = url.path.endsWith("/api/show")
                val status = if (show && row.getString("stage") == "show") row.getInt("status")
                    else if (show) 200 else row.getInt("status")
                object : HttpURLConnection(url) {
                    override fun getOutputStream() = ByteArrayOutputStream()
                    override fun getResponseCode() = status
                    override fun getErrorStream() = ByteArrayInputStream(row.optString("text").toByteArray())
                    override fun disconnect() {}
                    override fun connect() {}
                    override fun usingProxy() = false
                }
            }
            val expected = row.getJSONObject("answer")
            assertEquals("fixture $index", expected.optString("subscription"), answer.optString("subscription"))
            if (expected.has("retired"))
                assertEquals("fixture $index", expected.getString("retired"), answer.getString("retired"))
            else assertFalse(answer.has("retired"))
        }
    }

    @Test fun showGoneProducesTheRetirementDateWithoutCallingTheModel() = runBlocking {
        val connection = object : HttpURLConnection(URL("https://ollama.com/api/show")) {
            val body = ByteArrayOutputStream()
            override fun getOutputStream() = body
            override fun getResponseCode() = 410
            override fun getErrorStream() = ByteArrayInputStream("retired at 2026-09-28".toByteArray())
            override fun disconnect() {}
            override fun connect() {}
            override fun usingProxy() = false
        }
        val answer = ModelAccessProbe.checkDetailed("https://ollama.com/v1", "fixture-key", "old-model") { url ->
            assertEquals(connection.url, url)
            connection
        }
        assertEquals("2026-09-28", answer.getString("retired"))
        assertNull(connection.getRequestProperty("Authorization"))
        assertEquals("old-model", JSONObject(connection.body.toString("UTF-8")).getString("model"))
    }

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
