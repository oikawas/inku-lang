package app.inku.mobile.pipeline

import org.junit.Assert.assertEquals
import org.junit.Test

class SketchChoiceTest {
    @Test
    fun retiredGrainStaysReadableButDoesNotTurnOnNewDrawings() {
        assertEquals(SketchMode.Off, Sketches.DEFAULT_MODE)
        assertEquals(SketchMode.On, Sketches.modeOfWork("fine", "fine"))
        assertEquals(SketchGrain.Fine, Sketches.recordedGrainOf("fine"))
    }
}
