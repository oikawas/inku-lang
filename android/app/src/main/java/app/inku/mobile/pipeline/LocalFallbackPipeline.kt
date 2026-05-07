package app.inku.mobile.pipeline

import android.util.Log
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.render.DefaultSvgRenderer
import java.security.MessageDigest
import java.util.UUID
import kotlin.math.PI
import kotlin.math.min
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
                extractJsonObject(response)
            }.getOrNull()
                ?.takeIf { it.hasRenderableInstructions() }
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
            extractJsonObject(retryResponse)
        }.getOrNull()
        if (retryScore != null && retryScore.hasRenderableInstructions()) return retryScore
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
        val background = if (text.containsAny("夜", "黒", "暗")) "黒" else "白"
        val foreground = if (background == "黒") "白" else "黒"
        val accent = if (foreground == "黒" && text.containsAny("白", "雪")) "青" else "灰色"
        return "背景を${background}で塗りつぶす。${foreground}い細い斜めの線を三本並べる。${accent}の小さな点を十二個、画面全体に点々と散らす。"
    }

    private fun extractJsonObject(text: String): JSONObject {
        val trimmed = text.trim()
        runCatching { return unwrapScoreJson(JSONObject(trimmed)) }
        val start = trimmed.indexOf('{')
        val end = trimmed.lastIndexOf('}')
        if (start >= 0 && end > start) {
            return unwrapScoreJson(JSONObject(trimmed.substring(start, end + 1)))
        }
        error("Stage2 did not return a JSON object.")
    }

    private fun unwrapScoreJson(json: JSONObject): JSONObject {
        json.optJSONArray("tool_calls")?.let { calls ->
            for (i in 0 until calls.length()) {
                val call = calls.optJSONObject(i) ?: continue
                val arguments = call.optJSONObject("arguments")
                    ?: call.optJSONObject("parameters")
                    ?: call.optJSONObject("function")?.let { function ->
                        function.optJSONObject("arguments")
                            ?: function.optString("arguments").takeIf { it.isNotBlank() }?.let(::JSONObject)
                    }
                if (arguments != null) return arguments
            }
        }
        json.optJSONObject("arguments")?.let { return it }
        return json
    }

    private fun JSONObject.hasRenderableInstructions(): Boolean {
        val instructions = optJSONArray("instructions") ?: return false
        for (i in 0 until instructions.length()) {
            if (instructions.optJSONObject(i) != null) return true
        }
        return false
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
        val lower = text.lowercase()
        val filled = text.contains("塗") || lower.contains("fill")
        val base = JSONObject()
            .put("color", color)
            .put("weight", weight)
            .put("filled", filled)
            .put("style", when {
                text.contains("破線") || lower.contains("dashed") -> "dashed"
                text.contains("点線") || lower.contains("dotted") -> "dotted"
                else -> "solid"
            })
            .put("color_hint", "fallback from DDL")
        return when {
            text.containsAny("多角形", "五角", "六角", "結晶", "鉱物", "硬い欠片") || lower.contains("polygon") || lower.contains("crystal") -> base
                .put("primitive", "polygon")
                .put("center", JSONArray(listOf(0.62, 0.38)))
                .put("radius", 0.08)
                .put("sides", 6)
                .put("rotation", 18)
            text.containsAny("三角", "山", "屋根", "尖", "峰") || lower.contains("triangle") || lower.contains("mountain") -> base
                .put("primitive", "triangle")
                .put("position", JSONArray(listOf(0.54, 0.22)))
                .put("size", JSONArray(listOf(0.20, 0.18)))
                .put("rotation", -8)
            text.containsAny("弧", "円弧", "三日月", "波紋", "渦") || lower.contains("arc") || lower.contains("crescent") -> base
                .put("primitive", "arc")
                .put("center", JSONArray(listOf(0.72, 0.32)))
                .put("radius", 0.16)
                .put("angle_start", if (text.contains("半円")) 0 else 210)
                .put("angle_end", if (text.contains("半円")) 180 else 330)
            text.containsAny("四角", "紙片", "パッチワーク") || lower.contains("square") || lower.contains("rectangle") || lower.contains("patch") -> base
                .put("primitive", "square")
                .put("position", JSONArray(listOf(0.62, 0.28)))
                .put("size", JSONArray(listOf(if (text.contains("横長")) 0.28 else 0.18, if (text.contains("縦長")) 0.28 else 0.12)))
                .put("rotation", if (text.containsAny("回転", "斜め", "右上がり")) -18 else 0)
            text.containsAny("円", "丸", "月", "蕾", "花びら", "香り", "光") || lower.contains("circle") || lower.contains("moon") || lower.contains("petal") || lower.contains("bud") -> base
                .put("primitive", if (text.containsAny("楕円", "花びら", "蕾", "香り", "光")) "ellipse" else "circle")
                .put("center", focusPoint(text))
                .also {
                    if (it.optString("primitive") == "circle") {
                        it.put("radius", detectRadius(text) ?: 0.10)
                    } else {
                        it.put("size", JSONArray(listOf(0.18, 0.11))).put("rotation", -18)
                    }
                }
            else -> base
                .put("primitive", "line")
                .put("from", JSONArray(listOf(0.16, 0.78)))
                .put("to", JSONArray(listOf(0.84, 0.28)))
                .put("rotation", if (text.contains("右下がり")) 30 else -8)
        }
    }

    private fun arrangementFrom(text: String): JSONObject? {
        val lower = text.lowercase()
        val count = countHintFromDdl(text)
        val arrangement = when {
            text.containsAny("散ら", "点々", "全面", "画面全体", "満天", "砂", "雨", "雪") || lower.contains("scatter") || lower.contains("dotted") ->
                JSONObject().put("count", count ?: vagueCount(text)).put("layout", "scatter").put("margin", 0.18)
            text.containsAny("円環", "放射", "同心円", "正五角形") || lower.contains("radial") ->
                JSONObject().put("count", count ?: 8).put("layout", "radial").put("margin", 0.1)
            text.containsAny("並べ", "横に", "縦に", "上から下", "左から右") || lower.contains("line up") ->
                JSONObject().put("count", count ?: 3).put("layout", detectLayoutKey(text)).put("margin", 0.1)
            else -> null
        } ?: return null
        when {
            text.containsAny("波打つ軌跡", "波") || lower.contains("undulating trace") -> arrangement.put("path", "wave")
            text.containsAny("斜めの帯", "斜め") || lower.contains("diagonal band") -> arrangement.put("path", "diagonal")
            text.contains("右半分") || lower.contains("right half") -> arrangement.put("path", "right_half")
            text.contains("上から下") || lower.contains("top to bottom") -> arrangement.put("layout", "vertical").put("path", "top_to_bottom")
            text.contains("左から右") || lower.contains("left to right") -> arrangement.put("layout", "horizontal").put("path", "left_to_right")
            else -> arrangement.put("path", "none")
        }
        val originalCount = arrangement.optInt("count", 1)
        when {
            originalCount > 120 -> {
                arrangement.put("count", min(originalCount, 120))
                arrangement.put("density", if (originalCount >= 300) "high" else "medium")
                arrangement.put("cluster_count", if (originalCount >= 300) 9 else 5)
                arrangement.put("fade", if (arrangement.optString("path", "none") != "none") "directional" else "outward")
                arrangement.put("preserve_space", true)
            }
            originalCount >= 40 -> {
                arrangement.put("density", "medium")
                arrangement.put("cluster_count", 4)
                arrangement.put("fade", if (arrangement.optString("path", "none") != "none") "directional" else "outward")
                arrangement.put("preserve_space", true)
            }
        }
        return arrangement
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
        val repaired = repairedItems
            .dedupeInstructions()
            .withDdlCoverage(ddl, background)
            .withColorDelivery(ddl, background)
            .withShapeDelivery(ddl, background)
            .withComplexMotifRepair(ddl, background)
            .withCompositionDiversity(ddl, background)
            .withContextEnergy(ddl, background)
            .withMotionEnergy(ddl)
            .withPresenceAuxiliaryShapeRepair(presence)
            .withContextDensityGovernor(ddl, background)
            .withStructuralDuplicateRepair()
            .withDensityBudget()
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
        val primitive = when (source.optString("primitive", "line")) {
            "circle", "ellipse", "triangle", "square", "polygon", "arc" -> source.optString("primitive")
            else -> "line"
        }
        val data = JSONObject(source.toString()).put("primitive", primitive)
        data.put("color", visibleForeground(data.optString("color", detectColorKey(ddl, background)), background))
        data.put("weight", data.optString("weight", detectWeightKey(ddl)).ifBlank { "pen" })
        when (primitive) {
            "line" -> {
                if (!data.has("from")) data.put("from", JSONArray(listOf(0.1, 0.5)))
                if (!data.has("to")) data.put("to", JSONArray(listOf(0.9, 0.5)))
            }
            "circle" -> {
                if (!data.has("center")) data.put("center", data.optJSONArray("position") ?: JSONArray(listOf(0.5, 0.5)))
                if (data.optDouble("radius", -1.0) <= 0.0) data.put("radius", 0.15)
            }
            "ellipse" -> {
                if (!data.has("center")) data.put("center", data.optJSONArray("position") ?: JSONArray(listOf(0.5, 0.5)))
                if (!validSize(data.optJSONArray("size"))) data.put("size", JSONArray(listOf(0.3, 0.3)))
            }
            "arc" -> {
                if (!data.has("center")) data.put("center", data.optJSONArray("position") ?: JSONArray(listOf(0.5, 0.5)))
                if (data.optDouble("radius", -1.0) <= 0.0) data.put("radius", 0.15)
                if (!data.has("angle_start")) data.put("angle_start", 0.0)
                if (!data.has("angle_end")) data.put("angle_end", 270.0)
                if (kotlin.math.abs(data.optDouble("angle_start") - data.optDouble("angle_end")) < 1e-6) {
                    data.put("angle_end", (data.optDouble("angle_start") + 270.0) % 360.0)
                }
            }
            "polygon" -> {
                if (!data.has("center")) data.put("center", data.optJSONArray("position") ?: JSONArray(listOf(0.5, 0.5)))
                if (data.optDouble("radius", -1.0) <= 0.0) data.put("radius", 0.12)
                data.put("sides", data.optInt("sides", 5).coerceIn(5, 8))
            }
            "square", "triangle" -> {
                if (!data.has("position")) data.put("position", data.optJSONArray("center") ?: JSONArray(listOf(0.35, 0.35)))
                if (!validSize(data.optJSONArray("size"))) data.put("size", JSONArray(listOf(0.3, 0.3)))
            }
        }
        return data
    }

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

    private fun splitClauses(text: String): List<String> {
        return Regex("""(?<=[。.!?])""").split(text).map { it.trim() }.filter { it.isNotBlank() }
    }

    private fun splitDrawableClauses(text: String): List<String> {
        val markers = listOf(
            "線", "点", "円", "楕円", "四角", "三角", "多角形", "五角", "六角", "弧", "塗りつぶす", "散らす", "並べる",
            "膜", "霞", "霧", "靄", "気配", "余韻", "反射", "映り", "消え", "滲",
            "光", "陽光", "日差し", "香", "匂", "蕾", "つぼみ", "開花", "五感", "温",
            "line", "dot", "circle", "ellipse", "square", "triangle", "polygon", "arc", "scatter", "fill",
            "membrane", "haze", "fog", "mist", "trace", "reflection", "fade", "fading", "blur",
            "light", "sunlight", "scent", "fragrance", "bud", "bloom", "sense", "warm",
        )
        return splitClauses(text).filter { clause ->
            !clause.startsWith("背景") &&
                !clause.lowercase().startsWith("background") &&
                markers.any { it in clause }
        }
    }

    private fun primitiveFromClause(clause: String): String? = when {
        clause.containsAny("弧", "三日月", "半円", "上弦", "下弦", "波紋", "渦", "螺旋", "巻") -> "arc"
        clause.containsAny("楕円", "花びら", "蕾", "香り", "膜", "光") -> "ellipse"
        clause.containsAny("円", "丸", "月") -> "circle"
        clause.containsAny("三角", "山", "屋根", "尖", "鋭", "峰", "頂", "稜線", "切妻") -> "triangle"
        clause.containsAny("四角", "紙片", "破片", "折", "畳", "手紙", "格子", "街", "建物") -> "square"
        clause.containsAny("多角", "五角", "六角", "結晶", "鉱物", "硬い欠片", "硬い破片") -> "polygon"
        clause.containsAny("線", "雨", "雪", "砂", "点", "粒", "星") -> "line"
        else -> null
    }

    private fun coverageInstruction(clause: String, primitive: String, background: String): JSONObject {
        val color = _colorFromClause(clause, background)
        val weight = detectWeightKey(clause)
        val base = JSONObject()
            .put("primitive", primitive)
            .put("color", color)
            .put("weight", weight)
            .put("style", if (clause.contains("破線")) "dashed" else if (clause.contains("点線")) "dotted" else "solid")
            .put("filled", clause.contains("塗") && primitive != "line")
            .put("color_hint", "coverage from DDL clause: ${clause.take(48)}")
        when (primitive) {
            "line" -> base.put("from", JSONArray(listOf(0.18, 0.72))).put("to", JSONArray(listOf(0.82, 0.28)))
            "circle" -> base.put("center", focusPoint(clause)).put("radius", detectRadius(clause) ?: 0.10)
            "ellipse" -> base.put("center", focusPoint(clause)).put("size", JSONArray(listOf(0.18, 0.10))).put("rotation", -18)
            "arc" -> base.put("center", focusPoint(clause)).put("radius", detectRadius(clause) ?: 0.13).put("angle_start", 210).put("angle_end", 330)
            "polygon" -> base.put("center", focusPoint(clause)).put("radius", 0.10).put("sides", 6).put("rotation", 18)
            "square", "triangle" -> base.put("position", JSONArray(listOf(0.62, 0.30))).put("size", JSONArray(listOf(0.16, 0.12))).put("rotation", -12)
        }
        arrangementFrom(clause)?.let { base.put("arrangement", it) }
        return coerceInstruction(base, clause, background)
    }

    private fun requestedColors(text: String): List<String> {
        val result = mutableListOf<String>()
        val lower = text.lowercase()
        listOf("red" to listOf("赤", "red"), "blue" to listOf("青", "blue"), "green" to listOf("緑", "green"), "white" to listOf("白", "white"), "black" to listOf("黒", "black"), "gray" to listOf("灰", "gray", "grey")).forEach { (color, markers) ->
            if (markers.any { it in text || it in lower }) result += color
        }
        if (listOf("森", "forest", "leaf", "草", "grass", "苔", "moss", "竹", "bamboo", "庭", "garden", "香り", "scent", "fragrance", "芽", "落ち葉", "若葉", "木の葉", "葉っぱ", "葉脈")
                .any { it in text || it in lower }
        ) {
            result += "green"
        }
        if ((text.contains("色とりどり") || text.contains("多色") || lower.contains("colorful")) && result.size < 3) {
            result += listOf("red", "blue", "green", "black", "gray")
        }
        return result.distinct()
    }

    private fun _colorFromClause(clause: String, background: String): String {
        return requestedColors(clause).firstOrNull { it != background } ?: visibleForeground(detectColorKey(clause, background), background)
    }

    private fun colorMatchesClause(item: JSONObject, clause: String, background: String): Boolean {
        val colors = requestedColors(clause).filter { it != background }
        if (colors.isEmpty()) return true
        val itemColor = item.optString("color", "black")
        val cycle = item.optJSONObject("arrangement")?.optJSONArray("color_cycle")
        return itemColor in colors || (cycle != null && (0 until cycle.length()).any { cycle.optString(it) in colors })
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
        val primitive = item.optString("primitive", "line")
        return when (primitive) {
            "circle", "arc", "polygon" -> item.optDouble("radius", 0.0) * 2.0
            "ellipse", "square", "triangle" -> {
                val size = item.optJSONArray("size")
                maxOf(size?.optDouble(0, 0.0) ?: 0.0, size?.optDouble(1, 0.0) ?: 0.0)
            }
            else -> 0.0
        }
    }

    private fun compositionAccentColor(ddl: String, background: String, existing: Set<String>): String? {
        requestedColors(ddl).firstOrNull { it !in existing && it != background }?.let { return it }
        if (existing.isNotEmpty() && existing.any { it !in setOf("black", "gray") }) return null
        val lower = ddl.lowercase()
        if (ddl.containsAny("祭", "火", "灯", "温", "赤") || listOf("warm", "fire", "light").any { it in lower }) {
            return if (background != "red") "red" else "white"
        }
        if (ddl.containsAny("水", "夜", "湖", "冷", "青") || listOf("water", "night", "cold").any { it in lower }) {
            return if (background != "blue") "blue" else "white"
        }
        if (ddl.containsAny("森", "草", "苔", "庭", "竹") || listOf("green", "forest", "grass").any { it in lower }) {
            return if (background != "green") "green" else "white"
        }
        return null
    }

    private fun requestedShapes(ddl: String): Set<String> {
        val lower = ddl.lowercase()
        val shapes = linkedSetOf<String>()
        val markers = listOf(
            listOf("多角形", "五角", "六角", "結晶", "鉱物", "硬い欠片", "硬い破片", "polygon", "crystal", "mineral", "hard shard") to "polygon",
            listOf("山", "屋根", "尖", "鋭", "三角", "峰", "頂", "稜線", "切妻", "mountain", "roof", "sharp", "peak", "ridge", "triangle") to "triangle",
            listOf("弧", "渦", "螺旋", "波紋", "巻", "arc", "spiral", "coil", "curl", "ripple") to "arc",
            listOf("紙片", "破片", "折", "畳", "四角", "paper", "fragment", "fold", "shard", "square") to "square",
        )
        for ((terms, primitive) in markers) {
            if (terms.any { it in ddl || it.lowercase() in lower }) shapes += primitive
        }
        return shapes
    }

    private fun shapeRepairInstruction(primitive: String, index: Int, background: String): JSONObject {
        val offset = minOf(index, 3) * 0.08
        val item = JSONObject()
            .put("primitive", primitive)
            .put("color", visibleForeground("black", background))
            .put("weight", "brush_thin")
            .put("color_hint", "$primitive restored from DDL shape intent")
        when (primitive) {
            "triangle" -> item
                .put("position", JSONArray(listOf(0.58 - offset, 0.22 + offset)))
                .put("size", JSONArray(listOf(0.18, 0.16)))
                .put("rotation", -18 + index * 11)
            "polygon" -> item
                .put("center", JSONArray(listOf(0.62 - offset, 0.34 + offset)))
                .put("radius", 0.06)
                .put("sides", 6)
                .put("rotation", -18 + index * 13)
            "arc" -> item
                .put("center", JSONArray(listOf(0.66 - offset, 0.34 + offset)))
                .put("radius", 0.13)
                .put("angle_start", 205)
                .put("angle_end", 25)
                .put("rotation", -10 + index * 9)
            else -> item
                .put("position", JSONArray(listOf(0.56 - offset, 0.30 + offset)))
                .put("size", JSONArray(listOf(0.16, 0.11)))
                .put("rotation", -25 + index * 13)
        }
        return item
    }

    private fun requestedMotifs(ddl: String): List<String> {
        val lower = ddl.lowercase()
        val motifs = mutableListOf<String>()
        val markers = listOf(
            listOf("落ち葉", "若葉", "木の葉", "葉っぱ", "葉脈", "leaf", "leaves") to "leaf_cluster",
            listOf("紙片", "破片", "折", "手紙", "paper", "fragment", "shard", "letter") to "paper_shard",
            listOf("波紋", "渦", "螺旋", "巻", "ripple", "spiral", "coil") to "ripple_knot",
            listOf("山", "屋根", "峰", "稜線", "切妻", "mountain", "roof", "ridge", "peak") to "mountain_sign",
        )
        for ((terms, motif) in markers) {
            if (terms.any { it in ddl || it.lowercase() in lower }) motifs += motif
        }
        return motifs
    }

    private fun motifRepairInstructions(motif: String, index: Int, background: String): List<JSONObject> {
        val color = visibleForeground("black", background)
        val offset = minOf(index, 2) * 0.08
        return when (motif) {
            "leaf_cluster" -> listOf(
                JSONObject()
                    .put("primitive", "ellipse")
                    .put("center", JSONArray(listOf(0.38 + offset, 0.44)))
                    .put("size", JSONArray(listOf(0.13, 0.035)))
                    .put("rotation", -28)
                    .put("color", if (background != "green") "green" else "white")
                    .put("color_hint", "leaf_cluster motif restored from DDL intent"),
                JSONObject()
                    .put("primitive", "arc")
                    .put("center", JSONArray(listOf(0.40 + offset, 0.44)))
                    .put("radius", 0.08)
                    .put("angle_start", 200)
                    .put("angle_end", 335)
                    .put("rotation", -24)
                    .put("color", color)
                    .put("weight", "brush_thin")
                    .put("color_hint", "leaf_cluster motif restored from DDL intent"),
            )
            "paper_shard" -> listOf(
                JSONObject()
                    .put("primitive", "square")
                    .put("position", JSONArray(listOf(0.56 - offset, 0.36 + offset)))
                    .put("size", JSONArray(listOf(0.13, 0.09)))
                    .put("rotation", -24)
                    .put("color", color)
                    .put("color_hint", "paper_shard motif restored from DDL intent"),
                JSONObject()
                    .put("primitive", "line")
                    .put("from", JSONArray(listOf(0.55 - offset, 0.43 + offset)))
                    .put("to", JSONArray(listOf(0.70 - offset, 0.37 + offset)))
                    .put("color", color)
                    .put("weight", "hair")
                    .put("color_hint", "paper_shard motif restored from DDL intent"),
            )
            "ripple_knot" -> listOf(
                JSONObject()
                    .put("primitive", "arc")
                    .put("center", JSONArray(listOf(0.62 - offset, 0.58)))
                    .put("radius", 0.10)
                    .put("angle_start", 25)
                    .put("angle_end", 210)
                    .put("color", if (background != "blue") "blue" else "white")
                    .put("color_hint", "ripple_knot motif restored from DDL intent"),
                JSONObject()
                    .put("primitive", "ellipse")
                    .put("center", JSONArray(listOf(0.62 - offset, 0.58)))
                    .put("size", JSONArray(listOf(0.055, 0.025)))
                    .put("rotation", 18)
                    .put("color", color)
                    .put("color_hint", "ripple_knot motif restored from DDL intent"),
            )
            else -> listOf(
                JSONObject()
                    .put("primitive", "triangle")
                    .put("position", JSONArray(listOf(0.50 - offset, 0.27 + offset)))
                    .put("size", JSONArray(listOf(0.18, 0.15)))
                    .put("rotation", -12)
                    .put("color", color)
                    .put("color_hint", "mountain_sign motif restored from DDL intent"),
                JSONObject()
                    .put("primitive", "line")
                    .put("from", JSONArray(listOf(0.59 - offset, 0.25 + offset)))
                    .put("to", JSONArray(listOf(0.59 - offset, 0.45 + offset)))
                    .put("color", color)
                    .put("weight", "hair")
                    .put("color_hint", "mountain_sign motif restored from DDL intent"),
            )
        }
    }

    private fun compositionRepairSuppressed(ddl: String): Boolean {
        val lower = ddl.lowercase()
        return listOf("余白", "静か", "薄い", "一つ", "ひとつ", "だけ", "少しだけ", "quiet", "minimal", "single", "only", "negative space")
            .any { it in ddl || it in lower }
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
        val lower = ddl.lowercase()
        return markers.any { it in ddl || it.lowercase() in lower }
    }

    private fun contextHasDensityGovernor(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf(
                "静か", "静けさ", "沈黙", "余白", "薄い", "薄く", "細い", "少しだけ", "一つ", "一滴",
                "気配", "余韻", "記憶", "忘れ", "影", "冷たい", "透明", "膜", "霞", "霧", "靄", "滲",
                "低い雲", "押し沈", "quiet", "silence", "negative space", "thin", "pale", "slight", "single",
                "one ", "presence", "trace", "memory", "forgotten", "shadow", "cold", "transparent", "membrane",
                "haze", "fog", "mist", "blur", "low cloud", "pressing down",
            ),
        )
    }

    private fun contextHasVerticalDensity(ddl: String): Boolean {
        return contextHasMarker(ddl, listOf("雨", "雪", "降", "縦", "上から下", "rain", "snow", "falling", "vertical", "top to bottom"))
    }

    private fun contextHasMotion(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf(
                "渡る", "揺", "流れ", "消え", "ほどけ", "伸び", "回", "丸ま", "帰って", "風", "波", "ためらう",
                "moving", "sway", "flow", "fade", "dissolve", "stretch", "turn", "wind", "wave",
            ),
        )
    }

    private fun contextHasColorfulAccent(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf("祭", "色紙", "果実", "ネオン", "夕焼け", "赤", "青", "緑", "色とりどり", "多色", "festival", "colored paper", "fruit", "neon", "sunset", "colorful", "multi-color"),
        )
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
        return when (item.optString("primitive")) {
            "circle", "polygon" -> {
                val radius = item.optDouble("radius", 0.0)
                PI * radius * radius
            }
            "arc" -> {
                val radius = item.optDouble("radius", 0.0)
                PI * radius * radius * 0.35
            }
            "ellipse" -> {
                val size = item.optJSONArray("size")
                val width = size?.optDouble(0, 0.0) ?: 0.0
                val height = size?.optDouble(1, 0.0) ?: 0.0
                PI * (width / 2.0) * (height / 2.0)
            }
            "square" -> {
                val size = item.optJSONArray("size")
                (size?.optDouble(0, 0.0) ?: 0.0) * (size?.optDouble(1, 0.0) ?: 0.0)
            }
            "triangle" -> {
                val size = item.optJSONArray("size")
                (size?.optDouble(0, 0.0) ?: 0.0) * (size?.optDouble(1, 0.0) ?: 0.0) * 0.5
            }
            else -> 0.0
        }
    }

    private fun closedShapeGeometryKey(item: JSONObject): String? {
        fun roundedArray(value: JSONArray?): List<Double>? {
            if (value == null || value.length() < 2) return null
            return listOf(round2(value.optDouble(0, 0.0)), round2(value.optDouble(1, 0.0)))
        }
        return when (item.optString("primitive")) {
            "circle", "arc" -> {
                val center = roundedArray(item.optJSONArray("center")) ?: return null
                listOf(item.optString("primitive"), center[0], center[1], round2(item.optDouble("radius", 0.10))).joinToString("|")
            }
            "ellipse", "square", "triangle" -> {
                val center = roundedArray(item.optJSONArray("center") ?: item.optJSONArray("position")) ?: return null
                val size = roundedArray(item.optJSONArray("size")) ?: return null
                listOf(item.optString("primitive"), center[0], center[1], size[0], size[1], round2(item.optDouble("rotation", 0.0))).joinToString("|")
            }
            "polygon" -> {
                val center = roundedArray(item.optJSONArray("center")) ?: return null
                listOf("polygon", center[0], center[1], round2(item.optDouble("radius", 0.10)), item.optInt("sides", 5)).joinToString("|")
            }
            else -> null
        }
    }

    private fun isAtmosphericEffectHint(hint: String): Boolean {
        if (hint.isBlank()) return false
        val lower = hint.lowercase()
        return listOf(
            "membrane", "haze", "fog", "mist", "atmosphere", "膜", "霞", "霧", "靄",
            "soft light", "柔らかな光", "陽光", "日差し", "scent", "fragrance", "香り", "匂",
            "five-sense", "五感", "reflection", "反射", "映り",
        ).any { it in hint || it.lowercase() in lower }
    }

    private fun isPlainMaterialHint(hint: String): Boolean {
        if (hint.isBlank()) return true
        val lower = hint.lowercase()
        return "material inferred from ddl" in lower && !isAtmosphericEffectHint(hint)
    }

    private fun round2(value: Double): Double = kotlin.math.round(value * 100.0) / 100.0

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
        val requested = when {
            contextHasColorfulAccent(ddl) && background != "red" -> "red"
            background != "green" -> "green"
            else -> "blue"
        }
        val color = visibleForeground(requested, background)
        return if (contextHasMotion(ddl)) {
            JSONObject()
                .put("primitive", "arc")
                .put("center", JSONArray(listOf(0.68, 0.34)))
                .put("radius", 0.12)
                .put("angle_start", 205)
                .put("angle_end", 325)
                .put("color", color)
                .put("weight", "hair")
                .put("color_hint", "quiet expression accent restored after density governance")
                .put(
                    "arrangement",
                    JSONObject()
                        .put("count", 3)
                        .put("layout", "radial")
                        .put("margin", 0.24)
                        .put("density", "low")
                        .put("fade", "outward")
                        .put("preserve_space", true),
                )
        } else {
            JSONObject()
                .put("primitive", "ellipse")
                .put("center", JSONArray(listOf(0.67, 0.35)))
                .put("size", JSONArray(listOf(0.055, 0.026)))
                .put("rotation", -18)
                .put("color", color)
                .put("weight", "pencil")
                .put("filled", true)
                .put("color_hint", "quiet expression accent restored after density governance")
        }
    }

    private fun appendHint(existing: String?, note: String): String {
        val clean = existing?.takeIf { it.isNotBlank() }
        return if (clean == null) note else "$clean; $note"
    }

    private fun presenceFromDdl(ddl: String): JSONObject? {
        val hasHuman = ddl.containsAny("人", "人物", "人影", "人型", "顔", "表情", "視線", "まなざし", "眼差し", "目線", "誰か", "群衆", "老漁師", "息子") ||
            ddl.containsAnyIgnoreCase("human", "person", "people", "figure", "face", "gaze", "look", "crowd")
        val hasCreature = ddl.containsAny("動物", "獣", "鳥", "魚", "犬", "猫", "馬", "鹿", "群れ", "羽", "翼", "尾", "尻尾", "海鳥") ||
            ddl.containsAnyIgnoreCase("animal", "creature", "bird", "fish", "dog", "cat", "horse", "deer", "flock", "herd", "tail", "wing")
        if (!hasHuman && !hasCreature) return null
        val hasGroup = ddl.containsAny("群れ", "群衆", "複数", "集ま", "並ぶ") || ddl.containsAnyIgnoreCase("crowd", "group", "flock", "herd", "many figures")
        val hasGaze = ddl.containsAny("顔", "視線", "まなざし", "眼差し", "目線", "見つめ") || ddl.containsAnyIgnoreCase("face", "gaze", "look", "stare")
        val kind = when {
            hasGroup -> "group_like"
            hasCreature && !hasHuman -> "creature_like"
            else -> "figure_like"
        }
        val intensity = when {
            ddl.containsAny("強い", "圧力", "濃い") || ddl.containsAnyIgnoreCase("strong", "pressure", "dense") -> "high"
            hasGaze || hasGroup -> "medium"
            else -> "low"
        }
        val contourDensity = when {
            hasGroup -> "high"
            hasCreature || hasGaze -> "medium"
            else -> "low"
        }
        val presence = JSONObject()
            .put("kind", kind)
            .put("intensity", intensity)
            .put("symmetry", if (ddl.containsAny("人型", "顔", "正面", "対称") || ddl.containsAnyIgnoreCase("figure", "face", "frontal", "symmetry")) "bilateral" else "none")
            .put("gaze_pressure", if (hasGaze) "medium" else "none")
            .put("contour_density", contourDensity)
        presenceCenterFromContext(ddl)?.let { presence.put("center", it) }
        return presence
    }

    private fun presenceCenterFromContext(context: String): JSONArray? {
        return when {
            context.contains("右上") || context.contains("upper right", ignoreCase = true) -> JSONArray(listOf(0.68, 0.34))
            context.contains("左上") || context.contains("upper left", ignoreCase = true) -> JSONArray(listOf(0.32, 0.34))
            context.contains("右下") || context.contains("lower right", ignoreCase = true) -> JSONArray(listOf(0.68, 0.66))
            context.contains("左下") || context.contains("lower left", ignoreCase = true) -> JSONArray(listOf(0.32, 0.66))
            context.contains("右半分") || context.contains("right half", ignoreCase = true) -> JSONArray(listOf(0.68, 0.50))
            context.contains("左半分") || context.contains("left half", ignoreCase = true) -> JSONArray(listOf(0.32, 0.50))
            else -> null
        }
    }

    private fun detectBackground(text: String): String {
        val lower = text.lowercase()
        return when {
            text.contains("背景を黒") || lower.contains("fill background with black") -> "black"
            text.contains("背景を赤") || lower.contains("fill background with red") -> "red"
            text.contains("背景を青") || lower.contains("fill background with blue") -> "blue"
            text.contains("背景を緑") || lower.contains("fill background with green") -> "green"
            text.contains("夜") || text.contains("暗") -> "black"
            else -> "white"
        }
    }

    private fun detectColorKey(text: String, background: String): String {
        val lower = text.lowercase()
        return when {
            (text.contains("白") || lower.contains("white")) && background != "white" -> "white"
            (text.contains("青") || lower.contains("blue")) && background != "blue" -> "blue"
            (text.contains("赤") || lower.contains("red")) && background != "red" -> "red"
            (text.contains("緑") || lower.contains("green")) && background != "green" -> "green"
            listOf("森", "forest", "leaf", "草", "grass", "苔", "moss", "竹", "bamboo", "庭", "garden", "香り", "scent", "fragrance", "芽", "落ち葉", "若葉", "木の葉", "葉っぱ", "葉脈")
                .any { it in text || it in lower } && background != "green" -> "green"
            text.contains("灰") || lower.contains("gray") || lower.contains("grey") -> "gray"
            else -> if (background in setOf("black", "blue")) "white" else "black"
        }
    }

    private fun detectWeightKey(text: String): String = when {
        text.contains("ロットリング") || text.contains("rotring", ignoreCase = true) -> "rotring"
        text.contains("鉛筆") || text.contains("pencil", ignoreCase = true) -> "pencil"
        text.contains("クレヨン") || text.contains("crayon", ignoreCase = true) -> "crayon"
        text.contains("チョーク") || text.contains("chalk", ignoreCase = true) -> "chalk"
        text.contains("太筆") || text.contains("厚塗り") || text.contains("thick brush", ignoreCase = true) -> "brush_thick"
        text.contains("細筆") || text.contains("水墨") || text.contains("墨") || text.contains("fine brush", ignoreCase = true) -> "brush_thin"
        text.contains("縄") || text.contains("rope", ignoreCase = true) -> "rope"
        else -> "pen"
    }

    private fun detectLayoutKey(text: String): String = when {
        text.contains("縦") || text.contains("上から下") -> "vertical"
        text.contains("散ら") || text.contains("点々") || text.contains("scatter", ignoreCase = true) -> "scatter"
        text.contains("円環") || text.contains("放射") || text.contains("同心円") -> "radial"
        else -> "horizontal"
    }

    private fun detectColorCycle(text: String, foreground: String): List<String> {
        val lower = text.lowercase()
        val cycle = when {
            text.containsAny("色とりどり", "多色", "赤・青", "赤、青") || lower.contains("colorful") || lower.contains("multi-color") ->
                listOf("red", "blue", "green", "gray")
            text.containsAny("春", "花", "蕾", "桜", "温", "陽光") || lower.contains("spring") || lower.contains("flower") ->
                listOf("red", "green", "white")
            text.containsAny("夜", "月", "水", "雨", "霧", "冷") || lower.contains("night") || lower.contains("moon") || lower.contains("water") ->
                listOf("blue", "white", "gray")
            else -> emptyList()
        }
        return if (cycle.isEmpty() && foreground != "black") listOf(foreground) else cycle
    }

    private fun addVariationHint(instruction: JSONObject, text: String) {
        val variation = when {
            text.containsAny("ゆっくり揺れる", "ゆっくり波打つ") || text.contains("slow", ignoreCase = true) ->
                JSONObject().put("amplitude", "medium").put("frequency", "slow").put("quality", "wave").put("dimensions", JSONArray(listOf("position_x", "position_y")))
            text.containsAny("細かく揺れる", "細かく震える", "震える") ->
                JSONObject().put("amplitude", "fine").put("frequency", "medium").put("quality", "perlin").put("dimensions", JSONArray(listOf("position_y")))
            text.containsAny("滲む", "にじむ", "境界が滲む") ->
                JSONObject().put("amplitude", "medium").put("frequency", "medium").put("quality", "pink").put("dimensions", JSONArray(listOf("position_x", "position_y")))
            else -> null
        }
        if (variation != null) instruction.put("variation", variation)
    }

    private fun focusPoint(text: String): JSONArray = when {
        text.contains("右上の黄金比") -> JSONArray(listOf(0.618, 0.382))
        text.contains("左上の三分割") -> JSONArray(listOf(0.333, 0.333))
        text.contains("左下の白銀比") -> JSONArray(listOf(0.414, 0.586))
        text.contains("右上") -> JSONArray(listOf(0.72, 0.28))
        text.contains("左上") -> JSONArray(listOf(0.28, 0.28))
        text.contains("右下") -> JSONArray(listOf(0.72, 0.72))
        text.contains("左下") -> JSONArray(listOf(0.28, 0.72))
        text.contains("上端") -> JSONArray(listOf(0.5, 0.18))
        text.contains("右半分") -> JSONArray(listOf(0.72, 0.5))
        else -> JSONArray(listOf(0.5, 0.5))
    }

    private fun countHintFromDdl(text: String): Int? {
        Regex("""\d+""").find(text)?.value?.toIntOrNull()?.let { return it }
        return listOf(
            "千" to 1000, "六百十" to 610, "三百" to 300, "百三十七" to 137, "百二十" to 120,
            "三十四" to 34, "三十" to 30, "二十一" to 21, "二十" to 20, "十六" to 16,
            "十二" to 12, "十一" to 11, "十" to 10, "八" to 8, "七" to 7, "六" to 6,
            "五" to 5, "四" to 4, "三" to 3, "二" to 2, "一" to 1,
        ).firstOrNull { (marker, _) -> text.contains(marker) }?.second
    }

    private fun vagueCount(text: String): Int = when {
        text.containsAny("無数", "満天", "砂", "雨", "雪") -> 110
        text.containsAny("たくさん", "密集", "埋め") -> 80
        text.containsAny("点々", "散ら") -> 12
        else -> 3
    }

    private fun detectRadius(text: String): Double? {
        val match = Regex("""半径(?:は)?([0-9]+(?:\.[0-9]+)?)""").find(text) ?: return null
        return match.groupValues[1].toDoubleOrNull()?.coerceIn(0.005, 0.5)
    }

    private fun hasDrawableVocabulary(text: String): Boolean {
        return text.containsAny("線", "円", "楕円", "弧", "四角", "三角", "多角", "点", "粒", "背景", "塗", "散ら", "並べ", "膜", "光", "香り", "雨", "雪", "月", "山", "紙片", "波")
    }

    private fun ensurePlacement(text: String): String {
        val trimmed = text.trim().trimEnd('。')
        val hasPlacement = trimmed.containsAny("中央", "右上", "左上", "右下", "左下", "上から下", "左から右", "横に", "縦に", "散ら", "点々", "画面全体", "波打つ軌跡", "斜め", "放射", "円環", "同心円", "焦点")
        return if (hasPlacement) "$trimmed。" else "$trimmed。中央付近に置く。"
    }

    private fun sanitizePlacementWords(text: String): String {
        return WebDdlSpec.sanitizePlacementWords(text)
    }

    private fun String.cleanModelText(): String {
        return trim()
            .trim('`')
            .replace("<|turn>model", "", ignoreCase = true)
            .replace("<|turn>user", "", ignoreCase = true)
            .replace("<turn|>", "", ignoreCase = true)
            .replace(Regex("""<\|[^>]+>"""), "")
            .replace(Regex("""\n{3,}"""), "\n\n")
            .trim()
    }

    private fun String.normalizeStage1DdlText(): String {
        val cleaned = replace(Regex("""(?i)^\s*(出力|output)\s*[:：]\s*"""), "")
            .replace(Regex("""(?i)\s*(入力|input)\s*[:：].*$"""), "")
            .trim()
        val hasJapanese = cleaned.any { it in '\u3040'..'\u30ff' || it in '\u4e00'..'\u9fff' }
        val collapsed = if (hasJapanese) {
            cleaned.replace(Regex("""[ \t]*\n+[ \t]*"""), "")
        } else {
            cleaned.replace(Regex("""[ \t]*\n+[ \t]*"""), " ")
        }
        return collapsed
            .replace(Regex("""[ \t]{2,}"""), " ")
            .replace(Regex("""。{2,}"""), "。")
            .replace(Regex("""、{2,}"""), "、")
            .normalizeDdlNumberNoise()
            .dedupeDdlClauses()
            .trim()
    }

    private fun String.normalizeDdlNumberNoise(): String {
        return replace(Regex("""([一二三四五六七八九十百]+本)数を\1並べる"""), "$1並べる")
            .replace(Regex("""([一二三四五六七八九十百]+個)数を\1並べる"""), "$1並べる")
            .replace(Regex("""([一二三四五六七八九十百]+点)数を\1散らす"""), "$1散らす")
    }

    private fun String.dedupeDdlClauses(): String {
        val clauses = splitClauses(this)
        if (clauses.isEmpty()) return this
        val seen = mutableSetOf<String>()
        return clauses.filter { clause ->
            val key = clause.trim().trimEnd('。')
            seen.add(key)
        }.joinToString("") { if (it.endsWith("。")) it else "$it。" }
    }

    private fun String.isUsableStage1Ddl(): Boolean {
        if (isBlank()) return false
        if (contains("SELECT ", ignoreCase = true) || contains("```")) return false
        if (contains("FROM ", ignoreCase = true) && contains("WHERE ", ignoreCase = true)) return false
        return hasDrawableVocabulary(this)
    }

    private fun visibleBackground(background: String): String = if (background == "gray") "white" else background

    private fun visibleForeground(color: String, background: String): String {
        return if (color == background) {
            if (background == "black" || background == "blue") "white" else "black"
        } else {
            color
        }
    }

    private fun validSize(value: JSONArray?): Boolean {
        return value != null && value.length() >= 2 && value.optDouble(0, -1.0) > 0.0 && value.optDouble(1, -1.0) > 0.0
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
