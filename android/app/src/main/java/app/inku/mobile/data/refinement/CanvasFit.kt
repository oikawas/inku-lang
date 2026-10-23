package app.inku.mobile.data.refinement

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding
import org.json.JSONObject

/** Android's saved canvas field is the local counterpart of render_canvas_aspect_id. */
fun recordedCanvasAspect(item: HistoryItemEntity): String? {
    val metadata = JSONObject(item.renderMetadataJson)
    return listOf("render_canvas_aspect_id", "render_canvas_aspect").firstNotNullOfOrNull { key ->
        metadata.optString(key).takeUnless { metadata.isNull(key) || it.isBlank() }
    } ?: item.canvasAspect.takeIf { it.isNotBlank() }
}

/** Fitting changes the saved Score's canvas only. It never reads the DDL again. */
object CanvasFit {
    data class Render(val scoreJson: String, val derivationMetadata: Map<String, Any?>)

    fun render(scoreJson: String, drawnOn: String?, paper: String,
               binding: SharedPipelineBinding = NativePipelineBridge): Render {
        val answer = SharedSavedVariants.call("fit_render",
            "\"score\":$scoreJson,\"drawn_on\":${drawnOn?.let(SharedSavedVariants::q) ?: "null"}," +
                "\"paper\":${SharedSavedVariants.q(paper)}", binding)
        return Render(answer.rawScore(),
            SharedSavedVariants.metadata(answer.value.getJSONObject("derivation_metadata")))
    }

    /** Used again at the transaction boundary, before accepting a fitted child. */
    fun verify(parent: HistoryItemEntity, child: HistoryItemEntity, metadataJson: String) {
        val expected = render(parent.scoreJson, recordedCanvasAspect(parent), child.canvasAspect)
        require(child.normalizedDdl == parent.normalizedDdl && child.ddlSourceOrigin == parent.ddlSourceOrigin) {
            "canvas fit changed the saved DDL"
        }
        require(app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(JSONObject(child.scoreJson)) ==
            app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(JSONObject(expected.scoreJson))) {
            "canvas fit Score differs from the core result"
        }
        require(metadataJson == app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(expected.derivationMetadata)) {
            "canvas fit derivation differs from the core result"
        }
        JSONObject(parent.renderMetadataJson).optJSONObject("render_color_map")?.let { colors ->
            require(app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(colors) ==
                app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(JSONObject(child.renderMetadataJson).getJSONObject("render_color_map"))) {
                "canvas fit changed the saved colors"
            }
        }
    }
}
