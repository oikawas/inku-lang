package app.inku.mobile.data.model

import app.inku.mobile.ui.InkuUiState
import app.inku.mobile.ui.InkuViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.*
import org.junit.Test

class CanvasRatioTest {
    @Test
    fun onlyTheFirstWholeValidDeclarationSuppliesTheReducedRatio() {
        assertEquals(CanvasRatio(16, 9), CanvasRatio.declared("\uFEFF画面比　３２：１８。青の円を置く。画面比1:1。"))
        assertEquals(CanvasRatio(2, 3), CanvasRatio.declared("Aspect RATIO 4:6! place one circle."))
        assertNull(CanvasRatio.declared("画面比0:1。画面比10001:1。画面比1.5:1。画面比1:2の円。"))
        assertEquals(CanvasRatio(1, 10_000), CanvasRatio.declared("画面比1:10000。"))
    }

    @Test
    fun onlyAnUntouchedSavedDdlFallsBackToItsRecordedPaper() {
        installCanvasRegistryForJvmTest()
        val plain = "青の円を1個置く。"
        assertNull(canvasFitQuestion(plain, null, null, "vertical"))
        assertNull(canvasFitQuestion(plain, plain, null, "vertical"))
        assertNull(canvasFitQuestion(plain + "\n", plain, "square", "vertical"))
        assertNull(canvasFitQuestion("画面比18:32。$plain", null, null, "vertical"))
        assertEquals(CanvasRatio(1, 1), canvasFitQuestion(plain, plain, "square", "vertical")!!.basis)
        assertEquals(CanvasRatio(4, 3), canvasFitQuestion("Aspect ratio 4:3. $plain", plain, "square", "vertical")!!.basis)
    }

    @Test
    fun cancellingTheActualDrawEntranceKeepsTheDdlAndItsEditorWithoutStartingARun() {
        installCanvasRegistryForJvmTest()
        val before = InkuUiState(ddl = "画面比1:1。青の円を1個置く。", ddlEditorOpen = true,
            ddlEditedAfterGeneration = true, selectedCanvasAspect = "vertical")
        val state = MutableStateFlow(before)
        val unsafeType = Class.forName("sun.misc.Unsafe")
        val unsafe = unsafeType.getDeclaredField("theUnsafe").apply { isAccessible = true }.get(null)
        val vm = unsafeType.getMethod("allocateInstance", Class::class.java).invoke(unsafe, InkuViewModel::class.java) as InkuViewModel
        for (field in listOf("localState", "state")) {
            InkuViewModel::class.java.getDeclaredField(field).apply { isAccessible = true }.set(vm, state)
        }
        vm.drawFromDdl()
        assertNotNull(state.value.canvasFitQuestion)
        assertTrue(state.value.ddlEditorOpen)
        assertFalse(state.value.isDrawing)
        vm.cancelCanvasFit()
        assertEquals(before, state.value)
        // A stale answer after dismissal cannot draw through the old request.
        vm.answerCanvasFit(true)
        assertEquals(before, state.value)
    }
}
