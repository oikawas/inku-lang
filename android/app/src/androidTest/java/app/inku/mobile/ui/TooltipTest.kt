package app.inku.mobile.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.longClick
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class TooltipTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun tooltip_displaysTextOnLongClick() {
        val tooltipBody = "作品の偽ハッシュ"
        val contentLabel = "F123456"

        composeTestRule.setContent {
            ProvenanceTooltipTarget(
                tooltipText = tooltipBody,
                contentLabel = contentLabel,
            )
        }

        composeTestRule.onNodeWithText(contentLabel).assertIsDisplayed()

        composeTestRule.onNodeWithText(contentLabel).performTouchInput {
            longClick()
        }

        composeTestRule.onNodeWithText(tooltipBody).assertIsDisplayed()
    }
}
