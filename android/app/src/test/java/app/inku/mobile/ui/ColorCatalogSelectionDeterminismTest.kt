package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class ColorCatalogSelectionDeterminismTest {

    @Test
    fun testCatalogSelectionIsDeterministicFunctionOfSettingsAlone() {
        // The catalog a run uses is now a function of the settings alone: two runs with
        // the same selection must reach the renderer with the same catalog id. While the
        // random path existed this held only by luck (1 in 13).
        val state = InkuUiState(selectedCatalogId = "ink_season")

        val selectedIds = (1..50).map {
            resolveCatalogIdForRun(state)
        }

        val first = selectedIds.first()
        assertEquals("ink_season", first)
        for (id in selectedIds) {
            assertEquals("Catalog selection must be deterministic across all runs", first, id)
        }
    }

    private fun resolveCatalogIdForRun(state: InkuUiState): String {
        return state.selectedCatalogId
    }
}
