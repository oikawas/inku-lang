package app.inku.mobile.ui

import java.io.File
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class DdlTitlesTest {
    @Test
    fun sharedTitleCasesUseUtf16SpansAndRemoveTitles() {
        val cases = JSONObject(File(requireNotNull(System.getProperty("inku.ddlTitleCases"))).readText()).getJSONArray("cases")
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val text = case.getString("text")
            val lines = case.getJSONArray("lines")
            val expected = (0 until lines.length()).map { i ->
                val line = lines.getJSONArray(i)
                text.offsetByCodePoints(0, line.getInt(0)) until text.offsetByCodePoints(0, line.getInt(1))
            }
            assertEquals(case.getString("why"), expected, ddlTitleLineSpans(text))
            assertEquals(case.getString("why"), case.getString("without"), withoutDdlTitleLines(text))
        }
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
