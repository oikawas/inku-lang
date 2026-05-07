package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject

internal object ServerScoreRepairFactory {
    fun splitDrawableClauses(text: String): List<String> {
        val markers = listOf(
            "線", "点", "円", "楕円", "四角", "三角", "多角形", "五角", "六角", "弧", "塗りつぶす", "散らす", "並べる",
            "膜", "霞", "霧", "靄", "気配", "余韻", "反射", "映り", "消え", "滲",
            "光", "陽光", "日差し", "香", "匂", "蕾", "つぼみ", "開花", "五感", "温",
            "line", "dot", "circle", "ellipse", "square", "triangle", "polygon", "arc", "scatter", "fill",
            "membrane", "haze", "fog", "mist", "trace", "reflection", "fade", "fading", "blur",
            "light", "sunlight", "scent", "fragrance", "bud", "bloom", "sense", "warm",
        )
        return ServerDdlText.splitClauses(text).filter { clause ->
            !clause.startsWith("背景") &&
                !clause.lowercase().startsWith("background") &&
                markers.any { it in clause }
        }
    }

    fun primitiveFromClause(clause: String): String? = when {
        clause.containsAny("弧", "三日月", "半円", "上弦", "下弦", "波紋", "渦", "螺旋", "巻") -> "arc"
        clause.containsAny("楕円", "花びら", "蕾", "香り", "膜", "光") -> "ellipse"
        clause.containsAny("円", "丸", "月") -> "circle"
        clause.containsAny("三角", "山", "屋根", "尖", "鋭", "峰", "頂", "稜線", "切妻") -> "triangle"
        clause.containsAny("四角", "紙片", "破片", "折", "畳", "手紙", "格子", "街", "建物") -> "square"
        clause.containsAny("多角", "五角", "六角", "結晶", "鉱物", "硬い欠片", "硬い破片") -> "polygon"
        clause.containsAny("線", "雨", "雪", "砂", "点", "粒", "星") -> "line"
        else -> null
    }

    fun coverageInstruction(
        clause: String,
        primitive: String,
        background: String,
        coerceInstruction: (JSONObject, String, String) -> JSONObject,
    ): JSONObject {
        val color = colorFromClause(clause, background)
        val weight = ServerScoreSemantics.detectWeightKey(clause)
        val base = JSONObject()
            .put("primitive", primitive)
            .put("color", color)
            .put("weight", weight)
            .put("style", if (clause.contains("破線")) "dashed" else if (clause.contains("点線")) "dotted" else "solid")
            .put("filled", clause.contains("塗") && primitive != "line")
            .put("color_hint", "coverage from DDL clause: ${clause.take(48)}")
        when (primitive) {
            "line" -> base.put("from", JSONArray(listOf(0.18, 0.72))).put("to", JSONArray(listOf(0.82, 0.28)))
            "circle" -> base.put("center", ServerScoreSemantics.focusPoint(clause)).put("radius", ServerScoreSemantics.detectRadius(clause) ?: 0.10)
            "ellipse" -> base.put("center", ServerScoreSemantics.focusPoint(clause)).put("size", JSONArray(listOf(0.18, 0.10))).put("rotation", -18)
            "arc" -> base.put("center", ServerScoreSemantics.focusPoint(clause)).put("radius", ServerScoreSemantics.detectRadius(clause) ?: 0.13).put("angle_start", 210).put("angle_end", 330)
            "polygon" -> base.put("center", ServerScoreSemantics.focusPoint(clause)).put("radius", 0.10).put("sides", 6).put("rotation", 18)
            "square", "triangle" -> base.put("position", JSONArray(listOf(0.62, 0.30))).put("size", JSONArray(listOf(0.16, 0.12))).put("rotation", -12)
        }
        ServerFallbackComposer.arrangementFrom(clause)?.let { base.put("arrangement", it) }
        return coerceInstruction(base, clause, background)
    }

    fun requestedColors(text: String): List<String> {
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

    fun colorFromClause(clause: String, background: String): String {
        return requestedColors(clause).firstOrNull { it != background }
            ?: ServerScoreSemantics.visibleForeground(ServerScoreSemantics.detectColorKey(clause, background), background)
    }

    fun colorMatchesClause(item: JSONObject, clause: String, background: String): Boolean {
        val colors = requestedColors(clause).filter { it != background }
        if (colors.isEmpty()) return true
        val itemColor = item.optString("color", "black")
        val cycle = item.optJSONObject("arrangement")?.optJSONArray("color_cycle")
        return itemColor in colors || (cycle != null && (0 until cycle.length()).any { cycle.optString(it) in colors })
    }

    fun shapeExtent(item: JSONObject): Double {
        return when (item.optString("primitive", "line")) {
            "circle", "arc", "polygon" -> item.optDouble("radius", 0.0) * 2.0
            "ellipse", "square", "triangle" -> {
                val size = item.optJSONArray("size")
                maxOf(size?.optDouble(0, 0.0) ?: 0.0, size?.optDouble(1, 0.0) ?: 0.0)
            }
            else -> 0.0
        }
    }

    fun compositionAccentColor(ddl: String, background: String, existing: Set<String>): String? {
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

    fun requestedShapes(ddl: String): Set<String> {
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

    fun shapeRepairInstruction(primitive: String, index: Int, background: String): JSONObject {
        val offset = minOf(index, 3) * 0.08
        val item = JSONObject()
            .put("primitive", primitive)
            .put("color", ServerScoreSemantics.visibleForeground("black", background))
            .put("weight", "brush_thin")
            .put("color_hint", "$primitive restored from DDL shape intent")
        when (primitive) {
            "triangle" -> item.put("position", JSONArray(listOf(0.58 - offset, 0.22 + offset))).put("size", JSONArray(listOf(0.18, 0.16))).put("rotation", -18 + index * 11)
            "polygon" -> item.put("center", JSONArray(listOf(0.62 - offset, 0.34 + offset))).put("radius", 0.06).put("sides", 6).put("rotation", -18 + index * 13)
            "arc" -> item.put("center", JSONArray(listOf(0.66 - offset, 0.34 + offset))).put("radius", 0.13).put("angle_start", 205).put("angle_end", 25).put("rotation", -10 + index * 9)
            else -> item.put("position", JSONArray(listOf(0.56 - offset, 0.30 + offset))).put("size", JSONArray(listOf(0.16, 0.11))).put("rotation", -25 + index * 13)
        }
        return item
    }

    fun requestedMotifs(ddl: String): List<String> {
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

    fun motifRepairInstructions(motif: String, index: Int, background: String): List<JSONObject> {
        val color = ServerScoreSemantics.visibleForeground("black", background)
        val offset = minOf(index, 2) * 0.08
        return when (motif) {
            "leaf_cluster" -> listOf(
                JSONObject().put("primitive", "ellipse").put("center", JSONArray(listOf(0.38 + offset, 0.44))).put("size", JSONArray(listOf(0.13, 0.035))).put("rotation", -28).put("color", if (background != "green") "green" else "white").put("color_hint", "leaf_cluster motif restored from DDL intent"),
                JSONObject().put("primitive", "arc").put("center", JSONArray(listOf(0.40 + offset, 0.44))).put("radius", 0.08).put("angle_start", 200).put("angle_end", 335).put("rotation", -24).put("color", color).put("weight", "brush_thin").put("color_hint", "leaf_cluster motif restored from DDL intent"),
            )
            "paper_shard" -> listOf(
                JSONObject().put("primitive", "square").put("position", JSONArray(listOf(0.56 - offset, 0.36 + offset))).put("size", JSONArray(listOf(0.13, 0.09))).put("rotation", -24).put("color", color).put("color_hint", "paper_shard motif restored from DDL intent"),
                JSONObject().put("primitive", "line").put("from", JSONArray(listOf(0.55 - offset, 0.43 + offset))).put("to", JSONArray(listOf(0.70 - offset, 0.37 + offset))).put("color", color).put("weight", "hair").put("color_hint", "paper_shard motif restored from DDL intent"),
            )
            "ripple_knot" -> listOf(
                JSONObject().put("primitive", "arc").put("center", JSONArray(listOf(0.62 - offset, 0.58))).put("radius", 0.10).put("angle_start", 25).put("angle_end", 210).put("color", if (background != "blue") "blue" else "white").put("color_hint", "ripple_knot motif restored from DDL intent"),
                JSONObject().put("primitive", "ellipse").put("center", JSONArray(listOf(0.62 - offset, 0.58))).put("size", JSONArray(listOf(0.055, 0.025))).put("rotation", 18).put("color", color).put("color_hint", "ripple_knot motif restored from DDL intent"),
            )
            else -> listOf(
                JSONObject().put("primitive", "triangle").put("position", JSONArray(listOf(0.50 - offset, 0.27 + offset))).put("size", JSONArray(listOf(0.18, 0.15))).put("rotation", -12).put("color", color).put("color_hint", "mountain_sign motif restored from DDL intent"),
                JSONObject().put("primitive", "line").put("from", JSONArray(listOf(0.59 - offset, 0.25 + offset))).put("to", JSONArray(listOf(0.59 - offset, 0.45 + offset))).put("color", color).put("weight", "hair").put("color_hint", "mountain_sign motif restored from DDL intent"),
            )
        }
    }

    fun compositionRepairSuppressed(ddl: String): Boolean {
        val lower = ddl.lowercase()
        return listOf("余白", "静か", "薄い", "一つ", "ひとつ", "だけ", "少しだけ", "quiet", "minimal", "single", "only", "negative space")
            .any { it in ddl || it in lower }
    }

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }
}
