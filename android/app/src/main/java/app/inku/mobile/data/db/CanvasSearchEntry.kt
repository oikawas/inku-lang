package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import org.json.JSONObject

/** Search only the small columns; artwork and Scores never enter the search cursor. */
data class CanvasSearchEntry(
    val id: String,
    @ColumnInfo(name = "original_input") val originalInput: String,
    @ColumnInfo(name = "source_text") val sourceText: String?,
    @ColumnInfo(name = "render_hash") val renderHash: String,
    @ColumnInfo(name = "render_metadata_json") val renderMetadataJson: String,
) {
    fun matches(raw: String): Boolean {
        val query = raw.trim().lowercase()
        if (query.isEmpty()) return true
        if (UUID.matches(query)) return id.equals(query, ignoreCase = true)
        if ((sourceText ?: originalInput).contains(query, ignoreCase = true)) return true
        val descriptionHash = runCatching { JSONObject(renderMetadataJson).optString("description_hash") }.getOrDefault("")
        return listOf(renderHash, descriptionHash).any { stored ->
            val hash = stored.lowercase()
            hash.startsWith(query) || hash.endsWith(query) ||
                (':' !in query && hash.substringAfter(':').startsWith(query))
        }
    }

    private companion object {
        val UUID = Regex("[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
    }
}
