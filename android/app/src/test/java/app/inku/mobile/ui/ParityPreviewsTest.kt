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
