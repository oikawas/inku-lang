package app.inku.mobile.data.model

import org.json.JSONObject

data class CanvasAspect(
    val id: String,
    val label: String,
    val widthUnits: Int,
    val heightUnits: Int,
) {
    val ratioW: Double get() = widthUnits.toDouble()
    val ratioH: Double get() = heightUnits.toDouble()
    val ratioLabel: String get() = "$widthUnits:$heightUnits"
}

data class CanvasSize(
    val width: Int,
    val height: Int,
) {
    val unit: Int get() = minOf(width, height)
}

/**
 * Android labels joined to the canonical registry supplied by shared Rust.
 *
 * This object never references the JNI bridge. Android startup injects the
 * registry JSON, while local JVM tests can inject the same wire shape without
 * loading a native library.
 */
object CanvasAspects {
    const val basePx = 1000
    const val DEFAULT_ID = "square"
    const val REGISTRY_SCHEMA = "inku.canvas-format-registry.v1"
    const val LEGACY_PIXEL9_LANDSCAPE_SAFE_ID = "pixel9_landscape_safe"

    private data class InstalledRegistry(
        val digest: String,
        val formats: List<CanvasAspect>,
        val byId: Map<String, CanvasAspect>,
    )

    private val labels = linkedMapOf(
        "square" to "Square",
        "golden" to "Golden Ratio",
        "a4" to "A4 Root Rectangle",
        "b4" to "B4 Root Rectangle",
        "pillar" to "Pillar",
        "oban" to "Oban",
        "wide" to "CinemaScope",
        "byobu" to "Byobu",
        "vertical" to "Mobile Vertical",
        "sd_monitor" to "SD Monitor",
        "hd_monitor" to "HD Monitor",
    )

    // Read compatibility only. It is not offered for new paper and is never
    // aliased to a canonical 16:9 format.
    private val legacyPixel9LandscapeSafe = CanvasAspect(
        id = LEGACY_PIXEL9_LANDSCAPE_SAFE_ID,
        label = "Pixel 9 Landscape Safe",
        widthUnits = 9,
        heightUnits = 5,
    )

    @Volatile
    private var installed: InstalledRegistry? = null

    val all: List<CanvasAspect>
        get() = registry().formats

    val registryDigest: String
        get() = registry().digest

    fun installRegistry(reportJson: String) {
        val report = JSONObject(reportJson)
        val registryJson = report.getJSONObject("registry")
        require(registryJson.getString("schema") == REGISTRY_SCHEMA) { "unknown_canvas_registry" }
        val digest = report.getString("digest")
        require(DIGEST_PATTERN.matches(digest)) { "invalid_canvas_registry_digest" }
        val formatsJson = registryJson.getJSONArray("formats")
        require(formatsJson.length() == labels.size) { "unexpected_canvas_format_count" }

        val seen = linkedSetOf<String>()
        val formats = (0 until formatsJson.length()).map { index ->
            val value = formatsJson.getJSONObject(index)
            require(value.keys().asSequence().toSet() == FORMAT_KEYS) { "unexpected_canvas_format_shape" }
            val id = value.getString("id")
            require(seen.add(id)) { "duplicate_canvas_format_id" }
            val label = labels[id] ?: throw IllegalArgumentException("unknown_canvas_format")
            val widthUnits = value.getLong("width_units")
            val heightUnits = value.getLong("height_units")
            require(widthUnits in 1L..Int.MAX_VALUE.toLong() && heightUnits in 1L..Int.MAX_VALUE.toLong()) {
                "invalid_canvas_format_units"
            }
            CanvasAspect(
                id = id,
                label = label,
                widthUnits = widthUnits.toInt(),
                heightUnits = heightUnits.toInt(),
            )
        }
        require(seen == labels.keys) { "canvas_registry_labels_do_not_match" }
        val candidate = InstalledRegistry(digest, formats, formats.associateBy(CanvasAspect::id))
        synchronized(this) {
            installed?.let { current ->
                require(current == candidate) { "canvas_registry_changed_after_install" }
            }
            installed = candidate
        }
    }

    /** Selects the explicit default for a missing, legacy, or unknown new-paper choice. */
    fun newSelectionOrDefault(id: String?): String =
        id?.takeIf { registry().byId.containsKey(it) } ?: DEFAULT_ID

    /** Exact read lookup, including the one retained legacy paper identity. */
    fun normalize(id: String?): String {
        require(id != null && (registry().byId.containsKey(id) || id == LEGACY_PIXEL9_LANDSCAPE_SAFE_ID)) {
            "unknown_canvas_format"
        }
        return id
    }

    fun labelFor(id: String): String =
        registry().byId[id]?.label ?: if (id == LEGACY_PIXEL9_LANDSCAPE_SAFE_ID) legacyPixel9LandscapeSafe.label else id

    fun ratioFor(id: String?): Double {
        val exactId = normalize(id)
        val aspect = registry().byId[exactId] ?: legacyPixel9LandscapeSafe
        return aspect.ratioW / aspect.ratioH
    }

    /**
     * The paper's pixel width, using half-to-even rounding like the existing
     * Android/server export contract.
     */
    fun sizeFor(id: String?): CanvasSize {
        val ratio = ratioFor(id)
        return CanvasSize(width = Math.rint(basePx * ratio).toInt(), height = basePx)
    }

    private fun registry(): InstalledRegistry =
        checkNotNull(installed) { "canvas_registry_not_installed" }

    private val FORMAT_KEYS = setOf("id", "width_units", "height_units")
    private val DIGEST_PATTERN = Regex("[0-9a-f]{64}")
}
