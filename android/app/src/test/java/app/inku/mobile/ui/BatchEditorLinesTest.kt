package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class BatchEditorLinesTest {

    @Test
    fun deletingAnEmptyMiddleRowRemovesThatRowAndItsSeparator() {
        assertEquals(
            "A\nB",
            removeBatchEditorLine(listOf("A", "", "B"), index = 1),
        )
    }

    @Test
    fun deletingTheOnlyEmptyRowKeepsAnEmptyEditor() {
        assertEquals("", removeBatchEditorLine(listOf(""), index = 0))
    }

    @Test
    fun splitAndPasteNormalizeCrlfWithoutChangingEmptyRows() {
        assertEquals(
            listOf("A", "", "B"),
            splitBatchEditorLines("A\r\n\r\nB"),
        )
        assertEquals(
            "A\nC\nD",
            replaceBatchEditorLine(listOf("A", "B"), index = 1, edited = "C\r\nD"),
        )
    }
}
