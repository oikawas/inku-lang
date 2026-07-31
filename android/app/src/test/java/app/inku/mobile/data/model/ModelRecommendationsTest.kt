package app.inku.mobile.data.model

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
        assertEquals("Stage 1 既定推奨。構図と彩色のバランスに優れる", entry0.reasonJa)

        val entry1 = items[1]
        assertEquals("meta/llama-3.3-70b-instruct", entry1.modelId)
        assertEquals(1, entry1.recommendedStage)
        assertEquals("Stage 1 派生推奨。表現力と安定性が高い", entry1.reasonJa)

        val entry2 = items[2]
        assertEquals("google/gemma-4-31b-it", entry2.modelId)
        assertEquals(2, entry2.recommendedStage)
        assertEquals("Stage 2 既定推奨。DDL展開の精度が高い", entry2.reasonJa)
    }
}
