package app.inku.mobile.llm

import app.inku.mobile.ui.i18n.inkuError
import android.content.Context
import android.util.Log
import app.inku.mobile.data.db.ModelAssetDao
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.ExperimentalFlags
import com.google.ai.edge.litertlm.LogSeverity
import com.google.ai.edge.litertlm.SamplerConfig
import java.io.File
import kotlinx.coroutines.CancellationException
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
) : ModelProvider, VisionAnalyzer {
    override val providerId: String = "local-litert-lm"

    // A request owns the engine through conversation close. close() takes the
    // same lock, so it cannot tear down native state underneath text or vision.
    private val inferenceMutex = Mutex()
    private var loadedModelId: String? = null
    private var loadedModelPath: String? = null
    private var loadedMaxNumTokens: Int? = null
    private var engine: Engine? = null

    override suspend fun generate(request: ModelRequest): ModelResponse = withContext(Dispatchers.IO) {
        inferenceMutex.withLock {
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
                val text = StringBuilder()
                try {
                    withTimeout(REQUEST_TIMEOUT_MS) {
                        conversation.sendMessageAsync(prompt).collect { message ->
                            val rendered = conversation.renderMessageIntoString(message).trim()
                            if (rendered.isNotBlank()) {
                                mergeStreamText(text, rendered)
                            }
                        }
                    }
                } catch (error: TimeoutCancellationException) {
                    conversation.cancelProcess()
                    throw IllegalStateException("LiteRT-LM request timed out.", error)
                } catch (error: CancellationException) {
                    conversation.cancelProcess()
                    throw error
                }
                text.toString().ifBlank { error("LiteRT-LM returned an empty response.") }
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
    }

    suspend fun warmup(modelId: String): Unit = withContext(Dispatchers.IO) {
        inferenceMutex.withLock {
            val started = System.currentTimeMillis()
            val modelPath = resolveModelPath(modelId)
            engineFor(modelId, modelPath, ENGINE_MAX_NUM_TOKENS)
            Log.i(PERF_TAG, "litert_warmup_done model_id=$modelId elapsed_ms=${System.currentTimeMillis() - started}")
        }
    }

    override suspend fun analyze(request: VisionAnalysisRequest): VisionAnalysisResult = withContext(Dispatchers.IO) {
        require(request.outputMode == VisionOutputMode.DESCRIPTION) { "Only description output is supported." }
        require(request.modelId == LOCAL_VISION_MODEL_ID) { "Camera analysis requires the local Gemma 4 E2B model." }
        require(request.normalizedJpeg.isNotEmpty()) { "The normalized camera image is empty." }
        val started = System.currentTimeMillis()
        Log.i(
            PERF_TAG,
            "litert_vision_start model_id=${request.modelId} width=${request.width} height=${request.height} " +
                "jpeg_bytes=${request.normalizedJpeg.size} prompt_version=${VisionPrompts.VERSION}",
        )
        try {
            inferenceMutex.withLock {
                val modelPath = resolveModelPath(request.modelId)
                val activeEngine = engineFor(request.modelId, modelPath, ENGINE_MAX_NUM_TOKENS)
                val response = activeEngine.createConversation(visionConversationConfig()).use { conversation ->
                    val text = StringBuilder()
                    val contents = Contents.of(
                        Content.ImageBytes(request.normalizedJpeg),
                        Content.Text(VisionPrompts.forLanguage(request.languageCode)),
                    )
                    try {
                        withTimeout(REQUEST_TIMEOUT_MS) {
                            conversation.sendMessageAsync(contents).collect { message ->
                                val rendered = conversation.renderMessageIntoString(message).trim()
                                if (rendered.isNotBlank()) mergeStreamText(text, rendered)
                            }
                        }
                    } catch (error: TimeoutCancellationException) {
                        conversation.cancelProcess()
                        throw IllegalStateException("Local image analysis timed out.", error)
                    } catch (error: CancellationException) {
                        conversation.cancelProcess()
                        throw error
                    }
                    text.toString().trim().ifBlank { error("Local image analysis returned an empty description.") }
                }
                val elapsedMs = System.currentTimeMillis() - started
                Log.i(
                    PERF_TAG,
                    "litert_vision_done model_id=${request.modelId} width=${request.width} height=${request.height} " +
                        "jpeg_bytes=${request.normalizedJpeg.size} elapsed_ms=$elapsedMs success=true",
                )
                VisionAnalysisResult(response, request.modelId, elapsedMs)
            }
        } catch (error: Throwable) {
            Log.w(
                PERF_TAG,
                "litert_vision_done model_id=${request.modelId} width=${request.width} height=${request.height} " +
                    "jpeg_bytes=${request.normalizedJpeg.size} elapsed_ms=${System.currentTimeMillis() - started} " +
                    "success=false failure=${error::class.simpleName}",
            )
            throw error
        }
    }

    private suspend fun resolveModelPath(modelId: String): String {
        val asset = modelAssetDao.getByModelId(modelId) ?: inkuError { it.errorModelInfoMissing(modelId) }
        if (asset.downloadState != "ready") {
            inkuError { it.errorModelNotReady(asset.displayName) }
        }
        val path = asset.localPath ?: inkuError { it.errorModelPathMissing(asset.displayName) }
        if (!File(path).isFile) {
            inkuError { it.errorModelFileMissing(asset.displayName, path) }
        }
        return path
    }

    private suspend fun engineFor(modelId: String, modelPath: String, maxNumTokens: Int): Engine {
        val current = engine
        if (current != null && loadedModelId == modelId && loadedModelPath == modelPath && loadedMaxNumTokens == maxNumTokens) {
            return current
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
        return newEngine
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
                visionBackend = Backend.GPU(),
                maxNumTokens = maxNumTokens,
                maxNumImages = 1,
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

    private fun visionConversationConfig(): ConversationConfig = ConversationConfig(
        samplerConfig = SamplerConfig(
            topK = 10,
            topP = 0.9,
            temperature = 0.2,
        ),
    )

    private fun mergeStreamText(current: StringBuilder, rendered: String) {
        if (current.isEmpty()) {
            current.append(rendered)
            return
        }
        val existing = current.toString()
        if (rendered == existing) return
        if (rendered.startsWith(existing)) {
            current.append(rendered.substring(existing.length))
            return
        }
        current.append(rendered)
    }

    suspend fun close() {
        inferenceMutex.withLock {
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
