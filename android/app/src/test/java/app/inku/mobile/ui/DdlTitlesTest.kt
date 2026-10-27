package app.inku.mobile.ui

import org.junit.Assert.*
import org.junit.Test

class DdlTitlesTest {
    @Test
    fun aTitleLineIsTheWholeLineInOnePairOfBrackets() {
        assertEquals("灯台", ddlTitleName("  「灯台」 "))
        assertEquals("lighthouse", ddlTitleName("\"lighthouse\""))
        assertEquals("lighthouse", ddlTitleName("“lighthouse”"))
        assertEquals("the “low” moon", ddlTitleName("\"the “low” moon\""))
        assertEquals("", ddlTitleName("「」"))
        assertEquals("", ddlTitleName("\"\""))
        assertNull(ddlTitleName("\""))
        assertNull(ddlTitleName("「赤い円」を中心に置く。"))
        assertNull(ddlTitleName("「赤」と「青」"))
    }

    @Test
    fun aTitleLineColoursNoWordAndTheSentenceAfterItKeepsItsWords() {
        val text = "「赤い円」\n中央に、赤い円。\r\n\"red circle\"\r\nA red circle in the middle."
        val words = listOf("赤", "円", "circle")
        val spans = ddlKeywordSpans(text, words)
        val titles = ddlTitleLineSpans(text)
        assertEquals(listOf(0 until 5, text.indexOf("\"red") until text.indexOf("\"red") + 12), titles)
        assertTrue(spans.none { span -> titles.any { span.start in it || span.end - 1 in it } })
        val sentence = text.indexOf("中央")
        assertEquals(listOf(DdlKeywordSpan(0, sentence + 4, sentence + 5), DdlKeywordSpan(1, sentence + 6, sentence + 7)),
            spans.filter { it.start in sentence until sentence + 8 })
        assertEquals(listOf(DdlKeywordSpan(2, text.indexOf("circle in"), text.indexOf("circle in") + 6)),
            spans.filter { it.token == 2 })
    }

    @Test
    fun theVocabularyBarReadsTheDdlWithoutItsTitles() {
        assertEquals("中央に、円。", withoutDdlTitleLines("「灯台」\n中央に、円。"))
        assertEquals("「赤い円」を中心に置く。", withoutDdlTitleLines("「赤い円」を中心に置く。"))
    }
}
