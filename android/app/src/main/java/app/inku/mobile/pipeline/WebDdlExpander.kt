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

internal data class VariationPlan(
    val amplitude: String,
    val seed: Long,
    val offsets: List<Pair<String, Int>>,
) {
    val axes: List<String> get() = offsets.map { it.first }

    fun offset(axis: String): Int? = offsets.firstOrNull { it.first == axis }?.second

    fun restrictedTo(axis: String): VariationPlan =
        VariationPlan(amplitude, seed, offsets.filter { it.first == axis })
}

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

    private val focusShortJa = mapOf(
        "upper_right" to "右上",
        "upper_left" to "左上",
        "lower_right" to "右下",
        "lower_left" to "左下",
        "upper_edge" to "上端",
        "right_half" to "右半分",
    )

    private val focusShortEn = mapOf(
        "upper_right" to "upper right",
        "upper_left" to "upper left",
        "lower_right" to "lower right",
        "lower_left" to "lower left",
        "upper_edge" to "upper edge",
        "right_half" to "right half",
    )

    private val VARIATION_AMPLITUDES = listOf("small", "medium", "large")

    // Focus is the only axis. The six others (type swap, count, touch, colour,
    // composition family, type family) all varied sentences Stage 1.5 appended on
    // its own, and those went away with the staffage level (v2.11.0).
    private const val AXIS_FOCUS = "focus"

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

    fun expandIntermediateDdl(
        ddl: String,
        lang: String = "ja",
        contextText: String? = null,
        varySeed: Long? = null,
        enablePlugins: Boolean = true,
        pluginInstructionsPresent: Boolean = false,
        focus: String? = null,
        variationAmplitude: String? = null,
        variationSeed: Long? = null,
        variationReport: MutableMap<String, Any>? = null,
    ): String {
        val sanitized = applyNaturePluginMacros(
            avoidGrayBackground(WebDdlSpec.sanitizePlacementWords(ddl).trim(), lang),
            lang = lang,
            enablePlugins = enablePlugins,
        )
        if (sanitized.isBlank()) return sanitized

        fun runExpand(plan: VariationPlan?, decisions: MutableMap<String, Any>?): String {
            return if (lang == "en") {
                expandEn(
                    sanitized,
                    contextText = contextText,
                    varySeed = varySeed,
                    pluginInstructionsPresent = pluginInstructionsPresent,
                    focus = focus,
                    plan = plan,
                    decisions = decisions,
                )
            } else {
                expandJa(
                    sanitized,
                    contextText = contextText,
                    varySeed = varySeed,
                    pluginInstructionsPresent = pluginInstructionsPresent,
                    focus = focus,
                    plan = plan,
                    decisions = decisions,
                )
            }
        }

        val plan = buildVariationPlan(variationAmplitude, variationSeed)
        val baseDecisions = mutableMapOf<String, Any>()
        val baseText = runExpand(null, baseDecisions)

        if (variationReport != null) {
            variationReport["resolved_focus"] = baseDecisions[AXIS_FOCUS] ?: ""
            variationReport["moved_axes"] = emptyList<Map<String, String>>()
            variationReport["category_counts"] = baseDecisions["category_counts"] ?: listOf(0, 0, 0)
        }

        val effectivePlan = if (plan != null) {
            effectiveVariationPlan(plan, baseText = baseText) { p, d ->
                runExpand(p, d)
            }
        } else null

        if (effectivePlan == null) {
            return baseText
        }

        val decisions = mutableMapOf<String, Any>()
        val text = runExpand(effectivePlan, decisions)
        if (variationReport != null) {
            variationReport["resolved_focus"] = decisions[AXIS_FOCUS] ?: ""
            variationReport["category_counts"] = decisions["category_counts"] ?: listOf(0, 0, 0)
            variationReport["moved_axes"] = variationMovedAxes(
                effectivePlan,
                baseText = baseText,
                baseDecisions = baseDecisions,
                lang = lang,
            ) { p, d -> runExpand(p, d) }
        }
        return text
    }

    private fun expandJa(
        ddl: String,
        contextText: String?,
        varySeed: Long?,
        pluginInstructionsPresent: Boolean,
        focus: String?,
        plan: VariationPlan?,
        decisions: MutableMap<String, Any>?,
    ): String {
        if (pluginInstructionsPresent ||
            hasExplicitNumericRegions(ddl, "ja") ||
            jaExpansionMarkers.any { it in ddl }
        ) {
            return ddl
        }

        val focusId = resolveFocusId(ddl, focus, plan, lang = "ja")
        if (decisions != null) {
            decisions[AXIS_FOCUS] = focusId
        }
        val reframed = reframeStaticCenterJa(ddl, focusId)
        // Stage 1.5 reframes the focus and stops. The candidate pool that used to
        // append structural / musical / painterly sentences here was staffage: it
        // wrote lines the description never asked for (folded away in v2.11.0).
        return reframed
    }

    private fun expandEn(
        ddl: String,
        contextText: String?,
        varySeed: Long?,
        pluginInstructionsPresent: Boolean,
        focus: String?,
        plan: VariationPlan?,
        decisions: MutableMap<String, Any>?,
    ): String {
        val lower = ddl.lowercase()
        if (pluginInstructionsPresent ||
            hasExplicitNumericRegions(ddl, "en") ||
            enExpansionMarkers.any { it in lower }
        ) {
            return ddl
        }

        val focusId = resolveFocusId(ddl, focus, plan, lang = "en")
        if (decisions != null) {
            decisions[AXIS_FOCUS] = focusId
        }
        val reframed = reframeStaticCenterEn(ddl, focusId)
        // Stage 1.5 reframes the focus and stops. The candidate pool that used to
        // append structural / musical / painterly sentences here was staffage: it
        // wrote lines the description never asked for (folded away in v2.11.0).
        return reframed
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

    private val NATURE_PLUGIN_RE = Regex("""Nature\.(風|うねり|無風|wind|undulation|stillness|calm)""", RegexOption.IGNORE_CASE)

    private fun naturePluginTerms(text: String): Set<String> {
        val terms = mutableSetOf<String>()
        for (match in NATURE_PLUGIN_RE.findAll(text)) {
            val term = match.groupValues[1].lowercase()
            when (term) {
                "風", "wind" -> terms.add("wind")
                "うねり", "undulation" -> terms.add("undulation")
                "無風", "stillness", "calm" -> terms.add("stillness")
            }
        }
        return terms
    }

    private fun dropNaturePluginSentences(text: String, lang: String): String {
        val sentences = splitSentences(text, lang)
        val kept = sentences.filter { !NATURE_PLUGIN_RE.containsMatchIn(it) }
        if (kept.isNotEmpty()) {
            return joinSentences(kept, lang)
        }
        return ""
    }

    private fun applyNaturePluginMacros(ddl: String, lang: String, enablePlugins: Boolean): String {
        if (!enablePlugins) return ddl
        val terms = naturePluginTerms(ddl)
        if (terms.isEmpty()) return ddl
        val base = dropNaturePluginSentences(ddl, lang)
        val macro = mutableListOf<String>()
        if (lang == "en") {
            if ("stillness" in terms) {
                macro.add("Use no variation. Use no placement path; keep the repeated placement still.")
            } else {
                if ("wind" in terms) {
                    macro.add("Set repeated placement left to right in horizontal strata. Swaying slowly.")
                }
                if ("undulation" in terms) {
                    macro.add("Set repeated placement along an undulating trace. Broad slow swaying.")
                }
            }
        } else {
            if ("stillness" in terms) {
                macro.add("全体の揺らぎをなしにする。配置軌跡は使わず静止させる。")
            } else {
                if ("wind" in terms) {
                    macro.add("全体の反復配置を左から右への横の帯に沿わせる。ゆっくり揺れる。")
                }
                if ("undulation" in terms) {
                    macro.add("全体の反復配置を波打つ軌跡に沿わせる。揺らぎは大きくゆっくり。")
                }
            }
        }
        val joinedMacro = if (macro.isNotEmpty()) joinSentences(macro, lang) else ""
        return if (base.isNotEmpty() && joinedMacro.isNotEmpty()) {
            joinSentences(listOf(base, joinedMacro), lang)
        } else {
            base.ifEmpty { joinedMacro.ifEmpty { ddl } }
        }
    }

    private fun variationBaseOffset(amplitude: String, seed: Long, axis: String): Int {
        return 1 + (seed("$amplitude:${java.lang.Long.toUnsignedString(seed)}:$axis", "variation-offset") % 97UL).toInt()
    }

    /**
     * Focus is the one axis left. The others -- type swap, count, touch, colour,
     * composition family, type family -- all varied sentences Stage 1.5 invented,
     * and those went away with the staffage level (v2.11.0). The amplitude still
     * reaches the output: it is part of the offset key, so small / medium / large
     * resolve the focus differently for the same seed.
     */
    private fun buildVariationPlan(amplitude: String?, seed: Long?): VariationPlan? {
        if (amplitude == null || amplitude !in VARIATION_AMPLITUDES || seed == null) return null
        return VariationPlan(
            amplitude,
            seed,
            listOf(AXIS_FOCUS to variationBaseOffset(amplitude, seed, AXIS_FOCUS)),
        )
    }

    private const val VARIATION_OFFSET_TRIES = 8

    private fun effectiveVariationPlan(
        plan: VariationPlan,
        baseText: String,
        run: (VariationPlan, MutableMap<String, Any>?) -> String,
    ): VariationPlan? {
        val resolved = mutableListOf<Pair<String, Int>>()
        val baseOffset = variationBaseOffset(plan.amplitude, plan.seed, AXIS_FOCUS)
        for (step in 0 until VARIATION_OFFSET_TRIES) {
            val offset = baseOffset + step
            val trial = VariationPlan(plan.amplitude, plan.seed, listOf(AXIS_FOCUS to offset))
            if (run(trial, null) != baseText) {
                resolved.add(AXIS_FOCUS to offset)
                break
            }
        }
        if (resolved.isEmpty()) return null
        return VariationPlan(plan.amplitude, plan.seed, resolved)
    }

    private fun shiftChoice(default: String, pool: List<String>, offset: Int): String {
        val unique = pool.distinct()
        val others = unique.filter { it != default }
        if (others.isEmpty()) return default
        return others[offset % others.size]
    }




    private fun resolveFocusId(text: String, focus: String?, plan: VariationPlan? = null, lang: String): String {
        if (focus in FOCUS_IDS) return focus!!
        val salt = if (lang == "en") "en-focus" else "ja-focus"
        val defaultFocus = FOCUS_IDS[(seed(text, salt) % FOCUS_IDS.size.toULong()).toInt()]
        val offset = plan?.offset(AXIS_FOCUS)
        if (offset == null) return defaultFocus
        return shiftChoice(defaultFocus, FOCUS_IDS, offset)
    }



    private fun axisValue(axis: String, decisions: Map<String, Any>, lang: String, joiner: String): String {
        val value = decisions[axis]
        if (axis == AXIS_FOCUS) {
            val words = if (lang == "en") focusShortEn else focusShortJa
            return words[value?.toString()].orEmpty().ifEmpty { value?.toString().orEmpty() }
        }
        if (value is List<*>) {
            return value.filterNotNull().map { it.toString() }.filter { it.isNotBlank() }.joinToString(joiner)
        }
        return value?.toString().orEmpty()
    }

    private fun variationMovedAxes(
        plan: VariationPlan,
        baseText: String,
        baseDecisions: Map<String, Any>,
        lang: String,
        expand: (VariationPlan, MutableMap<String, Any>) -> String,
    ): List<Map<String, String>> {
        val joiner = if (lang == "en") ", " else "・"
        val moved = mutableListOf<Map<String, String>>()
        for (axis in plan.axes) {
            val soloDecisions = mutableMapOf<String, Any>()
            val soloText = expand(plan.restrictedTo(axis), soloDecisions)
            if (soloText == baseText) continue

            val before = axisValue(axis, baseDecisions, lang, joiner)
            val after = axisValue(axis, soloDecisions, lang, joiner)
            moved.add(mapOf("axis" to axis, "from" to before, "to" to after))
        }
        return moved
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
}

