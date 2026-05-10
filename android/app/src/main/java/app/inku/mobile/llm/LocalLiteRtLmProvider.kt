package app.inku.mobile.llm

import android.content.Context
import android.util.Log
import app.inku.mobile.data.db.ModelAssetDao
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.ExperimentalFlags
import com.google.ai.edge.litertlm.LogSeverity
import com.google.ai.edge.litertlm.SamplerConfig
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout

@OptIn(ExperimentalApi::class)
class LocalLiteRtLmProvider(
    private val context: Context,
    private val modelAssetDao: ModelAssetDao,
) : ModelProvider {
    override val providerId: String = "local-litert-lm"

    private val engineMutex = Mutex()
    private var loadedModelId: String? = null
    private var loadedModelPath: String? = null
    private var loadedMaxNumTokens: Int? = null
    private var engine: Engine? = null

    override suspend fun generate(request: ModelRequest): ModelResponse = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        val modelPath = resolveModelPath(request.modelId)
        val maxNumTokens = ENGINE_MAX_NUM_TOKENS
        val prompt = request.prompt
        Log.i(
            PERF_TAG,
            "litert_request_start model_id=${request.modelId} prompt_chars=${prompt.length} " +
                "system_chars=${request.systemInstruction?.length ?: 0} max_tokens=${request.maxTokens} engine_max_tokens=$maxNumTokens",
        )
        val activeEngine = engineFor(request.modelId, modelPath, maxNumTokens)
        val response = activeEngine.createConversation(conversationConfig(request)).use { conversation ->
            var text = ""
            try {
                withTimeout(REQUEST_TIMEOUT_MS) {
                    conversation.sendMessageAsync(prompt).collect { message ->
                        val rendered = conversation.renderMessageIntoString(message).trim()
                        if (rendered.isNotBlank()) {
                            text = mergeStreamText(text, rendered)
                        }
                    }
                }
            } catch (error: TimeoutCancellationException) {
                conversation.cancelProcess()
                throw IllegalStateException("LiteRT-LM request timed out.", error)
            }
            text.ifBlank { error("LiteRT-LM returned an empty response.") }
        }
        Log.i(
            PERF_TAG,
            "litert_request_done model_id=${request.modelId} elapsed_ms=${System.currentTimeMillis() - started} output_chars=${response.length}",
        )
        ModelResponse(
            text = response,
            modelId = request.modelId,
            elapsedMs = System.currentTimeMillis() - started,
        )
    }

    private suspend fun resolveModelPath(modelId: String): String {
        val asset = modelAssetDao.getByModelId(modelId) ?: error("モデル情報がありません: $modelId")
        if (asset.downloadState != "ready") {
            error("${asset.displayName} は未取得です。Settingsで取得を完了してください。")
        }
        val path = asset.localPath ?: error("${asset.displayName} の保存先がありません。")
        if (!File(path).isFile) {
            error("${asset.displayName} のモデルファイルが見つかりません: $path")
        }
        return path
    }

    private suspend fun engineFor(modelId: String, modelPath: String, maxNumTokens: Int): Engine {
        return engineMutex.withLock {
            val current = engine
            if (current != null && loadedModelId == modelId && loadedModelPath == modelPath && loadedMaxNumTokens == maxNumTokens) {
                return@withLock current
            }
            current?.close()
            Engine.setNativeMinLogSeverity(LogSeverity.ERROR)
            ExperimentalFlags.enableSpeculativeDecoding = true
            val cacheDir = File(context.cacheDir, "litert-lm").also { it.mkdirs() }.absolutePath
            val initStarted = System.currentTimeMillis()
            val newEngine = createInitializedEngine(modelPath, Backend.GPU(), maxNumTokens, cacheDir)
            Log.i(
                PERF_TAG,
                "litert_engine_init model_id=$modelId backend=${Backend.GPU().name} speculative_decoding=true " +
                    "engine_init_ms=${System.currentTimeMillis() - initStarted} max_tokens=$maxNumTokens",
            )
            loadedModelId = modelId
            loadedModelPath = modelPath
            loadedMaxNumTokens = maxNumTokens
            engine = newEngine
            newEngine
        }
    }

    private fun createInitializedEngine(
        modelPath: String,
        backend: Backend,
        maxNumTokens: Int,
        cacheDir: String,
    ): Engine {
        Log.i(TAG, "LiteRT-LM engine initializing backend=${backend.name} maxTokens=$maxNumTokens")
        val newEngine = Engine(
            EngineConfig(
                modelPath = modelPath,
                backend = backend,
                maxNumTokens = maxNumTokens,
                cacheDir = cacheDir,
            ),
        )
        newEngine.initialize()
        return newEngine
    }

    private fun conversationConfig(request: ModelRequest): ConversationConfig {
        return ConversationConfig(
            systemInstruction = request.systemInstruction
                ?.takeIf { it.isNotBlank() }
                ?.let { Contents.of(it) },
            samplerConfig = SamplerConfig(
                topK = 10,
                topP = 0.95,
                temperature = request.temperature,
            ),
        )
    }

    private fun mergeStreamText(current: String, rendered: String): String {
        if (current.isBlank()) return rendered
        if (rendered == current) return current
        if (rendered.startsWith(current)) return rendered
        return current + rendered
    }

    suspend fun close() {
        engineMutex.withLock {
            engine?.close()
            engine = null
            loadedModelId = null
            loadedModelPath = null
            loadedMaxNumTokens = null
        }
    }

    private companion object {
        private const val TAG = "InkuLiteRtLm"
        private const val PERF_TAG = "InkuPerf"
        private const val REQUEST_TIMEOUT_MS = 600_000L
        private const val ENGINE_MAX_NUM_TOKENS = 4096
    }
}
