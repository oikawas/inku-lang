package app.inku.mobile.pipeline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WebDdlExpanderTest {
    // Four of the tests here used to assert that Stage 1.5 appended staffage. The
    // staffage level was folded away in v2.11.0, so each has been re-pointed at a
    // property that is true after the fold and false before it: the layer reframes
    // the focus and adds nothing. Focus is what still authors the output.

    @Test
    fun addsNoSentenceBeyondTheReframe() {
        val ddl = "背景を灰で塗りつぶす。赤い小さな円をランダムに十二個散らす。青い小さな円をランダムに八個散らす。白い細筆の細い線を水平に三本引く。"
        val expanded = WebDdlExpander.expandIntermediateDdl(ddl)

        // The sanitizing rules that live before the fold still apply.
        assertFalse(expanded.contains("ランダム"))
        assertFalse(expanded.contains("背景を灰"))
        assertTrue(expanded.contains("背景を白で塗りつぶす"))
        assertTrue(expanded.contains("画面全体に点々と十二個"))

        // TRUE after the fold, FALSE before it: the sentence count is preserved.
        assertEquals(ddl.count { it == '。' }, expanded.count { it == '。' })
        for (invented in listOf("小さな楕円", "細い弧", "細い斜め線", "正五角形", "遠近法の奥行き")) {
            assertFalse("staffage sentence still appended: $invented", expanded.contains(invented))
        }
    }

    @Test
    fun isIdempotentAfterExpansion() {
        val ddl = "赤い小さな円を中央付近に五つ散らす。灰色の小さな円を右上の黄金比の位置に一点置く。半径は0.025。"
        assertEquals(ddl, WebDdlExpander.expandIntermediateDdl(ddl))
    }

    @Test
    fun variesByFocusAndReframesCenter() {
        val ddl = "中心に黒い四角を置く。白い横線を三本引く。"
        val first = WebDdlExpander.expandIntermediateDdl(ddl)
        val second = WebDdlExpander.expandIntermediateDdl("満天の星空に白い小さな円を画面全体に点々と六百十個散らす。")

        assertNotEquals(first, second)
        assertFalse(first.contains("中心"))
        assertFalse(first.contains("中央"))
        assertTrue(first.contains("焦点に黒い四角を置く"))

        // TRUE after the fold, FALSE before it: the second input is carried through
        // untouched -- it names no center, so there is nothing left for the layer to do.
        assertEquals("満天の星空に白い小さな円を画面全体に点々と六百十個散らす。", second)

        // The control: focus is what moves the output now.
        val upperLeft = WebDdlExpander.expandIntermediateDdl(ddl, focus = "upper_left")
        val rightHalf = WebDdlExpander.expandIntermediateDdl(ddl, focus = "right_half")
        assertEquals("左上の焦点に黒い四角を置く。白い横線を三本引く。", upperLeft)
        assertEquals("右半分の焦点に黒い四角を置く。白い横線を三本引く。", rightHalf)
        assertNotEquals(upperLeft, rightHalf)
    }

    @Test
    fun atmosphericAndSensoryContextNoLongerAddSentences() {
        val atmosphereDdl = "白い短い線を上から下へ九本散らす。"
        val atmosphere = WebDdlExpander.expandIntermediateDdl(
            atmosphereDdl,
            contextText = "透明な膜と雨の反射が残るバス停",
        )
        // TRUE after the fold, FALSE before it: the context wrote 透明な膜 / 薄い反射 here.
        assertEquals(atmosphereDdl, atmosphere)

        val sensoryDdl = "緑の三角を三つ置く。赤い楕円を三つ置く。"
        val sensory = WebDdlExpander.expandIntermediateDdl(
            sensoryDdl,
            contextText = "柔らかな陽光と沈丁花の香り、桜の蕾が開花を待つ春の五感",
        )
        assertEquals(sensoryDdl, sensory)
        for (invented in listOf("柔らかな光", "香りの層", "開花を待つ蕾", "五感の気配")) {
            assertFalse("staffage sentence still appended: $invented", sensory.contains(invented))
        }
    }

    @Test
    fun presenceContextNoLongerAddsBodySymbols() {
        val ddl = "青い横線を下端に三十本並べる。"
        val expanded = WebDdlExpander.expandIntermediateDdl(
            ddl,
            contextText = "川岸で人と熊が並んで待っている",
        )

        // TRUE after the fold, FALSE before it: the context wrote 存在の重心 / 輪郭の密度 here.
        assertEquals(ddl, expanded)
        for (invented in listOf("存在の重心", "輪郭の密度")) {
            assertFalse("staffage sentence still appended: $invented", expanded.contains(invented))
        }
    }
}
