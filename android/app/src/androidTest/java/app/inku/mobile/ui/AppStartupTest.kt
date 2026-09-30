package app.inku.mobile.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.inku.mobile.ui.i18n.InkuStringsJa
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The app starts.
 *
 * Every other test here builds [InkuViewModel] from Kotlin, either directly or
 * through a factory it wrote. The running app does neither: `InkuApp` calls
 * `viewModel()`, whose default factory finds the constructor by reflection as
 * `<init>(Application)`. Those are different paths, and between 2026-08-06 and
 * this contract they disagreed -- the app threw `NoSuchMethodException` on
 * launch and died, while the whole instrumented suite stayed green.
 *
 * So this composes what `MainActivity` composes, and asserts the navigation the
 * reader would see. It is a smoke test on purpose: what it is for is the step
 * before any screen, which nothing else takes.
 */
@RunWith(AndroidJUnit4::class)
class AppStartupTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun inkuApp_composesAndShowsEveryTab() {
        composeTestRule.setContent { InkuApp() }
        composeTestRule.waitForIdle()

        // Studio can also be the screen title. Camera is a global capture
        // action; lineage opens from a work rather than the global bar.
        listOf(
            InkuStringsJa.studioTitle,
            InkuStringsJa.camera,
            InkuStringsJa.worksTitle,
            InkuStringsJa.settings,
        ).forEach { label ->
            val found = composeTestRule.onAllNodesWithText(label).fetchSemanticsNodes()
            assertTrue("the app came up without a $label tab", found.isNotEmpty())
        }
        composeTestRule.onNodeWithText(InkuStringsJa.worksTitle).assertIsDisplayed()
    }
}
