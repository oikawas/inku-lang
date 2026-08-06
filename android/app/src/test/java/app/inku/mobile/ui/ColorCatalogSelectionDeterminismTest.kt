package app.inku.mobile.ui

import app.inku.mobile.data.model.CatalogSelection
import app.inku.mobile.data.model.ColorCatalogs
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The catalogue a run uses is a function of the settings alone (ledger I-081).
 *
 * This drives the real `CatalogSelection`, the way the server's
 * `test_color_auto_select` runs the real `select_catalog_id` and replaces only
 * the model call: hollowing out the resolver has to show up here. The version
 * of this file that shipped with I-081 asserted against a private helper of its
 * own that returned `state.selectedCatalogId`, so it held whatever the app did
 * -- putting the random pick back left all of it green (ledger I-103).
 *
 * It says nothing about whether the drawing paths call the resolver; that is
 * what the instrumented `CatalogSelectionWiringTest` is for.
 */
class ColorCatalogSelectionDeterminismTest {

    @Test
    fun t1_theSettingIsWhatTheRunUses() {
        for (catalog in ColorCatalogs.all) {
            assertEquals(
                "the run must use the catalogue the settings name",
                catalog.id,
                CatalogSelection.resolvedCatalogIdForRun(catalog.id),
            )
        }
    }

    @Test
    fun t2_repeatedRunsOfTheSameSettingReachTheSameCatalogue() {
        val resolved = (1..50).map { CatalogSelection.resolvedCatalogIdForRun("ink_season") }

        assertEquals("ink_season", resolved.first())
        assertEquals(
            "the resolver must answer with one catalogue across runs",
            1,
            resolved.toSet().size,
        )
    }

    @Test
    fun t3_everyCatalogueInTheListIsReachable() {
        // The counterpart of the server's "every id in the list is accepted":
        // a resolver that collapsed onto one catalogue would pass t2 alone.
        val resolved = ColorCatalogs.all.map { CatalogSelection.resolvedCatalogIdForRun(it.id) }

        assertEquals(ColorCatalogs.all.size, resolved.toSet().size)
    }

    @Test
    fun t4_aSettingThatIsNoLongerACatalogueFallsBackToTheDefault() {
        // The server answers 422 here. A value saved by an older build of this
        // app is not a request, so it falls back instead of refusing to draw.
        assertEquals("default", CatalogSelection.resolvedCatalogIdForRun("retired_catalog"))
    }
}
