package app.inku.mobile.pipeline

import java.security.MessageDigest

internal data class DdlFilterProfile(
    val intensity: Int,
    val tags: Set<String>,
    val mode: String,
)

internal data class DdlFilterCandidate(
    val text: String,
    val tags: Set<String>,
    val label: String = "",
)

internal object WebDdlExpander {
    private val FOCUS_IDS = listOf(
        "upper_right",
        "upper_left",
        "lower_right",
        "lower_left",
        "upper_edge",
        "right_half",
    )

    private val focusWordsJa = mapOf(
        "upper_right" to "右上の焦点",
        "upper_left" to "左上の焦点",
        "lower_right" to "右下の焦点",
        "lower_left" to "左下の焦点",
        "upper_edge" to "上端寄りの焦点",
        "right_half" to "右半分の焦点",
    )

    private val focusWordsEn = mapOf(
        "upper_right" to "upper-right focus",
        "upper_left" to "upper-left focus",
        "lower_right" to "lower-right focus",
        "lower_left" to "lower-left focus",
        "upper_edge" to "upper-edge focus",
        "right_half" to "right-half focus",
    )

    private val jaExpansionMarkers = setOf(
        "右半分の斜めの帯",
        "左下から右上へ",
        "波打つ軌跡に沿って",
        "左下の焦点から三つ",
        "右下の焦点から三つ",
        "黄金比の位置",
        "三分割の交点",
        "白銀比の位置",
        "正五角形の頂点",
        "対位法の反行",
        "倍音列",
        "輪唱のずれ",
        "一点透視法",
        "遠近法の奥行き",
        "素描の下線",
        "点描",
        "油絵の厚塗り",
        "水彩",
        "パッチワーク",
        "フレスコの下地",
        "水墨の濃淡",
        "鉛筆の余白線",
        "クレヨンの擦れ",
        "ロットリングの均一線",
        "透明な膜",
        "薄い反射",
        "消える線",
        "柔らかな光",
        "香りの層",
        "開花を待つ蕾",
        "五感の気配",
        "前の線を切る",
        "前の線に沿って",
        "前の形に触れない",
        "前の二つの間に",
        "斜めの線を三本",
        "右下の焦点から外へ",
        "右下の焦点から放射状に",
        "全体の反復配置",
        "全体の揺らぎ",
    )

    private val enExpansionMarkers = setOf(
        "diagonal band in the right half",
        "lower left to upper right",
        "undulating trace",
        "lower-left focus",
        "golden-ratio position",
        "rule-of-thirds point",
        "silver-ratio position",
        "regular pentagon vertices",
        "contrapuntal contrary motion",
        "harmonic overtone series",
        "canon offset",
        "one-point perspective",
        "perspective depth",
        "drawing underlines",
        "pointillism",
        "oil impasto",
        "watercolor",
        "patchwork",
        "fresco ground",
        "ink-wash value",
        "pencil negative-space line",
        "crayon rubbing",
        "rotring uniform lines",
        "transparent membrane",
        "faint reflection",
        "fading lines",
        "soft light",
        "scent layer",
        "waiting buds",
        "five-sense presence",
        "cutting the previous line",
        "along the previous line",
        "not touching the previous shape",
        "between the previous two",
        "outward from a lower-right focus",
        "radiating from a lower-right focus",
        "set repeated placement",
        "use no variation",
    )

    private val jaColors = listOf("赤", "青", "緑", "白", "黒", "灰")
    private val jaColorWord = mapOf(
        "赤" to "赤い",
        "青" to "青い",
        "緑" to "緑の",
        "白" to "白い",
        "黒" to "黒い",
        "灰" to "灰色の",
    )
    private val enColors = listOf("red", "blue", "green", "white", "black", "gray")

    fun expandIntermediateDdl(
        ddl: String,
        lang: String = "ja",
        contextText: String? = null,
        varySeed: Long? = null,
        enablePlugins: Boolean = true,
        pluginInstructionsPresent: Boolean = false,
        tenkei: String = "auto",
        focus: String? = null,
        variationAmplitude: String? = null,
        variationSeed: Long? = null,
        variationReport: MutableMap<String, Any>? = null,
    ): String {
        val sanitized = avoidGrayBackground(WebDdlSpec.sanitizePlacementWords(ddl).trim(), lang)
        if (sanitized.isBlank()) return sanitized

        return if (lang == "en") {
            expandEn(
                sanitized,
                contextText = contextText,
                varySeed = varySeed,
                pluginInstructionsPresent = pluginInstructionsPresent,
                tenkei = tenkei,
                focus = focus,
            )
        } else {
            expandJa(
                sanitized,
                contextText = contextText,
                varySeed = varySeed,
                pluginInstructionsPresent = pluginInstructionsPresent,
                tenkei = tenkei,
                focus = focus,
            )
        }
    }

    private fun expandJa(
        ddl: String,
        contextText: String?,
        varySeed: Long?,
        pluginInstructionsPresent: Boolean,
        tenkei: String,
        focus: String?,
    ): String {
        if (pluginInstructionsPresent ||
            hasExplicitNumericRegions(ddl, "ja") ||
            jaExpansionMarkers.any { it in ddl }
        ) {
            return ddl
        }

        val focusId = resolveFocusId(ddl, focus, lang = "ja")
        val reframed = reframeStaticCenterJa(ddl, focusId)
        if (tenkei == "none") return reframed

        val sentences = splitSentences(reframed, "ja")
        val structural = mutableListOf<DdlFilterCandidate>()
        val mainColor = dominantJaColor(reframed)
        val contrastColor = contrastJaColor(reframed)
        val context = "${contextText.orEmpty()}\n$reframed"
        val seedContext = varyContext(context, varySeed)
        val profile = profileJa(context)

        val touch = when {
            "geometry" in profile.tags -> "ロットリングの"
            "dense" in profile.tags -> "クレヨンの"
            profile.tags.intersect(setOf("water", "soft", "sensory", "atmosphere")).isNotEmpty() -> "細筆の"
            "contrast" in profile.tags -> "ペンの"
            else -> "鉛筆の"
        }

        fun add(label: String, text: String) {
            structural.add(DdlFilterCandidate(text, structuralTags(text), label))
        }

        if (reframed.containsAny("円", "点", "粒", "星", "楕円", "四角")) {
            add("楕円の帯", "${mainColor}右上がりの小さな楕円を右半分の斜めの帯に三個並べる。横長にする。")
            add("斜めの短線", "${mainColor}${touch}短い線を左下から右上へ三本散らす。細かく震える。")
        }
        if (reframed.containsAny("散らす", "点々", "舞", "漂", "雪", "雨")) {
            add("波の楕円", "${mainColor}右下がりの小さな楕円を波打つ軌跡に沿って七個散らす。ゆっくり揺れる。")
        }
        if ("線" in reframed) {
            add("斜線の反復", "${contrastColor}${touch}細い斜め線を右上がりに三本並べる。細かく震える。")
        }
        if (reframed.containsAny("弧", "円", "波", "水", "月", "中心")) {
            add("広がる弧", "${contrastColor}${touch}細い弧を左下の焦点から三つ広げる。半径は0.11。")
        }
        val roofPressureContext = context.containsAny("低い雲", "押し沈", "屋根")
        if (context.containsAny("山", "尖", "針葉樹", "頂", "鋭")) {
            add("尖りの三角", "${mainColor}細い三角を上端寄りの焦点に二つ置く。少し傾ける。")
        }
        if (context.containsAny("葉", "花びら", "羽", "紙片", "破片", "舟")) {
            add("葉片", "${mainColor}細い右上がりの楕円を葉片として波打つ軌跡に沿って五個散らす。")
        }
        if (!roofPressureContext && context.containsAny("扉", "窓", "箱", "街", "部屋", "格子")) {
            add("余白の切片", "${contrastColor}回転した細い四角を余白の切片として右半分に三つ散らす。")
        }
        if (roofPressureContext) {
            add("低い重さ", "${contrastColor}${touch}薄い斜め線を上端から下へ三本置く。低い重さとしてゆっくり揺れる。")
        }
        if (context.containsAny("膜", "透明", "霞", "霧", "靄", "気配", "余韻")) {
            add("透明な膜", "${mainColor}薄い水彩の楕円を透明な膜として右半分に三つ重ねる。境界が滲む。")
        }
        if (context.containsAny("反射", "映り")) {
            add("反射の線", "${contrastColor}${touch}薄い反射の線を波打つ軌跡に沿って五本散らす。ゆっくり揺れる。")
        }
        if (context.containsAny("消え", "薄れ", "遠ざか")) {
            add("消える線", "${contrastColor}${touch}消える線を左下から右上へ五本散らす。細かく震える。")
        }
        if (context.containsAny("陽光", "光", "日差し", "温", "柔ら")) {
            add("柔らかな光", "白い薄い水彩の横長の楕円を柔らかな光として上端寄りに三つ重ねる。境界が滲む。")
        }
        if (context.containsAny("香", "匂", "沈丁花")) {
            add("香りの層", "緑の小さな楕円を香りの層として波打つ軌跡に沿って七個散らす。ゆっくり揺れる。")
        }
        if (context.containsAny("蕾", "つぼみ", "開花", "春")) {
            add("蕾", "赤い右上がりの小さな楕円を開花を待つ蕾として右半分の斜めの帯に五個散らす。")
        }
        if (context.containsAny("五感", "気配", "訪れ")) {
            add("五感の気配", "白い細筆の薄い弧を五感の気配として左下の焦点から三つ広げる。半径は0.14。")
        }
        if (context.containsAny("人", "人物", "村人", "老人", "顔", "視線", "動物", "鳥", "魚", "熊", "群れ")) {
            add("存在の重心", "${contrastColor}${touch}細い余白線を存在の重心として右上の焦点へ二本引く。細かく震える。")
            add("輪郭の密度", "${mainColor}${touch}薄い弧を輪郭の密度として左下の焦点から二つ置く。半径は0.09。")
        }

        val music = listOf(
            DdlFilterCandidate("${contrastColor}${touch}細い線を前の線を切るように二本置く。細かく震える。", setOf("line", "music", "contrast"), "対位法"),
            DdlFilterCandidate("${contrastColor}${touch}細い弧を倍音列として右下の焦点から三つ並べる。半径は0.07。", setOf("music", "water", "soft"), "倍音列"),
            DdlFilterCandidate("${mainColor}${touch}短い線を前の線に沿って左から右へ四本並べる。ゆっくり揺れる。", setOf("particle", "music", "line"), "輪唱"),
        )
        val painting = listOf(
            DdlFilterCandidate("${contrastColor}${touch}細い線を前の線に沿って右上の焦点へ三本引く。", setOf("space", "line", "geometry"), "一点透視"),
            DdlFilterCandidate("${contrastColor}${touch}細い横線を遠近法の奥行きとして上へ細かく三本並べる。", setOf("space", "line"), "遠近法"),
            DdlFilterCandidate("黒い細筆の細い線を素描の下線として左から右へ三本並べる。細かく震える。", setOf("line", "quiet"), "素描"),
            DdlFilterCandidate("${contrastColor}鉛筆の細い線を余白線として上端寄りに二本並べる。細かく震える。", setOf("line", "quiet", "soft"), "鉛筆の余白線"),
            DdlFilterCandidate("${mainColor}クレヨンの短い線を擦れとして右半分の斜めの帯に七本散らす。", setOf("particle", "dense", "soft"), "クレヨンの擦れ"),
            DdlFilterCandidate("${contrastColor}ロットリングの細い線を均一線として左から右へ五本並べる。", setOf("line", "geometry", "contrast"), "ロットリング"),
            DdlFilterCandidate("${mainColor}回転した小さな四角を前の形に触れないように右半分の斜めの帯に十三個散らす。", setOf("particle", "dense", "geometry"), "点描の四角"),
            DdlFilterCandidate("${mainColor}太筆の短い線を油絵の厚塗りとして横に三本並べる。", setOf("dense", "contrast"), "油絵"),
            DdlFilterCandidate("${contrastColor}薄い水彩の楕円を左上に二つ重ねる。境界が滲む。", setOf("water", "soft", "quiet"), "水彩"),
            DdlFilterCandidate("赤・青・緑・灰の回転した小さな四角をパッチワークとして格子状に六個並べる。", setOf("geometry", "dense"), "パッチワーク"),
            DdlFilterCandidate("${contrastColor}チョークの横線をフレスコの下地として画面下に三本並べる。境界が滲む。", setOf("space", "line", "soft"), "フレスコ"),
            DdlFilterCandidate("黒い細筆の縦線を水墨の濃淡として左から右へ三本並べる。境界が滲む。", setOf("water", "contrast", "quiet"), "水墨"),
            DdlFilterCandidate("白い薄い水彩の楕円を五感の気配として右上に二つ重ねる。境界が滲む。", setOf("sensory", "soft", "quiet"), "五感の水彩"),
        )

        val counts = capCategoryPlan(categoryPlan(profile, structural.isNotEmpty()), tenkei)
        val (structuralCount, musicCount, paintingCount) = counts

        var selected = selectCategory(structural, structuralCount, profile, seedContext, modeSalt(profile, "ja-structure")) +
            selectCategory(music, musicCount, profile, seedContext, modeSalt(profile, "ja-music")) +
            selectCategory(painting, paintingCount, profile, seedContext, modeSalt(profile, "ja-painting"))

        selected = limitCentered(selected, listOf("中心", "中央", "放射状", "同心円状"))
        selected = applyCompositionFamilyJa(selected, profile, seedContext)

        return joinSentences(sentences + selected, "ja")
    }

    private fun expandEn(
        ddl: String,
        contextText: String?,
        varySeed: Long?,
        pluginInstructionsPresent: Boolean,
        tenkei: String,
        focus: String?,
    ): String {
        val lower = ddl.lowercase()
        if (pluginInstructionsPresent ||
            hasExplicitNumericRegions(ddl, "en") ||
            enExpansionMarkers.any { it in lower }
        ) {
            return ddl
        }

        val focusId = resolveFocusId(ddl, focus, lang = "en")
        val reframed = reframeStaticCenterEn(ddl, focusId)
        if (tenkei == "none") return reframed

        val reframedLower = reframed.lowercase()
        val sentences = splitSentences(reframed, "en")
        val structural = mutableListOf<DdlFilterCandidate>()
        val mainColor = dominantEnColor(reframed)
        val contrastColor = contrastEnColor(reframed)
        val context = "${contextText.orEmpty()}\n$reframed"
        val contextLower = context.lowercase()
        val seedContext = varyContext(context, varySeed)
        val profile = profileEn(context)

        val touch = when {
            "geometry" in profile.tags -> "rotring"
            "dense" in profile.tags -> "crayon"
            profile.tags.intersect(setOf("water", "soft", "sensory", "atmosphere")).isNotEmpty() -> "fine-brush"
            "contrast" in profile.tags -> "pen"
            else -> "pencil"
        }

        fun add(label: String, text: String) {
            structural.add(DdlFilterCandidate(text, structuralTags(text), label))
        }

        if (reframedLower.containsAny("circle", "dot", "particle", "star", "ellipse", "square")) {
            add("ellipse band", "Line up three small $mainColor ellipses rising to the right along a diagonal band in the right half. Make them wide.")
            add("diagonal strokes", "Scatter three short $mainColor $touch lines from lower left to upper right. Fine trembling.")
        }
        if (reframedLower.containsAny("scatter", "dotted", "drift", "snow", "rain")) {
            add("wave ellipses", "Scatter seven small $mainColor ellipses falling to the right along an undulating trace. Swaying slowly.")
        }
        if ("line" in reframedLower) {
            add("diagonal repetition", "Line up three thin $contrastColor $touch diagonal lines rising to the right. Fine trembling.")
        }
        if (reframedLower.containsAny("arc", "circle", "wave", "water", "moon", "center")) {
            add("spreading arcs", "Line up three thin $contrastColor $touch arcs spreading from a lower-left focus. Radius 0.11.")
        }
        val roofPressureContext = contextLower.containsAny("low cloud", "pressing down", "roof")
        if (contextLower.containsAny("mountain", "sharp", "pine", "peak", "needle")) {
            add("sharp triangles", "Place two thin $mainColor triangles near the upper-edge focus. Tilt them slightly.")
        }
        if (contextLower.containsAny("leaf", "petal", "feather", "paper", "fragment", "boat")) {
            add("leaf pieces", "Scatter five thin $mainColor ellipses rising to the right along an undulating trace as leaf-like pieces.")
        }
        if (!roofPressureContext && contextLower.containsAny("door", "window", "box", "city", "room", "grid")) {
            add("visual cuts", "Scatter three thin rotated $contrastColor squares in the right half as visual cuts.")
        }
        if (roofPressureContext) {
            add("overhead weight", "Place three pale $contrastColor $touch diagonal lines from the upper edge downward as slow overhead weight.")
        }
        if (contextLower.containsAny("membrane", "transparent", "haze", "fog", "mist", "atmosphere", "presence")) {
            add("transparent membrane", "Layer three pale $mainColor watercolor ellipses in the right half as a transparent membrane. Edges blurring.")
        }
        if (contextLower.containsAny("reflection", "reflected")) {
            add("reflection lines", "Scatter five thin $contrastColor $touch faint reflection lines along an undulating trace. Swaying slowly.")
        }
        if (contextLower.containsAny("fade", "fading", "vanish", "dissolve")) {
            add("fading lines", "Scatter five thin $contrastColor $touch fading lines from lower left to upper right. Fine trembling.")
        }
        if (contextLower.containsAny("sunlight", "light", "warm", "soft")) {
            add("soft light", "Layer three pale white watercolor ellipses near the upper edge as soft light. Edges blurring.")
        }
        if (hasEnTerms(contextLower, listOf("scent", "fragrance"))) {
            add("scent layer", "Scatter seven small green ellipses along an undulating trace as a scent layer. Swaying slowly.")
        }
        if (contextLower.containsAny("spring", "bud", "bloom", "waiting")) {
            add("waiting buds", "Scatter five small red ellipses rising to the right along a diagonal band in the right half as waiting buds.")
        }
        if (contextLower.containsAny("sense", "presence", "arrival")) {
            add("five-sense presence", "Line up three pale white fine-brush arcs from a lower-left focus as five-sense presence. Radius 0.14.")
        }
        if (contextLower.containsAny("human", "person", "people", "figure", "face", "gaze", "animal", "bird", "fish", "bear", "flock", "herd")) {
            add("presence weight", "Draw two thin $contrastColor $touch negative-space lines toward an upper-right focus as presence weight. Fine trembling.")
            add("contour density", "Place two pale $mainColor $touch arcs from a lower-left focus as contour density. Radius 0.09.")
        }

        val music = listOf(
            DdlFilterCandidate("Place two thin $contrastColor $touch lines cutting the previous line. Fine trembling.", setOf("line", "music", "contrast"), "counterpoint"),
            DdlFilterCandidate("Line up three thin $contrastColor $touch arcs from a lower-right focus as a harmonic overtone series. Radius 0.07.", setOf("music", "water", "soft"), "overtone series"),
            DdlFilterCandidate("Line up four short $mainColor $touch lines left to right along the previous line. Swaying slowly.", setOf("particle", "music", "line"), "canon"),
        )
        val painting = listOf(
            DdlFilterCandidate("Draw three thin $contrastColor $touch lines toward an upper-right focus along the previous line.", setOf("space", "line", "geometry"), "one-point perspective"),
            DdlFilterCandidate("Line up three thin $contrastColor $touch horizontal lines upward as perspective depth.", setOf("space", "line"), "perspective depth"),
            DdlFilterCandidate("Line up three thin black fine-brush lines left to right as drawing underlines. Fine trembling.", setOf("line", "quiet"), "drawing underline"),
            DdlFilterCandidate("Line up two thin $contrastColor pencil lines near the top edge as pencil negative-space line. Fine trembling.", setOf("line", "quiet", "soft"), "pencil negative space"),
            DdlFilterCandidate("Scatter seven short $mainColor crayon lines along a diagonal band in the right half as crayon rubbing.", setOf("particle", "dense", "soft"), "crayon rubbing"),
            DdlFilterCandidate("Line up five thin $contrastColor rotring uniform lines left to right.", setOf("line", "geometry", "contrast"), "rotring uniform"),
            DdlFilterCandidate("Scatter thirteen small rotated $mainColor squares not touching the previous shape along a diagonal band in the right half.", setOf("particle", "dense", "geometry"), "pointillist squares"),
            DdlFilterCandidate("Line up three short $mainColor thick-brush lines horizontally as oil impasto.", setOf("dense", "contrast"), "oil impasto"),
            DdlFilterCandidate("Layer two pale watercolor ellipses in the upper left. Edges blurring.", setOf("water", "soft", "quiet"), "watercolor"),
            DdlFilterCandidate("Line up six small rotated squares in red, blue, green, gray as patchwork grid.", setOf("geometry", "dense"), "patchwork"),
            DdlFilterCandidate("Line up three $contrastColor chalk horizontal lines at the bottom as fresco ground. Edges blurring.", setOf("space", "line", "soft"), "fresco"),
            DdlFilterCandidate("Line up three black fine-brush vertical lines left to right as ink-wash value. Edges blurring.", setOf("water", "contrast", "quiet"), "ink wash"),
            DdlFilterCandidate("Layer two pale white watercolor ellipses in the upper right as five-sense presence. Edges blurring.", setOf("sensory", "soft", "quiet"), "five-sense watercolor"),
        )

        val counts = capCategoryPlan(categoryPlan(profile, structural.isNotEmpty()), tenkei)
        val (structuralCount, musicCount, paintingCount) = counts

        var selected = selectCategory(structural, structuralCount, profile, seedContext, modeSalt(profile, "en-structure")) +
            selectCategory(music, musicCount, profile, seedContext, modeSalt(profile, "en-music")) +
            selectCategory(painting, paintingCount, profile, seedContext, modeSalt(profile, "en-painting"))

        selected = limitCentered(selected, listOf("center", "radial", "concentric"))
        selected = applyCompositionFamilyEn(selected, profile, seedContext)

        return joinSentences(sentences + selected, "en")
    }

    private fun seed(text: String, salt: String): ULong {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("$salt:$text".toByteArray(Charsets.UTF_8))
        var result = 0UL
        for (i in 0 until 8) {
            result = (result shl 8) or (digest[i].toUByte().toULong())
        }
        return result
    }

    private fun pick(items: List<String>, count: Int, text: String, salt: String): List<String> {
        if (count <= 0 || items.isEmpty()) return emptyList()
        val ranked = items.sortedBy { seed("$text:$it", salt) }
        return ranked.take(minOf(count, ranked.size))
    }

    private fun hasExplicitNumericRegions(ddl: String, lang: String): Boolean {
        val pattern = if (lang == "en") Regex("""\bregion\s*\[""", RegexOption.IGNORE_CASE)
        else Regex("""領域\s*\[""")
        return pattern.containsMatchIn(ddl)
    }

    private fun splitSentences(text: String, lang: String): List<String> {
        if (lang == "en") {
            return Regex("""(?<=[.!?])\s+""").split(text.trim()).map { it.trim() }.filter { it.isNotBlank() }
        }
        return Regex("""(?<=。)""").split(text.trim()).map { it.trim() }.filter { it.isNotBlank() }
    }

    private fun joinSentences(sentences: List<String>, lang: String): String {
        if (lang == "en") {
            return sentences.joinToString(" ") { if (it.endsWith(".") || it.endsWith("!") || it.endsWith("?")) it else "$it." }
        }
        return sentences.joinToString("") { if (it.endsWith("。")) it else "$it。" }
    }

    private fun avoidGrayBackground(text: String, lang: String): String {
        if (lang == "en") {
            return text.replace(Regex("""Fill background with gr[ae]y\.?""", RegexOption.IGNORE_CASE), "Fill background with white.")
        }
        return text.replace(Regex("""背景を灰(?:色)?で塗りつぶす。?"""), "背景を白で塗りつぶす。")
    }

    private fun varyContext(text: String, varySeed: Long?): String {
        if (varySeed == null) return text
        return "$text#vary${java.lang.Long.toUnsignedString(varySeed)}"
    }

    private fun resolveFocusId(text: String, focus: String?, lang: String): String {
        if (focus in FOCUS_IDS) return focus!!
        val salt = if (lang == "en") "en-focus" else "ja-focus"
        val idx = (seed(text, salt) % FOCUS_IDS.size.toULong()).toInt()
        return FOCUS_IDS[idx]
    }

    private fun dynamicFocusJa(text: String, focus: String?): String {
        focusWordsJa[focus.orEmpty()]?.let { return it }
        val idx = (seed(text, "ja-focus") % FOCUS_IDS.size.toULong()).toInt()
        return focusWordsJa.getValue(FOCUS_IDS[idx])
    }

    private fun dynamicFocusEn(text: String, focus: String?): String {
        focusWordsEn[focus.orEmpty()]?.let { return it }
        val idx = (seed(text, "en-focus") % FOCUS_IDS.size.toULong()).toInt()
        return focusWordsEn.getValue(FOCUS_IDS[idx])
    }

    private fun reframeStaticCenterJa(ddl: String, focusId: String): String {
        val f = focusWordsJa.getValue(focusId)
        var result = ddl
        for (word in listOf("画面中央", "中央付近", "中心付近", "中央", "中心")) {
            result = result.replace(word, f)
        }
        return result
    }

    private fun reframeStaticCenterEn(ddl: String, focusId: String): String {
        val f = focusWordsEn.getValue(focusId)
        var result = ddl
        val replacements = listOf(
            Regex("""\bnear the center\b""", RegexOption.IGNORE_CASE) to "near the $f",
            Regex("""\bat the center\b""", RegexOption.IGNORE_CASE) to "at the $f",
            Regex("""\bat center\b""", RegexOption.IGNORE_CASE) to "at the $f",
            Regex("""\btoward the center\b""", RegexOption.IGNORE_CASE) to "toward the $f",
            Regex("""\bfrom center\b""", RegexOption.IGNORE_CASE) to "from the $f",
            Regex("""\bfrom the center\b""", RegexOption.IGNORE_CASE) to "from the $f",
            Regex("""\bthe center\b""", RegexOption.IGNORE_CASE) to "the $f",
            Regex("""\bcenter\b""", RegexOption.IGNORE_CASE) to f,
        )
        for (pair in replacements) {
            result = pair.first.replace(result, pair.second)
        }
        return result
    }

    private fun dominantJaColor(ddl: String): String {
        val body = ddl.replace(Regex("""背景を[^\u3002。]*。?"""), "")
        for (color in jaColors) {
            if (color in body) return jaColorWord.getValue(color)
        }
        return when {
            body.containsAny("春", "桜", "花", "蕾", "夕", "温", "陽光", "祝", "祭") -> "赤い"
            body.containsAny("森", "葉", "草", "香", "匂", "畑", "苔") -> "緑の"
            body.containsAny("夜", "月", "水", "雨", "霧", "冷", "海", "空") -> "青い"
            else -> "黒い"
        }
    }

    private fun contrastJaColor(ddl: String): String {
        if ("背景を黒" in ddl || "暗い背景" in ddl) return "白い"
        if (ddl.containsAny("春", "桜", "花", "蕾", "温", "陽光")) return "緑の"
        if (ddl.containsAny("夜", "月", "水", "雨", "霧", "冷")) return "白い"
        return "黒い"
    }

    private fun dominantEnColor(ddl: String): String {
        val body = ddl.replace(Regex("""Fill background with \w+\.?""", RegexOption.IGNORE_CASE), "")
        val lower = body.lowercase()
        for (color in enColors) {
            if (color in lower) return color
        }
        if (lower.containsAny("spring", "cherry", "flower", "bud", "sunset", "warm", "sunlight", "festival")) return "red"
        if (hasEnTerms(lower, listOf("forest", "leaf", "grass", "scent", "fragrance", "field", "moss"))) return "green"
        if (lower.containsAny("night", "moon", "water", "rain", "mist", "cold", "sea", "sky")) return "blue"
        return "black"
    }

    private fun contrastEnColor(ddl: String): String {
        val lower = ddl.lowercase()
        if ("fill background with black" in lower) return "white"
        if (lower.containsAny("spring", "cherry", "flower", "bud", "warm", "sunlight")) return "green"
        if (lower.containsAny("night", "moon", "water", "rain", "mist", "cold")) return "white"
        return "black"
    }

    private fun hasEnTerms(text: String, tokens: List<String>): Boolean {
        return tokens.any { token ->
            Regex("""(?<![a-z])${Regex.escape(token)}(?![a-z])""").containsMatchIn(text)
        }
    }

    private fun profileJa(text: String): DdlFilterProfile {
        val tags = mutableSetOf<String>()
        var intensity = 2
        var mode = "asymmetric_rhythm"

        if (text.containsAny("余白", "静か", "一滴", "一本", "ひとつ", "孤独", "ぽつん", "霧", "淡", "薄い")) {
            intensity = 1
            tags += setOf("quiet", "space")
            mode = "single_tension"
        }
        if (text.containsAny("満天", "無数", "密集", "びっしり", "埋め尽く", "嵐", "群れ", "祭", "都市", "複雑")) {
            intensity = 3
            tags += "dense"
            mode = "layered_trace"
        }

        if (text.containsAny("円", "粒", "星", "雪", "雨", "砂", "花びら", "散らす", "点々")) tags += "particle"
        if (text.containsAny("線", "糸", "水平", "垂直", "縦", "横", "斜め")) {
            tags += "line"
            if (mode != "single_tension") mode = "asymmetric_rhythm"
        }
        if (text.containsAny("水", "波", "月", "霧", "滲", "淡", "雲")) tags += setOf("water", "soft")
        if (text.containsAny("膜", "透明", "霞", "霧", "靄", "気配", "余韻", "反射", "映り", "消え", "薄れ")) tags += setOf("soft", "atmosphere")
        if (text.containsAny("香", "匂", "陽光", "光", "春", "蕾", "つぼみ", "開花", "待つ", "五感", "温", "柔ら")) tags += setOf("soft", "sensory")
        if (text.containsAny("音", "リズム", "歌", "輪唱", "響", "反復", "揺", "舞", "流")) tags += "music"
        if (text.containsAny("建物", "都市", "寺", "古刹", "部屋", "道", "遠く", "奥", "畑")) {
            tags += "space"
            if (mode != "single_tension") mode = "edge_focus"
        }
        if (text.containsAny("黒", "白", "影", "明暗", "暗", "光", "灰")) tags += "contrast"
        if (text.containsAny("四角", "格子", "幾何", "均衡", "法則", "対称")) tags += "geometry"
        if (text.containsAny("人", "人物", "村人", "老人", "顔", "視線", "動物", "鳥", "魚", "熊", "群れ")) {
            tags += setOf("presence", "space")
            if (mode != "single_tension") mode = "field_and_interruption"
        }

        if (text.containsAny("影", "痕跡", "埃", "足跡", "残", "冷え", "錆") && mode != "single_tension") {
            mode = "field_and_interruption"
        }

        return DdlFilterProfile(intensity, tags, mode)
    }

    private fun profileEn(text: String): DdlFilterProfile {
        val lower = text.lowercase()
        val tags = mutableSetOf<String>()
        var intensity = 2
        var mode = "asymmetric_rhythm"

        if (lower.containsAny("empty space", "quiet", "single", "one ", "alone", "solitary", "mist", "pale")) {
            intensity = 1
            tags += setOf("quiet", "space")
            mode = "single_tension"
        }
        if (lower.containsAny("starry", "countless", "dense", "packed", "fill", "storm", "crowd", "city", "complex")) {
            intensity = 3
            tags += "dense"
            mode = "layered_trace"
        }

        if (lower.containsAny("circle", "dot", "particle", "star", "snow", "rain", "sand", "petal", "scatter", "dotted")) tags += "particle"
        if (lower.containsAny("line", "thread", "horizontal", "vertical", "diagonal")) {
            tags += "line"
            if (mode != "single_tension") mode = "asymmetric_rhythm"
        }
        if (lower.containsAny("water", "wave", "moon", "mist", "blur", "pale", "cloud")) tags += setOf("water", "soft")
        if (lower.containsAny("membrane", "transparent", "haze", "fog", "mist", "atmosphere", "presence", "reflection", "fade", "fading")) tags += setOf("soft", "atmosphere")
        if (lower.containsAny("scent", "fragrance", "sunlight", "light", "spring", "bud", "bloom", "waiting", "sense", "warm", "soft")) tags += setOf("soft", "sensory")
        if (lower.containsAny("sound", "rhythm", "song", "canon", "echo", "repeat", "sway", "drift")) tags += "music"
        if (lower.containsAny("building", "city", "temple", "room", "road", "distant", "depth", "field")) {
            tags += "space"
            if (mode != "single_tension") mode = "edge_focus"
        }
        if (lower.containsAny("black", "white", "shadow", "value", "dark", "light", "gray")) tags += "contrast"
        if (lower.containsAny("square", "grid", "geometric", "balance", "law", "symmetry")) tags += "geometry"
        if (lower.containsAny("human", "person", "people", "figure", "face", "gaze", "animal", "bird", "fish", "bear", "flock", "herd")) {
            tags += setOf("presence", "space")
            if (mode != "single_tension") mode = "field_and_interruption"
        }

        if (lower.containsAny("shadow", "trace", "dust", "footprint", "remains", "cold", "rust") && mode != "single_tension") {
            mode = "field_and_interruption"
        }

        return DdlFilterProfile(intensity, tags, mode)
    }

    private fun categoryPool(candidates: List<DdlFilterCandidate>, profile: DdlFilterProfile): List<DdlFilterCandidate> {
        val prefTags = profile.tags.intersect(setOf("atmosphere", "sensory", "presence"))
        if (prefTags.isNotEmpty()) {
            val matched = candidates.filter { it.tags.intersect(prefTags).isNotEmpty() }
            if (matched.isNotEmpty()) return matched
        }
        val matched = if (profile.intensity <= 1) {
            candidates.filter { it.tags.intersect(setOf("quiet", "soft", "water")).isNotEmpty() }
        } else {
            candidates.filter { it.tags.intersect(profile.tags).isNotEmpty() }
        }
        return matched.ifEmpty { candidates }
    }

    private fun selectCategory(candidates: List<DdlFilterCandidate>, count: Int, profile: DdlFilterProfile, text: String, salt: String): List<String> {
        if (count <= 0) return emptyList()
        val pool = categoryPool(candidates, profile).map { it.text }
        return pick(pool, count, text, salt)
    }

    private fun categoryPlan(profile: DdlFilterProfile, hasStructural: Boolean): Triple<Int, Int, Int> {
        if (profile.intensity <= 1) return Triple(0, 0, 0)
        if (profile.intensity >= 3) {
            if ("music" in profile.tags) return Triple(if (hasStructural) 1 else 0, 1, 0)
            return Triple(if (hasStructural) 1 else 0, 0, if (profile.tags.intersect(setOf("geometry", "space", "water")).isNotEmpty()) 1 else 0)
        }
        if ("music" in profile.tags) return Triple(0, 1, 0)
        if ("sensory" in profile.tags) return Triple(if (hasStructural) 2 else 0, 0, 1)
        if ("atmosphere" in profile.tags) return Triple(if (hasStructural) 2 else 0, 0, 0)
        if ("presence" in profile.tags) return Triple(if (hasStructural) 1 else 0, 0, 1)
        if (profile.tags.intersect(setOf("geometry", "space")).isNotEmpty()) return Triple(0, 0, 1)
        return Triple(if (hasStructural) 1 else 0, 0, 0)
    }

    private fun capCategoryPlan(plan: Triple<Int, Int, Int>, tenkei: String): Triple<Int, Int, Int> {
        if (tenkei == "none") return Triple(0, 0, 0)
        if (tenkei != "sparse") return plan
        val (structural, music, painting) = plan
        if (structural != 0) return Triple(1, 0, 0)
        if (music != 0) return Triple(0, 1, 0)
        if (painting != 0) return Triple(0, 0, 1)
        return plan
    }

    private fun structuralTags(text: String): Set<String> {
        val tags = mutableSetOf("particle", "line", "water", "space")
        val lower = text.lowercase()
        if (listOf("透明な膜", "薄い反射", "消える線", "transparent membrane", "faint reflection", "fading lines").any { it in text || it in lower }) {
            tags += setOf("atmosphere", "soft")
        }
        if (listOf("柔らかな光", "香りの層", "開花を待つ蕾", "五感の気配", "soft light", "scent layer", "waiting buds", "five-sense presence").any { it in text || it in lower }) {
            tags += setOf("sensory", "soft")
        }
        if (listOf("存在の重心", "輪郭の密度", "presence weight", "contour density").any { it in text || it in lower }) {
            tags += setOf("presence", "space")
        }
        return tags
    }

    private fun modeSalt(profile: DdlFilterProfile, category: String): String = "${profile.mode}:$category"

    private fun limitCentered(items: List<String>, centeredTokens: List<String>, maxCount: Int = 1): List<String> {
        var centeredCount = 0
        val result = mutableListOf<String>()
        for (item in items) {
            if (centeredTokens.any { it in item }) {
                if (centeredCount >= maxCount) continue
                centeredCount += 1
            }
            result.add(item)
        }
        return result
    }

    private fun compositionPool(profile: DdlFilterProfile): List<String> {
        if (profile.mode == "single_tension") return listOf("edge_retreat", "one_sided_focus", "central_stillness")
        if ("music" in profile.tags || "line" in profile.tags) return listOf("vertical_rhythm", "horizontal_strata", "dispersal", "radial_concentric", "edge_retreat")
        if ("particle" in profile.tags || "dense" in profile.tags) return listOf("dispersal", "horizontal_strata", "vertical_rhythm", "radial_concentric")
        if ("space" in profile.tags || "presence" in profile.tags) return listOf("edge_retreat", "one_sided_focus", "horizontal_strata", "central_stillness")
        if ("water" in profile.tags || "soft" in profile.tags) return listOf("horizontal_strata", "radial_concentric", "edge_retreat", "dispersal")
        return listOf("diagonal_band", "vertical_rhythm", "horizontal_strata", "radial_concentric", "one_sided_focus", "central_stillness", "edge_retreat", "dispersal")
    }

    private fun compositionFamily(profile: DdlFilterProfile, text: String, lang: String): String {
        val pool = compositionPool(profile)
        val idx = (seed(text, "$lang-composition-family") % pool.size.toULong()).toInt()
        return pool[idx]
    }

    private fun rewriteByMap(items: List<String>, replacements: List<Pair<String, String>>): List<String> {
        val result = mutableListOf<String>()
        for (item in items) {
            var changed = item
            for ((before, after) in replacements) {
                changed = changed.replace(before, after)
            }
            result.add(changed)
        }
        return result
    }

    private fun applyCompositionFamilyJa(items: List<String>, profile: DdlFilterProfile, text: String): List<String> {
        val family = compositionFamily(profile, text, "ja")
        val maps = mapOf(
            "vertical_rhythm" to listOf("右半分の斜めの帯" to "上から下への縦の帯", "左下から右上へ" to "上から下へ", "右上の焦点" to "上端寄りの焦点", "左下の焦点" to "上端寄りの焦点"),
            "horizontal_strata" to listOf("右半分の斜めの帯" to "左から右への横の帯", "左下から右上へ" to "左から右へ", "右上の焦点" to "右半分の焦点", "左下の焦点" to "右半分の焦点"),
            "radial_concentric" to listOf("右半分の斜めの帯" to "右下の焦点から放射状に", "左下から右上へ" to "右下の焦点から外へ", "左下の焦点" to "右下の焦点"),
            "one_sided_focus" to listOf("左下の焦点" to "右半分の焦点", "上端寄りの焦点" to "右半分の焦点"),
            "central_stillness" to listOf("右半分の斜めの帯" to "中央静止の周囲に", "左下から右上へ" to "中央静止の周囲へ", "右上の焦点" to "中央静止の周囲", "左下の焦点" to "中央静止の周囲"),
            "edge_retreat" to listOf("右半分の斜めの帯" to "上端寄りに", "左下から右上へ" to "上端寄りへ", "右上の焦点" to "上端寄りの焦点", "左下の焦点" to "上端寄りの焦点"),
            "dispersal" to listOf("右半分の斜めの帯" to "画面全体に点々と", "左下から右上へ" to "画面全体へ"),
        )
        return rewriteByMap(items, maps[family].orEmpty())
    }

    private fun applyCompositionFamilyEn(items: List<String>, profile: DdlFilterProfile, text: String): List<String> {
        val family = compositionFamily(profile, text, "en")
        val maps = mapOf(
            "vertical_rhythm" to listOf("along a diagonal band in the right half" to "from top to bottom in a vertical band", "from lower left to upper right" to "from top to bottom", "upper-right focus" to "upper-edge focus", "lower-left focus" to "upper-edge focus"),
            "horizontal_strata" to listOf("along a diagonal band in the right half" to "left to right in horizontal strata", "from lower left to upper right" to "left to right", "upper-right focus" to "right-half focus", "lower-left focus" to "right-half focus"),
            "radial_concentric" to listOf("along a diagonal band in the right half" to "radiating from a lower-right focus", "from lower left to upper right" to "outward from a lower-right focus", "lower-left focus" to "lower-right focus"),
            "one_sided_focus" to listOf("lower-left focus" to "right-half focus", "upper-edge focus" to "right-half focus"),
            "central_stillness" to listOf("along a diagonal band in the right half" to "around a central stillness", "from lower left to upper right" to "around a central stillness", "upper-right focus" to "central stillness", "lower-left focus" to "central stillness"),
            "edge_retreat" to listOf("along a diagonal band in the right half" to "near the upper edge", "from lower left to upper right" to "toward the upper edge", "upper-right focus" to "upper-edge focus", "lower-left focus" to "upper-edge focus"),
            "dispersal" to listOf("along a diagonal band in the right half" to "dotted across the whole canvas", "from lower left to upper right" to "across the whole canvas"),
        )
        return rewriteByMap(items, maps[family].orEmpty())
    }

    private fun String.containsAny(vararg tokens: String): Boolean = tokens.any { it in this }

    private fun String.containsAny(tokens: List<String>): Boolean = tokens.any { it in this }
}
