package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding
import java.math.BigInteger
import org.json.JSONObject

data class ColorArrangementPage(
    val entries: List<BigInteger>,
    val nextCursor: BigInteger?,
    val total: BigInteger,
)

data class ColorArrangementRender(
    val colorMap: Map<String, String>,
    val derivationMetadata: Map<String, Any?>,
)

/** Holds saved inputs; the core owns palette discovery, paging, and recoloring. */
class SavedColorArrangements private constructor(
    private val svg: String,
    private val colorMap: Map<String, String>,
    private val workId: String,
    private val binding: SharedPipelineBinding,
) {
    val total: BigInteger get() = page().total

    fun page(cursor: BigInteger = BigInteger.ZERO): ColorArrangementPage {
        val answer = SharedSavedVariants.call("color_plan", base() +
            ",\"cursor\":${SharedSavedVariants.q(cursor.toString())}", binding, wideNumbers = true).value
        val rows = answer.getJSONArray("entries")
        val entries = (0 until rows.length()).map { index ->
            SharedSavedVariants.integer(rows.getJSONObject(index).get("index"))
        }
        val nextCursor = if (answer.isNull("next_cursor")) null else
            SharedSavedVariants.integer(answer.get("next_cursor"))
        return ColorArrangementPage(entries, nextCursor,
            SharedSavedVariants.integer(answer.get("total")))
    }

    fun render(index: BigInteger, catalogId: String): ColorArrangementRender {
        val answer = SharedSavedVariants.call("color_render", base() +
            ",\"index\":${SharedSavedVariants.q(index.toString())}," +
            "\"catalog_id\":${SharedSavedVariants.q(catalogId)}", binding, wideNumbers = true)
        val colors = answer.value.getJSONObject("color_map").let { map ->
            map.keys().asSequence().associateWith(map::getString)
        }
        val metadataRaw = answer.rawValue("derivation_metadata")
        val rawIndex = SharedSavedVariants.rawObjectValue(metadataRaw, "color_arrangement_index")
        val metadataIndex: Any = if (rawIndex.startsWith('"'))
            JSONObject("{\"index\":$rawIndex}").getString("index") else BigInteger(rawIndex)
        val catalog = answer.value.getJSONObject("derivation_metadata").getString("catalog_id")
        return ColorArrangementRender(colors, mapOf("color_arrangement_index" to metadataIndex,
            "catalog_id" to catalog))
    }

    private fun base(): String = "\"svg\":${SharedSavedVariants.q(svg)}," +
        "\"color_map\":${SharedSavedVariants.stringMap(colorMap)}," +
        "\"work_id\":${SharedSavedVariants.q(workId)}"

    companion object {
        fun fromSaved(svg: String, colorMap: Map<String, String>, workId: String,
                      binding: SharedPipelineBinding = NativePipelineBridge): SavedColorArrangements =
            SavedColorArrangements(svg, colorMap, workId, binding)
    }
}
