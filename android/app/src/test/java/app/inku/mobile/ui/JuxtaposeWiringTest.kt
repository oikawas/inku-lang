package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

/** 取り合わせ in the work-actions menu and the child it draws (SPEC §7.8, Web `drawLineageDescriptionEdit`). */
class JuxtaposeWiringTest {
    private fun projectFile(relative: String): File {
        val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
        return candidates.firstOrNull(File::isFile) ?: candidates.first()
    }

    @Test
    fun theEntryFollowsModelChangeIsHiddenWithoutADescriptionAndHeldForADdlLedWork() {
        val app = projectFile("app/src/main/java/app/inku/mobile/ui/InkuApp.kt").readText()
        val menu = app.substring(app.indexOf("private fun WorkActionsDialog("), app.indexOf("private fun WorkSketchDialog("))
        val model = menu.indexOf("testTag(MODEL_ENTRY_TAG)")
        val entry = menu.indexOf("testTag(JUXTAPOSE_ENTRY_TAG)")
        assertTrue(model in 0 until entry)
        assertTrue(entry < menu.indexOf("openAutonomousRefinement"))
        val guard = menu.substring(model, entry)
        assertTrue(guard.contains("if (sourceTextOf(item).isNotBlank())"))
        assertTrue(guard.contains("enabled = descriptionLocked == false"))
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val open = viewModel.substring(viewModel.indexOf("fun openJuxtaposition("), viewModel.indexOf("fun selectJuxtapositionModel("))
        assertTrue(open.contains("current.workActionsDescriptionLocked != false) return"))
    }

    @Test
    fun theChildIsADescriptionEditThatRecordsTheSentenceAndKeepsItsParentsWildness() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val draw = viewModel.substring(viewModel.indexOf("fun drawJuxtaposition()"), viewModel.indexOf("/** Puts a candidate on the canvas"))
        assertTrue(draw.contains("JuxtaposedDraw(choice.joined, juxtapositionMetadata(choice, result), item.drawnWild)"))
        val submit = viewModel.substring(viewModel.indexOf("private fun runSubmit("), viewModel.indexOf("fun drawFromDdl()"))
        val declared = submit.substring(submit.indexOf("juxtaposed != null -> {"), submit.indexOf("sketchRedraw -> {"))
        assertTrue(declared.contains("derivationKind = SubmitDerivationKind.DESCRIPTION_EDIT"))
        assertTrue(declared.contains("mapOf(\"edited_from_history_id\" to parent.id) + juxtaposed.metadata"))
        assertTrue(submit.contains("renderWild = juxtaposed?.wild ?: current.renderWild"))
        assertTrue(submit.contains("if (sketchRedraw) refreshLineage()"))
    }
}
