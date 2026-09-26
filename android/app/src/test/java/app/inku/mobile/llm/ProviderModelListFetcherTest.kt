package app.inku.mobile.llm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.json.JSONObject
import org.junit.Test

class ProviderModelListFetcherTest {
    @Test
    fun serverCatalogRoutesUseTheRightCredentialForEachProvider() {
        val anthropic = providerModelListRequest("anthropic", "https://api.anthropic.com/", "secret")
        assertEquals("https://api.anthropic.com/v1/models", anthropic.url)
        assertEquals("secret", anthropic.headers["x-api-key"])
        assertEquals("2023-06-01", anthropic.headers["anthropic-version"])
        assertFalse(anthropic.headers.containsKey("Authorization"))

        val gemini = providerModelListRequest("gemini", "https://generativelanguage.googleapis.com", "a+b")
        assertEquals("https://generativelanguage.googleapis.com/v1beta/models", gemini.url)
        assertEquals(mapOf("x-goog-api-key" to "a+b"), gemini.headers)

        val compatible = providerModelListRequest("openai-compatible", "https://api.openai.com/v1", "secret")
        assertEquals("https://api.openai.com/v1/models", compatible.url)
        assertEquals(mapOf("Authorization" to "Bearer secret"), compatible.headers)
    }

    @Test
    fun eachProviderNamesItsNextPageUntilTheLast() {
        assertEquals(
            mapOf("after_id" to "claude-haiku"),
            nextModelListQuery("anthropic", JSONObject("""{"data":[],"has_more":true,"last_id":"claude-haiku"}""")),
        )
        assertNull(nextModelListQuery("anthropic", JSONObject("""{"data":[],"has_more":false,"last_id":"claude-haiku"}""")))
        assertEquals(
            mapOf("pageToken" to "next"),
            nextModelListQuery("gemini", JSONObject("""{"models":[],"nextPageToken":"next"}""")),
        )
        assertNull(nextModelListQuery("gemini", JSONObject("""{"models":[]}""")))
    }

    @Test
    fun catalogResponseKeepsUniqueIdsAndRejectsAnEmptyList() {
        assertEquals(
            listOf("claude-sonnet", "claude-haiku"),
            parseProviderModelList("""{"data":[{"id":"claude-sonnet"},{"id":"claude-sonnet"},{"name":"claude-haiku"}]}"""),
        )
        assertEquals(
            listOf("gemini-2.5-pro"),
            parseProviderModelList("""{"models":[{"name":"models/gemini-2.5-pro"}]}"""),
        )
        assertThrows(IllegalArgumentException::class.java) {
            parseProviderModelList("""{"data":[]}""")
        }
    }
}
