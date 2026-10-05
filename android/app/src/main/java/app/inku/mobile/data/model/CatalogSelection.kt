package app.inku.mobile.data.model

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
 * not resolved here: the sentinel goes to the shared pipeline, which chooses
 * the catalogue (`catalog_mode` "auto"), and the saved work receives only the
 * resulting real ID. The server's refinement-only `random` mode does not exist
 * here, and the demo path's former random pick remains removed.
 */
object CatalogSelection {

    const val AUTO_ID = "auto"

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
}
