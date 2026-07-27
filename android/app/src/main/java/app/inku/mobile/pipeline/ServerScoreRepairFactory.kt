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

    fun primitiveFromClause(clause: String): String? {
        val lower = clause.lowercase()
        return when {
            "多角形" in clause || "五角" in clause || "六角" in clause || "polygon" in lower -> "polygon"
            "四角" in clause || "square" in lower || "rectangle" in lower -> "square"
            "三角" in clause || "triangle" in lower -> "triangle"
            "弧" in clause || "arc" in lower -> "arc"
            "円" in clause || "楕円" in clause || "circle" in lower || "ellipse" in lower -> "ellipse"
            else -> "line"
        }
    }

    fun coverageInstruction(
        clause: String,
        primitive: String,
        background: String,
        index: Int,
        coerceInstruction: (JSONObject, String, String) -> JSONObject,
    ): JSONObject {
        val lower = clause.lowercase()
        val sensoryKind = sensoryKind(clause)
        val effectivePrimitive = when {
            sensoryKind == "sense" -> "arc"
            sensoryKind != null -> "ellipse"
            isAtmosphericClause(clause) -> "ellipse"
            isReflectionClause(clause) -> "line"
            else -> primitive
        }
        val color = colorFromClause(clause, background)
        val baseWeight = ServerScoreSemantics.detectWeightKey(clause)
        val weight = if ((sensoryKind != null || isAtmosphericClause(clause)) && baseWeight == "pen") "chalk" else baseWeight
        val base = JSONObject()
            .put("primitive", effectivePrimitive)
            .put("color", color)
            .put("weight", weight)
            .put("style", ServerScoreSemantics.styleKey(clause))
            .put("color_hint", "coverage from DDL clause: ${clause.take(48)}")
        val offset = minOf(index, 4) * 0.09
        when (effectivePrimitive) {
            "line" -> base.put("from", JSONArray(listOf(0.16 + offset, 0.76 - offset))).put("to", JSONArray(listOf(0.78, 0.30 + offset))).put("rotation", -8 + index * 7)
            "arc" -> base.put("center", JSONArray(listOf(0.68 - offset / 2.0, 0.30 + offset))).put("radius", 0.11).put("angle_start", 210).put("angle_end", 330)
            "polygon" -> base.put("center", JSONArray(listOf(0.68 - offset / 2.0, 0.30 + offset))).put("radius", 0.055).put("sides", if ("六角" in clause || "hex" in lower || "mineral" in lower || "鉱物" in clause) 6 else 5).put("rotation", -18 + index * 9)
            "ellipse" -> base.put("center", JSONArray(listOf(0.68 - offset / 2.0, 0.30 + offset))).put("size", JSONArray(listOf(0.16, 0.09))).put("rotation", -18 + index * 9)
            else -> base.put("position", JSONArray(listOf(0.58 - offset / 2.0, 0.24 + offset))).put("size", JSONArray(listOf(0.14, 0.10))).put("rotation", -12 + index * 8)
        }
        val count = ServerScoreSemantics.countHintFromDdl(clause)
        val colorCycle = colorCycleFromClause(clause, background)
        when {
            count != null && ("散らす" in clause || "scatter" in lower) -> base.put("arrangement", JSONObject().put("count", minOf(count, 120)).put("layout", "scatter").put("margin", 0.18))
            count != null && ("並べる" in clause || "line up" in lower) -> base.put("arrangement", JSONObject().put("count", minOf(count, 80)).put("layout", "horizontal").put("margin", 0.1))
            sensoryKind == "light" -> base.put("filled", true).put("center", JSONArray(listOf(0.50, 0.22 + minOf(index, 2) * 0.04))).put("size", JSONArray(listOf(0.42, 0.12))).put("rotation", -6 + index * 4).put("color", if (background != "white") "white" else "blue").put("arrangement", lowArrangement("horizontal", "outward", 3, 0.24)).put("color_hint", "${base.optString("color_hint")}; soft light")
            sensoryKind == "scent" -> base.put("center", JSONArray(listOf(0.56, 0.54))).put("size", JSONArray(listOf(0.05, 0.024))).put("rotation", -18).put("color", if (background != "green") "green" else "white").put("arrangement", lowArrangement("scatter", "directional", 7, 0.24).put("path", "wave")).put("color_hint", "${base.optString("color_hint")}; scent layer")
            sensoryKind == "bud" -> base.put("center", JSONArray(listOf(0.70, 0.62))).put("size", JSONArray(listOf(0.055, 0.026))).put("rotation", -30).put("color", if (background != "red") "red" else "white").put("arrangement", JSONObject().put("count", 5).put("layout", "scatter").put("path", "diagonal").put("margin", 0.18)).put("color_hint", "${base.optString("color_hint")}; waiting buds")
            sensoryKind == "sense" -> base.put("center", JSONArray(listOf(0.34, 0.70))).put("radius", 0.14).put("angle_start", 205).put("angle_end", 335).put("color", if (background != "white") "white" else "blue").put("arrangement", lowArrangement("radial", "outward", 3, 0.22)).put("color_hint", "${base.optString("color_hint")}; five-sense presence")
            isAtmosphericClause(clause) -> base.put("arrangement", lowArrangement("scatter", "outward", 5, 0.24).put("cluster_count", 3)).put("filled", true).put("color_hint", "${base.optString("color_hint")}; membrane haze")
            isReflectionClause(clause) -> base.put("arrangement", lowArrangement("vertical", "directional", 9, 0.18).put("path", "wave")).put("color_hint", "${base.optString("color_hint")}; reflection")
            isFadingClause(clause) -> base.put("arrangement", lowArrangement("scatter", "directional", 7, 0.24).put("path", "diagonal")).put("color_hint", "${base.optString("color_hint")}; fading")
        }
        if (clause.contains("塗") && effectivePrimitive != "line" && !base.has("filled")) base.put("filled", true)
        if (colorCycle.isNotEmpty()) {
            val arrangement = base.optJSONObject("arrangement") ?: JSONObject().put("count", maxOf(colorCycle.size, 3)).put("layout", "scatter").put("margin", 0.18)
            arrangement.put("color_cycle", JSONArray(colorCycle))
            base.put("arrangement", arrangement)
        }
        return coerceInstruction(base, clause, background)
    }

    private fun lowArrangement(layout: String, fade: String, count: Int, margin: Double): JSONObject {
        return JSONObject()
            .put("count", count)
            .put("layout", layout)
            .put("margin", margin)
            .put("density", "low")
            .put("fade", fade)
            .put("preserve_space", true)
    }

    fun requestedColors(text: String): List<String> {
        val result = mutableListOf<String>()
        val lower = text.lowercase()
        val negated = negatedColors(text)
        listOf(
            "white" to listOf("白", "white"),
            "black" to listOf("黒", "black"),
            "blue" to listOf("青", "blue", "空", "sky", "水", "water", "湖", "lake", "海", "sea", "雨", "rain", "冷たい", "cold"),
            "red" to listOf("赤", "red"),
            "green" to listOf(
                "緑", "green", "森", "forest", "leaf", "草", "grass", "苔", "moss", "竹", "bamboo", "庭", "garden", "香り", "scent", "fragrance",
                "芽", "落ち葉", "若葉", "木の葉", "葉っぱ", "葉脈",
            ),
            "gray" to listOf("灰", "gray", "grey"),
        ).forEach { (color, markers) ->
            if (color in negated) return@forEach
            if (markers.any { it in text || it in lower }) result += color
        }
        if ((text.contains("色とりどり") || text.contains("多色") || lower.contains("colorful")) && result.size < 3) {
            result += listOf("red", "blue", "green", "black", "gray").filterNot { it in negated }
        }
        return result.distinct()
    }

    fun colorFromClause(clause: String, background: String): String {
        return requestedColors(clause).firstOrNull { it != background }
            ?: ServerScoreSemantics.visibleForeground(ServerScoreSemantics.detectColorKey(clause, background), background)
    }

    fun colorCycleFromClause(clause: String, background: String): List<String> {
        val colors = requestedColors(clause).filter { it != background }.toMutableList()
        val lower = clause.lowercase()
        if (("色とりどり" in clause || "多色" in clause || "colorful" in lower || "multi-color" in lower) && colors.size < 3) {
            colors += listOf("red", "blue", "green", "black", "gray").filter { it != background && it !in negatedColors(clause) }
        }
        return colors.distinct()
    }

    fun negatedColors(text: String): Set<String> {
        val lower = text.lowercase()
        val greenMarkers = listOf(
            "not green", "avoid green", "without green", "no green",
            "緑には寄せず", "緑に寄せず", "緑ではなく", "緑を避け", "緑を使わず", "緑なし",
        )
        return buildSet {
            if (greenMarkers.any { it in text || it in lower }) add("green")
        }
    }

    fun isAtmosphericClause(clause: String): Boolean {
        val lower = clause.lowercase()
        return listOf("膜", "霞", "霧", "靄", "気配", "余韻", "透明", "membrane", "haze", "fog", "mist", "atmosphere")
            .any { it in clause || it in lower }
    }

    fun isReflectionClause(clause: String): Boolean {
        val lower = clause.lowercase()
        return listOf("反射", "映り", "reflection", "reflected").any { it in clause || it in lower }
    }

    fun isFadingClause(clause: String): Boolean {
        val lower = clause.lowercase()
        return listOf("消え", "薄れ", "fade", "fading", "vanish", "dissolve").any { it in clause || it in lower }
    }

    fun sensoryKind(clause: String): String? {
        val lower = clause.lowercase()
        return when {
            listOf("光", "陽光", "日差し", "柔ら", "light", "sunlight", "soft").any { it in clause || it in lower } -> "light"
            listOf("香", "匂", "沈丁花", "scent", "fragrance").any { it in clause || it in lower } -> "scent"
            listOf("蕾", "つぼみ", "開花", "bud", "bloom").any { it in clause || it in lower } -> "bud"
            listOf("五感", "気配", "訪れ", "sense", "presence", "arrival").any { it in clause || it in lower } -> "sense"
            else -> null
        }
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
            listOf("山", "尖", "鋭", "三角", "峰", "頂", "稜線", "mountain", "sharp", "peak", "ridge", "triangle") to "triangle",
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
            listOf("山", "峰", "稜線", "mountain", "ridge", "peak") to "mountain_sign",
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
                JSONObject().put("primitive", "line").put("from", JSONArray(listOf(0.55 - offset, 0.43 + offset))).put("to", JSONArray(listOf(0.70 - offset, 0.37 + offset))).put("color", color).put("weight", "silverpoint").put("color_hint", "paper_shard motif restored from DDL intent"),
            )
            "ripple_knot" -> listOf(
                JSONObject().put("primitive", "arc").put("center", JSONArray(listOf(0.62 - offset, 0.58))).put("radius", 0.10).put("angle_start", 25).put("angle_end", 210).put("color", if (background != "blue") "blue" else "white").put("color_hint", "ripple_knot motif restored from DDL intent"),
                JSONObject().put("primitive", "ellipse").put("center", JSONArray(listOf(0.62 - offset, 0.58))).put("size", JSONArray(listOf(0.055, 0.025))).put("rotation", 18).put("color", color).put("color_hint", "ripple_knot motif restored from DDL intent"),
            )
            else -> listOf(
                JSONObject().put("primitive", "triangle").put("position", JSONArray(listOf(0.50 - offset, 0.27 + offset))).put("size", JSONArray(listOf(0.18, 0.15))).put("rotation", -12).put("color", color).put("color_hint", "mountain_sign motif restored from DDL intent"),
                JSONObject().put("primitive", "line").put("from", JSONArray(listOf(0.59 - offset, 0.25 + offset))).put("to", JSONArray(listOf(0.59 - offset, 0.45 + offset))).put("color", color).put("weight", "silverpoint").put("color_hint", "mountain_sign motif restored from DDL intent"),
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
