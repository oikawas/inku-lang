package app.inku.mobile.pipeline

import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WebDdlExpanderTenkeiTest {

    @Test
    fun expandIntermediateDdl_changesOutputWhenTenkeiIsSpecified() {
        val inputDdl = "青い円を5個、横に並べる"

        val resultNone = WebDdlExpander.expandIntermediateDdl(
            inputDdl,
            tenkei = "none",
            variationAmplitude = "medium",
            variationSeed = 42L,
        )
        val resultAuto = WebDdlExpander.expandIntermediateDdl(
            inputDdl,
            tenkei = "auto",
            variationAmplitude = "medium",
            variationSeed = 42L,
        )

        assertNotEquals(resultNone, resultAuto)
        assertTrue(resultNone.isNotEmpty())
        assertTrue(resultAuto.isNotEmpty())
    }
}
