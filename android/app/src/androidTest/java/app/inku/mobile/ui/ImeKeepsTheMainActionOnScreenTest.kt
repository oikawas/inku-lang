package app.inku.mobile.ui

import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.test.hasScrollAction
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.inku.mobile.MainActivity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-11: the keyboard does not take the main action away with it.
 *
 * Measured on the device before stage B: focusing the description left about
 * 300px of empty space under the field, and neither 「描画する」 nor the bottom
 * bar was anywhere on screen. The reason is structural -- the whole compose
 * screen is one vertical scroll and `imePadding()` sits at its root, so the
 * keyboard lifts the bottom of that scroll and brings nothing with it. The fix
 * takes the action **out of the scroll**: while the description has focus it is
 * the window's bottom bar, in place of the four destinations.
 *
 * ### なぜ「表示されている」で測らないのか
 *
 * 最初は「IME を出して `assertIsDisplayed()`」で書いた。**計装では Compose が window
 * inset を 0 に固定する**（テストを決定的にするための仕組み）ので、`imePadding()` が
 * 何も持ち上げない。実測: `MainActivity` を起こし、IME の inset が
 * `ViewCompat.getRootWindowInsets` で 0 より大きくなるまで待っても、バーは 2424px の窓の
 * **y=2269** — キーボードの裏 — に居た。**摂動 P-7 を当てても外しても赤いままで、
 * これは製品ではなく計装の宿主を測っている検査だった。**
 *
 * だから**環境に依らない形**へ据え直した — **主操作がスクロールの外に居ること**、
 * および**下タブが場所を譲っていること**。これは修正が作った性質そのもので、
 * inset が 0 でも真になり、焦点の結線を切れば（P-7）偽になる。
 * **キーボードの上に出ていることの目視は実機のスクリーンショットが持つ**
 * （完了レポートの目視 3 枚。作者裁定 2026-08-08 でこの形を採った）。
 *
 * ⚠ 実機は排他資源。回す前に他の使い手を数えること (`adb shell ps -A | grep inku`)。
 * ⚠ **`connectedAndroidTest` は既定で実行後にアプリをアンインストールする**。作者の作品が
 * 入っている実機では `-Pandroid.injected.androidTest.leaveApksInstalledAfterRun=true`
 * を付けて回すこと（2026-08-08、この旗を付けずに回して DB を消した）。
 */
@RunWith(AndroidJUnit4::class)
class ImeKeepsTheMainActionOnScreenTest {

    // The shipped activity, not a generic host: it carries the manifest's
    // `adjustResize` and composes `InkuApp` the way the reader gets it.
    @get:Rule
    val composeTestRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun theDrawActionLeavesTheScrollWhenTheDescriptionTakesFocus() {
        composeTestRule.waitForIdle()

        // The compose screen clears focus whenever a work lands on the canvas
        // (`LaunchedEffect(state.isDrawing, state.selectedHistory?.id)`), and on a
        // cold start the database answers after the first frame. Clicking before
        // that gives the field focus and then takes it back -- a race the reader
        // never runs into and the test loses every time. 「系譜」 is on the bottom
        // bar always and beside the hash only when a work is on the canvas, so
        // two of them means the screen has settled. A device with no work at all
        // never gets there, and does not need to: nothing clears the focus.
        runCatching {
            composeTestRule.waitUntil(timeoutMillis = SETTLE_TIMEOUT_MS) {
                composeTestRule.onAllNodesWithText("系譜").fetchSemanticsNodes().size >= 2
            }
        }
        composeTestRule.waitForIdle()

        // The description starts below the fold, and a click on a node outside the
        // viewport lands nowhere -- measured, the field never took focus at all.
        composeTestRule.onNodeWithTag(DESCRIPTION_INPUT_TAG)
            .performScrollTo()
            .performSemanticsAction(SemanticsActions.RequestFocus)
        composeTestRule.waitForIdle()

        // The focus reaches the composition through the ViewModel's flow, and
        // `waitForIdle` does not pump the dispatcher that carries it: measured,
        // the bottom bar was still composed one idle later. Waiting for the bar to
        // give way is waiting for the state to arrive -- and it is bounded, so
        // cutting the focus wiring (P-7) times out here instead of passing.
        val gaveWay = runCatching {
            composeTestRule.waitUntil(timeoutMillis = FOCUS_TIMEOUT_MS) {
                composeTestRule.onAllNodesWithText("履歴").fetchSemanticsNodes().isEmpty()
            }
        }.isSuccess
        assertTrue(
            "the bottom navigation never gave way to the action: the description took " +
                "focus and nothing on screen changed, so the keyboard will cover 「" +
                "$DRAW_ACTION_LABEL」 the way it did before this stage",
            gaveWay,
        )

        val shown = composeTestRule
            .onAllNodesWithText(DRAW_ACTION_LABEL, substring = true)
            .fetchSemanticsNodes()
        assertTrue(
            "the description has focus and 「$DRAW_ACTION_LABEL」 is nowhere in the tree",
            shown.isNotEmpty(),
        )
        assertEquals(
            "there must be exactly one 「$DRAW_ACTION_LABEL」 while the description is " +
                "being written; the in-flow button gives way to the pinned one",
            1,
            shown.size,
        )

        val scroll = composeTestRule.onNode(hasScrollAction()).fetchSemanticsNode()
        assertFalse(
            "「$DRAW_ACTION_LABEL」 is still inside the scrolling content. The keyboard " +
                "lifts the bottom of that scroll and brings nothing with it, so the " +
                "action leaves the screen exactly when it is wanted",
            shown.single().isDescendantOf(scroll),
        )

    }

    private fun SemanticsNode.isDescendantOf(ancestor: SemanticsNode): Boolean {
        var walk = parent
        while (walk != null) {
            if (walk.id == ancestor.id) return true
            walk = walk.parent
        }
        return false
    }

    private companion object {
        const val SETTLE_TIMEOUT_MS = 10_000L
        const val FOCUS_TIMEOUT_MS = 5_000L
    }
}
