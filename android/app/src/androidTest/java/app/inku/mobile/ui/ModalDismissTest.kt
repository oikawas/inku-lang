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
class ModalDismissTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun customModal_dismissesOnOutsideScrimClick() {
        var dismissed = false

        composeTestRule.setContent {
            CustomModalContainer(
                visible = true,
                onDismissRequest = { dismissed = true },
            )
        }

        composeTestRule.onNodeWithText("モーダルコンテンツ").assertIsDisplayed()

        composeTestRule.onNodeWithTag("modal_scrim").performClick()

        composeTestRule.waitForIdle()

        assert(dismissed)
    }
}
