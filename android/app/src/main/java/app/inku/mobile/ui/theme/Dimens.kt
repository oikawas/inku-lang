package app.inku.mobile.ui.theme

import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Every distance the app measures with, named.
 *
 * Before this file there was no dimension layer at all: 429 `.dp` literals over
 * 53 distinct values, all inside `InkuApp.kt`. This is the counterpart of the
 * web side's `--btn-sm-*` tokens, where the `:root` block is canonical and a
 * hand-written px is a regression.
 *
 * **The values are exactly the ones the screens already used.** They are not on
 * a 4dp grid -- 22 of the 53 sit off it -- and pulling them onto one would move
 * the drawing. That work belongs to the next stage, where the screens are
 * rebuilt; doing it here would make it impossible to tell which stage moved a
 * pixel.
 *
 * Zero is deliberately absent. "No padding" is not a measurement, so the 20
 * places that ask for zero padding stay literal -- the one exception to writing
 * distances as tokens.
 */
object Dimens {

    // --- Spacing scale ------------------------------------------------------
    // The generic paddings and gaps, in the steps the screens actually use.
    // `spaceM` (8dp) is the most common distance in the app by a wide margin.

    /** 1dp. Border widths, and the vertical pad under a keyword highlight. */
    val hairline: Dp = 1.dp

    /** 2dp. The tightest gap; also the progress indicator's stroke. */
    val space2: Dp = 2.dp

    /** 4dp. */
    val spaceXs: Dp = 4.dp

    /** 5dp. The horizontal pad inside a vocabulary pill. */
    val space5: Dp = 5.dp

    /** 6dp. */
    val spaceS: Dp = 6.dp

    /** 8dp. The app's default gap. */
    val spaceM: Dp = 8.dp

    /** 9dp. */
    val space9: Dp = 9.dp

    /** 10dp. */
    val spaceL: Dp = 10.dp

    /** 12dp. */
    val spaceXl: Dp = 12.dp

    /** 14dp. Also the corner radius of every card and dialog surface. */
    val spaceXxl: Dp = 14.dp

    /** 18dp. */
    val space18: Dp = 18.dp

    /** 20dp. The line height reserved per row in the batch editor. */
    val space20: Dp = 20.dp

    /** 28dp. */
    val space28: Dp = 28.dp

    // --- Corner radii -------------------------------------------------------

    /** 2.5dp. The rounding on a drawn keyword highlight. */
    val radiusHighlight: Dp = 2.5.dp

    /** 3dp. Swatches and vocabulary pills. */
    val radiusXs: Dp = 3.dp

    /** 14dp. Cards, dialogs, and settings rows. */
    val radiusCard: Dp = spaceXxl

    /** 13dp. A history badge, which is a 26dp circle. */
    val radiusBadge: Dp = 13.dp

    /** 16dp. The nav button, the text field, and the hero tile's cut corner. */
    val radiusLarge: Dp = 16.dp

    /** 22dp. The local-model management dialog. */
    val radiusDialogLarge: Dp = 22.dp

    /** 28dp. A full-width action button, which is a 56dp pill. */
    val radiusPill: Dp = space28

    // --- Strokes ------------------------------------------------------------

    /** 1.5dp. The horizontal bleed of a drawn keyword highlight. */
    val highlightPadHorizontal: Dp = 1.5.dp

    /** 4dp. The ring drawn around a selected history tile. */
    val selectionRingWidth: Dp = spaceXs

    // --- Control sizes ------------------------------------------------------

    /** 26dp. A history badge. */
    val badgeSize: Dp = 26.dp

    /** 32dp. Icon-sized controls and the two mascots. */
    val controlSizeSmall: Dp = 32.dp

    /** 34dp. A presentation control button. */
    val controlSizeMedium: Dp = 34.dp

    /** 38dp. A square icon tile on a settings row. */
    val iconTileSize: Dp = 38.dp

    /** 40dp. A small button and the compose mode tabs. */
    val buttonHeightSmall: Dp = 40.dp

    /** 44dp. The narrowest a presentation control may get. */
    val presentationControlMinWidth: Dp = 44.dp

    /** 54dp. A wide presentation control, and the colour catalog row. */
    val buttonHeightMedium: Dp = 54.dp

    /** 56dp. A full-width action button. */
    val buttonHeightLarge: Dp = 56.dp

    /** 64dp. A bottom-nav button. */
    val navButtonWidth: Dp = 64.dp

    /** 72dp. The caption that overlays the hero card. */
    val heroCaptionMaxWidth: Dp = 72.dp

    /** 76dp. The label column in the SVG export help table. */
    val helpLabelWidth: Dp = 76.dp

    /** 82dp. The wider second column of that table. */
    val helpLabelWideWidth: Dp = 82.dp

    /** 80dp. The bottom navigation bar. */
    val bottomNavHeight: Dp = 80.dp

    /** 104dp. A lineage node card, and the stop button beside it. */
    val chipWidth: Dp = 104.dp

    // --- Insets -------------------------------------------------------------

    /** 78dp. Keeps the hero overlay buttons clear of the caption below them. */
    val heroOverlayBottomInset: Dp = 78.dp

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

    /** 250dp. The preview inside the demo panel. */
    val demoPreviewMaxHeight: Dp = 250.dp

    /** 260dp. The floor under the SVG export help popover. */
    val helpPopoverMinWidth: Dp = 260.dp

    /** 320dp. The numbered batch editor. */
    val batchEditorHeight: Dp = 320.dp

    /** 330dp. The artwork preview inside the hero card. */
    val heroPreviewMaxHeight: Dp = 330.dp

    /** 360dp. The raw SVG/JSON text view, and the help popover's ceiling. */
    val renderTextViewHeight: Dp = 360.dp

    // --- Dialogs ------------------------------------------------------------

    /** 420dp. The add-provider card. */
    val addProviderCardHeight: Dp = 420.dp

    /** 430dp. The model selection dialog. */
    val modelDialogMaxHeight: Dp = 430.dp

    /** 460dp. The canvas aspect dialog. */
    val aspectDialogHeight: Dp = 460.dp

    /** 520dp. The provider model picker. */
    val providerModelDialogHeight: Dp = 520.dp

    /** 560dp. The colour catalog dialog. */
    val colorCatalogDialogHeight: Dp = 560.dp

    /** 680dp. The local model management dialog. */
    val localModelDialogMaxHeight: Dp = 680.dp
}
