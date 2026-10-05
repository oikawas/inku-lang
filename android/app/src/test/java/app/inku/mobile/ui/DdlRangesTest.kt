package app.inku.mobile.ui

import app.inku.mobile.pipeline.SharedPipelineBinding
import org.junit.Assert.*
import org.junit.Test

class DdlRangesTest {
    // Small fake transport response. Production names and bounds come exclusively from core.
    private val table = CompositionRangeTable.load {
        """{"schema":"inku.composition-ranges.v1","ranges":[
          {"key":"cell-22","words":{"ja":"右下","en":"bottom right"},"bounds":[[2,3],[2,3],[1,1],[1,1]],"corner":false},
          {"key":"cell-00","words":{"ja":"左上","en":"top left"},"bounds":[[0,1],[0,1],[1,3],[1,3]],"corner":false}
        ]}"""
    }

    @Test
    fun foldingRequiresTheNameAndExactBoundsAndKeepsTheOriginalSource() {
        val ja = "［構図］右下（横４／６～１、縦２／３~１）に、赤い円を置く。\n"
        val display = displayDdlRanges(ja, table)
        assertEquals("右下に、赤い円を置く。\n", display.text)
        assertEquals("右下", display.text.substring(display.spans.single().start, display.spans.single().nameEnd))
        assertTrue(display.spans.single().folded)
        assertEquals("［構図］右下（横４／６～１、縦２／３~１）に、赤い円を置く。\n", ja)

        val en = "Place a red circle at [composition] the top left (horizontal 0 to 2/6, vertical 0 to 1/3)."
        assertEquals("Place a red circle at the top left.", displayDdlRanges(en, table).text)
        val mismatched = "右下（横0.9〜1、縦0.1〜0.2）に、赤い円を置く。"
        assertEquals(mismatched, displayDdlRanges(mismatched, table).text)
        val numbersOnly = "画面の横0.2〜0.5、縦0〜0.3の範囲に、円を置く。"
        assertEquals(numbersOnly, displayDdlRanges(numbersOnly, table).text)
        val approximate = "Place a circle at the top left (horizontal 0 to 0.333333, vertical 0 to 1/3)."
        assertEquals(approximate, displayDdlRanges(approximate, table).text)
    }

    @Test
    fun editingFollowsTheTableNameAndKeepsCustomNumbersAndTheLastValidFrame() {
        val source = "赤い円を、［構図］右下（横2/3〜1、縦2/3〜1）に置く。\r\n青い円を置く。"
        val editor = DdlRangeEdit.open(source, ddlNamedRanges(source, table).single())
        val matched = editor.update("（横0〜1/3、縦0〜1/3）", table)
        assertEquals("赤い円を、左上（横0〜1/3、縦0〜1/3）に置く。\r\n青い円を置く。", matched.source)
        assertTrue(displayDdlRanges(matched.source, table).spans.single().folded)
        val custom = matched.update("（横0.2〜0.5、縦0〜0.3）", table)
        assertTrue(custom.source.contains("左上（横0.2〜0.5、縦0〜0.3）"))
        assertFalse(displayDdlRanges(custom.source, table).spans.single().folded)
        val invalid = custom.update("（横0.2〜1.5、縦0〜0.3）", table)
        assertFalse(invalid.valid)
        assertEquals(custom.lastValidBounds, invalid.lastValidBounds)
        assertTrue(invalid.source.endsWith("に置く。\r\n青い円を置く。"))
    }

    @Test
    fun olderBindingsLeaveThePlainDisplayUsable() {
        val binding = object : SharedPipelineBinding {
            override fun versionReport() = "{}"
            override fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray) = byteArrayOf()
            override fun canvasRegistry() = "{}"
            override fun resolvePalette(inputBytes: ByteArray) = byteArrayOf()
            override fun resolveMacroCatalog(inputBytes: ByteArray) = byteArrayOf()
            override fun renderSaved(inputBytes: ByteArray) = byteArrayOf()
        }
        val source = "右下（横2/3〜1、縦2/3〜1）に、円を置く。"
        assertEquals(source, displayDdlRanges(source, CompositionRangeTable.load(binding::compositionRanges)).text)
        assertEquals(source, displayDdlRanges(source, CompositionRangeTable.load { throw UnsatisfiedLinkError() }).text)
    }

    @Test
    fun theFrameFollowsTheFittedAndRotatedImageInsteadOfItsLetterbox() {
        val bounds = table.ranges.first().bounds
        // A wide work rotated clockwise is a tall 200×400 bitmap centered in a 400×400 box.
        val frame = rangeFrame(bounds, 400f, 400f, 200f, 400f, 90)
        assertEquals(100f, frame.left, 0.001f)
        assertEquals(400f * 2 / 3, frame.top, 0.001f)
        assertEquals(100f + 200f / 3, frame.right, 0.001f)
        assertEquals(400f, frame.bottom, 0.001f)
    }
}
