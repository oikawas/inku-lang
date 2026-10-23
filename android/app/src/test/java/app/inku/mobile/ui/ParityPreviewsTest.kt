package app.inku.mobile.ui

import app.inku.mobile.data.CatalogModel
import app.inku.mobile.ui.i18n.UiLanguage
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ParityPreviewsTest {
    @Test fun canvasRatioExampleFollowsTheDdlLanguageInTheGroundGroup() {
        for (uiLanguage in UiLanguage.entries) {
            for (ddlLanguage in listOf("ja", "en")) {
                val preview = saijikiPreview("ji", "画面比", if (uiLanguage.isEnglish) "aspect ratio" else "画面比", uiLanguage, ddlLanguage)
                assertEquals(if (ddlLanguage == "ja") "画面比16:9。" else "Aspect ratio 16:9.", preview.example)
            }
        }
    }

    @Test fun saijikiEffectFollowsUiAndExampleFollowsDdl() {
        val jaUiEnglishDdl = saijikiPreview("omote", "刷き", "sweep", UiLanguage.Ja, "en")
        assertTrue(jaUiEnglishDdl.effect.contains("一枚の膜") && jaUiEnglishDdl.effect.contains("0.6倍"))
        assertEquals("Place a sweep square", jaUiEnglishDdl.example)
        assertEquals(2, Regex("""<g opacity="0\.6"""").findAll(jaUiEnglishDdl.svg).count())
        val sweepEn = saijikiPreview("omote", "刷き", "刷き", UiLanguage.En, "ja")
        assertTrue(sweepEn.effect.contains("one film of merged bands at 0.6"))
        assertEquals("刷きの四角を置く", sweepEn.example)
        val brushmarksJa = saijikiPreview("omote", "刷毛目", "brushmarks", UiLanguage.Ja, "en")
        val brushmarksEn = saijikiPreview("omote", "刷毛目", "刷毛目", UiLanguage.En, "ja")
        assertTrue(brushmarksJa.effect.contains("一本ずつ重ね") && brushmarksJa.effect.contains("閉じた形"))
        assertEquals("Place a brushmarks square", brushmarksJa.example)
        assertTrue(brushmarksEn.effect.contains("darken where they overlap"))
        assertEquals("刷毛目の四角を置く", brushmarksEn.example)
        assertEquals(brushmarksJa.svg, brushmarksEn.svg)
        assertTrue(brushmarksJa.svg.contains("surface-clip"))
        assertFalse(brushmarksJa.svg.contains("filter"))
        assertEquals(13, Regex("""stroke-opacity="0\.5"""").findAll(brushmarksJa.svg).count())
        assertNotEquals(jaUiEnglishDdl.svg, brushmarksJa.svg)
        val enUiJapaneseDdl = saijikiPreview("sabaki", "薄い", "薄い", UiLanguage.En, "ja")
        assertTrue(enUiJapaneseDdl.effect.contains("faintly"))
        assertEquals("鉛筆の薄い点描の四角を置く", enUiJapaneseDdl.example)
        assertNotEquals(saijikiPreview("omote", "粒", "grain", UiLanguage.En, "en").svg,
            saijikiPreview("omote", "点描", "stipple", UiLanguage.En, "en").svg)
        val textureWords = listOf("細かい" to "fine-grained", "粗い" to "coarse-grained", "密な" to "packed",
            "疎な" to "sparse", "下塗り" to "underpainted")
        val diagrams = textureWords.map { (word, english) ->
            val key = if (word == "下塗り") "shitaji" else "kime"
            val ja = saijikiPreview(key, word, english, UiLanguage.Ja, "en")
            val en = saijikiPreview(key, word, word, UiLanguage.En, "ja")
            assertTrue(ja.effect.contains("質感"))
            assertEquals("Place a pen $english stipple square", ja.example)
            assertTrue(en.effect.contains("texture"))
            val japaneseExample = if (word == "下塗り") "ペンの下塗りの点描の四角を置く" else "ペンの${word}点描の四角を置く"
            assertEquals(japaneseExample, en.example)
            assertEquals("the diagram is shared across languages", ja.svg, en.svg)
            assertTrue("$word has a surface comparison", ja.svg.contains("surface-clip") && ja.svg.contains("M90 20 V72"))
            ja.svg
        }
        assertEquals("each texture word has its own diagram", 5, diagrams.toSet().size)
        assertTrue("underpainted texture draws light marks over the tool colour", diagrams.last().contains("fill=\"#8a8a8a\""))
    }

    @Test fun recommendationUsesPurposeAndFallsBackToLegacyLevel() {
        val model = CatalogModel("test", JSONObject().put("recommendation_llm", 5)
            .put("recommendation_vision", 2).put("recommendation_level", 4), emptyList())
        assertEquals("★★★", modelRecommendationStars(model, "llm"))
        assertEquals("★☆☆", modelRecommendationStars(model, "vision"))
        assertEquals("★★★", modelRecommendationStars(CatalogModel("legacy",
            JSONObject().put("recommendation_level", 4), emptyList()), "vision"))
    }
}
