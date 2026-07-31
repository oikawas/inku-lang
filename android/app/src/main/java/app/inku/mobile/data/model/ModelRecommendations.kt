package app.inku.mobile.data.model

data class ModelRecommendation(
    val modelId: String,
    val recommendedStage: Int,
    val reasonJa: String,
)

object ModelRecommendations {
    val items: List<ModelRecommendation> = listOf(
        ModelRecommendation(
            modelId = "google/gemma-4-31b-it",
            recommendedStage = 1,
            reasonJa = "Stage 1 既定推奨。構図と彩色のバランスに優れる",
        ),
        ModelRecommendation(
            modelId = "meta/llama-3.3-70b-instruct",
            recommendedStage = 1,
            reasonJa = "Stage 1 派生推奨。表現力と安定性が高い",
        ),
        ModelRecommendation(
            modelId = "google/gemma-4-31b-it",
            recommendedStage = 2,
            reasonJa = "Stage 2 既定推奨。DDL展開の精度が高い",
        ),
    )
}
