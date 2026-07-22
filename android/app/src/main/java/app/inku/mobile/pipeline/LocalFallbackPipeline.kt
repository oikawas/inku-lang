package app.inku.mobile.pipeline

import android.util.Log
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.render.DefaultSvgRenderer
import java.security.MessageDigest
import java.util.UUID
import kotlin.math.round
import org.json.JSONArray
import org.json.JSONObject

class LocalFallbackPipeline(
    private val renderer: DefaultSvgRenderer = DefaultSvgRenderer(),
    private val modelProvider: ModelProvider? = null,
) {
    suspend fun paint(request: PaintRequest): PaintResult {
        val started = System.currentTimeMillis()
        Log.i(
            PERF_TAG,
            "paint_start stage1_model=${request.stage1Model} stage2_model=${request.stage2Model} " +
                "prompt_chars=${request.description.length} catalog_id=${request.colorCatalogId} canvas_aspect=${request.canvasAspect}",
        )
        val interpreted = interpret(request)
        return composeFromDdl(interpreted.ddlForDisplay, request).also {
            Log.i(
                PERF_TAG,
                "paint_done elapsed_ms=${System.currentTimeMillis() - started} stage1_model=${request.stage1Model} " +
                    "stage2_model=${request.stage2Model} prompt_chars=${request.description.length} hash=${it.renderHashShort}",
            )
        }
    }

    suspend fun interpret(request: PaintRequest): InterpretResult {
        val generatedDdl = generateStage1(request)
        val normalizedDdl = generatedDdl ?: if (request.stage1Model.isExplicitProviderModelId()) {
            error("Stage 1 explicit provider returned no usable DDL.")
        } else {
            interpretText(request.description)
        }
        val expandedDdl = if (request.autoRepair) {
            expandIntermediateDdl(normalizedDdl, request.originalText)
        } else {
            normalizedDdl
        }
        return InterpretResult(
            originalInput = request.originalText,
            normalizedDdl = normalizedDdl,
            expandedDdl = expandedDdl,
            ddlForDisplay = expandedDdl,
        )
    }

    suspend fun composeFromDdl(ddl: String, request: PaintRequest): PaintResult {
        val expandedDdl = if (request.autoRepair) {
            expandIntermediateDdl(ddl, request.originalText)
        } else {
            ddl
        }
        val generatedScore = generateStage2(request, expandedDdl)
        val scoreJson = generatedScore ?: if (request.stage2Model.isExplicitProviderModelId()) {
            error("Stage 2 explicit provider returned no usable Score.")
        } else {
            scoreFromWebRules(expandedDdl, request.originalText, request.canvasAspect).toString()
        }
        val renderStarted = System.currentTimeMillis()
        Log.i(
            PERF_TAG,
            "render_start model_id=${request.stage2Model} score_chars=${scoreJson.length} " +
                "catalog_id=${request.colorCatalogId} canvas_aspect=${request.canvasAspect}",
        )
        val render = renderer.render(
            RenderRequest(
                scoreJson = scoreJson,
                colorCatalogId = request.colorCatalogId,
                canvasAspect = request.canvasAspect,
                svgProfile = "display",
            ),
        )
        Log.i(
            PERF_TAG,
            "render_done render_ms=${System.currentTimeMillis() - renderStarted} svg_chars=${render.svg.length} " +
                "catalog_id=${request.colorCatalogId} canvas_aspect=${request.canvasAspect}",
        )
        val hash = renderHash(
            input = request.originalText,
            ddl = expandedDdl,
            scoreJson = scoreJson,
            svg = render.svg,
            renderMetadataJson = render.metadataJson,
            catalogId = request.colorCatalogId,
        )
        return PaintResult(
            originalInput = request.originalText,
            normalizedDdl = expandedDdl,
            expandedDdl = expandedDdl,
            scoreJson = scoreJson,
            displaySvg = render.svg,
            renderMetadataJson = render.metadataJson,
            renderHash = hash,
            renderHashShort = hash.takeLast(4).uppercase(),
        )
    }

    fun renderFromScore(scoreJson: String, request: PaintRequest): PaintResult {
        val normalizedScore = JSONObject(scoreJson).toString()
        val render = renderer.render(
            RenderRequest(
                scoreJson = normalizedScore,
                colorCatalogId = request.colorCatalogId,
                canvasAspect = request.canvasAspect,
                svgProfile = "display",
            ),
        )
        val hash = renderHash(
            input = request.originalText,
            ddl = request.description,
            scoreJson = normalizedScore,
            svg = render.svg,
            renderMetadataJson = render.metadataJson,
            catalogId = request.colorCatalogId,
        )
        return PaintResult(
            originalInput = request.originalText,
            normalizedDdl = request.description,
            expandedDdl = request.description,
            scoreJson = normalizedScore,
            displaySvg = render.svg,
            renderMetadataJson = render.metadataJson,
            renderHash = hash,
            renderHashShort = hash.takeLast(4).uppercase(),
        )
    }

    private suspend fun generateStage1(request: PaintRequest): String? {
        val provider = modelProvider ?: return null
        val started = System.currentTimeMillis()
        return runCatching {
            Log.i(
                PERF_TAG,
                "stage1_start model_id=${request.stage1Model} prompt_chars=${request.description.length}",
            )
            val generated = provider.generate(
                ModelRequest(
                    modelId = request.stage1Model,
                    prompt = request.description,
                    temperature = 0.2,
                    maxTokens = 1024,
                    systemInstruction = stage1SystemPromptFor(request.stage1Model, request.description, request.litertStage1PromptOptimization),
                ),
            ).text.cleanModelText().normalizeStage1DdlText()
            if (!generated.isUsableStage1Ddl()) {
                if (request.stage1Model.isExplicitProviderModelId()) {
                    error("Stage 1 model did not return usable DDL: ${generated.take(180)}")
                }
                return@runCatching null
            }
            sanitizePlacementWords(generated)
        }.onSuccess { generated ->
            Log.i(
                PERF_TAG,
                "stage1_done model_id=${request.stage1Model} stage1_ms=${System.currentTimeMillis() - started} " +
                    "output_chars=${generated?.length ?: 0} fallback=${generated == null}",
            )
        }.onFailure {
            Log.i(
                PERF_TAG,
                "stage1_failed model_id=${request.stage1Model} stage1_ms=${System.currentTimeMillis() - started} " +
                    "error=${it.message ?: it::class.java.simpleName}",
            )
            if (request.stage1Model.isExplicitProviderModelId()) throw it
            Log.w(TAG, "Stage 1 provider failed; using deterministic fallback.", it)
        }.getOrNull()
    }

    private suspend fun generateStage2(request: PaintRequest, expandedDdl: String): String? {
        val provider = modelProvider ?: return null
        val started = System.currentTimeMillis()
        return runCatching {
            val userPrompt = buildStage2UserMessage(expandedDdl, request.originalText)
            val systemPrompt = stage2SystemPromptFor(request.stage2Model)
            Log.i(
                PERF_TAG,
                "stage2_start model_id=${request.stage2Model} ddl_chars=${expandedDdl.length} " +
                    "user_prompt_chars=${userPrompt.length} system_prompt_chars=${systemPrompt.length}",
            )
            val response = provider.generate(
                ModelRequest(
                    modelId = request.stage2Model,
                    prompt = userPrompt,
                    temperature = 0.0,
                    maxTokens = 2048,
                    systemInstruction = systemPrompt,
                    tool = WebScoreTool.submitScore,
                ),
            ).text.cleanModelText()
            val extracted = runCatching {
                WebScoreTool.extractJsonObject(response)
            }
            val score = extracted.getOrNull()
                ?.takeIf { WebScoreTool.hasRenderableInstructions(it) }
                ?: run {
                    logStage2InvalidResponse(request.stage2Model, response, extracted.exceptionOrNull(), extracted.getOrNull())
                    retryStage2OrFallback(provider, request, expandedDdl, userPrompt)
                }
            normalizeServerScore(score, expandedDdl, request.canvasAspect).toString()
        }.onSuccess { scoreJson ->
            Log.i(
                PERF_TAG,
                "stage2_done model_id=${request.stage2Model} stage2_ms=${System.currentTimeMillis() - started} " +
                    "score_chars=${scoreJson.length}",
            )
        }.onFailure {
            Log.i(
                PERF_TAG,
                "stage2_failed model_id=${request.stage2Model} stage2_ms=${System.currentTimeMillis() - started} " +
                    "error=${it.message ?: it::class.java.simpleName}",
            )
            if (request.stage2Model.isExplicitProviderModelId()) throw it
            Log.w(TAG, "Stage 2 provider failed; using deterministic fallback.", it)
        }.getOrNull()
    }

    private suspend fun retryStage2OrFallback(
        provider: ModelProvider,
        request: PaintRequest,
        expandedDdl: String,
        userPrompt: String,
    ): JSONObject {
        if (!request.autoRepair && request.stage2Model.isExplicitProviderModelId()) {
            error("Stage 2 model did not return drawable instructions.")
        }
        val rescuePrompt = stage2SystemPromptFor(request.stage2Model) + "\n\n# 空描画リトライ / コンパクト描画リトライ\n" +
            "直前の Stage 2 出力は無効または非効率。2〜5個の簡潔な描画命令を返す。" +
            "instructions を空配列にしてはいけない。繰り返し図形は複数 instruction にせず、1 instruction + arrangement で表す。" +
            "DDLを説明し直さず、JSONを短く保つ。"
        val retryScore = runCatching {
            val retryResponse = provider.generate(
                ModelRequest(
                    modelId = request.stage2Model,
                    prompt = userPrompt,
                    temperature = 0.0,
                    maxTokens = 2048,
                    systemInstruction = rescuePrompt,
                    tool = WebScoreTool.submitScore,
                ),
            ).text.cleanModelText()
            WebScoreTool.extractJsonObject(retryResponse)
        }.getOrNull()
        if (retryScore != null && WebScoreTool.hasRenderableInstructions(retryScore)) return retryScore
        Log.w(TAG, "Stage 2 returned no drawable instructions after retry; rebuilding renderable score from DDL.")
        return scoreFromWebRules(expandedDdl, request.originalText, request.canvasAspect)
    }

    private fun logStage2InvalidResponse(modelId: String, response: String, error: Throwable?, score: JSONObject?) {
        val reason = when {
            error != null -> "json_extract_failed"
            score == null -> "json_extract_failed"
            score.optJSONArray("instructions") == null -> "missing_instructions"
            else -> "no_renderable_instructions"
        }
        val instructions = score?.optJSONArray("instructions")
        Log.i(
            PERF_TAG,
            "stage2_invalid model_id=$modelId reason=$reason response_chars=${response.length} " +
                "has_instructions=${instructions != null} instructions_count=${instructions?.length() ?: 0} " +
                "error=${error?.message?.let(::logPreview) ?: "-"} preview=${logPreview(response)}",
        )
    }

    private fun logPreview(text: String, limit: Int = 180): String {
        return text
            .replace(Regex("\\s+"), " ")
            .trim()
            .take(limit)
            .replace("|", "/")
            .ifBlank { "-" }
    }

    private fun stage2SystemPromptFor(modelId: String): String {
        return if (modelId.startsWith("local-litert-lm:")) {
            WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA_LITERT
        } else {
            WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA
        }
    }

    private fun stage1SystemPromptFor(modelId: String, text: String, optimizeLiteRt: Boolean): String {
        return if (optimizeLiteRt && modelId.startsWith("local-litert-lm:")) {
            WebDdlSpec.buildStage1LiteRtSystemPrompt(text)
        } else {
            WebDdlSpec.buildStage1SystemPrompt(text)
        }
    }

    private fun String.isExplicitProviderModelId(): Boolean {
        return startsWith("local-litert-lm:") ||
            startsWith("openai:") ||
            startsWith("anthropic:") ||
            startsWith("gemini:") ||
            startsWith("nvidia:") ||
            startsWith("ollama:") ||
            startsWith("ovms:")
    }

    private fun interpretText(text: String): String {
        val cleaned = sanitizePlacementWords(text.trim())
        if (cleaned.isBlank()) return fallbackDdlFromText(text)
        return ensurePlacement(cleaned)
    }

    private fun expandIntermediateDdl(ddl: String, originalText: String): String {
        return WebDdlExpander.expandIntermediateDdl(ddl, contextText = originalText)
    }

    private fun fallbackDdlFromText(text: String): String {
        return ServerFallbackComposer.fallbackDdlFromText(text)
    }

    private fun scoreFromWebRules(ddl: String, originalText: String, canvasAspect: String): JSONObject {
        val context = "$originalText\n$ddl"
        val background = detectBackground(context)
        val foreground = visibleForeground(detectColorKey(context, background), background)
        val colorCycle = detectColorCycle(context, foreground)
        val instruction = fallbackInstruction(context, foreground, detectWeightKey(context))
        val arrangement = arrangementFrom(context)
        if (arrangement != null) {
            if (colorCycle.isNotEmpty()) arrangement.put("color_cycle", JSONArray(colorCycle))
            instruction.put("arrangement", arrangement)
        } else if (colorCycle.isNotEmpty()) {
            instruction.put("color_hint", "${instruction.optString("color_hint", "fallback from DDL")}; palette ${colorCycle.joinToString("/")}")
        }
        addVariationHint(instruction, context)
        val score = JSONObject()
            .put("version", "0.1.0")
            .put("canvas", canvasAspect)
            .put("background", background)
            .put("instructions", JSONArray().put(coerceInstruction(instruction, "$ddl\n$originalText", background)))
        return normalizeServerScore(score, "$ddl\n$originalText", canvasAspect)
    }

    private fun fallbackInstruction(text: String, color: String, weight: String): JSONObject {
        return ServerFallbackComposer.fallbackInstruction(text, color, weight)
    }

    private fun arrangementFrom(text: String): JSONObject? {
        return ServerFallbackComposer.arrangementFrom(text)
    }

    private fun buildStage2UserMessage(ddl: String, originalText: String): String {
        return if (originalText.isNotBlank() && originalText.trim() != ddl.trim()) {
            "[原文]\n$originalText\n\n[正規化DDL]\n$ddl"
        } else {
            ddl
        }
    }

    private fun normalizeServerScore(score: JSONObject, ddl: String, canvasAspect: String): JSONObject {
        val background = backgroundDominanceGovernor(visibleBackground(score.optString("background", "white")), ddl)
        val source = score.optJSONArray("instructions") ?: JSONArray()
        val repairedItems = mutableListOf<JSONObject>()
        for (i in 0 until source.length()) {
            val instruction = source.optJSONObject(i) ?: continue
            repairedItems += coerceInstruction(instruction, ddl, background)
        }
        if (repairedItems.isEmpty()) {
            repairedItems += fallbackInstruction(ddl, visibleForeground("black", background), "pen")
        }
        val presence = score.optJSONObject("presence") ?: presenceFromDdl(ddl)
        val repaired = repairedItems
            .dedupeInstructions()
            .withDdlCoverage(ddl, background)
            .withColorDelivery(ddl, background)
            .withPrimaryColorDelivery(ddl, background)
            .withShapeDelivery(ddl, background)
            .withComplexMotifRepair(ddl, background)
            .withCompositionDiversity(ddl, background)
            .withStructuralDuplicateRepair()
            .withContextEnergy(ddl, background)
            .withSurfaceTension(ddl, background)
            .withPresenceAuxiliaryShapeRepair(presence)
            .withContextDensityGovernor(ddl, background)
            .withMotionEnergy(ddl)
            .withRhythmVariation(ddl)
            .withRepetitionEventVariation(ddl)
            .withMaPressure(ddl)
            .withVisualEvent(ddl, background)
            .withMotionFloor(ddl, background)
            .withDensityBudget()
            .fold(JSONArray()) { array, item -> array.put(item); array }
        val result = JSONObject()
            .put("version", "0.1.0")
            .put("canvas", canvasAspect)
            .put("background", background)
            .put("instructions", repaired)
        if (presence != null && presence.optString("kind", "none") != "none") result.put("presence", presence)
        return enforceModifierTargeting(result, ddl)
    }

    private fun enforceModifierTargeting(score: JSONObject, ddl: String): JSONObject {
        if (!containsMotionOrTextureTerm(ddl)) return score
        val targetPrimitives = mentionedValues(ddl, primitiveTerms)
        if (targetPrimitives.size != 1) return score
        val targetColors = mentionedValues(ddl, colorTerms)
        val targetPrimitive = targetPrimitives.first()
        val instructions = score.optJSONArray("instructions") ?: return score
        val targeted = mutableListOf<JSONObject>()
        for (i in 0 until instructions.length()) {
            val item = instructions.optJSONObject(i) ?: continue
            if (item.optString("primitive") == targetPrimitive && (targetColors.isEmpty() || item.optString("color") in targetColors)) {
                targeted += item
            }
        }
        if (targeted.isEmpty()) return score
        if (targeted.size == instructions.length() && targeted.all { it.optJSONObject("variation") != null }) return score
        val repaired = JSONArray()
        for (item in targeted) {
            val copy = copyJsonObject(item)
            if (copy.optJSONObject("variation") == null && targetPrimitive == "line") {
                copy.put(
                    "variation",
                    JSONObject()
                        .put("amplitude", "fine")
                        .put("frequency", "medium")
                        .put("quality", "perlin")
                        .put("dimensions", JSONArray(listOf("position_x", "position_y"))),
                )
            }
            repaired.put(copy)
        }
        return copyJsonObject(score).put("instructions", repaired)
    }

    private fun containsMotionOrTextureTerm(text: String): Boolean {
        val lower = text.lowercase()
        return motionOrTextureTerms.any { it.lowercase() in lower }
    }

    private fun mentionedValues(text: String, termsByValue: Map<String, List<String>>): Set<String> {
        val lower = text.lowercase()
        return termsByValue.filterValues { terms -> terms.any { it.lowercase() in lower } }.keys
    }

    private fun coerceInstruction(source: JSONObject, ddl: String, background: String): JSONObject {
        return ServerScoreCoercer.coerceInstruction(
            source = source,
            ddl = ddl,
            background = background,
            detectColorKey = ::detectColorKey,
            detectWeightKey = ::detectWeightKey,
            visibleForeground = ::visibleForeground,
        )
    }

    private fun List<JSONObject>.dedupeInstructions(): List<JSONObject> {
        val seen = mutableSetOf<String>()
        return filter { item ->
            val copy = copyJsonObject(item).also { it.remove("color_hint") }
            seen.add(canonicalJson(copy))
        }
    }

    private fun List<JSONObject>.withDdlCoverage(ddl: String, background: String): List<JSONObject> {
        val clauses = splitDrawableClauses(ddl)
        if (size != 1 || clauses.size <= 1) return this
        val repaired = toMutableList()
        val existing = repaired.map { Triple(it.optString("primitive"), it.optString("color"), it.optString("weight", "pen")) }.toMutableSet()
        for (clause in clauses) {
            val primitive = primitiveFromClause(clause) ?: continue
            if (repaired.size >= 5) break
            val fallback = coverageInstruction(clause, primitive, background, repaired.size)
            val key = Triple(fallback.optString("primitive"), fallback.optString("color"), fallback.optString("weight", "pen"))
            if (key in existing) continue
            repaired += fallback
            existing += key
        }
        return repaired
    }

    private fun List<JSONObject>.withColorDelivery(ddl: String, background: String): List<JSONObject> {
        val requested = requestedColors(ddl)
        if (requested.isEmpty()) return this
        val delivered = flatMap { item ->
            val colors = mutableListOf(item.optString("color", "black"))
            item.optJSONObject("arrangement")?.optJSONArray("color_cycle")?.let { cycle ->
                for (i in 0 until cycle.length()) colors += cycle.optString(i)
            }
            colors
        }.toSet()
        val missing = listOf("red", "blue", "green", "white", "black", "gray").filter { it in requested && it !in delivered }
        if (missing.isEmpty()) return this
        val targetIndex = indexOfFirst { it.optString("primitive") in setOf("ellipse", "arc", "circle", "square", "triangle") }.takeIf { it >= 0 } ?: 0
        return mapIndexed { index, item ->
            if (index != targetIndex) return@mapIndexed item
            val copy = copyJsonObject(item)
            val arrangement = copy.optJSONObject("arrangement") ?: JSONObject().put("count", maxOf(2, missing.size + 1)).put("layout", "scatter").put("margin", 0.16)
            val cycle = JSONArray()
            arrangement.optJSONArray("color_cycle")?.let { existing ->
                for (i in 0 until existing.length()) cycle.put(existing.optString(i))
            }
            val greenContext = greenIntentContext(ddl).takeIf { "green" in missing }
            if (greenContext?.contains("bamboo") == true) copy.put("color", "green")
            val base = copy.optString("color", visibleForeground("black", background))
            if (greenContext?.contains("withered") == true) cycle.put("gray")
            if (base != background) cycle.put(base)
            missing.forEach { color ->
                if ((0 until cycle.length()).none { cycle.optString(it) == color }) cycle.put(color)
            }
            arrangement.put("color_cycle", cycle)
            copy.put("arrangement", arrangement)
            val note = "${missing.joinToString("/")} restored in color_cycle from DDL color intent" +
                (greenContext?.let { "; $it" } ?: "")
            copy.put("color_hint", appendHint(copy.optString("color_hint"), note))
            copy
        }
    }

    private fun List<JSONObject>.withPrimaryColorDelivery(ddl: String, background: String): List<JSONObject> {
        val requested = requestedColors(ddl).filter { it != background && it != "white" }
        if (requested.isEmpty()) return this
        val repaired = toMutableList()
        for (color in requested) {
            if (repaired.any { it.optString("color") == color }) continue
            val candidateIndex = repaired.indexOfFirst { item ->
                val arrangement = item.optJSONObject("arrangement")
                arrangement != null &&
                    item.optString("primitive") in setOf("line", "arc", "ellipse", "square", "triangle", "polygon") &&
                    arrangement.optJSONArray("color_cycle")?.let { cycle ->
                        (0 until cycle.length()).any { cycle.optString(it) == color }
                    } == true
            }
            if (candidateIndex < 0) continue
            val copy = copyJsonObject(repaired[candidateIndex])
            copy.put("color", color)
            copy.put("color_hint", appendHint(copy.optString("color_hint"), "$color promoted to primary stroke from DDL color intent"))
            repaired[candidateIndex] = copy
        }
        return repaired
    }

    private fun greenIntentContext(ddl: String): String? {
        val lower = ddl.lowercase()
        if ("green" in ServerScoreRepairFactory.negatedColors(ddl)) return null
        return when {
            "竹" in ddl || "bamboo" in lower -> "bamboo green kept as primary contour"
            listOf("枯れ草", "枯草", "枯れた草").any { it in ddl } || "withered grass" in lower || "dry grass" in lower -> "withered grass kept as muted green-gray"
            ("森" in ddl || "forest" in lower) && listOf("落ち葉", "紅葉", "秋").any { it in ddl } -> "forest green kept as quiet residue behind warm leaves"
            else -> null
        }
    }

    private fun List<JSONObject>.withShapeDelivery(ddl: String, background: String): List<JSONObject> {
        val requested = requestedShapes(ddl)
        if (requested.isEmpty()) return this
        val repaired = toMutableList()
        for (primitive in listOf("polygon", "triangle", "arc", "square")) {
            if (primitive !in requested || repaired.any { it.optString("primitive") == primitive }) continue
            val limit = if (primitive in setOf("triangle", "polygon")) 8 else 6
            if (repaired.size >= limit) {
                if (primitive in setOf("triangle", "polygon")) {
                    val replaceIndex = repaired.indexOfFirst {
                        it.optString("primitive") in setOf("line", "ellipse", "square") && it.optJSONObject("arrangement") == null
                    }
                    if (replaceIndex >= 0) {
                        repaired[replaceIndex] = shapeRepairInstruction(primitive, replaceIndex, background)
                        continue
                    }
                }
                break
            }
            repaired += shapeRepairInstruction(primitive, repaired.size, background)
        }
        return repaired
    }

    private fun List<JSONObject>.withComplexMotifRepair(ddl: String, background: String): List<JSONObject> {
        val motifs = requestedMotifs(ddl)
        if (motifs.isEmpty()) return this
        val repaired = toMutableList()
        var added = 0
        for (motif in motifs) {
            if (added >= 2 || repaired.any { motif in it.optString("color_hint") }) continue
            val motifInstructions = motifRepairInstructions(motif, added, background)
            if (repaired.size + motifInstructions.size > 10) continue
            repaired += motifInstructions
            added += 1
        }
        return repaired
    }

    private fun List<JSONObject>.withCompositionDiversity(ddl: String, background: String): List<JSONObject> {
        if (size >= 10 || compositionRepairSuppressed(ddl)) return this
        val colors = scoreColorsWithCycles()
        val primitives = map { it.optString("primitive", "line") }.toSet()
        val result = toMutableList()
        val accent = compositionAccentColor(ddl, background, colors)
        val needsAnchor = result.isNotEmpty() && !hasVisibleAnchor() && (primitives == setOf("line") || primitives.size == 1)
        if (needsAnchor) {
            result += JSONObject()
                .put("primitive", "ellipse")
                .put("center", JSONArray(listOf(0.64, 0.40)))
                .put("size", JSONArray(listOf(0.18, 0.11)))
                .put("rotation", -18)
                .put("color", if (accent != null && accent != background) accent else visibleForeground("black", background))
                .put("weight", "brush_thick")
                .put("color_hint", "composition anchor restored for shape/color diversity")
        }
        val updatedColors = result.scoreColorsWithCycles()
        if (accent != null && accent !in colors && accent !in updatedColors && result.size < 10) {
            result += JSONObject()
                .put("primitive", "arc")
                .put("center", JSONArray(listOf(0.36, 0.62)))
                .put("radius", 0.09)
                .put("angle_start", 18)
                .put("angle_end", 205)
                .put("rotation", 8)
                .put("color", if (accent != background) accent else visibleForeground("black", background))
                .put("weight", "brush_thin")
                .put("color_hint", "composition accent restored for shape/color diversity")
        }
        return result
    }

    private fun List<JSONObject>.withContextEnergy(ddl: String, background: String): List<JSONObject> {
        if (size >= 10) return this
        val result = toMutableList()
        val contextCandidates = listOf(
            "leaf_grain" to listOf("落ち葉", "紅葉", "湿った土", "森", "leaf", "leaves", "autumn forest", "fallen leaves"),
            "silence_layer" to listOf("廃校", "廊下", "長い沈黙", "夕方の光", "abandoned school", "corridor", "long silence"),
            "hard_edge" to listOf("工場", "鉄骨", "錆", "錆び", "空を細かく分け", "factory", "steel frame", "rust", "girder"),
            "playful_motion" to listOf("自転車", "坂道", "花びら", "色紙", "風鈴", "bicycle", "slope", "petal", "colored paper", "wind chime"),
        )
        for ((kind, markers) in contextCandidates) {
            if (result.size >= 10) break
            if (!contextHasMarker(ddl, markers) || result.any { kind in it.optString("color_hint") }) continue
            result += contextEnergyInstruction(kind, background)
        }
        return result
    }

    private fun List<JSONObject>.withMotionEnergy(ddl: String): List<JSONObject> {
        if (!contextHasMotion(ddl)) return this
        return mapIndexed { index, item ->
            val copy = copyJsonObject(item)
            var changed = false
            val primitive = copy.optString("primitive", "line")
            val arrangement = copy.optJSONObject("arrangement")
            if (arrangement != null) {
                if (arrangement.optString("path", "none") == "none") {
                    arrangement.put("path", if (index % 2 == 0) "wave" else "diagonal")
                    changed = true
                }
                if (arrangement.optString("rhythm_spacing", "none") == "none") {
                    arrangement.put("rhythm_spacing", "loose")
                    changed = true
                }
                if (primitive in setOf("ellipse", "square", "triangle", "polygon") && !copy.has("rotation")) {
                    copy.put("rotation", if (index % 2 == 0) -24 else 18)
                    changed = true
                }
                copy.put("arrangement", arrangement)
            } else if (primitive in setOf("line", "ellipse", "arc", "square", "triangle", "polygon") && !copy.has("rotation")) {
                copy.put("rotation", if (index % 2 == 0) -18 else 22)
                changed = true
            }
            if (copy.optJSONObject("variation") == null && primitive in setOf("line", "ellipse", "arc", "polygon")) {
                copy.put(
                    "variation",
                    JSONObject()
                        .put("amplitude", "medium")
                        .put("frequency", "slow")
                        .put("quality", "wave")
                        .put("dimensions", JSONArray(listOf("position_x", "position_y"))),
                )
                changed = true
            }
            if (changed) {
                copy.put("color_hint", appendHint(copy.optString("color_hint").takeIf { it.isNotBlank() }, "motion energy restored through trajectory and rotation"))
            }
            copy
        }
    }

    private fun List<JSONObject>.withMotionFloor(ddl: String, background: String): List<JSONObject> {
        if (!contextHasMotion(ddl)) return this
        if (countHintFromDdl(ddl) != null || requestedShapes(ddl).isNotEmpty()) return this
        if (size >= 10 || hasMotionPath()) return this
        if (any { "motion floor restored" in it.optString("color_hint") }) return this
        return this + motionFloorInstruction(ddl, background)
    }

    private fun List<JSONObject>.hasMotionPath(): Boolean {
        return any { item ->
            val arrangement = item.optJSONObject("arrangement")
            arrangement != null && arrangement.optString("path", "none") != "none" && arrangement.optInt("count", 1) >= 3
        }
    }

    private fun motionFloorInstruction(ddl: String, background: String): JSONObject {
        val requested = requestedColors(ddl).filter { it != background }
        val color = requested.firstOrNull() ?: if (background != "red") "red" else visibleForeground(background, background)
        return JSONObject()
            .put("primitive", "arc")
            .put("center", JSONArray(listOf(0.58, 0.52)))
            .put("radius", 0.11)
            .put("angle_start", 205)
            .put("angle_end", 330)
            .put("rotation", -16)
            .put("color", color)
            .put("weight", "hair")
            .put("color_hint", "motion floor restored as a small directional trace")
            .put(
                "arrangement",
                JSONObject()
                    .put("count", 3)
                    .put("layout", "scatter")
                    .put("path", "diagonal")
                    .put("margin", 0.24)
                    .put("density", "low")
                    .put("fade", "directional")
                    .put("preserve_space", true)
                    .put("rhythm_spacing", "loose"),
            )
    }

    private fun List<JSONObject>.withRhythmVariation(ddl: String): List<JSONObject> {
        if (!contextHasRhythm(ddl)) return this
        return mapIndexed { index, item ->
            val copy = copyJsonObject(item)
            var changed = false
            val arrangement = copy.optJSONObject("arrangement")
            if (arrangement != null) {
                if (arrangement.optString("path", "none") == "none") {
                    arrangement.put("path", if (index % 2 == 0) "wave" else "diagonal")
                    changed = true
                }
                if (arrangement.optString("density", "none") == "none") {
                    arrangement.put("density", "low")
                    changed = true
                }
                if (arrangement.optString("rhythm_spacing", "none") == "none") {
                    arrangement.put("rhythm_spacing", "syncopated")
                    changed = true
                }
                if (arrangement.optDouble("margin", 0.1) < 0.14) {
                    arrangement.put("margin", 0.14)
                    changed = true
                }
                copy.put("arrangement", arrangement)
            }
            val primitive = copy.optString("primitive", "line")
            if (primitive in setOf("line", "ellipse", "arc", "square", "triangle", "polygon") && !copy.has("rotation")) {
                copy.put("rotation", if (index % 2 == 0) -15 else 21)
                changed = true
            }
            if (copy.optJSONObject("variation") == null && primitive in setOf("line", "ellipse", "arc", "polygon")) {
                copy.put(
                    "variation",
                    JSONObject().put("amplitude", "medium").put("frequency", "medium").put("quality", "wave")
                        .put("dimensions", JSONArray(listOf("position_x", "position_y", "rotation"))),
                )
                changed = true
            }
            if (changed) copy.put("color_hint", appendHint(copy.optString("color_hint"), "rhythm variation restored without increasing count"))
            copy
        }
    }

    private fun List<JSONObject>.withRepetitionEventVariation(ddl: String): List<JSONObject> {
        if (!contextHasMotion(ddl) && !contextHasVisualEvent(ddl) && !contextHasRhythm(ddl)) return this
        if (countHintFromDdl(ddl) != null || requestedShapes(ddl).isNotEmpty()) return this
        return mapIndexed { index, item ->
            if (item.optString("primitive") != "line" || item.optJSONObject("arrangement") == null || expandedCount(item) < 6) return@mapIndexed item
            val copy = copyJsonObject(item)
            val arrangement = copy.optJSONObject("arrangement") ?: return@mapIndexed copy
            var changed = false
            if (arrangement.optString("rhythm_spacing", "none") in setOf("none", "loose")) {
                arrangement.put("rhythm_spacing", "syncopated")
                changed = true
            }
            if (arrangement.optDouble("margin", 0.1) < 0.18) {
                arrangement.put("margin", 0.18)
                changed = true
            }
            if (arrangement.optString("fade", "none") == "none") {
                arrangement.put("fade", "directional")
                changed = true
            }
            if (!arrangement.optBoolean("preserve_space", false)) {
                arrangement.put("preserve_space", true)
                changed = true
            }
            if (arrangement.optString("path", "none") == "none") {
                arrangement.put("path", if (index % 2 == 0) "wave" else "diagonal")
                changed = true
            }
            if (changed) {
                copy.put("arrangement", arrangement)
                copy.put("color_hint", appendHint(copy.optString("color_hint"), "repetition event shaped with syncopated gaps"))
            }
            copy
        }
    }

    private fun List<JSONObject>.withMaPressure(ddl: String): List<JSONObject> {
        if (!contextHasMaPressure(ddl)) return this
        return map { item ->
            val arrangement = item.optJSONObject("arrangement") ?: return@map item
            val copy = copyJsonObject(item)
            var changed = false
            val adjusted = copy.optJSONObject("arrangement") ?: arrangement
            if (!adjusted.optBoolean("preserve_space", false)) {
                adjusted.put("preserve_space", true)
                changed = true
            }
            if (adjusted.optDouble("margin", 0.1) < 0.22) {
                adjusted.put("margin", 0.22)
                changed = true
            }
            if (adjusted.optString("fade", "none") == "none") {
                adjusted.put("fade", "outward")
                changed = true
            }
            if (adjusted.optString("density", "none") == "none") {
                adjusted.put("density", "low")
                changed = true
            }
            if (changed) {
                copy.put("arrangement", adjusted)
                copy.put("color_hint", appendHint(copy.optString("color_hint"), "ma pressure restored through spacing and preserved negative space"))
            }
            copy
        }
    }

    private fun List<JSONObject>.withVisualEvent(ddl: String, background: String): List<JSONObject> {
        if (!contextHasVisualEvent(ddl)) return this
        if (countHintFromDdl(ddl) != null || requestedShapes(ddl).isNotEmpty()) return this
        if (size >= 10 || any { "visual event restored" in it.optString("color_hint") }) return this
        val color = requestedColors(ddl).firstOrNull { it != background } ?: if (background != "blue") "blue" else visibleForeground(background, background)
        val hasAngular = any { it.optString("primitive") in setOf("square", "triangle", "polygon") && shapeExtent(it) >= 0.035 }
        val accent = if (!hasAngular) {
            JSONObject()
                .put("primitive", "polygon")
                .put("center", JSONArray(listOf(0.68, 0.34)))
                .put("radius", 0.045)
                .put("sides", 5)
                .put("rotation", -18)
                .put("color", if (color != background) color else visibleForeground(background, background))
                .put("weight", "brush_thin")
                .put("color_hint", "visual event restored as a small angular pulse")
        } else {
            JSONObject()
                .put("primitive", "arc")
                .put("center", JSONArray(listOf(0.68, 0.34)))
                .put("radius", 0.055)
                .put("angle_start", 35)
                .put("angle_end", 245)
                .put("rotation", -18)
                .put("color", color)
                .put("weight", "hair")
                .put("color_hint", "visual event restored as a small focal pulse")
        }
        return this + accent
    }

    private fun List<JSONObject>.withSurfaceTension(ddl: String, background: String): List<JSONObject> {
        if (!contextHasSurfaceTension(ddl)) return this
        if (countHintFromDdl(ddl) != null || requestedShapes(ddl).isNotEmpty()) return this
        if (size >= 9 || any { "surface tension restored" in it.optString("color_hint") }) return this
        if (background == "white" && none { closedShapeArea(it) >= 0.08 }) return this
        val color = if (background != "black") "black" else visibleForeground(background, background)
        return this + JSONObject()
            .put("primitive", "arc")
            .put("center", JSONArray(listOf(0.58, 0.62)))
            .put("radius", 0.18)
            .put("angle_start", 198)
            .put("angle_end", 342)
            .put("rotation", -4)
            .put("color", color)
            .put("weight", "hair")
            .put("color_hint", "surface tension restored as a quiet shadow trace")
    }

    private fun List<JSONObject>.withContextDensityGovernor(ddl: String, background: String): List<JSONObject> {
        if (!contextHasDensityGovernor(ddl)) return this
        val adjusted = mutableListOf<JSONObject>()
        var governedCount = 0
        val hasVerticalContext = contextHasVerticalDensity(ddl)
        val hasNeonBlurContext = contextHasNeonBlurDensity(ddl)
        for (item in this) {
            val copy = temperQuietSymbolicShape(copyJsonObject(item), ddl)
            val arrangement = copy.optJSONObject("arrangement")
            if (arrangement == null) {
                adjusted += copy
                continue
            }
            val count = arrangement.optInt("count", 1)
            val isVerticalLoad = hasVerticalContext &&
                (copy.optString("primitive") == "line" || arrangement.optString("layout") == "vertical" || arrangement.optString("path") == "top_to_bottom")
            val verticalCountCap = if (hasNeonBlurContext) MAX_NEON_BLUR_VERTICAL_COUNT else MAX_QUIET_VERTICAL_COUNT
            when {
                isVerticalLoad && count > verticalCountCap -> {
                    governedCount += 1
                    adjusted += copy.withArrangementGovernor(
                        count = verticalCountCap,
                        density = "low",
                        fade = "directional",
                        note = if (hasNeonBlurContext) "neon blur vertical density governed to keep transparent streaks legible" else "quiet vertical density governed to keep membrane/space legible",
                    )
                }
                closedShapeArea(copy) >= 0.04 && count > MAX_QUIET_LARGE_SHAPE_COUNT -> {
                    governedCount += 1
                    adjusted += copy.withArrangementGovernor(
                        count = MAX_QUIET_LARGE_SHAPE_COUNT,
                        density = "low",
                        fade = "outward",
                        note = "quiet large-shape repetition governed to preserve negative space",
                    )
                }
                count > MAX_QUIET_VISUAL_COUNT -> {
                    governedCount += 1
                    val countCap = if (hasNeonBlurContext) MAX_NEON_BLUR_VISUAL_COUNT else MAX_QUIET_VISUAL_COUNT
                    adjusted += copy.withArrangementGovernor(
                        count = countCap,
                        density = if (count >= 120) "medium" else "low",
                        fade = if (arrangement.optString("layout") == "scatter") "outward" else "directional",
                        note = if (hasNeonBlurContext) "neon blur density governed to avoid particle dominance" else "quiet density governed to preserve lightness",
                    )
                }
                else -> adjusted += copy
            }
        }
        if (governedCount > 0 && adjusted.size < 8 && !adjusted.hasCompensatingAccent() && contextHasDensityGovernor(ddl)) {
            adjusted += quietExpressionAccent(ddl, background)
        }
        return adjusted
    }

    private fun List<JSONObject>.withPresenceAuxiliaryShapeRepair(presence: JSONObject?): List<JSONObject> {
        if (presence == null || presence.optString("kind", "none") == "none") return this
        val atmosphericKeys = mapNotNull { item ->
            val key = closedShapeGeometryKey(item)
            if (key != null && closedShapeArea(item) >= 0.025 && isAtmosphericEffectHint(item.optString("color_hint"))) key else null
        }.toSet()
        if (atmosphericKeys.isEmpty()) return this
        return filterNot { item ->
            val key = closedShapeGeometryKey(item)
            key in atmosphericKeys && closedShapeArea(item) >= 0.025 && isPlainMaterialHint(item.optString("color_hint"))
        }
    }

    private fun List<JSONObject>.withStructuralDuplicateRepair(): List<JSONObject> {
        val kept = linkedMapOf<String, JSONObject>()
        for (item in this) {
            val key = structuralDuplicateKey(item)
            val existing = kept[key]
            if (existing == null) {
                kept[key] = item
                continue
            }
            if (item.structuralSpecificityScore() > existing.structuralSpecificityScore()) {
                kept[key] = item
            }
        }
        return kept.values.toList()
    }

    private fun structuralDuplicateKey(item: JSONObject): String {
        val arrangement = item.optJSONObject("arrangement")
        return listOf(
            item.optString("primitive", "line"),
            item.optString("color", "black"),
            item.optString("weight", "pen"),
            item.optJSONArray("center")?.toString().orEmpty(),
            item.optJSONArray("position")?.toString().orEmpty(),
            item.optJSONArray("from")?.toString().orEmpty(),
            item.optJSONArray("to")?.toString().orEmpty(),
            item.optJSONArray("size")?.toString().orEmpty(),
            item.optDouble("radius", -1.0).toString(),
            arrangement?.optInt("count", 1)?.toString().orEmpty(),
            arrangement?.optString("layout", "none").orEmpty(),
            arrangement?.optString("path", "none").orEmpty(),
        ).joinToString("|")
    }

    private fun JSONObject.structuralSpecificityScore(): Int {
        var score = 0
        val arrangement = optJSONObject("arrangement")
        if (arrangement != null) {
            score += 2
            if (arrangement.has("density")) score += 1
            if (arrangement.has("fade")) score += 1
            if (arrangement.optBoolean("preserve_space", false)) score += 1
        }
        if (optJSONObject("variation") != null) score += 1
        if (optString("color_hint").isNotBlank()) score += 1
        return score
    }

    private fun List<JSONObject>.withDensityBudget(): List<JSONObject> {
        return withPerInstructionDensityBudget().withTotalDensityBudget()
    }

    private fun List<JSONObject>.withPerInstructionDensityBudget(): List<JSONObject> {
        return map { item ->
            val count = expandedCount(item)
            if (item.optJSONObject("arrangement") == null || count <= MAX_EXPANDED_PER_INSTRUCTION) {
                item
            } else {
                item.withClusteredDensity("single arrangement density clustered to preserve negative space")
            }
        }
    }

    private fun List<JSONObject>.withTotalDensityBudget(): List<JSONObject> {
        val total = sumOf { expandedCount(it) }
        if (total <= MAX_EXPANDED_PRIMITIVES) return this

        var remainingBudget = MAX_EXPANDED_PRIMITIVES
        val adjusted = mutableListOf<JSONObject>()
        forEachIndexed { index, item ->
            val count = expandedCount(item)
            val restMinimum = size - index - 1
            if (item.optJSONObject("arrangement") == null) {
                adjusted += item
                remainingBudget -= 1
                return@forEachIndexed
            }

            val allowed = if (remainingBudget <= restMinimum + 1) {
                1
            } else {
                val remainingTotal = subList(index, size).sumOf { expandedCount(it) }
                val share = if (remainingTotal > 0) count.toDouble() / remainingTotal.toDouble() else 0.0
                maxOf(1, ((remainingBudget - restMinimum) * share).toInt())
            }

            val adjustedItem = if (allowed < count && count > 80) {
                val clustered = item.withClusteredDensity("expanded density clustered to preserve negative space")
                if (expandedCount(clustered) > allowed) {
                    clustered.withArrangementCount(allowed, "expanded density capped after clustering")
                } else {
                    clustered
                }
            } else {
                item.withArrangementCount(allowed, "expanded density capped to preserve negative space")
            }
            adjusted += adjustedItem
            remainingBudget -= expandedCount(adjustedItem)
        }
        return adjusted
    }

    private fun splitDrawableClauses(text: String): List<String> {
        return ServerScoreRepairFactory.splitDrawableClauses(text)
    }

    private fun primitiveFromClause(clause: String): String? {
        return ServerScoreRepairFactory.primitiveFromClause(clause)
    }

    private fun coverageInstruction(clause: String, primitive: String, background: String, index: Int): JSONObject {
        return ServerScoreRepairFactory.coverageInstruction(clause, primitive, background, index, ::coerceInstruction)
    }

    private fun requestedColors(text: String): List<String> {
        return ServerScoreRepairFactory.requestedColors(text)
    }

    private fun List<JSONObject>.scoreColorsWithCycles(): Set<String> {
        val colors = mutableSetOf<String>()
        forEach { item ->
            colors += item.optString("color", "black")
            item.optJSONObject("arrangement")?.optJSONArray("color_cycle")?.let { cycle ->
                for (i in 0 until cycle.length()) colors += cycle.optString(i)
            }
        }
        return colors
    }

    private fun List<JSONObject>.hasVisibleAnchor(): Boolean {
        return any { item ->
            item.optString("primitive", "line") != "line" && shapeExtent(item) in 0.08..0.42
        }
    }

    private fun shapeExtent(item: JSONObject): Double {
        return ServerScoreRepairFactory.shapeExtent(item)
    }

    private fun compositionAccentColor(ddl: String, background: String, existing: Set<String>): String? {
        return ServerScoreRepairFactory.compositionAccentColor(ddl, background, existing)
    }

    private fun requestedShapes(ddl: String): Set<String> {
        return ServerScoreRepairFactory.requestedShapes(ddl)
    }

    private fun shapeRepairInstruction(primitive: String, index: Int, background: String): JSONObject {
        return ServerScoreRepairFactory.shapeRepairInstruction(primitive, index, background)
    }

    private fun requestedMotifs(ddl: String): List<String> {
        return ServerScoreRepairFactory.requestedMotifs(ddl)
    }

    private fun motifRepairInstructions(motif: String, index: Int, background: String): List<JSONObject> {
        return ServerScoreRepairFactory.motifRepairInstructions(motif, index, background)
    }

    private fun compositionRepairSuppressed(ddl: String): Boolean {
        return ServerScoreRepairFactory.compositionRepairSuppressed(ddl)
    }

    private fun contextEnergyInstruction(kind: String, background: String): JSONObject {
        val visible = visibleForeground("black", background)
        return when (kind) {
            "leaf_grain" -> JSONObject()
                .put("primitive", "ellipse")
                .put("center", JSONArray(listOf(0.42, 0.62)))
                .put("size", JSONArray(listOf(0.045, 0.018)))
                .put("rotation", -28)
                .put("color", if (background != "red") "red" else visible)
                .put("filled", true)
                .put("color_hint", "leaf_grain energy restored without density growth")
                .put(
                    "arrangement",
                    JSONObject()
                        .put("count", 6)
                        .put("layout", "scatter")
                        .put("path", "diagonal")
                        .put("margin", 0.22)
                        .put("density", "low")
                        .put("fade", "directional")
                        .put("preserve_space", true)
                        .put("color_cycle", JSONArray(if (background !in setOf("red", "gray", "green")) listOf("red", "gray", "green") else listOf(visible))),
                )
            "silence_layer" -> JSONObject()
                .put("primitive", "line")
                .put("from", JSONArray(listOf(0.18, 0.70)))
                .put("to", JSONArray(listOf(0.82, 0.38)))
                .put("rotation", -7)
                .put("color", visible)
                .put("weight", "hair")
                .put("color_hint", "silence_layer energy restored as a long optical trace")
                .put(
                    "arrangement",
                    JSONObject()
                        .put("count", 4)
                        .put("layout", "horizontal")
                        .put("path", "diagonal")
                        .put("margin", 0.20)
                        .put("density", "low")
                        .put("fade", "directional")
                        .put("preserve_space", true),
                )
            "hard_edge" -> JSONObject()
                .put("primitive", "polygon")
                .put("center", JSONArray(listOf(0.66, 0.35)))
                .put("radius", 0.045)
                .put("sides", 6)
                .put("rotation", 18)
                .put("color", if (background != "gray") "gray" else visible)
                .put("weight", "brush_thin")
                .put("color_hint", "hard_edge energy restored with polygonal rust/steel fragments")
                .put(
                    "arrangement",
                    JSONObject()
                        .put("count", 5)
                        .put("layout", "scatter")
                        .put("path", "diagonal")
                        .put("margin", 0.18)
                        .put("density", "low")
                        .put("fade", "directional")
                        .put("preserve_space", true)
                        .put("color_cycle", JSONArray(if (background !in setOf("gray", "black")) listOf("gray", "black") else listOf(visible))),
                )
            else -> {
                val playfulColor = if (background == "red") "white" else if (background != "red") "red" else visible
                JSONObject()
                    .put("primitive", "ellipse")
                    .put("center", JSONArray(listOf(0.62, 0.40)))
                    .put("size", JSONArray(listOf(0.055, 0.024)))
                    .put("rotation", -24)
                    .put("color", playfulColor)
                    .put("filled", true)
                    .put("weight", "brush_thick")
                    .put("color_hint", "playful_motion energy restored as a small moving color cluster")
                    .put(
                        "arrangement",
                        JSONObject()
                            .put("count", 5)
                            .put("layout", "scatter")
                            .put("path", "wave")
                            .put("margin", 0.20)
                            .put("density", "low")
                            .put("fade", "outward")
                            .put("preserve_space", true)
                            .put(
                                "color_cycle",
                                JSONArray(
                                    when {
                                        background == "red" -> listOf("white", "blue", "black")
                                        background !in setOf("red", "blue", "white") -> listOf("red", "blue", "white")
                                        else -> listOf(playfulColor)
                                    },
                                ),
                            ),
                    )
            }
        }
    }

    private fun contextHasMarker(ddl: String, markers: List<String>): Boolean {
        return ServerScoreSemantics.contextHasMarker(ddl, markers)
    }

    private fun contextHasDensityGovernor(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasDensityGovernor(ddl)
    }

    private fun contextHasVerticalDensity(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasVerticalDensity(ddl)
    }

    private fun contextHasMotion(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasMotion(ddl)
    }

    private fun contextHasColorfulAccent(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasColorfulAccent(ddl)
    }

    private fun contextHasNeonBlurDensity(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasNeonBlurDensity(ddl)
    }

    private fun contextHasRhythm(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasRhythm(ddl)
    }

    private fun contextHasVisualEvent(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasVisualEvent(ddl)
    }

    private fun contextHasMaPressure(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasMaPressure(ddl)
    }

    private fun contextHasSurfaceTension(ddl: String): Boolean {
        return ServerScoreSemantics.contextHasSurfaceTension(ddl)
    }

    private fun countHintFromDdl(ddl: String): Int? {
        return ServerScoreSemantics.countHintFromDdl(ddl)
    }

    private fun JSONObject.withArrangementGovernor(count: Int, density: String, fade: String, note: String): JSONObject {
        val copy = JSONObject(toString())
        val arrangement = copy.optJSONObject("arrangement") ?: return copy
        val originalCount = arrangement.optInt("count", 1)
        arrangement.put("count", count)
        arrangement.put("density", density)
        arrangement.put("fade", fade)
        arrangement.put("preserve_space", true)
        arrangement.put("margin", maxOf(arrangement.optDouble("margin", 0.10), 0.18))
        copy.put("arrangement", arrangement)
        copy.put("color_hint", appendHint(copy.optString("color_hint"), "$note; original count $originalCount"))
        return copy
    }

    private fun JSONObject.withClusteredDensity(note: String): JSONObject {
        val copy = JSONObject(toString())
        val arrangement = copy.optJSONObject("arrangement") ?: return copy
        val originalCount = arrangement.optInt("count", 1)
        arrangement.put("count", clusteredVisualCount(originalCount))
        val existingDensity = arrangement.optString("density", "none")
        if (existingDensity == "none") arrangement.put("density", densityLabel(originalCount))
        if (!arrangement.has("cluster_count")) arrangement.put("cluster_count", clusterCount(originalCount))
        arrangement.put("preserve_space", true)
        arrangement.put("margin", maxOf(arrangement.optDouble("margin", 0.10), 0.18))
        if (arrangement.optString("fade", "none") == "none") {
            val layout = arrangement.optString("layout", "none")
            val hasPath = arrangement.optString("path", "none") != "none"
            arrangement.put("fade", if (hasPath || layout == "horizontal" || layout == "vertical") "directional" else "outward")
        }
        copy.put("arrangement", arrangement)
        copy.put("color_hint", appendHint(copy.optString("color_hint"), "$note; original count $originalCount"))
        return copy
    }

    private fun JSONObject.withArrangementCount(count: Int, note: String): JSONObject {
        val arrangement = optJSONObject("arrangement") ?: return this
        val targetCount = maxOf(1, count)
        if (arrangement.optInt("count", 1) == targetCount) return this
        val copy = JSONObject(toString())
        copy.optJSONObject("arrangement")?.put("count", targetCount)
        copy.put("color_hint", appendHint(copy.optString("color_hint"), note))
        return copy
    }

    private fun expandedCount(item: JSONObject): Int {
        return maxOf(1, item.optJSONObject("arrangement")?.optInt("count", 1) ?: 1)
    }

    private fun densityLabel(originalCount: Int): String {
        return when {
            originalCount >= 180 -> "high"
            originalCount >= 80 -> "medium"
            else -> "low"
        }
    }

    private fun clusterCount(originalCount: Int): Int {
        return when {
            originalCount >= 500 -> 9
            originalCount >= 240 -> 7
            originalCount >= 120 -> 5
            else -> 3
        }
    }

    private fun clusteredVisualCount(originalCount: Int): Int {
        return if (originalCount <= MAX_VISUAL_CLUSTERED_COUNT) {
            originalCount
        } else {
            minOf(MAX_VISUAL_CLUSTERED_COUNT, maxOf(48, (originalCount * 0.42).toInt()))
        }
    }

    private fun temperQuietSymbolicShape(item: JSONObject, ddl: String): JSONObject {
        val arrangement = item.optJSONObject("arrangement") ?: return item
        if (!contextHasDensityGovernor(ddl)) return item
        val primitive = item.optString("primitive")
        if (primitive !in setOf("circle", "ellipse", "square", "triangle", "polygon", "arc")) return item
        val count = arrangement.optInt("count", 1)
        if (count <= 8 || shapeExtent(item) <= 0.12) return item
        val copy = copyJsonObject(item)
        val adjusted = copy.optJSONObject("arrangement") ?: return copy
        adjusted.put("count", minOf(count, 8))
        adjusted.put("density", "low")
        adjusted.put("fade", "outward")
        adjusted.put("preserve_space", true)
        copy.put("arrangement", adjusted)
        copy.put("color_hint", appendHint(copy.optString("color_hint"), "quiet symbolic shape tempered to preserve negative space; original count $count"))
        return copy
    }

    private fun closedShapeArea(item: JSONObject): Double {
        return ServerScoreSemantics.closedShapeArea(item)
    }

    private fun closedShapeGeometryKey(item: JSONObject): String? {
        return ServerScoreSemantics.closedShapeGeometryKey(item)
    }

    private fun isAtmosphericEffectHint(hint: String): Boolean {
        return ServerScoreSemantics.isAtmosphericEffectHint(hint)
    }

    private fun isPlainMaterialHint(hint: String): Boolean {
        return ServerScoreSemantics.isPlainMaterialHint(hint)
    }

    private fun round2(value: Double): Double = ServerScoreSemantics.round2(value)

    private fun List<JSONObject>.hasCompensatingAccent(): Boolean {
        return any { item ->
            "quiet expression accent restored" in item.optString("color_hint") ||
                (item.optString("color") in setOf("red", "green", "blue") &&
                    (item.optJSONObject("arrangement")?.optInt("count", 1) ?: 1) <= 12 &&
                    closedShapeArea(item) <= 0.03) ||
                (item.optString("primitive") == "arc" && (item.optJSONObject("arrangement")?.optInt("count", 1) ?: 1) <= 9)
        }
    }

    private fun quietExpressionAccent(ddl: String, background: String): JSONObject {
        return ServerScoreSemantics.quietExpressionAccent(ddl, background, ::visibleForeground)
    }

    private fun appendHint(existing: String?, note: String): String {
        return ServerScoreSemantics.appendHint(existing, note)
    }

    private fun presenceFromDdl(ddl: String): JSONObject? {
        return ServerScoreSemantics.presenceFromDdl(ddl)
    }

    private fun presenceCenterFromContext(context: String): JSONArray? {
        return ServerScoreSemantics.presenceCenterFromContext(context)
    }

    private fun detectBackground(text: String): String {
        return ServerScoreSemantics.detectBackground(text)
    }

    private fun backgroundDominanceGovernor(background: String, ddl: String): String {
        if (background !in setOf("black", "red", "blue", "green")) return background
        if (hasExplicitBackgroundIntent(ddl) || hasIntentionalLargeSurface(ddl)) return background
        if (requestedColors(ddl).isNotEmpty() && requestedShapes(ddl).isEmpty()) return background
        return if (contextHasDensityGovernor(ddl) || presenceFromDdl(ddl) != null) "white" else background
    }

    private fun hasIntentionalLargeSurface(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf("大き", "巨大", "広い", "広がる", "布", "幕", "壁一面", "面で", "面として", "large", "huge", "wide", "broad surface", "cloth", "fabric"),
        )
    }

    private fun hasExplicitBackgroundIntent(ddl: String): Boolean {
        val context = ddl.substringBefore("\n").ifBlank { ddl }
        val lower = context.lowercase()
        if (looksLikeGeneratedBackgroundPlan(context)) return false
        if (listOf("背景", "地色", "画面全体", "塗りつぶ", "一面", "夜空", "暗闇", "background", "ground color", "full canvas", "fill the canvas", "night sky", "darkness").any { it in context || it in lower }) return true
        if (listOf("夕焼け空", "夕暮れの空", "sunset sky", "dusk sky").any { it in context || it in lower }) return true
        if (listOf("夜明け", "明け方", "朝焼け", "dawn", "daybreak", "sunrise").any { it in context || it in lower }) return false
        return listOf("夜", "night").any { it in context || it in lower }
    }

    private fun looksLikeGeneratedBackgroundPlan(context: String): Boolean {
        if ("\n" in context) return false
        val clauses = Regex("[。\\n;；]+").split(context).map { it.trim() }.filter { it.isNotBlank() }
        if (clauses.size < 4) return false
        val first = clauses.first().lowercase()
        if (!(first.startsWith("背景を") || first.startsWith("background") || "fill background" in first)) return false
        val lower = context.lowercase()
        return listOf("気配", "透明な膜", "五感", "存在", "境界が滲", "画面全体", "presence", "transparent membrane", "five-sense", "boundary blur", "full canvas")
            .any { it in context || it in lower }
    }

    private fun detectColorKey(text: String, background: String): String {
        return ServerScoreSemantics.detectColorKey(text, background)
    }

    private fun detectWeightKey(text: String): String {
        return ServerScoreSemantics.detectWeightKey(text)
    }

    private fun detectColorCycle(text: String, foreground: String): List<String> {
        return ServerScoreSemantics.detectColorCycle(text, foreground)
    }

    private fun addVariationHint(instruction: JSONObject, text: String) {
        ServerScoreSemantics.addVariationHint(instruction, text)
    }

    private fun hasDrawableVocabulary(text: String): Boolean {
        return ServerDdlText.hasDrawableVocabulary(text)
    }

    private fun ensurePlacement(text: String): String {
        return ServerDdlText.ensurePlacement(text)
    }

    private fun sanitizePlacementWords(text: String): String {
        return ServerDdlText.sanitizePlacementWords(text)
    }

    private fun String.cleanModelText(): String {
        return ServerDdlText.cleanModelText(this)
    }

    private fun String.normalizeStage1DdlText(): String {
        return ServerDdlText.normalizeStage1DdlText(this)
    }

    private fun String.normalizeDdlNumberNoise(): String {
        return ServerDdlText.normalizeDdlNumberNoise(this)
    }

    private fun String.dedupeDdlClauses(): String {
        return ServerDdlText.dedupeDdlClauses(this)
    }

    private fun String.isUsableStage1Ddl(): Boolean {
        return ServerDdlText.isUsableStage1Ddl(this)
    }

    private fun visibleBackground(background: String): String = ServerScoreSemantics.visibleBackground(background)

    private fun visibleForeground(color: String, background: String): String {
        return ServerScoreSemantics.visibleForeground(color, background)
    }

    fun descriptionHash(input: String): String {
        val normalized = java.text.Normalizer.normalize(input, java.text.Normalizer.Form.NFC)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .trim()
        return "dh1:" + sha256(normalized)
    }

    private fun renderHash(input: String, ddl: String, scoreJson: String, svg: String, renderMetadataJson: String, catalogId: String): String {
        val metadata = JSONObject(renderMetadataJson)
        val scoreObj = runCatching { JSONObject(scoreJson) }.getOrNull() ?: JSONObject()
        val payload = JSONObject()
            .put("version", "rh2")
            .put("score", scoreObj)
            .put("render_seed", metadata.opt("render_seed") ?: metadata.opt("seed"))
            .put("vary_seed", metadata.opt("vary_seed"))
            .put("render_build_number", metadata.opt("render_build_number"))
            .put("render_engine_id", metadata.opt("render_engine_id") ?: "default")
            .put("render_engine_version", metadata.opt("render_engine_version") ?: "2")
            .put("render_color_catalog_id", metadata.opt("render_color_catalog_id") ?: catalogId)
        return "rh2:" + sha256(canonicalJson(payload))
    }

    private fun canonicalJson(value: Any?): String {
        return when (value) {
            null, JSONObject.NULL -> "null"
            is JSONObject -> value.keys().asSequence().toList().sorted().joinToString(prefix = "{", postfix = "}") { key ->
                JSONObject.quote(key) + ":" + canonicalJson(value.opt(key))
            }
            is JSONArray -> (0 until value.length()).joinToString(prefix = "[", postfix = "]") { canonicalJson(value.opt(it)) }
            is String -> JSONObject.quote(value)
            is Number, is Boolean -> value.toString()
            else -> JSONObject.quote(value.toString())
        }
    }

    private fun copyJsonObject(source: JSONObject): JSONObject {
        val copy = JSONObject()
        source.keys().forEach { key -> copy.put(key, source.opt(key)) }
        return copy
    }

    private fun sha256(value: String): String {
        return MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") { "%02x".format(it) }
    }

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }

    private fun String.containsAnyIgnoreCase(vararg markers: String): Boolean {
        return markers.any { contains(it, ignoreCase = true) }
    }

    fun newHistoryId(): String = UUID.randomUUID().toString()

    companion object {
        private const val TAG = "InkuPipeline"
        private const val PERF_TAG = "InkuPerf"
        private const val MAX_EXPANDED_PRIMITIVES = 400
        private const val MAX_EXPANDED_PER_INSTRUCTION = 240
        private const val MAX_VISUAL_CLUSTERED_COUNT = 120
        private const val MAX_QUIET_VISUAL_COUNT = 64
        private const val MAX_QUIET_VERTICAL_COUNT = 48
        private const val MAX_NEON_BLUR_VISUAL_COUNT = 24
        private const val MAX_NEON_BLUR_VERTICAL_COUNT = 18
        private const val MAX_QUIET_LARGE_SHAPE_COUNT = 16
        private val motionOrTextureTerms = listOf(
            "震える", "震え", "揺れる", "揺らぐ", "揺れ", "小刻み", "滲む", "にじむ", "太い", "細い",
            "trembling", "tremble", "swaying", "sway", "wobble", "wobbly", "blurring", "blurred", "thick", "thin",
        )
        private val primitiveTerms = mapOf(
            "line" to listOf("直線", "線", "縦線", "横線", "line", "lines"),
            "circle" to listOf("円", "丸", "circle", "circles"),
            "ellipse" to listOf("楕円", "ellipse", "ellipses", "oval", "ovals"),
            "triangle" to listOf("三角", "triangle", "triangles"),
            "square" to listOf("四角", "square", "squares"),
            "polygon" to listOf("多角形", "polygon", "polygons"),
            "arc" to listOf("弧", "arc", "arcs"),
        )
        private val colorTerms = mapOf(
            "white" to listOf("白", "white"),
            "black" to listOf("黒", "black"),
            "blue" to listOf("青", "blue"),
            "red" to listOf("赤", "red"),
            "green" to listOf("緑", "green"),
            "gray" to listOf("灰", "グレー", "gray", "grey"),
        )
    }
}
