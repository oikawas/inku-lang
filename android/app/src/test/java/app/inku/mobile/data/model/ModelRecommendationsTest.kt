package app.inku.mobile.data.model

import app.inku.mobile.ui.i18n.InkuStringsJa
import org.junit.Assert.assertEquals
import org.junit.Test

class ModelRecommendationsTest {

    @Test
    fun modelRecommendations_containsExactExpectedEntries() {
        val items = ModelRecommendations.items

        // Every id below must exist in the shipped catalog; a recommendation for a
        // model nobody can select is worse than no recommendation.
        assertEquals(3, items.size)

        val entry0 = items[0]
        assertEquals("google/gemma-4-31b-it", entry0.modelId)
        assertEquals(1, entry0.recommendedStage)
        assertEquals("stage1_default", entry0.reasonKey)
        assertEquals("Stage 1 既定推奨。構図と彩色のバランスに優れる", InkuStringsJa.modelRecommendationReason(entry0.reasonKey))

        val entry1 = items[1]
        assertEquals("meta/llama-3.3-70b-instruct", entry1.modelId)
        assertEquals(1, entry1.recommendedStage)
        assertEquals("stage1_derived", entry1.reasonKey)
        assertEquals("Stage 1 派生推奨。表現力と安定性が高い", InkuStringsJa.modelRecommendationReason(entry1.reasonKey))

        val entry2 = items[2]
        assertEquals("google/gemma-4-31b-it", entry2.modelId)
        assertEquals(2, entry2.recommendedStage)
        assertEquals("stage2_default", entry2.reasonKey)
        assertEquals("Stage 2 既定推奨。DDL展開の精度が高い", InkuStringsJa.modelRecommendationReason(entry2.reasonKey))
    }
}
