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
    val effectJa: String,
    val exampleJa: String,
    val effectEn: String,
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
private fun surfaceDabs(count: Int, radius: Double, opacity: Double, salt: Double, x0: Int = 51, x1: Int = 129): String = buildString {
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
        append("<circle cx=\"${number(cx, 1)}\" cy=\"${number(cy, 1)}\" r=\"${number(r, 2)}\" fill=\"$INK\" opacity=\"${number(a, 2)}\"/>")
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

/** Exact surface and handling copy and diagram recipes from the Web preview table. */
private val surfaceAndHandling: Map<String, PreviewEntry> by lazy {
    mapOf(
        "空" to PreviewEntry("面には何も置かず、輪郭を残す。", "空の四角を置く", "Leaves the face untouched, keeping the contour.", "Place an empty square", surfaceSvg("")),
        "塗り" to PreviewEntry("面を一様に塗りつぶす。", "塗りの四角を置く", "Fills the face evenly.", "Place a flat square", surfaceSvg("<rect $SURFACE_BOX fill=\"$INK\"/>")),
        "刷き" to PreviewEntry(
            "少し角度を変えて面を二度掃く。各掃きは道具の不透明度の半分で、薄いを添えると淡くなる。線や弧では幅広い帯を作る。", "刷きの四角を置く",
            "Sweeps the face twice at slightly different angles, each at half the tool opacity. Faint handling makes it paler. On a line or arc it makes a broad band.", "Place a sweep square",
            surfaceSvg("<defs><filter id=\"surface-sweep\"><feGaussianBlur stdDeviation=\"2.4\"/></filter></defs>" +
                "<g filter=\"url(#surface-sweep)\" stroke=\"$INK\" stroke-width=\"15\" stroke-linecap=\"round\">" +
                "<g opacity=\"0.5\"><path d=\"M44 26 H136\"/><path d=\"M44 39 H136\"/><path d=\"M44 52 H136\"/><path d=\"M44 65 H136\"/></g>" +
                "<g opacity=\"0.5\" transform=\"rotate(6 90 46)\"><path d=\"M44 22 H136\"/><path d=\"M44 35 H136\"/><path d=\"M44 48 H136\"/><path d=\"M44 61 H136\"/><path d=\"M44 74 H136\"/></g></g>"),
        ),
        "粒" to PreviewEntry("細かい粒を面に撒き、擦れた粗さを出す。", "粒の四角を置く", "Scatters fine grain across the face for a scuffed roughness.", "Place a grain square", surfaceSvg(surfaceDabs(78, 1.3, 0.5, 1.7))),
        "点描" to PreviewEntry("点を面に撒いて濃淡を作る。", "点描の円を置く", "Scatters dots across the face to build tone.", "Place a stipple square", surfaceSvg(surfaceDabs(34, 2.6, 0.62, 5.3))),
        "平行線" to PreviewEntry("平行な線で面を埋める。密度が上がるほど線の間隔が詰まる。", "平行線の四角を置く", "Fills the face with parallel lines; the denser it is, the tighter the spacing.", "Place a hatch square", surfaceSvg(surfaceHatch(listOf(45), 8, 2, 0.62))),
        "交差線" to PreviewEntry("平行線にもう一組を交差させて重ねる。", "交差線の四角を置く", "Lays a second set of lines across the first.", "Place a crosshatch square", surfaceSvg(surfaceHatch(listOf(45, 115), 9, 2, 0.5))),
        "アクアチント" to PreviewEntry("粒の濃さを段に分ける。既定は三段。", "アクアチントの四角を置く", "Divides the grain into discrete tone steps, three by default.", "Place an aquatint square", surfaceSvg(
            surfaceDabs(26, 1.5, 0.28, 2.3, 51, 76) + surfaceDabs(26, 1.5, 0.56, 6.1, 77, 103) + surfaceDabs(26, 1.5, 0.84, 9.7, 104, 129))),
        "濃い" to PreviewEntry("道具の本来の濃さより濃く置く。線・弧・質感の面・塗りに添えられる。図は左が程よい鉛筆の点描、右が濃い点描。", "鉛筆の濃い点描の四角を置く",
            "Lays ink or paint more densely relative to the tool, on lines, arcs, textured faces or flat fills. Left: temperate pencil stipple; right: dense stipple.", "Place a dense stipple pencil square", surfaceSvg(handlingRelative(0.66 * 1.35))),
        "程よい" to PreviewEntry("道具の本来の濃さで置く。さばきを省略した痕と同じ。図は左右とも程よい鉛筆の点描。", "鉛筆の程よい点描の四角を置く",
            "Lays ink or paint at the tool’s own opacity, as when handling is omitted. Both halves show temperate pencil stipple.", "Place a temperate stipple pencil square", surfaceSvg(handlingRelative(0.66))),
        "薄い" to PreviewEntry("道具の本来の濃さより淡く置く。線・弧・質感の面・塗りに添えられる。図は左が程よい鉛筆の点描、右が薄い点描。", "鉛筆の薄い点描の四角を置く",
            "Lays ink or paint more faintly relative to the tool, on lines, arcs, textured faces or flat fills. Left: temperate pencil stipple; right: faint stipple.", "Place a faint stipple pencil square", surfaceSvg(handlingRelative(0.66 * 0.55))),
    )
}

private val genericLine = shapeSvg("<path d=\"M22 56 C56 26 95 76 158 38\" fill=\"none\" stroke=\"$INK\" stroke-width=\"5\" stroke-linecap=\"round\"/>")
private val fallbackExamples = mapOf(
    "点" to ("点を置く" to "Place a point"),
    "紙" to ("紙。" to "Paper."), "和紙" to ("和紙。" to "Washi."),
    "薄墨地" to ("薄墨地。" to "Ink wash ground."), "木炭地" to ("木炭地。" to "Charcoal ground."),
    "カンバス" to ("カンバス。" to "Canvas."), "画用紙" to ("画用紙。" to "Drawing paper."),
    "メゾチント" to ("メゾチント。" to "Mezzotint."),
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
    val effect = if (uiLanguage.isEnglish) entry?.effectEn ?: "A vocabulary word that shapes how the description is read."
        else entry?.effectJa ?: "記述の解釈に影響する語彙です。"
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
