package app.inku.mobile.pipeline

import java.math.BigInteger
import java.security.MessageDigest

internal data class DdlFilterProfile(
    val intensity: Int,
    val tags: Set<String>,
    val mode: String,
)

internal data class DdlFilterCandidate(
    val text: String,
    val tags: Set<String>,
)

internal object WebDdlExpander {
    private val jaExpansionMarkers = setOf(
        "右半分の斜めの帯",
        "左下から右上へ",
        "波打つ軌跡に沿って",
        "左下の焦点から三つ",
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
        "縄の撚り",
        "透明な膜",
        "薄い反射",
        "消える線",
        "柔らかな光",
        "香りの層",
        "開花を待つ蕾",
        "五感の気配",
    )

    private val jaColors = listOf("赤", "青", "緑", "白", "黒", "灰")
    private val jaColorWord = mapOf("赤" to "赤い", "青" to "青い", "緑" to "緑の", "白" to "白い", "黒" to "黒い", "灰" to "灰色の")

    fun expandIntermediateDdl(ddl: String, contextText: String? = null): String {
        val sanitized = avoidGrayBackground(WebDdlSpec.sanitizePlacementWords(ddl).trim())
        if (sanitized.isBlank()) return sanitized
        if (jaExpansionMarkers.any { it in sanitized }) return sanitized

        val reframed = reframeStaticCenter(sanitized)
        val sentences = splitSentences(reframed)
        val structural = mutableListOf<String>()
        val mainColor = dominantColor(reframed)
        val contrastColor = contrastColor(reframed)
        val context = "${contextText.orEmpty()}\n$reframed"
        val profile = profile(context)

        if (reframed.containsAny("円", "点", "粒", "星", "楕円", "四角")) {
            structural += "${mainColor}右上がりの小さな楕円を右半分の斜めの帯に三個並べる。横長にする。"
            structural += "${mainColor}短い線を左下から右上へ三本散らす。細かく震える。"
        }
        if (reframed.containsAny("散らす", "点々", "舞", "漂", "雪", "雨")) {
            structural += "${mainColor}右下がりの小さな楕円を波打つ軌跡に沿って七個散らす。ゆっくり揺れる。"
        }
        if ("線" in reframed) {
            structural += "${contrastColor}細い斜め線を右上がりに三本並べる。細かく震える。"
        }
        if (reframed.containsAny("弧", "円", "波", "水", "月", "中心")) {
            structural += "${contrastColor}細い弧を左下の焦点から三つ広げる。半径は0.11。"
        }
        val roofPressureContext = context.containsAny("低い雲", "押し沈", "屋根")
        if (context.containsAny("山", "尖", "針葉樹", "頂", "鋭")) {
            structural += "${mainColor}細い三角を上端寄りの焦点に二つ置く。少し傾ける。"
        }
        if (context.containsAny("葉", "花びら", "羽", "紙片", "破片", "舟")) {
            structural += "${mainColor}細い右上がりの楕円を葉片として波打つ軌跡に沿って五個散らす。"
        }
        if (!roofPressureContext && context.containsAny("扉", "窓", "箱", "街", "部屋", "格子")) {
            structural += "${contrastColor}回転した細い四角を余白の切片として右半分に三つ散らす。"
        }
        if (roofPressureContext) {
            structural += "${contrastColor}薄い斜め線を上端から下へ三本置く。低い重さとしてゆっくり揺れる。"
        }
        if (context.containsAny("膜", "透明", "霞", "霧", "靄", "気配", "余韻")) {
            structural += "${mainColor}薄い水彩の楕円を透明な膜として右半分に三つ重ねる。境界が滲む。"
        }
        if (context.containsAny("反射", "映り")) {
            structural += "${contrastColor}薄い反射の線を波打つ軌跡に沿って五本散らす。ゆっくり揺れる。"
        }
        if (context.containsAny("消え", "薄れ", "遠ざか")) {
            structural += "${contrastColor}消える線を左下から右上へ五本散らす。細かく震える。"
        }
        if (context.containsAny("陽光", "光", "日差し", "温", "柔ら")) {
            structural += "白い薄い水彩の横長の楕円を柔らかな光として上端寄りに三つ重ねる。境界が滲む。"
        }
        if (context.containsAny("香", "匂", "沈丁花")) {
            structural += "緑の小さな楕円を香りの層として波打つ軌跡に沿って七個散らす。ゆっくり揺れる。"
        }
        if (context.containsAny("蕾", "つぼみ", "開花", "春")) {
            structural += "赤い右上がりの小さな楕円を開花を待つ蕾として右半分の斜めの帯に五個散らす。"
        }
        if (context.containsAny("五感", "気配", "訪れ")) {
            structural += "白い薄い弧を五感の気配として左下の焦点から三つ広げる。半径は0.14。"
        }
        if (context.containsAny("人", "人物", "村人", "老人", "顔", "視線", "動物", "鳥", "魚", "熊", "群れ")) {
            structural += "${contrastColor}細い余白線を存在の重心として右上の焦点へ二本引く。細かく震える。"
            structural += "${mainColor}薄い弧を輪郭の密度として左下の焦点から二つ置く。半径は0.09。"
        }

        val music = listOf(
            DdlFilterCandidate("${contrastColor}細い線を対位法の反行として右下がりに二本並べる。細かく震える。", setOf("line", "music", "contrast")),
            DdlFilterCandidate("${contrastColor}細い弧を倍音列として右下の焦点から三つ並べる。半径は0.07。", setOf("music", "water", "soft")),
            DdlFilterCandidate("${mainColor}短い線を輪唱のずれとして左から右へ四本並べる。ゆっくり揺れる。", setOf("particle", "music", "line")),
        )
        val painting = listOf(
            DdlFilterCandidate("${contrastColor}細い線を一点透視法として右上の焦点へ向けて三本引く。", setOf("space", "line", "geometry")),
            DdlFilterCandidate("${contrastColor}細い横線を遠近法の奥行きとして上へ細かく三本並べる。", setOf("space", "line")),
            DdlFilterCandidate("黒い細筆の細い線を素描の下線として左から右へ三本並べる。細かく震える。", setOf("line", "quiet")),
            DdlFilterCandidate("${contrastColor}鉛筆の細い線を余白線として上端寄りに二本並べる。細かく震える。", setOf("line", "quiet", "soft")),
            DdlFilterCandidate("${mainColor}クレヨンの短い線を擦れとして右半分の斜めの帯に七本散らす。", setOf("particle", "dense", "soft")),
            DdlFilterCandidate("${contrastColor}ロットリングの細い線を均一線として左から右へ五本並べる。", setOf("line", "geometry", "contrast")),
            DdlFilterCandidate("${contrastColor}縄の横線を撚りとして下端寄りに一本引く。ゆっくり揺れる。", setOf("line", "dense", "contrast")),
            DdlFilterCandidate("${mainColor}回転した小さな四角を点描として右半分の斜めの帯に十三個散らす。", setOf("particle", "dense", "geometry")),
            DdlFilterCandidate("${mainColor}太筆の短い線を油絵の厚塗りとして横に三本並べる。", setOf("dense", "contrast")),
            DdlFilterCandidate("${contrastColor}薄い水彩の楕円を左上に二つ重ねる。境界が滲む。", setOf("water", "soft", "quiet")),
            DdlFilterCandidate("赤・青・緑・灰の回転した小さな四角をパッチワークとして格子状に六個並べる。", setOf("geometry", "dense")),
            DdlFilterCandidate("${contrastColor}チョークの横線をフレスコの下地として画面下に三本並べる。境界が滲む。", setOf("space", "line", "soft")),
            DdlFilterCandidate("黒い細筆の縦線を水墨の濃淡として左から右へ三本並べる。境界が滲む。", setOf("water", "contrast", "quiet")),
            DdlFilterCandidate("白い薄い水彩の楕円を五感の気配として右上に二つ重ねる。境界が滲む。", setOf("sensory", "soft", "quiet")),
        )
        val structuralCandidates = structural.map { DdlFilterCandidate(it, structuralTags(it)) }
        val (structuralCount, musicCount, paintingCount) = categoryPlan(profile, structuralCandidates.isNotEmpty())
        val selected = selectCategory(structuralCandidates, structuralCount, profile, context, modeSalt(profile, "ja-structure")) +
            selectCategory(music, musicCount, profile, context, modeSalt(profile, "ja-music")) +
            selectCategory(painting, paintingCount, profile, context, modeSalt(profile, "ja-painting"))
        return joinSentences(sentences + limitCentered(selected))
    }

    private fun splitSentences(text: String): List<String> = Regex("(?<=。)").split(text.trim()).map { it.trim() }.filter { it.isNotBlank() }

    private fun joinSentences(sentences: List<String>): String = sentences.joinToString("") { if (it.endsWith("。")) it else "$it。" }

    private fun avoidGrayBackground(text: String): String = text.replace(Regex("背景を灰(?:色)?で塗りつぶす。?"), "背景を白で塗りつぶす。")

    private fun profile(text: String): DdlFilterProfile {
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
        if (text.containsAny("影", "痕跡", "埃", "足跡", "残", "冷え", "錆") && mode != "single_tension") mode = "field_and_interruption"
        return DdlFilterProfile(intensity, tags, mode)
    }

    private fun selectCategory(candidates: List<DdlFilterCandidate>, count: Int, profile: DdlFilterProfile, text: String, salt: String): List<String> {
        if (count <= 0) return emptyList()
        val preferredTags = profile.tags.intersect(setOf("atmosphere", "sensory", "presence"))
        if (preferredTags.isNotEmpty()) {
            val matched = candidates.filter { it.tags.intersect(preferredTags).isNotEmpty() }
            if (matched.isNotEmpty()) return pick(matched.map { it.text }, count, text, salt)
        }
        val matched = if (profile.intensity <= 1) {
            candidates.filter { it.tags.intersect(setOf("quiet", "soft", "water")).isNotEmpty() }
        } else {
            candidates.filter { it.tags.intersect(profile.tags).isNotEmpty() }
        }
        return pick((matched.ifEmpty { candidates }).map { it.text }, count, text, salt)
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

    private fun structuralTags(text: String): Set<String> {
        val tags = mutableSetOf("particle", "line", "water", "space")
        val lower = text.lowercase()
        if (listOf("透明な膜", "薄い反射", "消える線", "transparent membrane", "faint reflection", "fading lines").any { it in text || it in lower }) tags += setOf("atmosphere", "soft")
        if (listOf("柔らかな光", "香りの層", "開花を待つ蕾", "五感の気配", "soft light", "scent layer", "waiting buds", "five-sense presence").any { it in text || it in lower }) tags += setOf("sensory", "soft")
        if (listOf("存在の重心", "輪郭の密度", "presence weight", "contour density").any { it in text || it in lower }) tags += setOf("presence", "space")
        return tags
    }

    private fun modeSalt(profile: DdlFilterProfile, category: String): String = "${profile.mode}:$category"

    private fun limitCentered(items: List<String>, maxCount: Int = 1): List<String> {
        val centeredTokens = listOf("中心", "中央", "放射状", "同心円状")
        var centeredCount = 0
        val result = mutableListOf<String>()
        for (item in items) {
            if (centeredTokens.any { it in item }) {
                if (centeredCount >= maxCount) continue
                centeredCount += 1
            }
            result += item
        }
        return result
    }

    private fun dynamicFocus(text: String): String {
        val focuses = listOf("右上の焦点", "左上の焦点", "右下の焦点", "左下の焦点", "上端寄りの焦点", "右半分の焦点")
        return focuses[seedModulo(text, "ja-focus", focuses.size)]
    }

    private fun reframeStaticCenter(ddl: String): String {
        val focus = dynamicFocus(ddl)
        var result = ddl
        for (word in listOf("画面中央", "中央付近", "中心付近", "中央", "中心")) {
            result = result.replace(word, focus)
        }
        return result
    }

    private fun dominantColor(ddl: String): String {
        val body = ddl.replace(Regex("背景を[^\\u3002。]*。?"), "")
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

    private fun contrastColor(ddl: String): String = when {
        "背景を黒" in ddl || "暗い背景" in ddl -> "白い"
        ddl.containsAny("春", "桜", "花", "蕾", "温", "陽光") -> "緑の"
        ddl.containsAny("夜", "月", "水", "雨", "霧", "冷") -> "白い"
        else -> "黒い"
    }

    private fun pick(items: List<String>, count: Int, text: String, salt: String): List<String> {
        if (count <= 0 || items.isEmpty()) return emptyList()
        return items.sortedBy { seedHex("$text:$it", salt) }.take(count.coerceAtMost(items.size))
    }

    private fun seedHex(text: String, salt: String): String = MessageDigest.getInstance("SHA-256")
        .digest("$salt:$text".toByteArray())
        .joinToString("") { "%02x".format(it) }

    private fun seedModulo(text: String, salt: String, modulo: Int): Int {
        val digest = MessageDigest.getInstance("SHA-256").digest("$salt:$text".toByteArray()).copyOfRange(0, 8)
        return BigInteger(1, digest).mod(BigInteger.valueOf(modulo.toLong())).toInt()
    }

    private fun String.containsAny(vararg tokens: String): Boolean = tokens.any { it in this }
}
