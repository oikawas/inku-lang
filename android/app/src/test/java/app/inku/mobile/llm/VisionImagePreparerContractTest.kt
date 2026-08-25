package app.inku.mobile.llm

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VisionImagePreparerContractTest {

    @Test
    fun preparationBoundsAndReencodesTheCameraImage() {
        var source = File("src/main/java/app/inku/mobile/llm/VisionImagePreparer.kt")
        if (!source.isFile) source = File("app/src/main/java/app/inku/mobile/llm/VisionImagePreparer.kt")
        assertTrue("VisionImagePreparer.kt must exist", source.isFile)

        val text = source.readText()
        assertTrue(text.contains("MAX_LONG_EDGE = 1280"))
        assertTrue(text.contains("JPEG_QUALITY = 85"))
        assertTrue(text.contains("ImageDecoder"))
        assertTrue(text.contains("setTargetSize"))
        assertTrue(text.contains("Bitmap.CompressFormat.JPEG"))
    }

    @Test
    fun boundedSizePreservesAspectAndNeverUpscales() {
        assertEquals(1280 to 640, VisionImagePreparer.boundedSize(4000, 2000))
        assertEquals(640 to 1280, VisionImagePreparer.boundedSize(2000, 4000))
        assertEquals(800 to 600, VisionImagePreparer.boundedSize(800, 600))
    }
}
