package app.inku.mobile.pipeline

/**
 * Which counts the description asked for outright, in either language.
 *
 * `ServerScoreSemantics.countHintFromDdl` answers "what is the count here" and stops at
 * the first match. This answers "which counts were asked for at all", which is what tells
 * a group written to order apart from one a density governor is free to thin.
 *
 * Mirrors `_explicit_counts_from_ddl` and `_count_follows_ddl_request` in
 * `inku_server/counts.py` (they moved out of `coerce/compose.py` when the expansion layer
 * began reading counts through the same module). The English side matches on word tokens,
 * never on substrings: on the server a substring marker for "one " once fired inside
 * "one hundred twenty" and killed exactly the count it was supposed to protect.
 */
internal object ServerScoreCounts {

    /** Above this, coerce stops expanding, and the prompt asks for a representative band instead. */
    const val LITERAL_COUNT_THRESHOLD = 240
    const val REPRESENTED_COUNT_MIN = 80
    const val REPRESENTED_COUNT_MAX = 120

    private val KANJI_NUMBERS = mapOf(
        "一" to 1, "二" to 2, "三" to 3, "四" to 4, "五" to 5,
        "六" to 6, "七" to 7, "八" to 8, "九" to 9,
        "十" to 10, "百" to 100, "千" to 1000,
    )

    private val ENGLISH_SMALL_NUMBERS = mapOf(
        "one" to 1, "two" to 2, "three" to 3, "four" to 4, "five" to 5,
        "six" to 6, "seven" to 7, "eight" to 8, "nine" to 9, "ten" to 10,
    )

    private val ENGLISH_COUNT_UNITS: Map<String, Int> = ENGLISH_SMALL_NUMBERS + mapOf(
        "eleven" to 11, "twelve" to 12, "thirteen" to 13, "fourteen" to 14, "fifteen" to 15,
        "sixteen" to 16, "seventeen" to 17, "eighteen" to 18, "nineteen" to 19,
        "twenty" to 20, "thirty" to 30, "forty" to 40, "fifty" to 50,
        "sixty" to 60, "seventy" to 70, "eighty" to 80, "ninety" to 90,
    )

    private val NUMBER_WORDS: Set<String> = ENGLISH_COUNT_UNITS.keys + setOf("hundred", "thousand", "and")

    private val JAPANESE_COUNT_PATTERN =
        Regex("""(\d{1,4}|[一二三四五六七八九十百千]{1,8})(?:本|個|つ(?!の方向)|点|枚)""")

    // Ruling B ([I-204], 2026-08-11): the English path reads numerals as well as number
    // words, and asks nothing of the noun that follows. The 32-word COUNTED_OBJECT_WORDS
    // table is gone on the server too; it had no other reader.
    private val COUNT_TOKEN_PATTERN = Regex("""[a-z]+|\d+""")
    private val CJK_PATTERN = Regex("""[぀-ヿ㐀-䶿一-鿿豈-﫿]""")
    private const val CJK_WINDOW = 12
    private const val NUMBER_EXPRESSION_PUNCTUATION = ".,/:"

    fun parseSmallJapaneseNumber(text: String): Int? {
        if (text.isEmpty()) return null
        if (text.all { it.isDigit() }) return text.toIntOrNull()
        if (text == "千") return 1000
        if (text.contains("千")) {
            val head = text.substringBefore("千")
            val tail = text.substringAfter("千")
            val value = (if (head.isEmpty()) 1 else KANJI_NUMBERS[head] ?: 1) * 1000
            return value + (parseSmallJapaneseNumber(tail) ?: 0)
        }
        if (text == "百") return 100
        if (text.length == 2 && text.endsWith("百")) return (KANJI_NUMBERS[text.substring(0, 1)] ?: 1) * 100
        if (text.contains("百")) {
            val head = text.substringBefore("百")
            val tail = text.substringAfter("百")
            val value = (if (head.isEmpty()) 1 else KANJI_NUMBERS[head] ?: 1) * 100
            return value + (parseSmallJapaneseNumber(tail) ?: 0)
        }
        if (text == "十") return 10
        if (text.length == 2 && text.endsWith("十")) return (KANJI_NUMBERS[text.substring(0, 1)] ?: 1) * 10
        if (text.contains("十")) {
            val head = text.substringBefore("十")
            val tail = text.substringAfter("十")
            val value = (if (head.isEmpty()) 1 else KANJI_NUMBERS[head] ?: 1) * 10
            return value + (if (tail.isEmpty()) 0 else KANJI_NUMBERS[tail] ?: 0)
        }
        if (text.length == 1) return KANJI_NUMBERS[text]
        return null
    }

    /**
     * Is this digit run a count, or a piece of some other number?
     *
     * Mirrors `_numeral_is_a_bare_count` in `counts.py`, condition for condition.
     * CJK within twelve characters means the numeral sits in Japanese text, where a
     * bare numeral is an angle or a fraction as often as it is a count; a digit
     * beside a decimal point, a slash, a colon or a percent sign belongs to that
     * number, not to a count.
     */
    private fun numeralIsABareCount(text: String, start: Int, end: Int): Boolean {
        val window = text.substring(maxOf(0, start - CJK_WINDOW), minOf(text.length, end + CJK_WINDOW))
        if (CJK_PATTERN.containsMatchIn(window)) return false
        if (start >= 2 && text[start - 1] in NUMBER_EXPRESSION_PUNCTUATION && text[start - 2].isDigit()) {
            return false
        }
        if (end < text.length) {
            if (text[end] == '%') return false
            if (text[end] in NUMBER_EXPRESSION_PUNCTUATION && end + 1 < text.length && text[end + 1].isDigit()) {
                return false
            }
        }
        return true
    }

    fun explicitCountsFromDdl(ddl: String?): Set<Int> {
        if (ddl.isNullOrEmpty()) return emptySet()
        val counts = mutableSetOf<Int>()

        for (match in JAPANESE_COUNT_PATTERN.findAll(ddl)) {
            parseSmallJapaneseNumber(match.groupValues[1])?.takeIf { it != 0 }?.let { counts.add(it) }
        }

        val text = ddl.lowercase().replace("-", " ")
        val tokens = COUNT_TOKEN_PATTERN.findAll(text).map { Triple(it.value, it.range.first, it.range.last + 1) }.toList()
        var index = 0
        while (index < tokens.size) {
            val (token, start, stop) = tokens[index]
            if (token.all { it.isDigit() }) {
                val value = token.toIntOrNull()
                if (value != null && value != 0 && numeralIsABareCount(text, start, stop)) counts.add(value)
                index += 1
                continue
            }
            if (token !in NUMBER_WORDS || token == "and") {
                index += 1
                continue
            }
            var end = index
            val phrase = mutableListOf<String>()
            while (end < tokens.size && tokens[end].first in NUMBER_WORDS) {
                phrase.add(tokens[end].first)
                end += 1
            }
            var total = 0
            var current = 0
            for (word in phrase) {
                when (word) {
                    "and" -> {}
                    "hundred" -> current = maxOf(current, 1) * 100
                    "thousand" -> {
                        total += maxOf(current, 1) * 1000
                        current = 0
                    }
                    else -> current += ENGLISH_COUNT_UNITS.getValue(word)
                }
            }
            if (total + current != 0) counts.add(total + current)
            index = end
        }
        return counts
    }

    /** Is this count the one the description asked for, literally or as its stand-in? */
    fun countFollowsDdlRequest(count: Int, requested: Set<Int>): Boolean {
        if (count in requested) return true
        if (count in REPRESENTED_COUNT_MIN..REPRESENTED_COUNT_MAX) {
            return requested.any { it >= LITERAL_COUNT_THRESHOLD }
        }
        return false
    }
}
