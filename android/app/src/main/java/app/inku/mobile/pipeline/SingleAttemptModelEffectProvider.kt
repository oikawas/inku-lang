package app.inku.mobile.pipeline

import android.util.Log
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelProviderHttpException
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelTool
import java.io.IOException
import java.net.SocketTimeoutException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.withTimeout
import org.json.JSONException
import org.json.JSONObject

fun interface PipelineProviderEffect {
    suspend fun perform(actionJson: String, models: PipelineModelSelection): String
}

/** Executes one action once. Retry, fallback, and response judgment stay in Rust. */
class SingleAttemptModelEffectProvider(
    private val provider: ModelProvider,
) : PipelineProviderEffect {
    override suspend fun perform(actionJson: String, models: PipelineModelSelection): String {
        val action = JSONObject(actionJson)
        val tag = action.requiredString("tag")
        val resultTag = when (tag) {
            "generate_sketch" -> "sketch_generated"
            "select_description_catalog" -> "description_catalog_selected"
            "generate_normalized_ddl" -> "normalized_ddl_generated"
            "read_composition" -> "composition_read"
            "complete_visible_ddl_holes" -> "visible_ddl_hole_patch_generated"
            else -> throw PipelineHostException("unsupported_provider_effect")
        }
        val identity = action.requiredObject("identity")
        val prompt = action.requiredObject("payload").requiredObject("prompt")
        val timeoutMs = action.requiredCanonicalLong("timeout_ms")
        val stage2 = tag == "complete_visible_ddl_holes"
        val modelId = if (stage2) models.stage2ModelId else models.stage1ModelId
        val maxTokens = if (stage2) models.holeMaxTokens else models.stage1MaxTokens
        require(maxTokens > 0) { "positive model token limit required" }
        val started = System.nanoTime()
        return try {
            val response = withTimeout(timeoutMs) {
                provider.generate(
                    ModelRequest(
                        modelId = modelId,
                        prompt = prompt.requiredString("message"),
                        temperature = 0.0,
                        maxTokens = maxTokens,
                        systemInstruction = prompt.requiredString("system"),
                        tool = ModelTool(
                            name = "submit_pipeline_response",
                            description = "Submit the requested pipeline response.",
                            parametersJson = prompt.requiredObject("response_schema").toString(),
                        ),
                        timeoutMs = timeoutMs,
                        pipelineAction = prompt.requiredString("action_name"),
                    ),
                ).text
            }
            effectResult(resultTag, identity, response, elapsedMs(started)).toString()
        } catch (_: TimeoutCancellationException) {
            providerFailure(identity, "transport_timeout", elapsedMs(started)).toString()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Throwable) {
            if (error is ModelProviderHttpException) {
                Log.w(PROVIDER_LOG_TAG, providerHttpErrorLine(tag, modelId, error))
            }
            providerFailure(identity, failureCode(error), elapsedMs(started)).toString()
        }
    }

    private fun effectResult(tag: String, identity: JSONObject, response: String, elapsedMs: Long) =
        JSONObject()
            .put("tag", tag)
            .put("identity", JSONObject(identity.toString()))
            .put("response", response)
            .put("elapsed_ms", elapsedMs.toString())

    private fun providerFailure(identity: JSONObject, failure: String, elapsedMs: Long) =
        JSONObject()
            .put("tag", "provider_failed")
            .put("identity", JSONObject(identity.toString()))
            .put("failure", failure)
            .put("elapsed_ms", elapsedMs.toString())

    // The core's failure classes. It retries every one within its budget but
    // `provider_rejected`, so only a refusal that would repeat maps there.
    private fun failureCode(error: Throwable): String = when (error) {
        is ModelProviderHttpException -> when {
            error.statusCode == 429 -> "rate_limited"
            error.statusCode >= 500 -> "transport_unavailable"
            else -> "provider_rejected"
        }
        is SocketTimeoutException -> "transport_timeout"
        is JSONException -> "malformed_payload"
        is IOException -> "transport_unavailable"
        is IllegalArgumentException -> "provider_rejected"
        else -> "transport_unavailable"
    }

    private fun elapsedMs(started: Long): Long =
        ((System.nanoTime() - started) / 1_000_000L).coerceAtLeast(0L)
}

/**
 * The pipeline keeps only the failure class; this line is where the provider's
 * own reason survives (a 400 for a field, a 403 for access), as the server's
 * `provider_http_error` log line does. The model id names the connection
 * (`openai:gpt-5.6-luna`).
 */
internal fun providerHttpErrorLine(
    action: String,
    modelId: String,
    error: ModelProviderHttpException,
): String {
    val fields = JSONObject()
        .put("action", action)
        .put("model", modelId)
        .put("status", error.statusCode)
    error.refusal.keys().forEach { key -> fields.put(key, error.refusal.get(key)) }
    return "provider_http_error $fields"
}

private const val PROVIDER_LOG_TAG = "InkuProvider"

internal fun JSONObject.requiredObject(name: String): JSONObject =
    optJSONObject(name) ?: throw PipelineHostException("pipeline_schema_violation")

internal fun JSONObject.requiredString(name: String): String =
    optString(name).takeIf { it.isNotEmpty() }
        ?: throw PipelineHostException("pipeline_schema_violation")

internal fun JSONObject.requiredCanonicalLong(name: String): Long {
    val value = requiredString(name)
    if (!value.all { it in '0'..'9' } || (value.length > 1 && value.startsWith('0'))) {
        throw PipelineHostException("pipeline_schema_violation")
    }
    return value.toLongOrNull()?.takeIf { it > 0L }
        ?: throw PipelineHostException("pipeline_schema_violation")
}
