package app.inku.mobile.ui

import androidx.activity.ComponentActivity
import androidx.compose.material3.Text
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class UiModeAndMascotTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun uiModeContainer_displaysSimpleModeContent() {
        composeTestRule.setContent {
            UiModeContainer(
                uiMode = "simple",
                fullContent = { Text("フルモード表示") },
                simpleContent = { Text("シンプルモード表示") },
            )
        }

        composeTestRule.onNodeWithText("シンプルモード表示").assertIsDisplayed()
    }

    @Test
    fun uiModeContainer_displaysFullModeContent() {
        composeTestRule.setContent {
            UiModeContainer(
                uiMode = "full",
                fullContent = { Text("フルモード表示") },
                simpleContent = { Text("シンプルモード表示") },
            )
        }

        composeTestRule.onNodeWithText("フルモード表示").assertIsDisplayed()
    }

    @Test
    fun mascotWidget_displaysIncuMascot() {
        composeTestRule.setContent {
            MascotWidget(mascotKind = "incu")
        }

        composeTestRule.onNodeWithTag("mascot_incu").assertIsDisplayed()
    }

    @Test
    fun mascotWidget_displaysYuragiMascot() {
        composeTestRule.setContent {
            MascotWidget(mascotKind = "yuragi")
        }

        composeTestRule.onNodeWithTag("mascot_yuragi").assertIsDisplayed()
    }
}
