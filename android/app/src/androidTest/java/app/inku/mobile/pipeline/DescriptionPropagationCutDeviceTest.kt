package app.inku.mobile.pipeline

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-8 of 契約 description-propagation-cut, on the device.
 *
 * The same five readings as the JVM test beside it, and not redundant with it:
 * the JVM test links `org.json:json`, while this one runs against Android's own
 * `JSONObject`, which is a different implementation. The whole fallback is built
 * out of JSONObject, so the pass that matters for a shipped app is this one.
 *
 * 作者裁定 2026-07-31: the device is a USB-connected Pixel 9, never an emulator.
 */
@RunWith(AndroidJUnit4::class)
class DescriptionPropagationCutDeviceTest {

    private val pipeline = LocalFallbackPipeline()

    private fun backgroundOf(ddl: String, originalText: String): String =
        pipeline.scoreFromWebRules(ddl, "square").optString("background")

    @Test
    fun theGovernorNoLongerReadsANightTheDdlNeverWrote() {
        val ddl = "白い細い弧を三百本、上から下へ散らす。境界が滲む。透明な膜を重ねる。"
        assertEquals("white", backgroundOf(ddl, "夜である。静かな気配がある。"))
    }

    @Test
    fun aBackgroundTheDdlAsksForSurvives() {
        val ddl = "背景を黒で塗りつぶす。白い細い弧を三百本、上から下へ散らす。境界が滲む。透明な膜を重ねる。"
        assertEquals("black", backgroundOf(ddl, "夜である。静かな気配がある。"))
    }

    @Test
    fun aProductionShapedPlanIsNotMistakenForAPastedOne() {
        val ddl = "背景を青で塗りつぶす。画面全体に白い細い縦線を三百本散らす。" +
            "黒い細い余白線を存在の重心として右上の焦点へ二本引く。透明な膜を重ねる。境界が滲む。"
        assertEquals("blue", backgroundOf(ddl, "静かな水面がある。"))
    }

    @Test
    fun aSurfaceWordBelowTheFirstLineIsRead() {
        val ddl = "地: 生成りの紙、細かい紙目。\n夜空に白い細い弧を静かに散らす。"
        assertEquals("black", backgroundOf(ddl, "夜である。静かな気配がある。"))
    }

    @Test
    fun aSecondLineWithNoSurfaceWordIsStillGoverned() {
        val ddl = "地: 生成りの紙、細かい紙目。\n静かに白い細い弧を散らす。"
        assertEquals("white", backgroundOf(ddl, "夜である。静かな気配がある。"))
    }
}
