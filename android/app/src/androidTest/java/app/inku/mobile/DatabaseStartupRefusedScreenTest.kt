package app.inku.mobile

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DatabaseStartupRefusedScreenTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun localizedRefusalOffersOnlyRetryAndInvokesItOnce() {
        val title = composeTestRule.activity.getString(R.string.database_startup_refused_title)
        val message = composeTestRule.activity.getString(R.string.database_startup_refused_message)
        val retry = composeTestRule.activity.getString(R.string.database_startup_retry)
        var retryCount = 0

        composeTestRule.setContent {
            DatabaseStartupRefusedScreen(onRetry = { retryCount += 1 })
        }

        composeTestRule.onNodeWithText(title).assertIsDisplayed()
        composeTestRule.onNodeWithText(message).assertIsDisplayed()
        composeTestRule.onAllNodes(hasClickAction()).assertCountEquals(1)
        composeTestRule.onNodeWithText(retry)
            .assertIsDisplayed()
            .assertHasClickAction()
            .performClick()
        composeTestRule.runOnIdle {
            assertEquals("Retry invokes the startup callback exactly once", 1, retryCount)
        }
    }
}
