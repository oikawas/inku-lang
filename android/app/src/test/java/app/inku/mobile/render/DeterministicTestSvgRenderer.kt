package app.inku.mobile.render

import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.pipeline.RenderRequest
import java.security.MessageDigest
import org.json.JSONObject

/** Explicit host-JVM test double; production never falls back from the Rust library. */
class DeterministicTestSvgRenderer : SvgRenderer {
    override fun render(request: RenderRequest): RenderResult {
        val catalog = ColorCatalogs.get(request.colorCatalogId)
        val colors = request.workColorSnapshot?.colorMap ?: catalog.renderMap
        val catalogId = request.workColorSnapshot?.catalogId ?: catalog.id
        val svg = buildString {
            append("<svg xmlns=\"http://www.w3.org/2000/svg\" data-seed=\"")
            append(request.renderSeed)
            append("\"><path d=\"M 20 50 L 80 50\" stroke=\"")
            append(colors.getValue("red"))
            append("\"/><circle cx=\"75\" cy=\"25\" r=\"12\" fill=\"")
            append(colors.getValue("blue"))
            append("\"/></svg>")
        }
        val metadata = JSONObject()
            .put("render_engine_id", "test-double")
            .put("render_engine_version", "0")
            .put("render_seed", request.renderSeed ?: JSONObject.NULL)
            .put("render_color_catalog_id", catalogId)
            .put("render_color_map", JSONObject(colors))
        val metadataJson = metadata.toString()
        val hash = MessageDigest.getInstance("SHA-256")
            .digest((svg + metadataJson).toByteArray())
            .joinToString("") { "%02x".format(it) }
        return RenderResult(svg, metadataJson, hash)
    }
}
