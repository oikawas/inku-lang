package app.inku.mobile.ui

import app.inku.mobile.data.model.CatalogSelection
import app.inku.mobile.data.model.ColorCatalogs
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * A fixed setting is a pure lookup through the catalogue list. Auto is not
 * resolved on this side: the sentinel goes to the shared pipeline, and
 * ColorCatalogAutoWiringTest guards that no drawing route picks a catalogue
 * before it.
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
        assertEquals("default", CatalogSelection.normalizedSelectionId("retired_catalog"))
        assertEquals("auto", CatalogSelection.normalizedSelectionId("auto"))
    }
}
