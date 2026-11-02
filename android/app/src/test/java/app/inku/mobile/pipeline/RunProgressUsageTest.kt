package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import java.io.IOException
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class RunProgressUsageTest {
    @Test fun sendsIncludeRetriesAndMissingUsage() = runBlocking {
        var call = 0
        val provider = object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse = when (call++) {
                0 -> throw IOException("offline")
                1 -> ModelResponse("ok", "fixture", 120, 13)
                2 -> ModelResponse("ok", "fixture")
                else -> ModelResponse("ok", "fixture", 20, 3)
            }
        }
        val tracker = ProgressTracker("run")
        tracker.update("""{"run_progress":{"current":null,"finished":[]}}""".encodeToByteArray())
        val action = JSONObject().put("tag", "generate_sketch")
            .put("identity", JSONObject().put("action_id", "a").put("attempt", 1).put("request_digest", "d"))
            .put("timeout_ms", "5000").put("payload", JSONObject().put("prompt",
                JSONObject().put("action_name", "generate_sketch").put("system", "s").put("message", "m")
                    .put("response_schema", JSONObject().put("type", "object"))))
        val adapter = SingleAttemptModelEffectProvider(provider)
        repeat(4) { index ->
            val name = if (index == 3) "choose_laws" else "generate_sketch"
            val request = JSONObject(action.toString()).put("tag", name)
            adapter.performObserved(request.toString(), PipelineModelSelection("one", "two"),
                { input, output -> tracker.usage(name, input, output) }, {})
        }
        val result = tracker.value()!!
        assertEquals(ProgressUsage(120, 13, 2), result.stageTokens["generate_sketch"])
        assertEquals(ProgressUsage(20, 3, 0), result.stageTokens["choose_laws"])
        assertEquals(ProgressUsage(140, 16, 2), result.total)
    }
}
