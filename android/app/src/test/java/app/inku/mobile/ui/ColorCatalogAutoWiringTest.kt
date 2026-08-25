package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JVM-only guard for the call-site ownership of I-382's auto selector.
 *
 * The focused selector test exercises the real resolver against a recording
 * provider. These source assertions keep the UI routes from accidentally
 * moving that call to a DDL, replay, or refinement path without requiring an
 * emulator or Room fixture.
 */
class ColorCatalogAutoWiringTest {

    @Test
    fun normalDrawSelectsFromSketchProseBeforeComposing() {
        val draw = viewModelSection("private fun runSubmit", "fun drawFromDdl()")

        assertTrue(
            "normal draw must prefer the Stage 0.5 prose while retaining prompt fallback",
            Regex("interpreted\\.sketchText\\s*\\?:\\s*current\\.prompt").containsMatchIn(draw),
        )
        assertEquals("normal draw must choose exactly once", 1, selectorCalls(draw))
        assertTrue(
            "a replay must keep its recorded catalog and skip auto selection",
            Regex("if\\s*\\(sketchRequest\\.text\\s*!=\\s*null\\).*?\\\"default\\\".*?else.*?repository\\.selectCatalogId", RegexOption.DOT_MATCHES_ALL).containsMatchIn(draw),
        )
    }

    @Test
    fun batchSelectsOnceForEachNonBlankLine() {
        val batch = viewModelSection("fun runBatch()", "private fun rememberBatchPrompt")

        assertTrue("selection must stay inside the per-line loop", batch.contains("lines.forEachIndexed"))
        assertEquals("a batch line must select exactly once", 1, selectorCalls(batch))
    }

    @Test
    fun demoSelectsOnceForEachCycle() {
        val demo = viewModelSection("fun startDemo()", "fun stopDrawing()")

        assertTrue("selection must stay inside the demo cycle", demo.contains("while (isActive"))
        assertEquals("a demo cycle must select exactly once", 1, selectorCalls(demo))
    }

    @Test
    fun ddlReplayAndRefinementNeverInvokeTheSelector() {
        assertEquals(0, selectorCalls(viewModelSection("fun drawFromDdl()", "fun runBatch()")))
        assertEquals(0, selectorCalls(viewModelSectionToEnd("fun openRefinement")))
        assertEquals("only normal, batch, and demo own selector calls", 3, selectorCalls(source("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt")))
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
        Regex("repository\\.selectCatalogId\\(").findAll(source).count()

    private fun viewModelSection(start: String, end: String): String {
        return sourceSection(source("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt"), start, end)
    }

    private fun viewModelSectionToEnd(start: String): String {
        val content = source("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt")
        val from = content.indexOf(start)
        assertTrue("missing source section beginning $start", from >= 0)
        return content.substring(from)
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
