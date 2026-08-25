package app.inku.mobile.data.model

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import kotlinx.coroutines.CancellationException

/**
 * The one place a run's colour catalogue is decided.
 *
 * This mirrors the server, where every paint resolves its catalogue through a
 * single helper (`_resolved_paint_catalog_id` in
 * `api_core/routers/render.py`, called once at the one place the route needs
 * it). Before this object existed the five drawing paths here each read
 * `InkuUiState.selectedCatalogId` on their own, so "nothing but the setting
 * decides the catalogue" was a statement about five places at once and no test
 * could stand on it (ledger I-103).
 *
 * Android keeps fixed catalogue IDs plus the `auto` setting sentinel. Auto is
 * resolved here through the selected Stage 1 model; the saved work receives
 * only the resulting real ID. The server's refinement-only `random` mode does
 * not exist here, and the demo path's former random pick remains removed.
 */
object CatalogSelection {

    const val AUTO_ID = "auto"

    private val jsonIdPattern = Regex("\\\"catalog_id\\\"\\s*:\\s*\\\"([A-Za-z0-9_]+)\\\"")

    /**
     * The catalogue id a run uses.
     *
     * The value is normalised through the catalogue list, which is what the
     * server's `_resolved_catalog_id` does with the requested id. The two part
     * ways on an id that is not in the list: the server answers 422, while a
     * setting saved by an older build of this app falls back to the default
     * catalogue rather than refusing to draw.
     */
    fun resolvedCatalogIdForRun(selectedCatalogId: String): String =
        ColorCatalogs.get(selectedCatalogId).id

    /** Keeps the auto sentinel but normalizes every fixed setting through the allowlist. */
    fun normalizedSelectionId(selectedCatalogId: String): String =
        if (selectedCatalogId == AUTO_ID) AUTO_ID else resolvedCatalogIdForRun(selectedCatalogId)

    /**
     * Resolves the auto sentinel through the already selected Stage 1 provider.
     * A failed or unusable selection falls back to the default catalog so a
     * drawing can continue without changing any pipeline behavior.
     */
    suspend fun resolveCatalogIdForRun(
        selectedCatalogId: String,
        sourceText: String,
        stage1ModelId: String,
        modelProvider: ModelProvider,
    ): String {
        if (selectedCatalogId != AUTO_ID) return resolvedCatalogIdForRun(selectedCatalogId)
        val text = sourceText.trim()
        if (text.isEmpty()) return DEFAULT_ID
        val raw = try {
            modelProvider.generate(
                ModelRequest(
                    modelId = stage1ModelId,
                    prompt = text,
                    temperature = 0.3,
                    maxTokens = 200,
                    systemInstruction = buildCatalogCard(),
                ),
            ).text
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            return DEFAULT_ID
        }
        return extractCatalogId(raw)?.takeIf { ColorCatalogs.find(it) != null } ?: DEFAULT_ID
    }

    fun buildCatalogCard(): String = buildString {
        appendLine("You choose one color catalog for a drawing, by reading its description.")
        appendLine("Read what the description is about -- its subject, its light, its season,")
        appendLine("its material -- and pick the catalog whose colors belong to it.")
        appendLine()
        appendLine("Catalogs:")
        ColorCatalogs.all.forEach { catalog ->
            appendLine("- ${catalog.id}: ${catalog.name} -- ${catalog.sub} / ${catalog.subJa} [${catalog.paletteNamesJa.joinToString(", ")}]")
        }
        appendLine()
        appendLine("Answer with JSON only: {\"catalog_id\": \"<one id from the list>\"}")
        append("No other text.")
    }

    private fun extractCatalogId(raw: String): String? {
        jsonIdPattern.find(raw)?.groupValues?.getOrNull(1)?.let { return it }
        return ColorCatalogs.all
            .asSequence()
            .map { it.id }
            .sortedByDescending { it.length }
            .firstOrNull { candidate -> Regex("\\b${Regex.escape(candidate)}\\b").containsMatchIn(raw) }
    }

    private const val DEFAULT_ID = "default"
}
