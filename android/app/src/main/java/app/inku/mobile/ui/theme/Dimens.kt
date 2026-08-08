package app.inku.mobile.ui.theme

import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Every distance the app measures with, named and on one grid.
 *
 * Stage A named the distances without moving any of them: 429 `.dp` literals
 * over 53 values came out of `InkuApp.kt` exactly as they were, and 22 of the 53
 * sat off a 4dp grid. Pulling them on would have moved the drawing, and the
 * point of that stage was that nothing moved.
 *
 * This is the stage that moves them. Everything below is a multiple of 4dp, and
 * [hairline] is the single exception: a 1dp border is a line, not a distance,
 * and 4dp of it would be a bar.
 *
 * Three things collapsed at the same time, because a scale is only a scale if
 * the steps are far enough apart to mean something:
 *
 * - **Spacing is four steps.** 4 / 8 / 16 / 24. The 5, 6, 9, 10, 12, 14 and 18
 *   that used to sit between them were not decisions anyone made; they were what
 *   each screen happened to be written with.
 * - **Buttons are three heights.** 56 主 / 40 副 / 32 補助. 54dp and 34dp are
 *   gone: nothing could say why they differed from the 56 and 32 beside them.
 * - **Corners are two.** [radiusCard] for anything with a surface, and a pill
 *   (`RoundedCornerShape(100)`, or [radiusPill] where a Dp is wanted) for
 *   anything that is pressed. The 2.5, 3, 13 and 22 in between are gone.
 *
 * Nothing here is defined as another token from a different family. `radiusCard`
 * used to be `spaceXxl` and `radiusPill` was `space28`, which meant a corner
 * quietly followed a gap whenever the gap was retuned.
 *
 * Zero is deliberately absent. "No padding" is not a measurement, so the places
 * that ask for zero padding stay literal -- the one exception to writing
 * distances as tokens.
 */
object Dimens {

    // --- Spacing scale ------------------------------------------------------
    // Four steps, and nothing between them.

    /** 1dp. Border widths, and the bleed around a drawn keyword highlight. */
    val hairline: Dp = 1.dp

    /** 4dp. Inside a control, and between things that belong to one control. */
    val spaceXs: Dp = 4.dp

    /** 8dp. The app's default gap. */
    val spaceM: Dp = 8.dp

    /** 16dp. Between blocks, and the page's own side margin. */
    val spaceL: Dp = 16.dp

    /** 24dp. The widest gap the screens use. */
    val spaceXl: Dp = 24.dp

    // --- Corner radii -------------------------------------------------------
    // Two. Anything not listed here is a pill: `RoundedCornerShape(100)`.

    /** 16dp. Cards, dialogs, settings rows, and the text fields. */
    val radiusCard: Dp = 16.dp

    /** 28dp. Half of [buttonHeightLarge]: the full-width action button. */
    val radiusPill: Dp = 28.dp

    // --- Drawing ------------------------------------------------------------
    // Marks the app paints itself, which are not controls and take no corner
    // from the two above.

    /** 4dp. The rounding on a drawn keyword highlight. */
    val highlightCorner: Dp = 4.dp

    /** 4dp. The ring drawn around a selected history tile. */
    val selectionRingWidth: Dp = 4.dp

    // --- Control sizes ------------------------------------------------------

    /** 24dp. A history badge. */
    val badgeSize: Dp = 24.dp

    /** 28dp. A colour swatch. */
    val swatchSize: Dp = 28.dp

    /** 32dp. 補助 -- icon-sized controls and the two mascots. */
    val controlSizeSmall: Dp = 32.dp

    /** 40dp. 副 -- small buttons, the compose tabs, a settings row's icon tile. */
    val buttonHeightSmall: Dp = 40.dp

    /** 40dp. A square icon tile on a settings row. */
    val iconTileSize: Dp = 40.dp

    /** 44dp. The narrowest a presentation control may get. */
    val presentationControlMinWidth: Dp = 44.dp

    /** 56dp. 主 -- the one action a screen is for. */
    val buttonHeightLarge: Dp = 56.dp

    /** 64dp. A bottom-nav button. */
    val navButtonWidth: Dp = 64.dp

    /** 76dp. The 全選択 / 全解除 pair in the model picker. */
    val modelActionWidth: Dp = 76.dp

    /** 80dp. The bottom navigation bar. */
    val bottomNavHeight: Dp = 80.dp

    /** 104dp. A lineage node card, and the stop button beside it. */
    val chipWidth: Dp = 104.dp

    // --- The batch editor ---------------------------------------------------
    // Its rows are laid out by hand, so the line box and the number column are
    // sizes rather than spacings.

    /** 20dp. The height reserved per line. */
    val batchLineHeight: Dp = 20.dp

    /** 28dp. The line-number column. */
    val batchLineNumberWidth: Dp = 28.dp

    // --- Insets -------------------------------------------------------------

    /** 80dp. Keeps the hero overlay buttons clear of the caption below them. */
    val heroOverlayBottomInset: Dp = 80.dp

    /** 92dp. Keeps the presentation caption clear of the control bar. */
    val presentationCaptionBottomInset: Dp = 92.dp

    /** 96dp. Tail space so the compose screen scrolls clear of the nav bar. */
    val scrollTailSpace: Dp = 96.dp

    // --- Panels -------------------------------------------------------------

    /** 112dp. The floor under the DDL preview, and the draw panel's ceiling. */
    val panelMinHeight: Dp = 112.dp

    /** 116dp. The batch progress panel. */
    val batchProgressHeight: Dp = 116.dp

    /** 124dp. The wider of the two draw panel columns. */
    val panelWideMaxWidth: Dp = 124.dp

    /** 140dp. The demo panel. */
    val demoPanelHeight: Dp = 140.dp

    /** 220dp. A chip naming a published model. */
    val publishedChipMaxWidth: Dp = 220.dp

    /** 248dp. The vocabulary bar's ceiling. */
    val vocabularyBarMaxHeight: Dp = 248.dp

    /** 252dp. The preview inside the demo panel. */
    val demoPreviewMaxHeight: Dp = 252.dp

    /** 320dp. The numbered batch editor. */
    val batchEditorHeight: Dp = 320.dp

    /** 328dp. The artwork preview inside the hero card. */
    val heroPreviewMaxHeight: Dp = 328.dp

    /** 360dp. The raw SVG/JSON text view. */
    val renderTextViewHeight: Dp = 360.dp

    // --- Dialogs ------------------------------------------------------------

    /** 420dp. The add-provider card. */
    val addProviderCardHeight: Dp = 420.dp

    /** 432dp. The model selection dialog. */
    val modelDialogMaxHeight: Dp = 432.dp

    /** 460dp. The canvas aspect dialog. */
    val aspectDialogHeight: Dp = 460.dp

    /** 520dp. The provider model picker. */
    val providerModelDialogHeight: Dp = 520.dp

    /** 560dp. The colour catalog dialog. */
    val colorCatalogDialogHeight: Dp = 560.dp

    /** 680dp. The local model management dialog. */
    val localModelDialogMaxHeight: Dp = 680.dp
}
