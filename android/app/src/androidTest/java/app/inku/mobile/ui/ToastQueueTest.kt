package app.inku.mobile.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ToastQueueTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun toastQueue_displaysMultipleMessagesAndReplacesDuplicates() {
        val manager = ToastQueueManager()

        manager.pushToast("通知メッセージA")
        assert(manager.messages.value.size == 1)

        manager.pushToast("通知メッセージB")
        assert(manager.messages.value.size == 2)
        assert(manager.messages.value[0].text == "通知メッセージA")
        assert(manager.messages.value[1].text == "通知メッセージB")

        manager.pushToast("通知メッセージA")
        assert(manager.messages.value.size == 2)
        assert(manager.messages.value[0].text == "通知メッセージB")
        assert(manager.messages.value[1].text == "通知メッセージA")

        composeTestRule.setContent {
            ToastQueueWidget(messages = manager.messages.value)
        }

        composeTestRule.onNodeWithText("通知メッセージA").assertIsDisplayed()
        composeTestRule.onNodeWithText("通知メッセージB").assertIsDisplayed()
    }
}
