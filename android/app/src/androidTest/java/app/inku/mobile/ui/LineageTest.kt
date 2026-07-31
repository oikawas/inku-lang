package app.inku.mobile.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LineageTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun lineagePanel_displaysNodeAndRootNodeInfo() {
        composeTestRule.setContent {
            LineagePanel(
                nodeId = "node-101",
                rootNodeId = "root-001",
                onSelectNode = {},
            )
        }

        composeTestRule.onNodeWithTag("lineage_panel").assertIsDisplayed()
        composeTestRule.onNodeWithText("作品系譜 (Lineage)").assertIsDisplayed()
        composeTestRule.onNodeWithText("★ 原点ノード: root-001", substring = true).assertIsDisplayed()
        composeTestRule.onNodeWithText("➔ 現在ノード: node-101", substring = true).assertIsDisplayed()
    }
}
