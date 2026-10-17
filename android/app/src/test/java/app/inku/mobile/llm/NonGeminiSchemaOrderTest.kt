package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Test

class NonGeminiSchemaOrderTest {
    @Test
    fun everyApiTransportWritesOrderedPropertiesAndKeepsUnorderedRequestsByteForByte() = runBlocking {
        for (route in listOf("openai", "nvidia", "ollama", "anthropic")) {
            lateinit var connection: SchemaConnection
            val open = { url: URL -> SchemaConnection(url, route).also { connection = it } }
            val base = when (route) {
                "openai" -> "https://api.openai.com/v1"
                "anthropic" -> "https://api.anthropic.com"
                "ollama" -> "http://127.0.0.1:11434/v1"
                else -> "https://integrate.api.nvidia.com/v1"
            }
            val provider: ModelProvider = if (route == "anthropic") AnthropicModelProvider(route, base, "test-only", open)
                else OpenAiCompatibleProvider(route, base, "test-only", open)
            val cases = listOf("read_composition" to SchemaOrderFixtures.reading) + SchemaOrderFixtures.plain
            for ((action, schema) in cases) {
                val request = SchemaOrderFixtures.request("$route:fixture-model", action, schema)
                val before = ProviderWireTransport.build(if (route == "anthropic") "anthropic" else "openai_compatible",
                    route, base, request).getString("body")
                provider.generate(request)
                val wire = connection.sent.toString(Charsets.UTF_8.name())
                if (action == "read_composition") {
                    val body = JSONObject(wire)
                    val sentSchema = when (route) {
                        "openai" -> body.getJSONArray("tools").getJSONObject(0).getJSONObject("parameters")
                        "anthropic" -> body.getJSONArray("tools").getJSONObject(0).getJSONObject("input_schema")
                        "ollama" -> body.getJSONObject("response_format").getJSONObject("json_schema").getJSONObject("schema")
                        else -> body.getJSONArray("tools").getJSONObject(0).getJSONObject("function").getJSONObject("parameters")
                    }
                    SchemaOrderFixtures.assertOrdered(wire, sentSchema)
                } else SchemaOrderFixtures.assertBytes(before, wire)
            }
        }
    }
}

private class SchemaConnection(url: URL, private val route: String) : HttpURLConnection(url) {
    val sent = ByteArrayOutputStream()
    override fun getOutputStream() = sent
    override fun getResponseCode() = 200
    override fun getInputStream() = when (route) {
        "openai" -> """{"status":"completed","output":[{"type":"function_call","name":"submit_pipeline_response","arguments":"{}"}]}"""
        "anthropic" -> """{"content":[{"type":"tool_use","name":"submit_pipeline_response","input":{}}]}"""
        else -> """{"choices":[{"message":{"content":"{}"}}]}"""
    }.byteInputStream()
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
}
