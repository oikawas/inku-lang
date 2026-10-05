package app.inku.mobile.ui

import app.inku.mobile.pipeline.InstructionLanguages
import org.json.JSONObject

/** Display arithmetic only. The compiler still owns the meaning of the instructions. */
data class RangeFraction private constructor(val numerator: Long, val denominator: Long) {
    val value: Float get() = numerator.toFloat() / denominator
    fun below(other: RangeFraction): Boolean = numerator * other.denominator < other.numerator * denominator

    companion object {
        fun of(numerator: Long, denominator: Long): RangeFraction? {
            if (numerator !in 0..1_000_000 || denominator !in 1..1_000_000) return null
            var a = numerator
            var b = denominator
            while (b != 0L) { val rest = a % b; a = b; b = rest }
            return RangeFraction(numerator / a, denominator / a)
        }

        fun parse(text: String, language: String): RangeFraction? {
            val ascii = if (language == "ja") buildString {
                text.forEach { append(when (it) {
                    in '０'..'９' -> '0' + (it - '０')
                    '．' -> '.'
                    '／' -> '/'
                    else -> it
                }) }
            } else text
            if (!Regex("[0-9]+(?:\\.[0-9]{1,6}|/[0-9]+)?").matches(ascii)) return null
            val slash = ascii.indexOf('/')
            val point = ascii.indexOf('.')
            return when {
                slash >= 0 -> of(ascii.substring(0, slash).toLongOrNull() ?: return null,
                    ascii.substring(slash + 1).toLongOrNull() ?: return null)
                point >= 0 -> of(ascii.replace(".", "").toLongOrNull() ?: return null,
                    (1..ascii.length - point - 1).fold(1L) { value, _ -> value * 10 })
                else -> of(ascii.toLongOrNull() ?: return null, 1)
            }
        }
    }
}

data class DdlRangeBounds(
    val left: RangeFraction, val top: RangeFraction,
    val right: RangeFraction, val bottom: RangeFraction,
) {
    val valid: Boolean get() = listOf(left, top, right, bottom).all { it.numerator <= it.denominator } &&
        left.below(right) && top.below(bottom)
}

internal data class CompositionRangeName(val key: String, val ja: String, val en: String, val bounds: DdlRangeBounds) {
    fun words(language: String): String = if (language == "en") en else ja
}

/** The table is always supplied by core, never copied into the Android source. */
internal class CompositionRangeTable(val ranges: List<CompositionRangeName>) {
    fun at(bounds: DdlRangeBounds): CompositionRangeName? = ranges.firstOrNull { it.bounds == bounds }
    fun matches(name: String, language: String, bounds: DdlRangeBounds?): Boolean =
        bounds != null && ranges.any { it.bounds == bounds && it.words(language).equals(name, ignoreCase = language == "en") }

    companion object {
        val Empty = CompositionRangeTable(emptyList())
        fun load(fetch: () -> String): CompositionRangeTable = try {
            val root = JSONObject(fetch())
            require(root.getString("schema") == "inku.composition-ranges.v1")
            val entries = root.getJSONArray("ranges")
            CompositionRangeTable((0 until entries.length()).map { index ->
                val entry = entries.getJSONObject(index)
                val words = entry.getJSONObject("words")
                val array = entry.getJSONArray("bounds")
                require(array.length() == 4)
                val values = (0..3).map {
                    val pair = array.getJSONArray(it)
                    require(pair.length() == 2)
                    requireNotNull(RangeFraction.of(pair.getLong(0), pair.getLong(1)))
                }
                val bounds = DdlRangeBounds(values[0], values[1], values[2], values[3])
                require(bounds.valid)
                CompositionRangeName(entry.getString("key"), words.getString("ja"), words.getString("en"), bounds)
            })
        } catch (_: Exception) { Empty } catch (_: LinkageError) { Empty }
    }
}

internal data class DdlNamedRange(
    val start: Int, val end: Int, val language: String, val name: String,
    val article: String, val numbers: String, val bounds: DdlRangeBounds?, val foldable: Boolean,
) {
    val label: String get() = article + name
}

private const val JapaneseSpace = "[ \\t\\u3000]*"
private const val EnglishSpace = "[ \\t]*"
private val JapaneseNumbers = Regex("[（(]${JapaneseSpace}横${JapaneseSpace}([^-〜～~－、，,（）()]+)[-〜～~－]([^、，,（）()]+)[、，,]${JapaneseSpace}縦${JapaneseSpace}([^-〜～~－（）()]+)[-〜～~－]([^（）()]+)[）)]")
private val EnglishNumbers = Regex("\\(${EnglishSpace}horizontal[ \\t]+(.+?)[ \\t]+to[ \\t]+(.+?),[ \\t]*vertical[ \\t]+(.+?)[ \\t]+to[ \\t]+(.+?)${EnglishSpace}\\)", RegexOption.IGNORE_CASE)
private val EnglishNamed = Regex("\\b(?:at|in|on)[ \\t]+([^,;.!?\\n\\r()（）]+?)[ \\t]*(\\(horizontal[^()\\n\\r]*\\))", RegexOption.IGNORE_CASE)
private val OldMark = Regex("^(?:［構図］|\\[composition\\])[ \\t\\u3000]*", RegexOption.IGNORE_CASE)

internal fun rangeNumbersBounds(numbers: String, language: String): DdlRangeBounds? {
    val match = (if (language == "en") EnglishNumbers else JapaneseNumbers).matchEntire(numbers) ?: return null
    val values = (1..4).map { RangeFraction.parse(match.groupValues[it].trim(), language) ?: return null }
    return DdlRangeBounds(values[0], values[2], values[1], values[3]).takeIf { it.valid }
}

internal fun ddlNamedRanges(source: String, table: CompositionRangeTable): List<DdlNamedRange> {
    if (table.ranges.isEmpty()) return emptyList()
    val language = InstructionLanguages.resolve(source, "auto")
    fun range(start: Int, end: Int, rawName: String, numbers: String): DdlNamedRange? {
        var words = rawName.trim().replace(OldMark, "").trim()
        val article = if (language == "en" && words.startsWith("the ", ignoreCase = true)) {
            val prefix = words.take(4)
            words = words.drop(4).replace(OldMark, "").trim()
            prefix
        } else ""
        if (words.isEmpty()) return null
        val bounds = rangeNumbersBounds(numbers, language)
        return DdlNamedRange(start, end, language, words, article, numbers, bounds,
            table.matches(words, language, bounds))
    }
    return if (language == "en") EnglishNamed.findAll(source).mapNotNull { match ->
        val words = match.groups[1]!!
        range(words.range.first, match.range.last + 1, words.value, match.groupValues[2])
    }.toList() else JapaneseNumbers.findAll(source).mapNotNull { match ->
        val following = source.substring(match.range.last + 1).trimStart(' ', '\t', '\u3000')
        if (!following.startsWith("に")) return@mapNotNull null
        val stop = source.substring(0, match.range.first).indexOfLast {
            it in "、，,を。．.!！?？\n\r）)（(；;"
        }
        var start = stop + 1
        while (start < match.range.first && source[start] in " \t\u3000") start++
        range(start, match.range.last + 1, source.substring(start, match.range.first), match.value)
    }.toList()
}

internal data class RangeDisplaySpan(
    val range: DdlNamedRange, val start: Int, val nameEnd: Int, val end: Int, val folded: Boolean,
)
internal data class RangeDisplay(val text: String, val spans: List<RangeDisplaySpan>)

internal fun displayDdlRanges(source: String, table: CompositionRangeTable, expandedStart: Int? = null): RangeDisplay {
    val spans = mutableListOf<RangeDisplaySpan>()
    val display = buildString {
        var cursor = 0
        ddlNamedRanges(source, table).forEach { range ->
            append(source.substring(cursor, range.start))
            val start = length
            val folded = range.foldable && range.start != expandedStart
            if (folded || range.start == expandedStart) append(range.label) else {
                val original = source.substring(range.start, range.end)
                append(original.substringBefore(range.numbers))
            }
            val nameEnd = length
            if (!folded) append(range.numbers)
            spans += RangeDisplaySpan(range, start, nameEnd, length, folded)
            cursor = range.end
        }
        append(source.substring(cursor))
    }
    return RangeDisplay(display, spans)
}

/** One in-place editor. Outside this span the source bytes are retained verbatim. */
internal data class DdlRangeEdit(
    val before: String, val after: String, val range: DdlNamedRange,
    val numbers: String, val source: String, val lastValidBounds: DdlRangeBounds?, val valid: Boolean,
) {
    fun update(value: String, table: CompositionRangeTable): DdlRangeEdit {
        val bounds = rangeNumbersBounds(value, range.language)
        val name = bounds?.let { table.at(it)?.words(range.language) } ?: range.name
        val updated = before + range.article + name + (if (range.language == "en") " " else "") + value + after
        return copy(range = range.copy(name = name), numbers = value, source = updated,
            lastValidBounds = bounds ?: lastValidBounds, valid = bounds != null)
    }

    companion object {
        fun open(source: String, range: DdlNamedRange) = DdlRangeEdit(
            source.substring(0, range.start), source.substring(range.end), range,
            range.numbers, source, range.bounds, range.bounds != null,
        )
    }
}

data class DdlRangePreview(val source: String, val bounds: DdlRangeBounds)
internal data class RangeFrame(val left: Float, val top: Float, val right: Float, val bottom: Float)

/** Coordinates follow the fitted image, including letterboxing and presentation rotation. */
internal fun rangeFrame(bounds: DdlRangeBounds, width: Float, height: Float, imageWidth: Float,
    imageHeight: Float, rotationDegrees: Int = 0): RangeFrame {
    val rotation = ((rotationDegrees % 360) + 360) % 360
    val l = bounds.left.value; val t = bounds.top.value; val r = bounds.right.value; val b = bounds.bottom.value
    val rotated = when (rotation) {
        90 -> RangeFrame(1 - b, l, 1 - t, r)
        180 -> RangeFrame(1 - r, 1 - b, 1 - l, 1 - t)
        270 -> RangeFrame(t, 1 - r, b, 1 - l)
        else -> RangeFrame(l, t, r, b)
    }
    val scale = minOf(width / imageWidth, height / imageHeight)
    val w = imageWidth * scale; val h = imageHeight * scale
    val x = (width - w) / 2; val y = (height - h) / 2
    return RangeFrame(x + w * rotated.left, y + h * rotated.top, x + w * rotated.right, y + h * rotated.bottom)
}
