package app.inku.mobile.data.model

import org.junit.Assert.assertEquals
import org.junit.Test

// The staffage level is a level, not a motif. web/src/lib/tenkei.ts is the
// single source; these three ids and labels are written out one by one so that
// adding a motif like "moon" fails here instead of shipping.
class TenkeiTest {

    @Test
    fun tenkeiOptions_areExactlyTheThreeWebLevels() {
        assertEquals(3, TenkeiOptions.size)

        assertEquals("none", TenkeiOptions[0].id)
        assertEquals("なし", TenkeiOptions[0].labelJa)
        assertEquals("入力に書かれた要素だけを描く", TenkeiOptions[0].hintJa)

        assertEquals("sparse", TenkeiOptions[1].id)
        assertEquals("控えめ", TenkeiOptions[1].labelJa)
        assertEquals("添景は控えめに、主題より小さく薄く", TenkeiOptions[1].hintJa)

        assertEquals("auto", TenkeiOptions[2].id)
        assertEquals("おまかせ", TenkeiOptions[2].labelJa)
        assertEquals("現行のまま（添景をAIに任せる）", TenkeiOptions[2].hintJa)
    }

    @Test
    fun normalizeTenkei_fallsBackToAutoForAnythingElse() {
        assertEquals("none", normalizeTenkei("none"))
        assertEquals("sparse", normalizeTenkei("sparse"))
        assertEquals("auto", normalizeTenkei("auto"))
        assertEquals("auto", normalizeTenkei(null))
        assertEquals("auto", normalizeTenkei("moon"))
        assertEquals(DEFAULT_TENKEI, normalizeTenkei(""))
    }
}
