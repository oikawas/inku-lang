package app.inku.mobile.llm

/** Server gemini_thinking(): minimal only for known models; moving aliases default to low. */
internal fun geminiThinkingLevel(model: String): String? {
    val name = model.removePrefix("models/")
    return when {
        NO_LEVEL.containsMatchIn(name) -> null
        name in MINIMAL || name.startsWith("gemma-") -> "minimal"
        else -> "low"
    }
}

internal const val THINKING_ROOM_TOKENS = 8192
private val NO_LEVEL = Regex("^(?:gemini-2\\.5-flash-(?:lite|image)(?:-|$)|antigravity-)")
private val MINIMAL = setOf(
    "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest",
    "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview",
    "gemini-3.1-flash-image", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-lite-image",
    "gemini-robotics-er-2-preview", "nano-banana-pro-preview", "gemini-nano-banana-2.1",
)
