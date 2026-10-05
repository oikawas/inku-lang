package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JVM-only guard for where the colour catalogue of a run is chosen (I-382).
 *
 * `auto` is resolved inside the shared pipeline (`catalog_mode` "auto"), so
 * every drawing route hands the setting over as it is. These source
 * assertions keep a route from growing its own selector again -- the batch and
 * demo used to call a repository selector that by then only returned its
 * argument -- without requiring an emulator or Room fixture.
 */
class ColorCatalogAutoWiringTest {

    @Test
    fun batchHandsEachLineTheSettingAsItIs() {
        val batch = viewModelSection("fun runBatch()", "private fun rememberBatchPrompt")

        assertTrue("the catalogue is read inside the per-line loop", batch.contains("lines.forEachIndexed"))
        assertTrue("a batch line draws in the setting", batch.contains("val catalogId = current.selectedCatalogId"))
        assertEquals("no batch line chooses a catalogue of its own", 0, selectorCalls(batch))
    }

    @Test
    fun demoHandsEachCycleTheSettingAsItIs() {
        val demo = viewModelSection("fun startDemo()", "fun stopDrawing()")

        assertTrue("the catalogue is read inside the demo cycle", demo.contains("while (isActive"))
        assertTrue("a demo cycle draws in the setting", demo.contains("val catalogId = cycle.selectedCatalogId"))
        assertEquals("no demo cycle chooses a catalogue of its own", 0, selectorCalls(demo))
    }

    @Test
    fun noRouteChoosesACatalogueBeforeThePipeline() {
        // A normal draw, DDL, replay and refinement never did; the batch and
        // the demo no longer do. The auto catalogue is chosen inside the
        // shared pipeline.
        assertEquals(0, selectorCalls(source("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt")))
        assertEquals(0, selectorCalls(source("app/src/main/java/app/inku/mobile/data/InkuRepository.kt")))
    }

    @Test
    fun autoIsPreservedBySettingsAndShownAsTheCatalogSentinel() {
        val viewModel = source("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt")
        val app = source("app/src/main/java/app/inku/mobile/ui/InkuApp.kt")

        assertTrue("setCatalog must preserve auto while allowlisting fixed IDs", Regex("fun setCatalog\\(id: String\\).*?normalizedSelectionId\\(id\\).*?selectedCatalogId = selectionId", RegexOption.DOT_MATCHES_ALL).containsMatchIn(viewModel))
        assertTrue("setCatalog must persist the normalized selection including auto", Regex("persistSetting\\(\\\"color_catalog\\\".*?selectionId", RegexOption.DOT_MATCHES_ALL).containsMatchIn(viewModel))
        val dialog = sourceSection(app, "private fun ColorCatalogSelectionDialog", "private fun CanvasAspectSelectionDialog")
        assertTrue("the catalog dialog must expose the auto sentinel", dialog.contains("CatalogSelection.AUTO_ID"))
        assertTrue("the catalog dialog must place auto before the fixed catalog list", dialog.indexOf("CatalogSelection.AUTO_ID") < dialog.indexOf("ColorCatalogs.all"))
        assertTrue("only the exact auto sentinel may show auto details", dialog.contains("if (autoSelected)"))
        assertTrue("unknown legacy IDs must retain the default catalog display", dialog.contains("ColorCatalogs.get(state.selectedCatalogId)"))
    }

    private fun selectorCalls(source: String): Int =
        Regex("selectCatalogId\\(|resolveCatalogIdForRun\\(").findAll(source).count()

    private fun viewModelSection(start: String, end: String): String {
        return sourceSection(source("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt"), start, end)
    }

    private fun sourceSection(content: String, start: String, end: String): String {
        val from = content.indexOf(start)
        assertTrue("missing source section beginning $start", from >= 0)
        val until = content.indexOf(end, startIndex = from + start.length)
        assertTrue("missing source section ending $end", until > from)
        return content.substring(from, until)
    }

    private fun source(relativePath: String): String {
        val direct = File(relativePath)
        val parent = File("../$relativePath")
        val file = when {
            direct.exists() -> direct
            parent.exists() -> parent
            else -> error("missing source $relativePath")
        }
        return file.readText()
    }
}
