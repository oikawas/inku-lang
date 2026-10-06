package app.inku.mobile.ui

import android.graphics.Bitmap
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.db.HistoryItemEntity
import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Real display components and JNI, with fixed SVG only; no repository or provider. */
@RunWith(AndroidJUnit4::class)
class SharedDisplayUiDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun candidateAndRotatedArtworkKeepTheirColorsAndRangeFrames() {
        val quarter = requireNotNull(RangeFraction.of(1, 4))
        val bounds = DdlRangeBounds(requireNotNull(RangeFraction.of(0, 1)), quarter,
            quarter, requireNotNull(RangeFraction.of(3, 4)))
        val item = HistoryItemEntity(id = "display-check", createdAt = 0, updatedAt = 0,
            originalInput = "", normalizedDdl = null, scoreJson = "{}", displaySvg = SVG,
            stage1Model = null, stage2Model = null, renderMetadataJson = "{}",
            renderHash = "display-check", renderHashShort = "check", colorCatalogId = "check",
            canvasAspect = "landscape", starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null)
        compose.setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = Color.Magenta)) {
                Column {
                    RefinementCandidateImage("display-check", SVG,
                        Modifier.size(200.dp).testTag("candidate"), bounds)
                    ArtworkPreview(item, modifier = Modifier.size(200.dp).testTag("rotated"),
                        presentationMode = true, presentationBackground = Color.White,
                        rotationDegrees = 90, rangeBounds = bounds, fitArtwork = true)
                }
            }
        }
        // A 2:1 red/blue SVG must fit, with white margin. Clockwise rotation
        // moves red to the top and turns the left-quarter frame into a top frame.
        compose.waitUntil(20_000) {
            val candidate = compose.onNodeWithTag("candidate").captureToImage()
            val rotated = compose.onNodeWithTag("rotated").captureToImage()
            isColor(candidate, .125f, .5f, Color.Red) && isColor(candidate, .875f, .5f, Color.Blue) &&
                isColor(rotated, .5f, .125f, Color.Red) && isColor(rotated, .5f, .875f, Color.Blue)
        }
        val candidate = compose.onNodeWithTag("candidate").captureToImage()
        val rotated = compose.onNodeWithTag("rotated").captureToImage()
        assertTrue("candidate margin", isColor(candidate, .5f, .125f, Color.White))
        assertTrue("rotated margin", isColor(rotated, .125f, .5f, Color.White))
        assertTrue("candidate range at the SVG's left quarter", hasMagenta(candidate, .25f, .5f))
        assertTrue("rotated range at the SVG's top quarter", hasMagenta(rotated, .5f, .25f))
        save("candidate", candidate)
        save("rotated", rotated)
        Log.i("InkuDisplayUiCheck", "candidate/rotated colors, aspect-fit margins and range frames passed")
    }

    private fun isColor(image: ImageBitmap, x: Float, y: Float, expected: Color): Boolean {
        val actual = image.toPixelMap()[(image.width * x).toInt(), (image.height * y).toInt()]
        return kotlin.math.abs(actual.red - expected.red) < .03f &&
            kotlin.math.abs(actual.green - expected.green) < .03f &&
            kotlin.math.abs(actual.blue - expected.blue) < .03f
    }

    private fun hasMagenta(image: ImageBitmap, x: Float, y: Float): Boolean {
        val pixels = image.toPixelMap()
        val cx = (image.width * x).toInt()
        val cy = (image.height * y).toInt()
        return (-3..3).any { dx -> (-3..3).any { dy ->
            val color = pixels[(cx + dx).coerceIn(0, image.width - 1), (cy + dy).coerceIn(0, image.height - 1)]
            color.red > .8f && color.green < .2f && color.blue > .8f
        } }
    }

    private fun save(name: String, image: ImageBitmap) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir, "skia-display-check")
        check(directory.mkdirs() || directory.isDirectory)
        File(directory, "$name.png").outputStream().use { image.asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    companion object {
        private const val SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
            <path d="M0 0h200v200H0z" fill="#ff0000"/><path d="M200 0h200v200H200z" fill="#0000ff"/>
            </svg>"""
    }
}
