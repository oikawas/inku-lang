package app.inku.mobile.ui

import androidx.activity.ComponentActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class TenkeiTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun tenkeiSelect_updatesSelectedTenkeiStateOnChipClick() {
        var selectedTenkei by mutableStateOf("auto")

        composeTestRule.setContent {
            TenkeiSelect(
                selected = selectedTenkei,
                onSelect = { selectedTenkei = it },
            )
        }

        composeTestRule.onNodeWithTag("tenkei_chip_moon").performClick()
        composeTestRule.waitForIdle()

        assertEquals("moon", selectedTenkei)
    }
}
