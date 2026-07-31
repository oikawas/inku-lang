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
        val resultSparse = WebDdlExpander.expandIntermediateDdl(
            inputDdl,
            tenkei = "sparse",
            variationAmplitude = "medium",
            variationSeed = 42L,
        )

        assertNotEquals(resultNone, resultSparse)
        assertTrue(resultNone.isNotEmpty())
        assertTrue(resultSparse.isNotEmpty())
    }
}
