package app.inku.mobile.data.model

data class ModelRecommendation(
    val modelId: String,
    val recommendedStage: Int,
    /** Looked up in `InkuStrings.modelRecommendationReason`; the sentence is wording. */
    val reasonKey: String,
)

object ModelRecommendations {
    val items: List<ModelRecommendation> = listOf(
        ModelRecommendation(
            modelId = "google/gemma-4-31b-it",
            recommendedStage = 1,
            reasonKey = "stage1_default",
        ),
        ModelRecommendation(
            modelId = "meta/llama-3.3-70b-instruct",
            recommendedStage = 1,
            reasonKey = "stage1_derived",
        ),
        ModelRecommendation(
            modelId = "google/gemma-4-31b-it",
            recommendedStage = 2,
            reasonKey = "stage2_default",
        ),
    )
}
