package app.inku.mobile

import android.app.Activity
import android.os.Bundle
import android.util.Log
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.model.CompatibilityConstants
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

class HeadlessRenderActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        scope.launch {
            val runId = resolveRunId()
            val outputDir = resolveHeadlessOutputDir(runId)
            runCatching {
                withContext(Dispatchers.IO) {
                    outputDir.mkdirs()
                    File(outputDir, "status.json").writeText(JSONObject().put("status", "running").put("run_id", runId).toString(2))
                }
                render(runId, outputDir)
            }.onFailure { error ->
                Log.e(TAG, "headless render failed runId=$runId", error)
                withContext(Dispatchers.IO) {
                    outputDir.mkdirs()
                    File(outputDir, "result.json").writeText(
                        JSONObject()
                            .put("run_id", runId)
                            .put("status", "error")
                            .put("error", error.message ?: error.toString())
                            .toString(2),
                    )
                    File(outputDir, "status.json").writeText(JSONObject().put("status", "error").put("run_id", runId).toString(2))
                }
            }
            finish()
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    private suspend fun render(runId: String, outputDir: File) {
        val app = application as InkuApplication
        val repository = InkuRepository(applicationContext, app.database)
        repository.ensureDefaultModelAssets()
        repository.ensureDefaultProviderSettings()
        repository.ensureDefaultExportTemplates()

        try {
            val text = resolveInputText()
            require(text.isNotBlank()) { "text or text_file extra is required." }

            val settings = repository.getSetting("model_selection")?.let { JSONObject(it) }
            val stage1Model = intent.getStringExtra("stage1_model")?.takeIf { it.isNotBlank() }
                ?: settings?.optString("stage1_model")?.takeIf { it.isNotBlank() }
                ?: CompatibilityConstants.defaultStage1Model
            val stage2Model = intent.getStringExtra("stage2_model")?.takeIf { it.isNotBlank() }
                ?: settings?.optString("stage2_model")?.takeIf { it.isNotBlank() }
                ?: CompatibilityConstants.defaultStage2Model
            val catalogId = intent.getStringExtra("catalog_id")?.takeIf { it.isNotBlank() }
                ?: repository.getSetting("color_catalog")?.let { JSONObject(it).optString("value") }?.takeIf { it.isNotBlank() }
                ?: CompatibilityConstants.defaultColorCatalogId
            val canvasAspect = intent.getStringExtra("canvas_aspect")?.takeIf { it.isNotBlank() }
                ?: repository.getSetting("canvas_aspect")?.let { JSONObject(it).optString("value") }?.takeIf { it.isNotBlank() }
                ?: CompatibilityConstants.defaultCanvasAspect
            val autoRepair = intent.getBooleanExtra("auto_repair", true)
            val litertStage1PromptOptimization = if (intent.hasExtra("litert_stage1_prompt_optimization")) {
                intent.getBooleanExtra("litert_stage1_prompt_optimization", false)
            } else {
                repository.getSetting("litert_stage1_prompt_optimization")?.let { JSONObject(it).optBoolean("enabled", false) } ?: false
            }
            val saveHistory = intent.getBooleanExtra("save_history", false)
            val inputMode = intent.getStringExtra("input_mode")?.takeIf { it.isNotBlank() } ?: "paint"
            val originalText = intent.getStringExtra("original_text")?.takeIf { it.isNotBlank() } ?: text

            val item = when (inputMode) {
                "ddl" -> repository.composeFromDdl(
                    description = originalText,
                    ddl = text,
                    catalogId = catalogId,
                    canvasAspect = canvasAspect,
                    stage1ModelId = stage1Model,
                    stage2ModelId = stage2Model,
                    autoRepair = autoRepair,
                    litertStage1PromptOptimization = litertStage1PromptOptimization,
                )
                "score" -> repository.renderFromScore(
                    description = originalText,
                    scoreJson = text,
                    catalogId = catalogId,
                    canvasAspect = canvasAspect,
                    stage1ModelId = stage1Model,
                    stage2ModelId = stage2Model,
                )
                else -> repository.paint(
                    description = text,
                    catalogId = catalogId,
                    canvasAspect = canvasAspect,
                    stage1ModelId = stage1Model,
                    stage2ModelId = stage2Model,
                    autoRepair = autoRepair,
                    historyInput = text,
                    litertStage1PromptOptimization = litertStage1PromptOptimization,
                )
            }
            if (!saveHistory) {
                repository.deleteHistoryPermanently(item.id)
            }

            withContext(Dispatchers.IO) {
                File(outputDir, "input.txt").writeText(text)
                File(outputDir, "normalized.ddl").writeText(item.normalizedDdl)
                File(outputDir, "score.json").writeText(JSONObject(item.scoreJson).toString(2))
                File(outputDir, "output.svg").writeText(item.displaySvg)
                val metadata = JSONObject(item.renderMetadataJson)
                File(outputDir, "metadata.json").writeText(metadata.toString(2))
                val result = JSONObject()
                    .put("run_id", runId)
                    .put("status", "ok")
                    .put("history_id", item.id)
                    .put("render_hash", item.renderHash)
                    .put("render_hash_short", item.renderHashShort)
                    .put("render_engine_id", metadata.opt("render_engine_id"))
                    .put("render_engine_version", metadata.opt("render_engine_version"))
                    .put("render_canvas_aspect", metadata.opt("render_canvas_aspect"))
                    .put("render_canvas_aspect_id", metadata.opt("render_canvas_aspect_id"))
                    .put("render_canvas_aspect_ratio", metadata.opt("render_canvas_aspect_ratio"))
                    .put("render_color_catalog_id", metadata.opt("render_color_catalog_id"))
                    .put("render_color_catalog_name", metadata.opt("render_color_catalog_name"))
                    .put("render_color_catalog_sub", metadata.opt("render_color_catalog_sub"))
                    .put("render_color_profile", metadata.opt("render_color_profile"))
                    .put("render_color_map", metadata.opt("render_color_map"))
                    .put("stage1_model", item.stage1Model)
                    .put("stage2_model", item.stage2Model)
                    .put("catalog_id", item.colorCatalogId)
                    .put("canvas_aspect", item.canvasAspect)
                    .put("input_mode", inputMode)
                    .put("elapsed_ms", item.elapsedMs)
                    .put("normalized_ddl", item.normalizedDdl)
                    .put("score_path", "files/headless/$runId/score.json")
                    .put("svg_path", "files/headless/$runId/output.svg")
                    .put("metadata_path", "files/headless/$runId/metadata.json")
                File(outputDir, "result.json").writeText(result.toString(2))
                File(outputDir, "status.json").writeText(JSONObject().put("status", "ok").put("run_id", runId).toString(2))
            }
            Log.i(TAG, "headless render completed runId=$runId hash=${item.renderHashShort}")
        } finally {
            repository.close()
        }
    }

    private suspend fun resolveInputText(): String = withContext(Dispatchers.IO) {
        val text = intent.getStringExtra("text")?.takeIf { it.isNotBlank() } ?: run {
            val path = intent.getStringExtra("text_file")?.takeIf { it.isNotBlank() } ?: return@withContext ""
            resolveHeadlessInputFile(path).readText()
        }
        require(text.length <= MAX_INPUT_CHARS) { "headless input is too large: ${text.length} chars." }
        text
    }

    private fun resolveRunId(): String {
        val raw = intent.getStringExtra("run_id")?.takeIf { it.isNotBlank() } ?: "run-${System.currentTimeMillis()}"
        require(RUN_ID_PATTERN.matches(raw)) { "run_id contains unsupported characters." }
        return raw
    }

    private fun resolveHeadlessOutputDir(runId: String): File {
        val root = File(filesDir, HEADLESS_OUTPUT_DIR).canonicalFile
        val outputDir = File(root, runId).canonicalFile
        require(outputDir.path == root.path || outputDir.path.startsWith(root.path + File.separator)) {
            "headless output path is outside the app headless directory."
        }
        return outputDir
    }

    private fun resolveHeadlessInputFile(path: String): File {
        require(path.startsWith("app:")) { "text_file must use app:$HEADLESS_INPUT_DIR/<file>." }
        val relative = path.removePrefix("app:").trimStart('/')
        require(relative.startsWith("$HEADLESS_INPUT_DIR/")) { "text_file must be under app:$HEADLESS_INPUT_DIR/." }
        val root = File(filesDir, HEADLESS_INPUT_DIR).canonicalFile
        val input = File(filesDir, relative).canonicalFile
        require(input.path.startsWith(root.path + File.separator)) { "text_file is outside the headless input directory." }
        require(input.isFile) { "text_file was not found: app:$relative" }
        return input
    }

    private companion object {
        private const val TAG = "InkuHeadless"
        private const val HEADLESS_OUTPUT_DIR = "headless"
        private const val HEADLESS_INPUT_DIR = "headless-inputs"
        private const val MAX_INPUT_CHARS = 250_000
        private val RUN_ID_PATTERN = Regex("[A-Za-z0-9._-]{1,80}")
    }
}
