package app.inku.mobile.ui

// Chunk titles (DDL 27), the rule of the shared core's `chunk_title.rs`
// (web's `ddl-titles.ts`): a line that is only a bracketed name, 「灯台」 or
// "lighthouse" (or “lighthouse”), names the chunk of sentences after it. A
// title draws nothing, so a DDL view shows it as a heading and colours no word
// in it.

private val TitleBrackets = listOf("「" to "」", "\"" to "\"", "“" to "”")

/** The name a line gives when the whole line, without the spaces around it,
 *  is a title (empty for a title that ends a chunk); null for any other line.
 *  A name leaves out its own pair's characters only. */
internal fun ddlTitleName(line: String): String? {
    val trimmed = line.trim()
    for ((open, close) in TitleBrackets) {
        if (trimmed.length < open.length + close.length || !trimmed.startsWith(open) || !trimmed.endsWith(close)) continue
        val inner = trimmed.substring(open.length, trimmed.length - close.length)
        if (open !in inner && close !in inner && '\n' !in inner) return inner.trim()
    }
    return null
}

/** Where each title line stands in `text`, without its line break. */
internal fun ddlTitleLineSpans(text: String): List<IntRange> {
    val spans = mutableListOf<IntRange>()
    var start = 0
    for (line in text.split('\n')) {
        val content = line.removeSuffix("\r")
        if (ddlTitleName(content) != null) spans += start until start + content.length
        start += line.length + 1
    }
    return spans
}

/** `text` without its title lines. */
internal fun withoutDdlTitleLines(text: String): String =
    text.split('\n').filter { ddlTitleName(it) == null }.joinToString("\n")

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
