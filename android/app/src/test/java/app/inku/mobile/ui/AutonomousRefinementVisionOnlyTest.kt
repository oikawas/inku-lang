package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Random autonomous refinement was removed (the author, 2026-10-18; SPEC 「自律推敲の方式」). */
class AutonomousRefinementVisionOnlyTest {
    private fun projectFile(relative: String): File {
        val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
        return candidates.firstOrNull(File::isFile) ?: candidates.first()
    }

    @Test
    fun visionNamesEachGenerationAndNothingDrawsItAtRandom() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val run = viewModel.substring(viewModel.indexOf("fun startAutonomousRefinement()"), viewModel.indexOf("/** Puts a candidate on the canvas"))
        assertTrue(run.contains("advice?.suggestedKind?.takeIf { it in settings.allowedKinds } ?: settings.allowedKinds.first()"))
        assertFalse(run.contains("allowedKinds.random()"))
        assertTrue(run.contains("\"autonomous_refine_mode\" to \"vision\""))
        // A work drawn straight from DDL shows Vision its instructions, not an empty text.
        assertTrue(run.contains("instruction = sourceTextOf(item).ifBlank { item.normalizedDdl.orEmpty() }"))
        val dialogs = projectFile("app/src/main/java/app/inku/mobile/ui/SavedWorkParityDialogs.kt").readText()
        val parity = projectFile("app/src/main/java/app/inku/mobile/ui/ParityState.kt").readText()
        assertFalse(dialogs.contains("AutonomousRefinementMode"))
        assertFalse(parity.contains("AutonomousRefinementMode"))
    }
}
