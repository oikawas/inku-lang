package app.inku.mobile.ui

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.util.UUID

data class ToastMessage(
    val id: String = UUID.randomUUID().toString(),
    val text: String,
    val timestamp: Long = System.currentTimeMillis(),
)

class ToastQueueManager {
    private val _messages = MutableStateFlow<List<ToastMessage>>(emptyList())
    val messages: StateFlow<List<ToastMessage>> = _messages.asStateFlow()

    fun pushToast(text: String) {
        val trimmed = text.trim()
        if (trimmed.isBlank()) return
        _messages.update { current ->
            val filtered = current.filterNot { it.text == trimmed }
            filtered + ToastMessage(text = trimmed)
        }
    }

    fun popToast() {
        _messages.update { current ->
            if (current.isNotEmpty()) current.drop(1) else emptyList()
        }
    }

    fun clear() {
        _messages.value = emptyList()
    }
}
