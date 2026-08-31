package app.inku.mobile.ui

import android.app.Application
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.inku.mobile.render.NativeRenderBridge
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class VersionInfoPanelTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun versionInfoPanel_displaysRenderEngineVersion() {
        val application = ApplicationProvider.getApplicationContext<Application>()
        val viewModel = InkuViewModel(application)
        composeTestRule.setContent {
            VersionInfoPanel(viewModel = viewModel)
        }

        composeTestRule.onNodeWithText("render engine").assertIsDisplayed()
        // The product label must come from the packaged Rust library itself.
        composeTestRule.onNodeWithText(
            "${NativeRenderBridge.renderEngineId()} ${NativeRenderBridge.renderEngineVersion()}",
        ).assertIsDisplayed()
    }
}
