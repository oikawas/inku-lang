package app.inku.mobile.ui

import app.inku.mobile.pipeline.NativePipelineBridge
import org.json.JSONArray

// DDL title lines are read from the shared core's `ddl_title_lines` through JNI.

/** Where each title line stands in `text`, without its line break. */
internal fun ddlTitleLineSpans(text: String): List<IntRange> = runCatching {
    val lines = JSONArray(NativePipelineBridge.ddlTitleLines(text))
    val scalarCount = text.codePointCount(0, text.length)
    var scalar = 0
    var utf16 = 0
    fun advance(target: Int): Int {
        val bounded = target.coerceIn(0, scalarCount)
        require(bounded >= scalar)
        while (scalar < bounded) {
            utf16 += Character.charCount(text.codePointAt(utf16))
            scalar++
        }
        return utf16
    }
    (0 until lines.length()).map { index ->
        val line = lines.getJSONArray(index)
        val start = advance(line.getInt(0))
        val end = advance(line.getInt(1))
        start until end
    }
}.getOrDefault(emptyList())

/** `text` without its title lines. */
internal fun withoutDdlTitleLines(text: String): String =
    runCatching { NativePipelineBridge.withoutDdlTitleLines(text) }.getOrDefault(text)

/** One coloured vocabulary word in a DDL view: `token` indexes the word list. */
internal data class DdlKeywordSpan(val token: Int, val start: Int, val end: Int)

/** Every place a vocabulary word is coloured in `text`, in list order, the
 *  first word to reach a character keeping it, and none inside a title line. */
internal fun ddlKeywordSpans(text: String, words: List<String>): List<DdlKeywordSpan> {
    if (text.isBlank()) return emptyList()
    val occupied = BooleanArray(text.length)
    ddlTitleLineSpans(text).forEach { span -> for (i in span) occupied[i] = true }
    val spans = mutableListOf<DdlKeywordSpan>()
    words.forEachIndexed { index, word ->
        if (word.isBlank()) return@forEachIndexed
        var start = text.indexOf(word)
        while (start >= 0) {
            val end = start + word.length
            if ((start until end).none { occupied[it] }) {
                spans += DdlKeywordSpan(index, start, end)
                for (i in start until end) occupied[i] = true
            }
            start = text.indexOf(word, end)
        }
    }
    return spans
}
