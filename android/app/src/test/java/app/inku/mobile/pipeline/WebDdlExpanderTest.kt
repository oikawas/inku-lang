package app.inku.mobile.pipeline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WebDdlExpanderTest {
    @Test
    fun selectsFocusedLayers() {
        val ddl = "背景を灰で塗りつぶす。赤い小さな円をランダムに十二個散らす。青い小さな円をランダムに八個散らす。白い細筆の細い線を水平に三本引く。"
        val expanded = WebDdlExpander.expandIntermediateDdl(ddl)

        assertFalse(expanded.contains("ランダム"))
        assertFalse(expanded.contains("背景を灰"))
        assertTrue(expanded.contains("背景を白で塗りつぶす"))
        assertTrue(expanded.contains("画面全体に点々と十二個"))
        assertFalse(expanded.contains("正五角形"))
        assertFalse(expanded.contains("中心から"))
        assertFalse(expanded.contains("中央へ"))
        assertTrue(expanded.count { it == '。' } <= ddl.count { it == '。' } + 8)
        assertTrue(listOf("小さな楕円", "短い線", "小さな四角", "細い弧").any { it in expanded })
        assertTrue(listOf("右上がり", "右下がり", "回転した", "焦点").any { it in expanded })
    }

    @Test
    fun isIdempotentAfterExpansion() {
        val ddl = "赤い小さな円を中央付近に五つ散らす。灰色の小さな円を右上の黄金比の位置に一点置く。半径は0.025。"
        assertEquals(ddl, WebDdlExpander.expandIntermediateDdl(ddl))
    }

    @Test
    fun variesByInputAndReframesCenter() {
        val first = WebDdlExpander.expandIntermediateDdl("中心に黒い四角を置く。白い横線を三本引く。")
        val second = WebDdlExpander.expandIntermediateDdl("満天の星空に白い小さな円を画面全体に点々と六百十個散らす。")

        assertNotEquals(first, second)
        assertFalse(first.contains("中心"))
        assertFalse(first.contains("中央"))
        assertTrue(first.contains("焦点に黒い四角を置く"))
        assertTrue(listOf("遠近法の奥行き", "一点透視法", "パッチワーク", "水彩", "素描の下線", "点描").any { it in first })
        assertTrue(listOf("左下の焦点から三つ", "波打つ軌跡に沿って七個", "左下から右上へ三本").any { it in second })
    }

    @Test
    fun carriesAtmosphericAndSensoryContext() {
        val atmosphere = WebDdlExpander.expandIntermediateDdl(
            "白い短い線を上から下へ九本散らす。",
            contextText = "透明な膜と雨の反射が残るバス停",
        )
        assertTrue(atmosphere.contains("透明な膜"))
        assertTrue(atmosphere.contains("薄い反射"))

        val sensory = WebDdlExpander.expandIntermediateDdl(
            "緑の三角を三つ置く。赤い楕円を三つ置く。",
            contextText = "柔らかな陽光と沈丁花の香り、桜の蕾が開花を待つ春の五感",
        )
        val selected = listOf("柔らかな光", "香りの層", "開花を待つ蕾", "五感の気配").count { it in sensory }
        assertTrue(selected >= 2)
        assertTrue(sensory.count { it == '。' } <= 8)
    }

    @Test
    fun abstractsPresenceWithoutBodySymbols() {
        val expanded = WebDdlExpander.expandIntermediateDdl(
            "青い横線を下端に三十本並べる。",
            contextText = "川岸で人と熊が並んで待っている",
        )

        assertTrue(listOf("存在の重心", "輪郭の密度").any { it in expanded })
        assertFalse(expanded.contains("縦線"))
        assertFalse(expanded.contains("小さな楕円"))
    }
}
