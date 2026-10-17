package app.inku.mobile.pipeline

/**
 * Which language the instructions to Stage 1, Stage 1.5 and Stage 2 are written in.
 *
 * The shared core owns normalization and script detection. This host retains
 * only the supported prompt choices and the UI fallback selection.
 */
enum class InstructionLanguage(val code: String) {
    Ja("ja"),
    En("en"),
    ;

    val isEnglish: Boolean get() = this == En
}

object InstructionLanguages {
    const val DEFAULT_LANG: String = "ja"
    const val AUTO: String = "auto"

    /** `SUPPORTED_INSTRUCTION_LANGS` (`registry.py:18`). */
    val SUPPORTED: Set<String> = InstructionLanguage.entries.map { it.code }.toSet()

    /** `REQUESTED_INSTRUCTION_LANGS` (`registry.py:19`): the supported ones plus `auto`. */
    val REQUESTED: Set<String> = SUPPORTED + AUTO

    /** Normalize through the shared core, including Python whitespace. */
    fun normalize(value: String?, default: String = DEFAULT_LANG): String =
        NativePipelineBridge.normalizeInstructionLanguage(value, default)
            ?: throw IllegalArgumentException("unsupported instruction language: $value")

    /** Resolve through the shared core, keeping the host exception contract. */
    fun resolve(text: String, requested: String?, fallback: String = DEFAULT_LANG): String =
        NativePipelineBridge.resolveInstructionLanguage(text, requested, fallback)
            ?: run {
                // Query the same core to identify which argument was rejected.
                normalize(requested)
                normalize(fallback)
                throw IllegalArgumentException("unsupported instruction language")
            }

    /**
     * `instruction_language` (`registry.py:43-47`).
     *
     * Refusing `auto` here is the order being enforced: resolve first, then
     * select the support. Every caller that reaches for a prompt goes through
     * this, so a path that forgot to resolve cannot quietly draw in Japanese.
     */
    fun support(lang: String): InstructionLanguage {
        val normalized = normalize(lang)
        require(normalized != AUTO) { "auto must be resolved before selecting language support" }
        return InstructionLanguage.entries.first { it.code == normalized }
    }

    /**
     * `_resolve_instruction_lang` (`api_core/common.py:68-70`), the wrapper the
     * routers actually call.
     *
     * The server lets the UI language stand in as the fallback when it is one of
     * the supported ones, and uses `"ja"` when it is not -- an unknown `ui_lang`
     * is not an error there. This client passes its interface language
     * (`UiLanguage.code`) from the describe, DDL, batch, demo and camera paths,
     * and a run that names none inherits its parent's (`AndroidWorkPipeline`);
     * with neither, it takes the same `"ja"` branch the server takes for `"fr"`.
     */
    fun resolveWithUiLang(text: String, requested: String?, uiLang: String? = null): String {
        val fallback = if (uiLang in SUPPORTED) uiLang!! else DEFAULT_LANG
        return resolve(text, requested, fallback = fallback)
    }

    /**
     * The language a DDL is read in, for the label beside it: the one its saved
     * work resolved while [ddl] is still that work's DDL, else the `auto` rule
     * over the text, as the core will read an edit. One Japanese character is
     * enough to make it Japanese, which is what the label is there to show.
     */
    fun ofDdl(ddl: String, savedDdl: String?, savedLang: String?, uiLang: String?): String =
        if (savedDdl != null && ddl == savedDdl && savedLang in SUPPORTED) savedLang!! else resolveWithUiLang(ddl, AUTO, uiLang)
}
