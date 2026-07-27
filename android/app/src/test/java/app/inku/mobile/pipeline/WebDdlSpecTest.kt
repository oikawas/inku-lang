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

    @Test
    fun testStage5dDisplayVocabulary10TermsExactOrder() {
        val expected = listOf("鉛筆", "ペン", "ロットリング", "クレヨン", "チョーク", "細筆", "太筆", "ビュラン", "ドライポイント", "コンピュータ")
        val touchGroup = app.inku.mobile.ui.saijikiGroups.firstOrNull { it.label == "てざわり" }
        org.junit.Assert.assertNotNull("てざわり group must exist", touchGroup)
        org.junit.Assert.assertEquals("てざわり display terms must match section 3.9 exactly", expected, touchGroup!!.words)
    }

    @Test
    fun testComputerWeightDetectionHairRetentionAndRopeRemoval() {
        // 1. Computer weight detection
        org.junit.Assert.assertEquals("computer", ServerScoreSemantics.detectWeightKey("コンピュータの直線を引く"))

        // 2. Hair weight retention (backward compatibility)
        val sourceJson = org.json.JSONObject("""{"primitive":"line","weight":"hair"}""")
        val coerced = ServerScoreCoercer.coerceInstruction(
            source = sourceJson,
            ddl = "髪の毛",
            background = "white",
            detectColorKey = ServerScoreSemantics::detectColorKey,
            detectWeightKey = ServerScoreSemantics::detectWeightKey,
            visibleForeground = ServerScoreSemantics::visibleForeground
        )
        org.junit.Assert.assertEquals("legacy hair must be replaced by silverpoint, not dropped to the default", "silverpoint", coerced.getString("weight"))

        // 3. Rope / 縄 removal verification
        val fullPrompt = WebDdlSpec.buildStage1SystemPrompt("テスト")
        org.junit.Assert.assertFalse("rope must not appear in prompt", fullPrompt.contains("rope"))
        org.junit.Assert.assertFalse("縄 must not appear in prompt", fullPrompt.contains("縄"))
        org.junit.Assert.assertFalse("rope must not be detected", ServerScoreSemantics.detectWeightKey("縄の太い線") == "rope")

        // 4. The retired tool must be gone from the drawing tables too, not only
        //    from the words. rope was unreachable through the coercer, so a
        //    prompt-only check passes while the tables still carry it.
        org.junit.Assert.assertEquals(
            "the style table must treat rope as unknown",
            app.inku.mobile.render.ServerRendererStyle.strokeOpacity("unknown-tool"),
            app.inku.mobile.render.ServerRendererStyle.strokeOpacity("rope"),
            1e-9,
        )
        org.junit.Assert.assertEquals(
            "the width table must treat rope as unknown",
            app.inku.mobile.render.ServerRendererStyle.strokeWidth("unknown-tool", 1000.0),
            app.inku.mobile.render.ServerRendererStyle.strokeWidth("rope", 1000.0),
            1e-9,
        )
        org.junit.Assert.assertNull(
            "rope must not have a stroke engine grammar",
            app.inku.mobile.render.GRAMMARS["rope"],
        )
    }
}
