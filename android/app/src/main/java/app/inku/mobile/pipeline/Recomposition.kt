package app.inku.mobile.pipeline

import app.inku.mobile.data.DdlSource
import java.util.concurrent.CancellationException
import org.json.JSONObject

enum class RecomposeMode(val id: String) {
    Principled("principled"),
    Chance("chance"),
}

data class RecompositionMove(val layer: Int, val from: String, val to: String)

/** Temporary candidate information; the reading is not saved with a work. */
data class RecompositionInfo(
    val moves: List<RecompositionMove> = emptyList(),
    val unchangedReason: String? = null,
)

internal data class RecomposedDdl(val source: String, val info: RecompositionInfo)

/** Rust alone decides the ranges; a failed selection keeps the original DDL. */
internal fun recomposeDdl(
    binding: SharedPipelineBinding,
    source: String,
    config: PreparedPipelineConfig,
    mode: RecomposeMode,
    workId: String,
    seed: Long,
): RecomposedDdl {
    fun unchanged(reason: String) = RecomposedDdl(source, RecompositionInfo(unchangedReason = reason))
    try {
        val input = JSONObject()
            .put("config", JSONObject(config.configJson))
            .put("source", source)
            .put("mode", mode.id)
            .put("seed", java.lang.Long.toUnsignedString(seed))
            .put("work_id", workId)
        val output = JSONObject(binding.recompose(input.toString().encodeToByteArray()).toString(Charsets.UTF_8))
        if (output.has("error") || output.optString("schema") != "inku.composition-recompose.v1") {
            return unchanged("unavailable")
        }
        return when (output.getString("outcome")) {
            "recomposed" -> {
                val selected = output.getString("source")
                require(DdlSource.hasBody(selected))
                val moves = output.getJSONArray("moves")
                val info = RecompositionInfo(moves = (0 until moves.length()).map { index ->
                    val move = moves.getJSONObject(index)
                    val layer = move.getInt("layer")
                    require(layer >= 0)
                    RecompositionMove(layer, move.getString("from"), move.getString("to"))
                })
                RecomposedDdl(selected, info)
            }
            "unchanged" -> unchanged(output.getString("reason"))
            else -> unchanged("unavailable")
        }
    } catch (error: Exception) {
        if (error is CancellationException) throw error
        return unchanged("unavailable")
    } catch (_: LinkageError) {
        return unchanged("unavailable")
    }
}
