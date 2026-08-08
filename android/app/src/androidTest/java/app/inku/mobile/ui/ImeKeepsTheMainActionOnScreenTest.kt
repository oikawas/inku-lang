package app.inku.mobile.ui

import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-11: the keyboard does not take the main action away with it.
 *
 * Measured on the device before stage B: focusing the description left about
 * 300px of empty space under the field, and neither 「描画する」 nor the bottom
 * bar was anywhere on screen. Written down, the reason is structural -- the
 * whole screen is one vertical scroll and `imePadding()` sits at its root, so
 * the keyboard lifts the bottom of the scroll and brings nothing with it.
 *
 * **This cannot be read off the source.** Whether a button is on screen with the
 * keyboard up is a question about insets, the scroll position and the window,
 * and the answer only exists on a running device. The other ten gates for this
 * contract are structural and live in the server's pytest; this one is here.
 *
 * ⚠ 実機は排他資源。回す前に他の使い手を数えること (`adb shell ps -A | grep inku`).
 */
@RunWith(AndroidJUnit4::class)
class ImeKeepsTheMainActionOnScreenTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun theDrawActionStaysOnScreenWhileTheKeyboardIsUp() {
        composeTestRule.activityRule.scenario.onActivity { activity ->
            // `MainActivity` declares this in the manifest. The generic test
            // activity does not, and the whole point of the measurement is that
            // the window resizes the way the shipped one does.
            activity.window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        }
        composeTestRule.setContent { InkuApp() }
        composeTestRule.waitForIdle()

        composeTestRule.onNodeWithTag(DESCRIPTION_INPUT_TAG).performClick()

        // Wait for the keyboard itself, not for a recomposition: the bar is
        // placed against the IME inset, and asserting before the inset arrives
        // would measure the layout of a screen without a keyboard on it.
        composeTestRule.waitUntil(timeoutMillis = IME_TIMEOUT_MS) { imeIsShown() }
        composeTestRule.waitForIdle()

        val shown = composeTestRule
            .onAllNodesWithText(DRAW_ACTION_LABEL, substring = true)
            .fetchSemanticsNodes()
        assertTrue(
            "the keyboard is up and 「$DRAW_ACTION_LABEL」 is nowhere on screen",
            shown.isNotEmpty(),
        )
        assertEquals(
            "there must be exactly one 「$DRAW_ACTION_LABEL」 while the keyboard is up; " +
                "the in-flow button gives way to the pinned one",
            1,
            shown.size,
        )

        // On screen, not merely in the tree: the bar has to sit inside the part
        // of the window the keyboard left behind.
        val bounds = shown.single().boundsInWindow
        val visibleBottom = composeTestRule.activity.window.decorView.height
        assertTrue(
            "「$DRAW_ACTION_LABEL」 is at ${bounds.top}..${bounds.bottom} in a window " +
                "$visibleBottom tall: the keyboard pushed it off",
            bounds.top >= 0f && bounds.bottom <= visibleBottom.toFloat(),
        )
    }

    /** `mInputShown` is what the device itself says about the keyboard. */
    private fun imeIsShown(): Boolean = "mInputShown=true" in shell("dumpsys input_method")

    private fun shell(command: String): String {
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        return automation.executeShellCommand(command).use { descriptor ->
            android.os.ParcelFileDescriptor.AutoCloseInputStream(descriptor).use { stream ->
                stream.readBytes().toString(Charsets.UTF_8)
            }
        }
    }

    private companion object {
        const val IME_TIMEOUT_MS = 10_000L
    }
}
