package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject

/**
 * The one road that turns an entry of `svg_index.json` into a drawing.
 *
 * The index states, for every one of its drawings, which colour catalog the
 * server drew it with. Six places in this suite redrew those drawings to compare
 * them against the frozen reference and all six wrote `colorCatalogId =
 * "default"`, so the five drawings the index attributes to another catalog were
 * compared against pictures made with tools the reference never used. Nothing
 * went red for it, because the quantities those guards compare -- `d`, `points`,
 * element counts, class attributes -- carry no colour.
 *
 * Reading the declaration lives here rather than in each of the six so that the
 * claim "the guard hands over what the index declares" has a single place to be
 * asserted about, and a single place to be broken by a perturbation. A copy in
 * each caller would be a copy of the decision, and a test of one copy would say
 * nothing about the other five.
 */
object ReferenceRendering {

    fun index(): JSONObject = JSONObject(ReferenceCorpus.text("svg_index.json"))

    fun entry(key: String): JSONObject = index().getJSONObject(key)

    /**
     * The colour catalog the index declares for a drawing.
     *
     * Read with no fallback on purpose. A drawing whose entry has no
     * `color_catalog_id` is a hole in the index, and a default here would draw it
     * with a catalog nobody declared and call the comparison green.
     */
    fun catalogId(entry: JSONObject): String = entry.getString("color_catalog_id")

    /**
     * The request the guard hands to the renderer for one index entry.
     *
     * Every field is read the way the corpus keeps it: the seed sits beside the
     * Score because the server takes it as an argument, `wild` is put onto the
     * Score, and the composition seed is read with "is it stated" rather than a
     * falsy test, because 0 is a seed a caller can legitimately give.
     */
    fun request(entry: JSONObject): RenderRequest {
        val scoreObj = entry.getJSONObject("score")
        val renderSeed = if (entry.isNull("render_seed")) null else entry.getLong("render_seed")
        if (entry.has("wild") && !entry.isNull("wild")) {
            scoreObj.put("render_wild", entry.getBoolean("wild"))
        }

        val canvasOpt = scoreObj.opt("canvas")
        val aspect = when {
            entry.has("canvas_aspect") -> entry.getString("canvas_aspect")
            canvasOpt is String -> canvasOpt
            canvasOpt is JSONObject -> canvasOpt.optString("aspect", "square")
            else -> "square"
        }
        val compositionSeed = if (entry.has("composition_seed") && !entry.isNull("composition_seed")) {
            entry.getLong("composition_seed")
        } else {
            null
        }
        return RenderRequest(
            scoreJson = scoreObj.toString(),
            colorCatalogId = catalogId(entry),
            canvasAspect = aspect,
            svgProfile = "editable",
            renderSeed = renderSeed,
            compositionSeed = compositionSeed,
        )
    }

    fun svg(entry: JSONObject): String = DefaultSvgRenderer().render(request(entry)).svg

    fun svg(key: String): String = svg(entry(key))
}
