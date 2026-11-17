package app.inku.mobile.ui

import app.inku.mobile.data.CatalogModel
import app.inku.mobile.pipeline.SaijikiGenerated
import app.inku.mobile.ui.i18n.stringsFor
import app.inku.mobile.ui.i18n.UiLanguage
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ParityPreviewsTest {
    private fun description(key: String, word: String, language: UiLanguage): String? {
        val category = SaijikiGenerated.CATEGORIES.first { it.key == key }
        val index = category.wordsJa.indexOf(word)
        return (if (language.isEnglish) category.descriptionsEn else category.descriptionsJa)[index]
    }

    @Test fun generatedDescriptionsFollowUiLanguageIncludingRelations() {
        for ((key, word, english) in listOf(Triple("omote", "刷き", "sweep"), Triple("aida", "沿う", "along"))) {
            for (ui in UiLanguage.entries) for (ddl in listOf("ja", "en")) {
                val preview = saijikiPreview(key, word, if (ddl == "ja") word else english, ui, ddl)
                assertEquals(description(key, word, ui), preview.effect)
            }
        }
    }

    @Test fun nullDescriptionUsesLocalizedFallback() {
        for (ui in UiLanguage.entries) {
            assertEquals(null, description("ji", "画面比", ui))
            val preview = saijikiPreview("ji", "画面比", "aspect ratio", ui, "en")
            assertEquals(stringsFor(ui).saijikiDescriptionFallback, preview.effect)
            assertEquals("Aspect ratio 16:9.", preview.example)
        }
    }
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
        assertEquals(description("omote", "刷き", UiLanguage.Ja), jaUiEnglishDdl.effect)
        assertEquals("Place a sweep square", jaUiEnglishDdl.example)
        assertEquals(2, Regex("""<g opacity="0\.6"""").findAll(jaUiEnglishDdl.svg).count())
        val sweepEn = saijikiPreview("omote", "刷き", "刷き", UiLanguage.En, "ja")
        assertEquals(description("omote", "刷き", UiLanguage.En), sweepEn.effect)
        assertEquals("刷きの四角を置く", sweepEn.example)
        val brushmarksJa = saijikiPreview("omote", "刷毛目", "brushmarks", UiLanguage.Ja, "en")
        val brushmarksEn = saijikiPreview("omote", "刷毛目", "刷毛目", UiLanguage.En, "ja")
        assertEquals(description("omote", "刷毛目", UiLanguage.Ja), brushmarksJa.effect)
        assertEquals("Place a brushmarks square", brushmarksJa.example)
        assertEquals(description("omote", "刷毛目", UiLanguage.En), brushmarksEn.effect)
        assertEquals("刷毛目の四角を置く", brushmarksEn.example)
        assertEquals(brushmarksJa.svg, brushmarksEn.svg)
        assertTrue(brushmarksJa.svg.contains("surface-clip"))
        assertFalse(brushmarksJa.svg.contains("filter"))
        assertEquals(13, Regex("""stroke-opacity="0\.5"""").findAll(brushmarksJa.svg).count())
        assertNotEquals(jaUiEnglishDdl.svg, brushmarksJa.svg)
        val enUiJapaneseDdl = saijikiPreview("sabaki", "薄い", "薄い", UiLanguage.En, "ja")
        assertEquals(description("sabaki", "薄い", UiLanguage.En), enUiJapaneseDdl.effect)
        assertEquals("鉛筆の薄い点描の四角を置く", enUiJapaneseDdl.example)
        assertNotEquals(saijikiPreview("omote", "粒", "grain", UiLanguage.En, "en").svg,
            saijikiPreview("omote", "点描", "stipple", UiLanguage.En, "en").svg)
        val textureWords = listOf("細かい" to "fine-grained", "粗い" to "coarse-grained", "密な" to "packed",
            "疎な" to "sparse", "下塗り" to "underpainted")
        val diagrams = textureWords.map { (word, english) ->
            val key = "kime"
            val ja = saijikiPreview(key, word, english, UiLanguage.Ja, "en")
            val en = saijikiPreview(key, word, word, UiLanguage.En, "ja")
            assertEquals(description(key, word, UiLanguage.Ja), ja.effect)
            assertEquals("Place a pen $english stipple square", ja.example)
            assertEquals(description(key, word, UiLanguage.En), en.effect)
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
        val model = app.inku.mobile.data.ModelCatalog.EMPTY.classify(JSONObject().put("id", "test").put("recommendation_llm", 5)
            .put("recommendation_vision", 2).put("recommendation_level", 4))
        assertEquals("★★★", modelRecommendationStars(model, "llm"))
        assertEquals("★☆☆", modelRecommendationStars(model, "vision"))
        assertEquals("★★★", modelRecommendationStars(app.inku.mobile.data.ModelCatalog.EMPTY.classify(
            JSONObject().put("id", "legacy").put("recommendation_level", 4)), "vision"))
    }
}
