package app.inku.mobile.llm

/** Server gemini_thinking(): the lowest listed level, or no opt-in for 2.5 Flash-Lite. */
internal fun geminiThinkingLevel(model: String): String? {
    val name = model.removePrefix("models/")
    return when {
        FLASH_LITE.containsMatchIn(name) -> null
        FLASH_25.containsMatchIn(name) || PRO.containsMatchIn(name) || FLASH_38.containsMatchIn(name) -> "low"
        else -> "minimal"
    }
}

private val FLASH_LITE = Regex("^gemini-2\\.5-flash-lite(?:-|$)")
private val FLASH_25 = Regex("^gemini-2\\.5-flash(?:-|$)")
private val PRO = Regex("^gemini-[\\d.]+-pro(?:-|$)")
private val FLASH_38 = Regex("^gemini-3\\.8-flash(?:-|$)")
