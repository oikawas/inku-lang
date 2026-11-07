package app.inku.mobile.render

import org.junit.Assert.assertEquals
import org.junit.Test

/** The allowance is counted without copying the SVG, and counts as the UTF-8 copy did. */
class SvgOutputLimitLengthTest {
    @Test
    fun theCountMatchesTheUtf8CopyAtEveryBoundary() {
        val samples = listOf(
            "<svg/>",
            "<text>灯台と夕立</text>",
            "<text>🎨 🌸</text>",
            "lone \uD83D surrogate",
            "trailing \uDC00",
            "é ß ü",
            "",
        )
        for (text in samples) {
            val bytes = text.toByteArray(Charsets.UTF_8).size.toLong()
            for (limit in 0L..bytes + 1) {
                assertEquals("$text at $limit", bytes > limit, SvgOutputLimit.utf8LengthExceeds(text, limit))
            }
        }
    }
}
