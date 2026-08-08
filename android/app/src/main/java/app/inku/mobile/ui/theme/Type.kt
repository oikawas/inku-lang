package app.inku.mobile.ui.theme

import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp

/**
 * Type sizes the app sets by hand, and a record of which Material scale steps it
 * actually uses.
 *
 * The app defines no `Typography` of its own: all 140 text styles come from
 * `MaterialTheme.typography`, which is M3's default scale. That is deliberate
 * and stays. What did not have a home were the eight places that override a
 * size or a line height on top of a scale step -- five distinct values, written
 * as literals. They live here now.
 *
 * As with [Dimens], the values are exactly the ones already in use. None was
 * rounded or brought onto a common ratio.
 *
 * ### Which scale steps the screens use
 *
 * Measured on the tree this file was added to, so it says what the app leans on
 * rather than what M3 offers:
 *
 * | step           | uses | what it carries                          |
 * |----------------|------|------------------------------------------|
 * | `labelSmall`   |   73 | the app's workhorse -- chips, units, hints |
 * | `bodySmall`    |   28 | prose in cards and dialogs                |
 * | `labelMedium`  |   11 | buttons and tabs                          |
 * | `titleSmall`   |    7 | card headings                             |
 * | `bodyMedium`   |    6 | longer prose                              |
 * | `titleMedium`  |    5 | dialog headings                           |
 * | `labelLarge`   |    4 | primary action labels                     |
 * | `headlineSmall`|    4 | screen headings                           |
 * | `titleLarge`   |    2 | the presentation caption                  |
 *
 * The distribution is the useful part: `labelSmall` carries more than half of
 * all text, so a change to it is a change to the whole app.
 */
object TypeScale {

    /** 11sp. The model picker's action buttons, which must fit on one line. */
    val labelTiny: TextUnit = 11.sp

    /** 16sp. The multi-line DDL input, sized up from the scale step for editing. */
    val editorBody: TextUnit = 16.sp

    /** 17sp. Line height for dense monospace-ish text: the DDL preview and inputs. */
    val denseLineHeight: TextUnit = 17.sp

    /** 21sp. Line height paired with [editorBody]. */
    val editorLineHeight: TextUnit = 21.sp

    /** 22sp. Line height for the demo panel's prose. */
    val proseLineHeight: TextUnit = 22.sp
}
