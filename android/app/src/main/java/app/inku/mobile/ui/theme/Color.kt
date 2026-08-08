package app.inku.mobile.ui.theme

import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color

/**
 * Every colour the app paints with, named by what it is for.
 *
 * Before this file the 57 distinct colours lived as 89 literals inside
 * `InkuApp.kt`, so nothing could name a role: `Color(0xFF34302B)` appeared four
 * times as the hairline around a card and nowhere said so. The names here are
 * roles, not values -- `CardHairline`, not `Ink34302B` -- the same rule the web
 * side follows with `--action-bg` / `--accent`.
 *
 * The values are exactly the ones the screens already used. Nothing was merged,
 * rounded, or "tidied": two roles that happen to share an ARGB keep two names,
 * because they are two decisions that only currently agree.
 *
 * The app is dark-only. There is no `lightColorScheme` and adding one has not
 * been ruled on.
 */

// --- Scheme roles -----------------------------------------------------------
// The nine roles `MaterialTheme.colorScheme` exposes. 160 call sites read these
// indirectly, so a change here moves the whole app.

/** The page behind everything. */
val InkBackground = Color(0xFF11100F)

/** Cards, dialogs, and rows that sit one step above the page. */
val InkSurface = Color(0xFF181715)

/** Inset wells and pressed states, one step above `InkSurface`. */
val InkSurfaceVariant = Color(0xFF24211E)

/** The blue the app uses for selection and primary actions. */
val InkPrimary = Color(0xFF7FA6D8)

/** The sand tone the app uses for the drawing action and active hints. */
val InkSecondary = Color(0xFFEAD7A3)

/** Dividers and field outlines. */
val InkOutline = Color(0xFF514A43)

/** Body text on the page and on surfaces. */
val InkOnSurface = Color(0xFFEDE7DE)

/** Secondary text: captions, units, and disabled labels. */
val InkOnSurfaceMuted = Color(0xFFCFC6BA)

val InkuColors = darkColorScheme(
    background = InkBackground,
    surface = InkSurface,
    surfaceVariant = InkSurfaceVariant,
    primary = InkPrimary,
    secondary = InkSecondary,
    outline = InkOutline,
    onBackground = InkOnSurface,
    onSurface = InkOnSurface,
    onSurfaceVariant = InkOnSurfaceMuted,
)

// --- Text that sits on a filled action --------------------------------------

/** Text on a `primary`-filled button. */
val InkOnPrimary = Color(0xFF101010)

/** Text on a `secondary`-filled button. */
val InkOnSecondary = Color(0xFF19150F)

/** Text on a light vocabulary pill (chosen when the pill's fill is light). */
val PillInkOnLight = Color(0xFF12110F)

/** Text on a dark vocabulary pill (chosen when the pill's fill is dark). */
val PillInkOnDark = Color(0xFFF8F8F6)

// --- The canvas the server draws on -----------------------------------------

/** The area around the drawing, outside the sheet. */
val ServerCanvasAreaColor = Color(0xFF20201F)

/** The box that holds the sheet. */
val ServerCanvasBoxColor = Color(0xFF242321)

/** The sheet itself -- the paper the ink lands on. */
val ServerCanvasPaperColor = Color(0xFFF5F1E9)

// --- Presentation mode ------------------------------------------------------
// Picked by the artwork's own luminance, so both a dark and a light ground exist.

/** The ground behind a light artwork. */
val PresentationDarkBackground = Color(0xFF11100F)

/** The ground behind a dark artwork. */
val PresentationLightBackground = Color(0xFFF8F8F6)

/** The scrim behind the caption strip. */
val PresentationCaptionScrim = Color(0xB8000000)

/** Caption text over the scrim. */
val PresentationCaptionInk = Color(0xFFFFFDF8)

/** The bar that holds the presentation controls. */
val PresentationControlsSurface = Color(0xE01C1C1C)

/** The hairline around the control bar, and the idle outline of a button. */
val PresentationControlOutline = Color(0x2EFFFFFF)

/** The secondary label inside the control bar. */
val PresentationControlLabelMuted = Color(0xB8FFFDF8)

/** A selected control button's fill. */
val PresentationControlFillSelected = Color(0x29FFFFFF)

/** An idle control button's fill. */
val PresentationControlFillIdle = Color(0x10FFFFFF)

/** The outline of the favourite (★) button when it is on. */
val PresentationStarOutline = Color(0x9EFFD45C)

/** A disabled control button's label. */
val PresentationControlLabelDisabled = Color(0x59FFFDF8)

/** The favourite (★) glyph when it is on. */
val PresentationStarInk = Color(0xFFFFD45C)

/** A control button's label. */
val PresentationControlLabel = Color(0xFFFFFDF8)

// --- Saijiki vocabulary groups ----------------------------------------------
// Nine groups, nine hues, in the order the groups are declared. The pill under a
// recognised word takes the colour of the group the word belongs to.

val SaijikiGroupSand = Color(0xFFEAD7A3)
val SaijikiGroupSky = Color(0xFF9CC6E8)
val SaijikiGroupLeaf = Color(0xFFB8D58A)
val SaijikiGroupClay = Color(0xFFE08A7A)
val SaijikiGroupIris = Color(0xFFD2B7F0)
val SaijikiGroupMint = Color(0xFF8FD8C1)
val SaijikiGroupAmber = Color(0xFFF2B66D)
val SaijikiGroupSlate = Color(0xFFAEB7D8)
val SaijikiGroupBlossom = Color(0xFFE7A9C1)

// --- Status -----------------------------------------------------------------

/** A model download that failed or was cancelled. */
val StatusFailed = Color(0xFFE08A7A)

/** A model that is ready to download. */
val StatusReady = Color(0xFFB8D58A)

/** The wash behind the batch failure summary. */
val FailureSummaryWash = Color(0x22E08A7A)

// --- Surfaces and containers ------------------------------------------------

/** The well behind a dense text input. */
val InputWellSurface = Color(0xFF191816)

/** A settings card's container. */
val SettingsCardSurface = Color(0xFF1B1A18)

/** The card that frames the canvas. */
val CanvasPanelSurface = Color(0xFF1B1B1A)

/** A chip that names a published model, and the inset well inside the canvas panel. */
val ChipSurface = Color(0xFF20201E)

/** The square that stands in for a lineage node's artwork before it loads. */
val LineagePlaceholderSurface = Color(0xFF2A2622)

/** The ground under exported render text, which reads as paper. */
val RenderTextPaper = Color(0xFFF8F8F6)

/** Ink on that paper. */
val RenderTextInk = Color(0xFF22201D)

/** A history badge that is not selected. */
val HistoryBadgeSurface = Color(0xCC24211E)

/** A mini pill that is not selected. */
val MiniPillSurface = Color(0xDD24211E)

/** The drawing action button when it is not tonal. */
val DrawingActionSurface = Color(0xFF233144)

// --- Borders and hairlines --------------------------------------------------

/** The hairline around a card, a settings card, and the model asset rows. */
val CardHairline = Color(0xFF34302B)

/** The divider above the bottom navigation bar. */
val BottomNavDivider = Color(0xFF26221E)

/** The hairline around the canvas panel. */
val CanvasPanelHairline = Color(0xFF2C2925)

/** The hairline around the hero card. */
val HeroCardHairline = Color(0x1A000000)

/** The hairline around a colour swatch, dark enough to read on a pale swatch. */
val SwatchHairline = Color(0x66000000)

/** The ring that marks a selected history tile or nav button. */
val SelectionRing = Color(0x337FA6D8)

// --- Overlays and tints -----------------------------------------------------

/** The scrim over the hero card's artwork, behind the overlay buttons. */
val HeroOverlayScrim = Color(0xCC11100F)

/** The hairline around those overlay buttons. */
val HeroOverlayHairline = Color(0x55EDE7DE)

/** The label on those overlay buttons. */
val HeroOverlayInk = Color(0xFFEDE7DE)

/** The wash behind an active row in a selection dialog. */
val ActiveRowTint = Color(0x1AEAD7A3)

/** The wash behind an active settings row. */
val ActiveSettingsRowTint = Color(0x1A7FA6D8)

/** The unfilled part of a progress bar. */
val ProgressTrack = Color(0x3324211E)

// --- The empty-canvas sketch ------------------------------------------------
// Three weights of a pale ink, drawn at 72% alpha, so the placeholder reads as a
// pencil study rather than as content.

val CanvasSketchInkLight = Color(0xFFCFC6B6)
val CanvasSketchInkMid = Color(0xFFDED6C9)
val CanvasSketchInkStrong = Color(0xFFD8CFC0)
