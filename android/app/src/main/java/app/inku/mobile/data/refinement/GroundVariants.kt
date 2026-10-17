package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding

data class GroundVariantEntry(val material: String, val labelJa: String, val labelEn: String)

data class GroundVariantPlan(
    val current: String,
    val currentLabelJa: String?,
    val currentLabelEn: String?,
    val entries: List<GroundVariantEntry>,
)

/** Plan and redraw through the shared saved-variant rules. */
object GroundVariants {
    fun plan(scoreJson: String, binding: SharedPipelineBinding = NativePipelineBridge): GroundVariantPlan {
        val answer = SharedSavedVariants.call("ground_plan", "\"score\":$scoreJson", binding).value
        val entries = answer.getJSONArray("entries").let { rows ->
            (0 until rows.length()).map { index ->
                val row = rows.getJSONObject(index)
                GroundVariantEntry(row.getString("material"), row.getString("label_ja"), row.getString("label_en"))
            }
        }
        return GroundVariantPlan(answer.getString("current"),
            if (answer.isNull("current_label_ja")) null else answer.getString("current_label_ja"),
            if (answer.isNull("current_label_en")) null else answer.getString("current_label_en"), entries)
    }

    fun render(scoreJson: String, source: String, material: String, language: String?,
               binding: SharedPipelineBinding = NativePipelineBridge): SavedVariantRender {
        val answer = SharedSavedVariants.call("ground_render",
            "\"score\":$scoreJson,\"source\":${SharedSavedVariants.q(source)}," +
                "\"material\":${SharedSavedVariants.q(material)}," +
                "\"language\":${language?.let(SharedSavedVariants::q) ?: "null"}", binding)
        return SavedVariantRender(answer.rawScore(), answer.value.getString("ddl"),
            SharedSavedVariants.metadata(answer.value.getJSONObject("derivation_metadata")))
    }
}
