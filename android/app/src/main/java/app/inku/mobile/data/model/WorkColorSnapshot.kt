package app.inku.mobile.data.model

import org.json.JSONObject

data class WorkColorSnapshot(
    val catalogId: String,
    val colorMap: Map<String, String>,
)

fun workColorSnapshot(renderMetadataJson: String): WorkColorSnapshot? = runCatching {
    val metadata = JSONObject(renderMetadataJson)
    val colorMap = metadata.optJSONObject("render_color_map")
    if (colorMap == null || colorMap.length() == 0) {
        return null
    }
    val drawnWith = metadata.optString("render_color_catalog_id")
        .ifBlank { metadata.optString("catalog_id") }
        .ifBlank { "default" }
    WorkColorSnapshot(
        catalogId = drawnWith,
        colorMap = colorMap.keys().asSequence().associateWith { colorMap.get(it).toString() },
    )
}.getOrNull()
