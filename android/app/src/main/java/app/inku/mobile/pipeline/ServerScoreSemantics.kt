package app.inku.mobile.pipeline

import kotlin.math.PI
import org.json.JSONArray
import org.json.JSONObject

internal object ServerScoreSemantics {
    fun contextHasMarker(ddl: String, markers: List<String>): Boolean {
        val lower = ddl.lowercase()
        return markers.any { it in ddl || it.lowercase() in lower }
    }

    fun contextHasDensityGovernor(ddl: String): Boolean {
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

    fun contextHasVerticalDensity(ddl: String): Boolean {
        return contextHasMarker(ddl, listOf("雨", "雪", "降", "縦", "上から下", "rain", "snow", "falling", "vertical", "top to bottom"))
    }

    fun contextHasMotion(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf(
                "渡る", "揺", "流れ", "消え", "ほどけ", "伸び", "回", "丸ま", "帰って", "先に帰", "風", "波", "ためらう",
                "低い雲", "押し沈", "影だけ", "滲", "涙", "震える", "一滴", "残る",
                "moving", "sway", "flow", "fade", "dissolve", "stretch", "turn", "wind", "wave",
                "goes home first", "returns first", "low cloud", "pressing down", "shadow only", "blur", "tear",
                "trembling", "single drop", "remain", "remains",
            ),
        )
    }

    fun contextHasColorfulAccent(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf("祭", "色紙", "果実", "ネオン", "夕焼け", "赤", "青", "緑", "色とりどり", "多色", "festival", "colored paper", "fruit", "neon", "sunset", "colorful", "multi-color"),
        )
    }

    fun contextHasNeonBlurDensity(ddl: String): Boolean {
        val sceneMarkers = listOf("夜", "ガラス", "ネオン", "night", "glass", "neon")
        val blurMarkers = listOf("涙", "滲", "にじ", "blur", "tear")
        return contextHasMarker(ddl, sceneMarkers) && contextHasMarker(ddl, blurMarkers)
    }

    fun contextHasRhythm(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf("リズム", "踊", "跳ね", "弾む", "反復", "交互", "楽しい", "楽しさ", "喜び", "祝祭", "明快", "rhythm", "dance", "bounce", "alternating", "playful", "joy", "celebration"),
        )
    }

    fun contextHasVisualEvent(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf(
                "衝突", "反転", "集中", "破裂", "弾け", "核", "一点", "転がる", "抜ける", "迷う", "消えかけ", "震える", "一滴", "先に帰", "丸ま",
                "低い雲", "押し沈", "影だけ", "滲", "涙", "白い息", "映", "反射", "灯台", "光だけ", "足跡", "輪郭", "ほどけ", "花びら", "ためらう",
                "collision", "burst", "focus", "turning point", "pop", "release", "wandering", "fading", "trembling", "single drop", "goes home first",
                "curling", "low cloud", "pressing down", "shadow only", "blur", "tear", "breath", "reflect", "reflection", "lighthouse", "only light", "footprint", "outline", "unravel", "petal",
            ),
        )
    }

    fun contextHasMaPressure(ddl: String): Boolean {
        return contextHasMarker(
            ddl,
            listOf("余白", "間", "空白", "気配", "押す", "避け", "離れ", "紙", "新聞", "手紙", "紙片", "風", "交差", "迷う", "漂う", "negative space", "ma", "empty space", "presence", "pull", "push", "avoid", "paper", "newspaper", "letter", "sheet", "wind", "crossing", "wander", "drift"),
        )
    }

    fun contextHasSurfaceTension(ddl: String): Boolean {
        return contextHasMarker(ddl, listOf("布", "果実", "重", "影", "沈む", "沈め", "cloth", "fabric", "fruit", "heavy", "weight", "shadow", "sink"))
    }

    fun closedShapeArea(item: JSONObject): Double {
        return when (item.optString("primitive")) {
            "circle", "polygon" -> {
                val radius = item.optDouble("radius", 0.0)
                PI * radius * radius
            }
            "arc" -> {
                val radius = item.optDouble("radius", 0.0)
                PI * radius * radius * 0.35
            }
            "ellipse", "cloudform" -> {
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

    fun closedShapeGeometryKey(item: JSONObject): String? {
        fun roundedArray(value: JSONArray?): List<Double>? {
            if (value == null || value.length() < 2) return null
            return listOf(round2(value.optDouble(0, 0.0)), round2(value.optDouble(1, 0.0)))
        }
        return when (item.optString("primitive")) {
            "circle", "arc" -> {
                val center = roundedArray(item.optJSONArray("center")) ?: return null
                listOf(item.optString("primitive"), center[0], center[1], round2(item.optDouble("radius", 0.10))).joinToString("|")
            }
            "ellipse", "square", "triangle", "cloudform" -> {
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

    fun isAtmosphericEffectHint(hint: String): Boolean {
        if (hint.isBlank()) return false
        val lower = hint.lowercase()
        return listOf(
            "membrane", "haze", "fog", "mist", "atmosphere", "膜", "霞", "霧", "靄",
            "soft light", "柔らかな光", "陽光", "日差し", "scent", "fragrance", "香り", "匂",
            "five-sense", "五感", "reflection", "反射", "映り",
        ).any { it in hint || it.lowercase() in lower }
    }

    fun isPlainMaterialHint(hint: String): Boolean {
        if (hint.isBlank()) return true
        val lower = hint.lowercase()
        return "material inferred from ddl" in lower && !isAtmosphericEffectHint(hint)
    }

    fun quietExpressionAccent(ddl: String, background: String, visibleForeground: (String, String) -> String): JSONObject {
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

    fun appendHint(existing: String?, note: String): String {
        val clean = existing?.takeIf { it.isNotBlank() }
        return if (clean == null) note else "$clean; $note"
    }

    fun presenceFromDdl(ddl: String): JSONObject? {
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

    fun presenceCenterFromContext(context: String): JSONArray? {
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

    fun detectBackground(text: String): String {
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

    fun detectColorKey(text: String, background: String): String {
        val lower = text.lowercase()
        val negatedGreen = listOf(
            "not green", "avoid green", "without green", "no green",
            "緑には寄せず", "緑に寄せず", "緑ではなく", "緑を避け", "緑を使わず", "緑なし",
        ).any { it in text || it in lower }
        return when {
            (text.contains("白") || lower.contains("white")) && background != "white" -> "white"
            (listOf("青", "空", "水", "湖", "海", "雨", "冷たい").any { it in text } || listOf("blue", "sky", "water", "lake", "sea", "rain", "cold").any { it in lower }) && background != "blue" -> "blue"
            (text.contains("赤") || lower.contains("red")) && background != "red" -> "red"
            !negatedGreen && (text.contains("緑") || lower.contains("green")) && background != "green" -> "green"
            listOf("森", "forest", "leaf", "草", "grass", "苔", "moss", "竹", "bamboo", "庭", "garden", "香り", "scent", "fragrance", "芽", "落ち葉", "若葉", "木の葉", "葉っぱ", "葉脈")
                .any { it in text || it in lower } && !negatedGreen && background != "green" -> "green"
            text.contains("灰") || lower.contains("gray") || lower.contains("grey") -> "gray"
            else -> if (background in setOf("black", "blue")) "white" else "black"
        }
    }

    fun detectWeightKey(text: String): String = when {
        text.contains("髪") || text.contains("ヘア") || text.contains("hair", ignoreCase = true) -> "hair"
        text.contains("ビュラン") || text.contains("burin", ignoreCase = true) -> "burin"
        text.contains("ドライポイント") || text.contains("drypoint", ignoreCase = true) -> "drypoint"
        text.contains("コンピュータ") || text.contains("コンピューター") || text.contains("computer", ignoreCase = true) -> "computer"
        text.contains("ロットリング") || text.contains("rotring", ignoreCase = true) -> "rotring"
        text.contains("鉛筆") || text.contains("pencil", ignoreCase = true) -> "pencil"
        text.contains("ペン") || text.contains("pen", ignoreCase = true) -> "pen"
        text.contains("クレヨン") || text.contains("crayon", ignoreCase = true) -> "crayon"
        text.contains("チョーク") || text.contains("chalk", ignoreCase = true) -> "chalk"
        text.contains("太筆") || text.contains("厚塗り") || text.contains("油絵") || text.contains("thick-brush", ignoreCase = true) || text.contains("thick brush", ignoreCase = true) || text.contains("oil impasto", ignoreCase = true) -> "brush_thick"
        text.contains("細筆") || text.contains("水墨") || text.contains("墨") || text.contains("fine-brush", ignoreCase = true) || text.contains("fine brush", ignoreCase = true) || text.contains("ink-wash", ignoreCase = true) || text.contains("ink wash", ignoreCase = true) -> "brush_thin"
        else -> "pen"
    }

    fun styleKey(text: String): String = when {
        text.contains("一点鎖線") || text.contains("dash_dot", ignoreCase = true) || text.contains("dash dot", ignoreCase = true) -> "dash_dot"
        text.contains("破線") || text.contains("dashed", ignoreCase = true) -> "dashed"
        text.contains("点線") || text.contains("dotted", ignoreCase = true) -> "dotted"
        else -> "solid"
    }

    fun hasStrokeStyleWord(text: String): Boolean {
        return listOf("実線", "破線", "点線", "一点鎖線").any { text.contains(it) } ||
            listOf("solid", "dashed", "dotted", "dash_dot", "dash dot").any { text.contains(it, ignoreCase = true) }
    }

    fun detectLayoutKey(text: String): String = when {
        text.contains("縦") || text.contains("上から下") -> "vertical"
        text.contains("散ら") || text.contains("点々") || text.contains("scatter", ignoreCase = true) -> "scatter"
        text.contains("円環") || text.contains("放射") || text.contains("同心円") -> "radial"
        else -> "horizontal"
    }

    fun detectColorCycle(text: String, foreground: String): List<String> {
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

    fun addVariationHint(instruction: JSONObject, text: String) {
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

    fun focusPoint(text: String): JSONArray = when {
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

    fun countHintFromDdl(text: String): Int? {
        Regex("""\d+""").find(text)?.value?.toIntOrNull()?.let { return it }
        return listOf(
            "千" to 1000, "六百十" to 610, "三百" to 300, "百三十七" to 137, "百二十" to 120,
            "三十四" to 34, "三十" to 30, "二十一" to 21, "二十" to 20, "十六" to 16,
            "十二" to 12, "十一" to 11, "十" to 10, "八" to 8, "七" to 7, "六" to 6,
            "五" to 5, "四" to 4, "三" to 3, "二" to 2, "一" to 1,
        ).firstOrNull { (marker, _) -> text.contains(marker) }?.second
    }

    fun vagueCount(text: String): Int = when {
        text.containsAny("無数", "満天", "砂", "雨", "雪") -> 110
        text.containsAny("たくさん", "密集", "埋め") -> 80
        text.containsAny("点々", "散ら") -> 12
        else -> 3
    }

    fun detectRadius(text: String): Double? {
        val match = Regex("""半径(?:は)?([0-9]+(?:\.[0-9]+)?)""").find(text) ?: return null
        return match.groupValues[1].toDoubleOrNull()?.coerceIn(0.005, 0.5)
    }

    fun visibleBackground(background: String): String = if (background == "gray") "white" else background

    fun visibleForeground(color: String, background: String): String {
        return if (color == background) {
            if (background == "black" || background == "blue") "white" else "black"
        } else {
            color
        }
    }

    fun round2(value: Double): Double = kotlin.math.round(value * 100.0) / 100.0

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }

    private fun String.containsAnyIgnoreCase(vararg markers: String): Boolean {
        return markers.any { contains(it, ignoreCase = true) }
    }
}
