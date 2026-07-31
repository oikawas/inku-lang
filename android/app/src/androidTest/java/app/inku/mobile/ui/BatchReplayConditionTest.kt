package app.inku.mobile.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class BatchReplayConditionTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun conditionChips_invokesOnToggleExpandOnToggleClick() {
        var toggled = false

        composeTestRule.setContent {
            ConditionChipsContainer(
                expanded = true,
                onToggleExpand = { toggled = true },
            )
        }

        composeTestRule.onNodeWithTag("condition_chips_toggle").performClick()
        composeTestRule.waitForIdle()

        assert(toggled)
    }

    @Test
    fun conditionChips_hidesContentWhenExpandedIsFalse() {
        composeTestRule.setContent {
            ConditionChipsContainer(
                expanded = false,
                aspectRatio = "1:1",
            )
        }

        composeTestRule.onNodeWithTag("condition_chips_content").assertDoesNotExist()
        composeTestRule.onNodeWithText("比率: 1:1").assertDoesNotExist()
    }

    @Test
    fun conditionChips_showsContentWhenExpandedIsTrue() {
        composeTestRule.setContent {
            ConditionChipsContainer(
                expanded = true,
                aspectRatio = "1:1",
            )
        }

        composeTestRule.onNodeWithTag("condition_chips_content").assertIsDisplayed()
        composeTestRule.onNodeWithText("比率: 1:1").assertIsDisplayed()
    }
}
