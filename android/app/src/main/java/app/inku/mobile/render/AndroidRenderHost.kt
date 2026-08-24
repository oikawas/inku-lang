package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalog
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.pipeline.RenderRequest
import java.math.BigInteger
import java.security.MessageDigest
import org.json.JSONObject

/**
 * Android-owned preparation of one canonical Rust render request.
 *
 * This adapter does not migrate raw model output, render geometry, or own history identity.
 * Production uses this host for the current Rust renderer; tests may inject a bridge.
 */
class AndroidRenderHost(
    private val bridge: RenderBridge = NativeRenderBridge,
    private val catalogResolver: (String?) -> ColorCatalog = ColorCatalogs::get,
) : SvgRenderer {
    override fun render(request: RenderRequest): RenderResult {
        bridge.requireCompatibleNativePackage()

        // Compatibility/coerce owns migration before this host seam. The host
        // only parses the already-renderable canonical Score it is handed.
        val score = JSONObject(request.scoreJson)
        val aspectId = resolvedAspectId(request, score)
        val canvas = CanvasAspects.sizeFor(aspectId)
        val catalog = catalogResolver(request.colorCatalogId)
        val snapshot = request.workColorSnapshot
        val resolvedColorMap = snapshot?.colorMap ?: catalog.renderMap
        val resolvedCatalogId = snapshot?.catalogId ?: catalog.id
        val recordedCatalog = snapshot?.let { ColorCatalogs.find(it.catalogId) }
        val catalogName = snapshot?.catalogName?.takeIf(String::isNotEmpty)
            ?: recordedCatalog?.name
            ?: resolvedCatalogId
        val catalogSub = snapshot?.catalogSub?.takeIf(String::isNotEmpty)
            ?: recordedCatalog?.sub
            ?: ""

        val renderSeed = resolvedSeed(request.renderSeed, score, "render_seed")
        val compositionSeed = resolvedSeed(request.compositionSeed, score, "composition_seed")
        val wild = request.wild
            ?: score.optBoolean("render_wild", score.optBoolean("wild", false))

        val options = JSONObject()
            .put("resolved_color_map", JSONObject(resolvedColorMap))
            .put("catalog_id", resolvedCatalogId)
            .put(
                "canvas",
                JSONObject()
                    .put("width", canvas.width)
                    .put("height", canvas.height),
            )
            .put("canvas_aspect_id", aspectId)
            .put("svg_profile", request.svgProfile)
            .putSemanticSeed("render_seed", renderSeed)
            .putSemanticSeed("composition_seed", compositionSeed)
            .put("wild", wild)
        val requestJson = JSONObject()
            .put("score", score)
            .put("options", options)
            .toString()

        val native = bridge.render(requestJson)
        require(native.svg.startsWith("<svg")) { "Rust renderer returned a non-SVG payload" }
        val metadata = JSONObject(native.metadataJson)
        val engineId = bridge.renderEngineId()
        val engineVersion = bridge.renderEngineVersion()
        check(metadata.optString("render_engine_id") == engineId) {
            "Rust render metadata engine id does not match the binding"
        }
        check(metadata.optString("render_engine_version") == engineVersion) {
            "Rust render metadata engine version does not match the binding"
        }

        metadata
            .put("render_canvas_aspect", aspectId)
            .put("render_canvas_aspect_id", aspectId)
            .put("render_canvas_aspect_ratio", CanvasAspects.ratioFor(aspectId))
            .put("render_color_catalog_id", resolvedCatalogId)
            .put("render_color_catalog_name", catalogName)
            .put("render_color_catalog_sub", catalogSub)
            .put(
                "render_color_profile",
                JSONObject()
                    .put("id", "srgb")
                    .put("name", "sRGB IEC61966-2.1")
                    .put("standard", "IEC 61966-2-1:1999"),
            )
            .put("render_color_map", JSONObject(resolvedColorMap))
            .put("render_wild", wild)

        // RenderResult still carries this adapter projection for legacy callers.
        // The pipeline/history owner calculates the canonical work identity separately.
        val renderHash = sha256(native.svg + metadata.toString())
        metadata.put("render_hash", renderHash)
        return RenderResult(
            svg = native.svg,
            metadataJson = metadata.toString(),
            renderHash = renderHash,
        )
    }

    private fun resolvedAspectId(request: RenderRequest, score: JSONObject): String {
        val requested = request.canvasAspect.takeIf(String::isNotBlank)
        val scoreCanvas = when (val value = score.opt("canvas")) {
            is JSONObject -> value.optString("aspect").takeIf(String::isNotBlank)
            is String -> value.takeIf(String::isNotBlank)
            else -> null
        }
        return CanvasAspects.normalize(requested ?: scoreCanvas)
    }

    private fun resolvedSeed(explicit: Long?, score: JSONObject, key: String): BigInteger? {
        if (explicit != null) return exactSeed(explicit)
        if (!score.has(key) || score.isNull(key)) return null
        return when (val value = score.opt(key)) {
            is BigInteger -> value
            is Long -> exactSeed(value)
            is Int, is Short, is Byte -> exactSeed((value as Number).toLong())
            is Number -> value.toString().toBigIntegerOrNull()
            is String -> value.toBigIntegerOrNull()
            else -> null
        }
    }

    private fun exactSeed(seed: Long): BigInteger = if (seed >= 0L) {
        BigInteger.valueOf(seed)
    } else {
        BigInteger(java.lang.Long.toUnsignedString(seed))
    }

    private fun JSONObject.putSemanticSeed(key: String, seed: BigInteger?): JSONObject =
        put(key, seed ?: JSONObject.NULL)

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { byte -> "%02x".format(byte) }
}
