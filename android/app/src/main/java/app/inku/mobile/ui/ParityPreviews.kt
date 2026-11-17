package app.inku.mobile.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.produceState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.testTag
import app.inku.mobile.render.RustArtworkRasterizer
import app.inku.mobile.ui.i18n.UiLanguage
import app.inku.mobile.ui.i18n.stringsFor
import app.inku.mobile.pipeline.SaijikiGenerated
import app.inku.mobile.ui.theme.Dimens
import java.util.Locale
import kotlin.math.sin
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Built-in saijiki preview. Effect is UI prose; example is a DDL fragment. */
internal data class SaijikiPreview(
    val categoryKey: String,
    val word: String,
    val canonicalWord: String,
    val effect: String,
    val example: String,
    val svg: String,
)

internal data class PreviewEntry(
    val exampleJa: String,
    val exampleEn: String,
    val svg: String,
)

private const val INK = "#2b2b2b"
private const val SURFACE_BOX = "x=\"50\" y=\"20\" width=\"80\" height=\"52\" rx=\"2\""
private fun shapeSvg(shape: String): String =
    "<svg viewBox=\"0 0 180 92\"><rect width=\"180\" height=\"92\" rx=\"6\" fill=\"#fffdf8\"/>$shape</svg>"
private fun surfaceSvg(interior: String): String = shapeSvg(
    "<defs><clipPath id=\"surface-clip\"><rect $SURFACE_BOX/></clipPath></defs>" +
        "<g clip-path=\"url(#surface-clip)\">$interior</g>" +
        "<rect $SURFACE_BOX fill=\"none\" stroke=\"$INK\" stroke-width=\"4\"/>"
)

// The stable scatter is the same index hash as Web's saijiki-surface.ts.
private fun surfaceDabs(count: Int, radius: Double, opacity: Double, salt: Double, x0: Int = 51, x1: Int = 129, fill: String = INK): String = buildString {
    fun number(value: Double, places: Int) = String.format(Locale.ROOT, "%.${places}f", value)
    for (i in 0 until count) {
        fun hash(n: Double): Double {
            val value = sin((i + 1) * n + salt) * 43758.5453
            return ((value % 1.0) + 1.0) % 1.0
        }
        val cx = x0 + hash(12.9898) * (x1 - x0)
        val cy = 21 + hash(78.233) * 50
        val r = radius * (0.6 + hash(37.719) * 0.8)
        val a = opacity * (0.5 + hash(19.31) * 0.5)
        append("<circle cx=\"${number(cx, 1)}\" cy=\"${number(cy, 1)}\" r=\"${number(r, 2)}\" fill=\"$fill\" opacity=\"${number(a, 2)}\"/>")
    }
}

private fun surfaceHatch(angles: List<Int>, spacing: Int, width: Int, opacity: Double): String = buildString {
    for (angle in angles) {
        append("<g transform=\"rotate($angle 90 46)\" fill=\"none\" stroke=\"$INK\" stroke-width=\"$width\" opacity=\"$opacity\">")
        for (offset in -70..70 step spacing) append("<path d=\"M-12 ${46 + offset} H192\"/>")
        append("</g>")
    }
}

private fun handlingRelative(opacity: Double): String =
    surfaceDabs(21, 2.1, 0.66, 4.5, 51, 89) +
        surfaceDabs(21, 2.1, opacity, 4.5, 91, 129) +
        "<path d=\"M90 20 V72\" stroke=\"#d7d1c4\" stroke-width=\"1.5\"/>"

private fun textureRelative(right: String): String =
    surfaceDabs(21, 2.1, 0.66, 4.5, 51, 89) + right +
        "<path d=\"M90 20 V72\" stroke=\"#d7d1c4\" stroke-width=\"1.5\"/>"

/** Web's comparison drawings, using the same default stipple on the left. */
internal fun finenessPreviewSvg(count: Int, radius: Double): String =
    surfaceSvg(textureRelative(surfaceDabs(count, radius, 0.66, 4.5, 91, 129)))

internal fun underlayerPreviewSvg(): String = surfaceSvg(textureRelative(
    "<rect x=\"91\" y=\"20\" width=\"39\" height=\"52\" fill=\"$INK\"/>" +
        surfaceDabs(21, 2.1, 0.75, 4.5, 91, 129, "#8a8a8a"),
))

/** Exact surface and handling copy and diagram recipes from the Web preview table. */
private val surfaceAndHandling: Map<String, PreviewEntry> by lazy {
    mapOf(
        "空" to PreviewEntry("空の四角を置く", "Place an empty square", surfaceSvg("")),
        "塗り" to PreviewEntry("塗りの四角を置く", "Place a flat square", surfaceSvg("<rect $SURFACE_BOX fill=\"$INK\"/>")),
        "刷き" to PreviewEntry("刷きの四角を置く", "Place a sweep square", surfaceSvg("<defs><filter id=\"surface-sweep\"><feGaussianBlur stdDeviation=\"2.4\"/></filter></defs>" +
                "<g filter=\"url(#surface-sweep)\" stroke=\"$INK\" stroke-width=\"15\" stroke-linecap=\"round\">" +
                "<g opacity=\"0.6\"><path d=\"M44 26 H136\"/><path d=\"M44 39 H136\"/><path d=\"M44 52 H136\"/><path d=\"M44 65 H136\"/></g>" +
                "<g opacity=\"0.6\" transform=\"rotate(6 90 46)\"><path d=\"M44 22 H136\"/><path d=\"M44 35 H136\"/><path d=\"M44 48 H136\"/><path d=\"M44 61 H136\"/><path d=\"M44 74 H136\"/></g></g>")),
        "刷毛目" to PreviewEntry("刷毛目の四角を置く", "Place a brushmarks square", surfaceSvg("<g stroke=\"$INK\" stroke-linecap=\"round\">" +
                "<g><path stroke-width=\"13\" stroke-opacity=\"0.5\" d=\"M44 24 H136\"/><path stroke-width=\"11\" stroke-opacity=\"0.5\" d=\"M44 33 H136\"/><path stroke-width=\"14\" stroke-opacity=\"0.5\" d=\"M44 42 H136\"/><path stroke-width=\"12\" stroke-opacity=\"0.5\" d=\"M44 51 H136\"/><path stroke-width=\"13\" stroke-opacity=\"0.5\" d=\"M44 60 H136\"/><path stroke-width=\"11\" stroke-opacity=\"0.5\" d=\"M44 69 H136\"/></g>" +
                "<g transform=\"rotate(6 90 46)\"><path stroke-width=\"12\" stroke-opacity=\"0.5\" d=\"M44 20 H136\"/><path stroke-width=\"14\" stroke-opacity=\"0.5\" d=\"M44 29 H136\"/><path stroke-width=\"11\" stroke-opacity=\"0.5\" d=\"M44 38 H136\"/><path stroke-width=\"13\" stroke-opacity=\"0.5\" d=\"M44 47 H136\"/><path stroke-width=\"12\" stroke-opacity=\"0.5\" d=\"M44 56 H136\"/><path stroke-width=\"14\" stroke-opacity=\"0.5\" d=\"M44 65 H136\"/><path stroke-width=\"11\" stroke-opacity=\"0.5\" d=\"M44 74 H136\"/></g>" +
                "</g>")),
        "粒" to PreviewEntry("粒の四角を置く", "Place a grain square", surfaceSvg(surfaceDabs(78, 1.3, 0.5, 1.7))),
        "点描" to PreviewEntry("点描の円を置く", "Place a stipple square", surfaceSvg(surfaceDabs(34, 2.6, 0.62, 5.3))),
        "平行線" to PreviewEntry("平行線の四角を置く", "Place a hatch square", surfaceSvg(surfaceHatch(listOf(45), 8, 2, 0.62))),
        "交差線" to PreviewEntry("交差線の四角を置く", "Place a crosshatch square", surfaceSvg(surfaceHatch(listOf(45, 115), 9, 2, 0.5))),
        "メゾチント" to PreviewEntry("メゾチントの四角を置く", "Place a mezzotint square", surfaceSvg(
            surfaceDabs(26, 1.5, 0.28, 2.3, 51, 76) + surfaceDabs(26, 1.5, 0.56, 6.1, 77, 103) + surfaceDabs(26, 1.5, 0.84, 9.7, 104, 129))),
        "濃い" to PreviewEntry("鉛筆の濃い点描の四角を置く", "Place a dense stipple pencil square", surfaceSvg(handlingRelative(0.66 * 1.35))),
        "程よい" to PreviewEntry("鉛筆の程よい点描の四角を置く", "Place a moderate stipple pencil square", surfaceSvg(handlingRelative(0.66))),
        "薄い" to PreviewEntry("鉛筆の薄い点描の四角を置く", "Place a faint stipple pencil square", surfaceSvg(handlingRelative(0.66 * 0.55))),
    )
}

private val genericLine = shapeSvg("<path d=\"M22 56 C56 26 95 76 158 38\" fill=\"none\" stroke=\"$INK\" stroke-width=\"5\" stroke-linecap=\"round\"/>")
private val fallbackExamples = mapOf(
    "点" to ("点を置く" to "Place a point"),
    "紙" to ("紙。" to "Paper."), "和紙" to ("和紙。" to "Washi."),
    "薄墨地" to ("薄墨地。" to "Ink wash ground."), "木炭地" to ("木炭地。" to "Charcoal ground."),
    "カンバス" to ("カンバス。" to "Canvas."), "画用紙" to ("画用紙。" to "Drawing paper."),
    "メゾチント" to ("メゾチント。" to "Mezzotint."),
    "画面比" to ("画面比16:9。" to "Aspect ratio 16:9."),
    "ゆるやかに" to ("ゆるやかに揺れる線" to "A loosely swaying line"),
    "小刻みに" to ("小刻みに揺れる線" to "A tightly swaying line"),
)

/** Canonical Japanese word comes from SaijikiGenerated.wordsJa at the display word's index. */
internal fun saijikiPreview(
    categoryKey: String,
    canonicalWord: String,
    displayWord: String,
    uiLanguage: UiLanguage,
    ddlLanguage: String,
): SaijikiPreview {
    val wordIsJapanese = ddlLanguage != "en"
    val entry = surfaceAndHandling[canonicalWord] ?: webSaijikiPreviewEntries[canonicalWord]
    val fallback = fallbackExamples[canonicalWord]
    val category = SaijikiGenerated.CATEGORIES.firstOrNull { it.key == categoryKey }
    val index = category?.wordsJa?.indexOf(canonicalWord) ?: -1
    val descriptions = if (uiLanguage.isEnglish) category?.descriptionsEn else category?.descriptionsJa
    val effect = descriptions?.getOrNull(index)?.takeIf { it.isNotEmpty() }
        ?: stringsFor(uiLanguage).saijikiDescriptionFallback
    val example = if (wordIsJapanese) entry?.exampleJa ?: fallback?.first ?: "${displayWord}を使う"
        else entry?.exampleEn ?: fallback?.second ?: "Use \"$displayWord\""
    return SaijikiPreview(categoryKey, displayWord, canonicalWord, effect, example, entry?.svg ?: genericLine)
}

private val previewBitmapCache = SharedRenderCache<String, ImageBitmap>(
    12L * 1024 * 1024, { it.width.toLong() * it.height * 4L }, 2,
)

/** Preview card for both the saijiki panel and the DDL vocabulary bar. */
@Composable
internal fun SaijikiPreviewCard(preview: SaijikiPreview?, uiLanguage: UiLanguage, modifier: Modifier = Modifier) {
    Surface(modifier = modifier.fillMaxWidth().testTag("SaijikiPreview"), color = MaterialTheme.colorScheme.surfaceVariant) {
        if (preview == null) {
            Text(if (uiLanguage.isEnglish) "Tap a word to preview how it affects the drawing."
                else "語彙をタップすると、描画への効き方を表示します。", modifier = Modifier.padding(Dimens.spaceM),
                style = MaterialTheme.typography.labelSmall)
        } else {
            val bitmap = produceState<ImageBitmap?>(initialValue = null, key1 = preview.svg) {
                value = try {
                    withContext(Dispatchers.Default) {
                        previewBitmapCache.get(preview.svg) {
                            RustArtworkRasterizer().rasterize(preview.svg, targetWidth = 360, targetHeight = 184).asImageBitmap()
                        }
                    }
                } catch (_: Exception) {
                    null
                }
            }.value
            Column(modifier = Modifier.padding(Dimens.spaceM), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                if (bitmap != null) Image(bitmap, contentDescription = null, modifier = Modifier.fillMaxWidth().height(Dimens.vocabularyPreviewImageHeight))
                Text(preview.word, style = MaterialTheme.typography.titleSmall)
                Text(preview.effect, style = MaterialTheme.typography.bodySmall)
                Text((if (uiLanguage.isEnglish) "Example instructions: " else "指示書の例：") + preview.example,
                    style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
