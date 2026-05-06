package app.inku.mobile.pipeline

import android.util.Log
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.render.DefaultSvgRenderer
import java.security.MessageDigest
import java.util.UUID
import kotlin.math.min
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
        val normalizedDdl = generateStage1(request) ?: interpretText(request.description)
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
        val scoreJson = generateStage2(request, expandedDdl) ?: scoreFromWebRules(expandedDdl, request.originalText, request.canvasAspect).toString()
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
            val response = provider.generate(
                ModelRequest(
                    modelId = request.stage2Model,
                    prompt = "原文:\n${request.originalText}\n\n正規化DDL:\n$expandedDdl",
                    temperature = 0.0,
                    maxTokens = 1024,
                    systemInstruction = WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA,
                    tool = WebScoreTool.submitScore,
                ),
            ).text.cleanModelText()
            val score = runCatching {
                extractJsonObject(response)
            }.getOrElse { error ->
                if (request.stage2Model.isExplicitProviderModelId()) throw error
                if (!request.autoRepair) throw error
                Log.w(TAG, "Stage 2 returned invalid JSON; rebuilding renderable score from DDL.", error)
                scoreFromWebRules(expandedDdl, request.originalText, request.canvasAspect)
            }
            coerceScore(score, "${request.originalText}\n$expandedDdl", request.canvasAspect).toString()
        }.onFailure {
            if (request.stage2Model.isExplicitProviderModelId()) throw it
            Log.w(TAG, "Stage 2 provider failed; using deterministic fallback.", it)
        }.getOrNull()
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
        runCatching { return JSONObject(trimmed) }
        val start = trimmed.indexOf('{')
        val end = trimmed.lastIndexOf('}')
        if (start >= 0 && end > start) {
            return JSONObject(trimmed.substring(start, end + 1))
        }
        error("Stage2 did not return a JSON object.")
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
        val repaired = repairedItems
            .dedupeInstructions()
            .withDdlCoverage(ddl, background)
            .withColorDelivery(ddl, background)
            .withCompositionDiversity(ddl, background)
            .withContextEnergy(ddl, background)
            .withDensityBudget()
            .fold(JSONArray()) { array, item -> array.put(item); array }
        val result = JSONObject()
            .put("version", "0.1.0")
            .put("canvas", canvasAspect)
            .put("background", background)
            .put("instructions", repaired)
        val presence = score.optJSONObject("presence") ?: presenceFromDdl(ddl)
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
        val repaired = toMutableList()
        for (clause in splitClauses(ddl)) {
            if (!hasDrawableVocabulary(clause)) continue
            val primitive = primitiveFromClause(clause) ?: continue
            if (repaired.any { it.optString("primitive") == primitive && colorMatchesClause(it, clause, background) }) continue
            if (repaired.size >= 10) break
            repaired += coverageInstruction(clause, primitive, background)
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

    private fun List<JSONObject>.withCompositionDiversity(ddl: String, background: String): List<JSONObject> {
        if (size >= 3) return this
        val colors = map { it.optString("color", "black") }.toSet()
        val primitives = map { it.optString("primitive", "line") }.toSet()
        val result = toMutableList()
        val accent = requestedColors(ddl).firstOrNull { it != background && it !in colors }
        if (accent != null && result.size < 10) {
            result += JSONObject()
                .put("primitive", "ellipse")
                .put("center", JSONArray(listOf(0.72, 0.28)))
                .put("size", JSONArray(listOf(0.09, 0.045)))
                .put("rotation", -18)
                .put("color", accent)
                .put("weight", "pen")
                .put("color_hint", "composition accent restored for shape/color diversity")
        }
        if (primitives.size == 1 && result.size < 10 && (ddl.containsAny("光", "香", "気配", "余韻", "反射", "影") || result.size == 1)) {
            result += JSONObject()
                .put("primitive", "arc")
                .put("center", JSONArray(listOf(0.34, 0.66)))
                .put("radius", 0.12)
                .put("angle_start", 210)
                .put("angle_end", 330)
                .put("color", visibleForeground("gray", background))
                .put("weight", "pencil")
                .put("variation", JSONObject().put("amplitude", "fine").put("frequency", "medium").put("quality", "perlin").put("dimensions", JSONArray(listOf("position_x", "position_y"))))
                .put("color_hint", "composition anchor restored for shape diversity")
        }
        return result
    }

    private fun List<JSONObject>.withContextEnergy(ddl: String, background: String): List<JSONObject> {
        if (size >= 10) return this
        val result = toMutableList()
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

    private fun primitiveFromClause(clause: String): String? = when {
        clause.containsAny("弧", "三日月", "半円", "上弦", "下弦", "波紋") -> "arc"
        clause.containsAny("楕円", "花びら", "蕾", "香り", "膜", "光") -> "ellipse"
        clause.containsAny("円", "丸", "月") -> "circle"
        clause.containsAny("三角", "山", "峰") -> "triangle"
        clause.containsAny("四角", "紙片", "格子", "街", "建物") -> "square"
        clause.containsAny("多角", "五角", "六角", "結晶") -> "polygon"
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
            .trim()
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
