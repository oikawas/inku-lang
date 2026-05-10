package app.inku.mobile.pipeline

import org.junit.Assert.assertTrue
import org.junit.Test

class WebDdlSpecTest {
    @Test
    fun liteRtStage1PromptIsCompressedButKeepsCoreContract() {
        val text = "春の朝、白い花びらが青い川面をゆっくり渡り、遠い街の影が揺れる"
        val full = WebDdlSpec.buildStage1SystemPrompt(text)
        val liteRt = WebDdlSpec.buildStage1LiteRtSystemPrompt(text)

        assertTrue(liteRt.length < full.length / 2)
        listOf(
            "Saijiki語彙",
            "正規化DDL本文のみ",
            "色、素材、数量、太さ、サイズ、方向、場所、配置、ゆらぎは落とさない",
            "ランダムは禁止",
            "真円固定禁止",
            "人/顔/動物は具象化しない",
            "灰背景は禁止",
        ).forEach { required ->
            assertTrue("missing required contract phrase: $required", liteRt.contains(required))
        }
    }

    @Test
    fun liteRtStage1PromptUsesSameFixtureOutputsForMatchedExamples() {
        val fixtures = mapOf(
            "花びらが散る" to "上から下へ白い右下がりの小さな楕円を四十七個散らす。大きく揺れる。",
            "白い背景に白い線を引く" to "背景を白で塗りつぶす。黒い横線を中央に引く。",
            "三本の竹を縦に並べる" to "縦の実線を横に三本並べる。",
        )

        fixtures.forEach { (input, expectedOutput) ->
            val full = WebDdlSpec.buildStage1SystemPrompt(input)
            val liteRt = WebDdlSpec.buildStage1LiteRtSystemPrompt(input)
            assertTrue("full prompt fixture missing for $input", full.contains(expectedOutput))
            assertTrue("LiteRT prompt fixture mismatch for $input", liteRt.contains(expectedOutput))
        }
    }
}
