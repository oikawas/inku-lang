package app.inku.mobile.ui

import app.inku.mobile.data.CatalogModel
import app.inku.mobile.ui.i18n.UiLanguage
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ParityPreviewsTest {
    @Test fun saijikiEffectFollowsUiAndExampleFollowsDdl() {
        val jaUiEnglishDdl = saijikiPreview("omote", "刷き", "sweep", UiLanguage.Ja, "en")
        assertTrue(jaUiEnglishDdl.effect.contains("二度掃く"))
        assertEquals("Place a sweep square", jaUiEnglishDdl.example)
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
