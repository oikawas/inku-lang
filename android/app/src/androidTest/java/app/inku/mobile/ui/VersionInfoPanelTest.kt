package app.inku.mobile.ui

import android.app.Application
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.inku.mobile.data.model.CompatibilityConstants
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
        composeTestRule.setContent {
            val viewModel = InkuViewModel(application)
            VersionInfoPanel(viewModel = viewModel)
        }

        composeTestRule.onNodeWithText("render engine").assertIsDisplayed()
        // Verify that the panel is wired to the same compatibility values as the product.
        composeTestRule.onNodeWithText(
            "${CompatibilityConstants.renderEngineId} ${CompatibilityConstants.renderEngineVersion}",
        ).assertIsDisplayed()
    }
}
