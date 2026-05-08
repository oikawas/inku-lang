package app.inku.mobile.pipeline

internal object ServerDdlText {
    fun cleanModelText(text: String): String {
        return text.trim()
            .trim('`')
            .replace("<|turn>model", "", ignoreCase = true)
            .replace("<|turn>user", "", ignoreCase = true)
            .replace("<turn|>", "", ignoreCase = true)
            .replace(Regex("""<\|[^>]+>"""), "")
            .replace(Regex("""\n{3,}"""), "\n\n")
            .trim()
    }

    fun normalizeStage1DdlText(text: String): String {
        val cleaned = text.replace(Regex("""(?i)^\s*(出力|output)\s*[:：]\s*"""), "")
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
            .let(::normalizeDdlNumberNoise)
            .let(::dedupeDdlClauses)
            .trim()
    }

    fun normalizeDdlNumberNoise(text: String): String {
        return text.replace(Regex("""([一二三四五六七八九十百]+本)数を\1並べる"""), "$1並べる")
            .replace(Regex("""([一二三四五六七八九十百]+個)数を\1並べる"""), "$1並べる")
            .replace(Regex("""([一二三四五六七八九十百]+点)数を\1散らす"""), "$1散らす")
    }

    fun dedupeDdlClauses(text: String): String {
        val clauses = splitClauses(text)
        if (clauses.isEmpty()) return text
        val seen = mutableSetOf<String>()
        return clauses.filter { clause ->
            val key = clause.trim().trimEnd('。')
            seen.add(key)
        }.joinToString("") { if (it.endsWith("。")) it else "$it。" }
    }

    fun isUsableStage1Ddl(text: String): Boolean {
        if (text.isBlank()) return false
        if (text.contains("SELECT ", ignoreCase = true) || text.contains("```")) return false
        if (text.contains("FROM ", ignoreCase = true) && text.contains("WHERE ", ignoreCase = true)) return false
        return hasDrawableVocabulary(text)
    }

    fun hasDrawableVocabulary(text: String): Boolean {
        return text.containsAny("線", "円", "楕円", "弧", "四角", "三角", "多角", "点", "粒", "背景", "塗", "散ら", "並べ", "膜", "光", "香り", "雨", "雪", "月", "山", "紙片", "波")
    }

    fun ensurePlacement(text: String): String {
        val trimmed = text.trim().trimEnd('。')
        val hasPlacement = trimmed.containsAny("中央", "右上", "左上", "右下", "左下", "上から下", "左から右", "横に", "縦に", "散ら", "点々", "画面全体", "波打つ軌跡", "斜め", "放射", "円環", "同心円", "焦点")
        return if (hasPlacement) "$trimmed。" else "$trimmed。中央付近に置く。"
    }

    fun sanitizePlacementWords(text: String): String {
        return WebDdlSpec.sanitizePlacementWords(text)
    }

    fun splitClauses(text: String): List<String> {
        return Regex("""(?<=[。.!?])""").split(text).map { it.trim() }.filter { it.isNotBlank() }
    }

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }
}
