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
        val interpreted = interpret(request)
        return composeFromDdl(interpreted.ddlForDisplay, request)
    }

    suspend fun interpret(request: PaintRequest): InterpretResult {
        val generatedDdl = generateStage1(request)
        val normalizedDdl = generatedDdl ?: if (request.stage1Model.isExplicitProviderModelId()) {
            error("Stage 1 explicit provider returned no usable DDL.")
        } else {
            interpretText(request.description)
        }
        val expandedDdl = expandIntermediateDdl(normalizedDdl, request.originalText)
        return InterpretResult(
            originalInput = request.originalText,
            normalizedDdl = normalizedDdl,
            expandedDdl = expandedDdl,
            ddlForDisplay = expandedDdl,
        )
    }

    suspend fun composeFromDdl(ddl: String, request: PaintRequest): PaintResult {
        val expandedDdl = expandIntermediateDdl(ddl, request.originalText)
        val generatedScore = generateStage2(request, expandedDdl)
        val scoreJson = generatedScore ?: if (request.stage2Model.isExplicitProviderModelId()) {
            error("Stage 2 explicit provider returned no usable Score.")
        } else {
            scoreFromWebRules(expandedDdl, request.originalText, request.canvasAspect).toString()
        }
        val render = renderer.render(
            RenderRequest(
                scoreJson = scoreJson,
                colorCatalogId = request.colorCatalogId,
                canvasAspect = request.canvasAspect,
                svgProfile = "display",
            ),
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

    private suspend fun generateStage1(request: PaintRequest): String? {
        val provider = modelProvider ?: return null
        return runCatching {
            val generated = provider.generate(
                ModelRequest(
                    modelId = request.stage1Model,
                    prompt = request.description,
                    temperature = 0.2,
                    maxTokens = 1024,
                    systemInstruction = WebDdlSpec.buildStage1SystemPrompt(request.description),
                ),
            ).text.cleanModelText().normalizeStage1DdlText()
            if (!generated.isUsableStage1Ddl()) {
                if (request.stage1Model.isExplicitProviderModelId()) {
                    error("Stage 1 model did not return usable DDL: ${generated.take(180)}")
                }
                return@runCatching null
            }
            sanitizePlacementWords(generated)
        }.onFailure {
            if (request.stage1Model.isExplicitProviderModelId()) throw it
            Log.w(TAG, "Stage 1 provider failed; using deterministic fallback.", it)
        }.getOrNull()
    }

    private suspend fun generateStage2(request: PaintRequest, expandedDdl: String): String? {
        val provider = modelProvider ?: return null
        return runCatching {
            val userPrompt = "原文:\n${request.originalText}\n\n正規化DDL:\n$expandedDdl"
            val response = provider.generate(
                ModelRequest(
                    modelId = request.stage2Model,
                    prompt = userPrompt,
                    temperature = 0.0,
                    maxTokens = 2048,
                    systemInstruction = WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA,
                    tool = WebScoreTool.submitScore,
                ),
            ).text.cleanModelText()
            val score = runCatching {
                WebScoreJson.extractJsonObject(response)
            }.getOrNull()
                ?.takeIf { WebScoreJson.hasRenderableInstructions(it) }
                ?: retryStage2OrFallback(provider, request, expandedDdl, userPrompt)
            coerceScore(score, "${request.originalText}\n$expandedDdl", request.canvasAspect).toString()
        }.onFailure {
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
        val rescuePrompt = WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA + "\n\n# 空描画リトライ / コンパクト描画リトライ\n" +
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
            WebScoreJson.extractJsonObject(retryResponse)
        }.getOrNull()
        if (retryScore != null && WebScoreJson.hasRenderableInstructions(retryScore)) return retryScore
        Log.w(TAG, "Stage 2 returned no drawable instructions after retry; rebuilding renderable score from DDL.")
        return scoreFromWebRules(expandedDdl, request.originalText, request.canvasAspect)
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
        return coerceScore(score, "$ddl\n$originalText", canvasAspect)
    }

    private fun fallbackInstruction(text: String, color: String, weight: String): JSONObject {
        return ServerFallbackComposer.fallbackInstruction(text, color, weight)
    }

    private fun arrangementFrom(text: String): JSONObject? {
        return ServerFallbackComposer.arrangementFrom(text)
    }

    private fun coerceScore(score: JSONObject, ddl: String, canvasAspect: String): JSONObject {
        val background = visibleBackground(score.optString("background", "white"))
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
        val repaired = ServerScoreRepairPipeline.repair(
            instructions = repairedItems,
            ddl = ddl,
            background = background,
            presence = presence,
            hooks = scoreRepairHooks,
        )
            .fold(JSONArray()) { array, item -> array.put(item); array }
        val result = JSONObject()
            .put("version", "0.1.0")
            .put("canvas", canvasAspect)
            .put("background", background)
            .put("instructions", repaired)
        if (presence != null && presence.optString("kind", "none") != "none") result.put("presence", presence)
        return result
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

    private val scoreRepairHooks = ServerScoreRepairPipeline.Hooks(
        dedupeInstructions = { it.dedupeInstructions() },
        withDdlCoverage = { items, ddl, background -> items.withDdlCoverage(ddl, background) },
        withColorDelivery = { items, ddl, background -> items.withColorDelivery(ddl, background) },
        withShapeDelivery = { items, ddl, background -> items.withShapeDelivery(ddl, background) },
        withComplexMotifRepair = { items, ddl, background -> items.withComplexMotifRepair(ddl, background) },
        withCompositionDiversity = { items, ddl, background -> items.withCompositionDiversity(ddl, background) },
        withContextEnergy = { items, ddl, background -> items.withContextEnergy(ddl, background) },
        withMotionEnergy = { items, ddl -> items.withMotionEnergy(ddl) },
        withPresenceAuxiliaryShapeRepair = { items, presence -> items.withPresenceAuxiliaryShapeRepair(presence) },
        withContextDensityGovernor = { items, ddl, background -> items.withContextDensityGovernor(ddl, background) },
        withStructuralDuplicateRepair = { it.withStructuralDuplicateRepair() },
        withDensityBudget = { it.withDensityBudget() },
    )

    private fun List<JSONObject>.dedupeInstructions(): List<JSONObject> {
        val seen = mutableSetOf<String>()
        return filter { item ->
            val copy = JSONObject(item.toString()).also { it.remove("color_hint") }
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
            val fallback = coverageInstruction(clause, primitive, background)
            val key = Triple(fallback.optString("primitive"), fallback.optString("color"), fallback.optString("weight", "pen"))
            if (key in existing) continue
            repaired += fallback
            existing += key
        }
        return repaired
    }

    private fun List<JSONObject>.withColorDelivery(ddl: String, background: String): List<JSONObject> {
        val requested = requestedColors(ddl).filter { it != background }
        if (requested.isEmpty()) return this
        val delivered = flatMap { item ->
            val colors = mutableListOf(item.optString("color", "black"))
            item.optJSONObject("arrangement")?.optJSONArray("color_cycle")?.let { cycle ->
                for (i in 0 until cycle.length()) colors += cycle.optString(i)
            }
            colors
        }.toSet()
        val missing = requested.filterNot { it in delivered }
        if (missing.isEmpty()) return this
        val targetIndex = indexOfFirst { it.optJSONObject("arrangement") != null }.takeIf { it >= 0 } ?: 0
        return mapIndexed { index, item ->
            if (index != targetIndex) return@mapIndexed item
            val copy = JSONObject(item.toString())
            val arrangement = copy.optJSONObject("arrangement") ?: JSONObject().put("count", maxOf(2, missing.size + 1)).put("layout", "scatter").put("margin", 0.16)
            val cycle = JSONArray()
            val base = copy.optString("color", visibleForeground("black", background))
            if (base != background) cycle.put(base)
            missing.forEach { cycle.put(it) }
            arrangement.put("color_cycle", cycle)
            copy.put("arrangement", arrangement)
            copy.put("color_hint", appendHint(copy.optString("color_hint"), "${missing.joinToString("/")} restored in color_cycle from DDL color intent"))
            copy
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
        val hasSoft = any { (it.optString("color_hint") + it.optString("weight")).containsAny("soft", "膜", "香", "light", "水彩") }
        if (!hasSoft && ddl.containsAny("膜", "透明", "霞", "霧", "気配", "余韻")) {
            result += JSONObject()
                .put("primitive", "ellipse")
                .put("center", JSONArray(listOf(0.62, 0.38)))
                .put("size", JSONArray(listOf(0.28, 0.16)))
                .put("color", visibleForeground("gray", background))
                .put("weight", "brush_thin")
                .put("variation", JSONObject().put("amplitude", "medium").put("frequency", "medium").put("quality", "pink").put("dimensions", JSONArray(listOf("position_x", "position_y"))))
                .put("color_hint", "membrane haze restored from DDL context")
        }
        if (result.size < 10 && ddl.containsAny("揺れる", "震える", "波打つ", "流", "舞", "風") && result.none { it.optJSONObject("variation") != null }) {
            val first = JSONObject(result.first().toString())
            first.put("variation", JSONObject().put("amplitude", "fine").put("frequency", "medium").put("quality", "perlin").put("dimensions", JSONArray(listOf("position_x", "position_y"))))
            result[0] = first
        }
        return result
    }

    private fun List<JSONObject>.withMotionEnergy(ddl: String): List<JSONObject> {
        if (!contextHasMotion(ddl) && !ddl.containsAny("震える", "波打つ", "舞", "浮か", "floating")) return this
        return mapIndexed { index, item ->
            val copy = JSONObject(item.toString())
            var changed = false
            val primitive = copy.optString("primitive", "line")
            val arrangement = copy.optJSONObject("arrangement")
            if (arrangement != null) {
                if (arrangement.optString("path", "none") == "none") {
                    arrangement.put("path", if (index % 2 == 0) "wave" else "diagonal")
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

    private fun List<JSONObject>.withContextDensityGovernor(ddl: String, background: String): List<JSONObject> {
        if (!contextHasDensityGovernor(ddl)) return this
        val adjusted = mutableListOf<JSONObject>()
        var governedCount = 0
        val hasVerticalContext = contextHasVerticalDensity(ddl)
        for (item in this) {
            val copy = temperQuietSymbolicShape(JSONObject(item.toString()), ddl)
            val arrangement = copy.optJSONObject("arrangement")
            if (arrangement == null) {
                adjusted += copy
                continue
            }
            val count = arrangement.optInt("count", 1)
            val isVerticalLoad = hasVerticalContext &&
                (copy.optString("primitive") == "line" || arrangement.optString("layout") == "vertical" || arrangement.optString("path") == "top_to_bottom")
            when {
                isVerticalLoad && count > 48 -> {
                    governedCount += 1
                    adjusted += copy.withArrangementGovernor(
                        count = 48,
                        density = "low",
                        fade = "directional",
                        note = "quiet vertical density governed to keep membrane/space legible",
                    )
                }
                closedShapeArea(copy) >= 0.04 && count > 16 -> {
                    governedCount += 1
                    adjusted += copy.withArrangementGovernor(
                        count = 16,
                        density = "low",
                        fade = "outward",
                        note = "quiet large-shape repetition governed to preserve negative space",
                    )
                }
                count > 64 -> {
                    governedCount += 1
                    adjusted += copy.withArrangementGovernor(
                        count = 64,
                        density = if (count >= 120) "medium" else "low",
                        fade = if (arrangement.optString("layout") == "scatter") "outward" else "directional",
                        note = "quiet density governed to preserve lightness",
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
        val total = sumOf { it.optJSONObject("arrangement")?.optInt("count", 1) ?: 1 }
        if (total <= 180) return this
        var remaining = 180
        return mapIndexed { index, item ->
            val copy = JSONObject(item.toString())
            val arrangement = copy.optJSONObject("arrangement") ?: run {
                remaining -= 1
                return@mapIndexed copy
            }
            val rest = size - index - 1
            val count = arrangement.optInt("count", 1)
            val allowed = maxOf(1, minOf(count, remaining - rest))
            if (allowed < count) {
                arrangement.put("count", allowed)
                if (!arrangement.has("density") || arrangement.optString("density") == "none") {
                    arrangement.put("density", if (count >= 180) "high" else "medium")
                }
                if (!arrangement.has("cluster_count")) arrangement.put("cluster_count", if (count >= 300) 9 else 5)
                arrangement.put("preserve_space", true)
                if (!arrangement.has("fade") || arrangement.optString("fade") == "none") arrangement.put("fade", "directional")
                copy.put("arrangement", arrangement)
                copy.put("color_hint", appendHint(copy.optString("color_hint"), "expanded density capped to preserve negative space; original count $count"))
            }
            remaining -= allowed
            copy
        }
    }

    private fun splitDrawableClauses(text: String): List<String> {
        return ServerScoreRepairFactory.splitDrawableClauses(text)
    }

    private fun primitiveFromClause(clause: String): String? {
        return ServerScoreRepairFactory.primitiveFromClause(clause)
    }

    private fun coverageInstruction(clause: String, primitive: String, background: String): JSONObject {
        return ServerScoreRepairFactory.coverageInstruction(clause, primitive, background, ::coerceInstruction)
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

    private fun temperQuietSymbolicShape(item: JSONObject, ddl: String): JSONObject {
        val arrangement = item.optJSONObject("arrangement") ?: return item
        if (!contextHasDensityGovernor(ddl)) return item
        val primitive = item.optString("primitive")
        if (primitive !in setOf("circle", "ellipse", "square", "triangle", "polygon", "arc")) return item
        val count = arrangement.optInt("count", 1)
        if (count <= 8 || shapeExtent(item) <= 0.12) return item
        val copy = JSONObject(item.toString())
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

    private fun renderHash(input: String, ddl: String, scoreJson: String, svg: String, renderMetadataJson: String, catalogId: String): String {
        val metadata = JSONObject(renderMetadataJson)
        val payload = JSONObject()
            .put("input", input)
            .put("ddl", ddl)
            .put("score", JSONObject(scoreJson))
            .put("svg", svg)
            .put("render_build_number", JSONObject.NULL)
            .put("render_engine_id", metadata.opt("render_engine_id"))
            .put("render_engine_version", metadata.opt("render_engine_version"))
            .put("render_canvas_aspect", metadata.opt("render_canvas_aspect"))
            .put("render_color_catalog_id", metadata.opt("render_color_catalog_id") ?: catalogId)
            .put("render_color_catalog_name", metadata.opt("render_color_catalog_name"))
            .put("render_color_catalog_sub", metadata.opt("render_color_catalog_sub"))
            .put("render_color_map", metadata.optJSONObject("render_color_map"))
        return sha256(canonicalJson(payload))
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
    }
}
