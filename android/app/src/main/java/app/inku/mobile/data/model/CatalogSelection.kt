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
 * The server offers three modes -- `fixed`, `auto` and `random` -- and this
 * client has none of them: the catalogue is the setting, and the demo path
 * that used to pick one at random was removed in I-081. Should a mode arrive
 * here it belongs in this function, not at a call site.
 */
object CatalogSelection {

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
}
