package app.inku.mobile.pipeline

/**
 * Which language the instructions to Stage 1, Stage 1.5 and Stage 2 are written in.
 *
 * The server's `language_support/registry.py` is the source of truth and this is
 * a condition-for-condition port of it, not a re-derivation: the same two
 * supported codes, the same third requestable word, the same order of the two
 * script probes, and the same normalisation of the fallback.
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

    /** `_JAPANESE_TEXT_RE` / `_LATIN_TEXT_RE` (`registry.py:21-22`), same ranges. */
    private val JAPANESE_TEXT = Regex("[\\u3040-\\u30ff\\u3400-\\u9fff]")
    private val LATIN_TEXT = Regex("[A-Za-z]")

    /**
     * `normalize_instruction_lang` (`registry.py:24-28`).
     *
     * The first line is `(value or default)`, and it is written here as the same
     * falsy test rather than as a default-valued read: Python falls back for
     * `None` and for `""` and for nothing else, so a value of only spaces is
     * truthy, survives to `.strip()`, and raises with the spaces still in the
     * message. `value ?: default` would send that one case down another road.
     */
    fun normalize(value: String?, default: String = DEFAULT_LANG): String {
        val raw = if (value.isNullOrEmpty()) default else value
        val lang = raw.trim().lowercase()
        require(lang in REQUESTED) { "unsupported instruction language: $value" }
        return lang
    }

    /**
     * `resolve_instruction_lang` (`registry.py:31-40`).
     *
     * The order of the two probes is the judgment, not a detail: a text holding
     * both scripts resolves to `ja` because the Japanese one is asked first. A
     * requested `ja` or `en` never reads the text at all, and the fallback is
     * normalised before it is returned so an unknown one cannot pass through.
     */
    fun resolve(text: String, requested: String?, fallback: String = DEFAULT_LANG): String {
        val lang = normalize(requested)
        if (lang != AUTO) return lang
        if (JAPANESE_TEXT.containsMatchIn(text)) return InstructionLanguage.Ja.code
        if (LATIN_TEXT.containsMatchIn(text)) return InstructionLanguage.En.code
        val normalizedFallback = normalize(fallback)
        return if (normalizedFallback == AUTO) InstructionLanguage.Ja.code else normalizedFallback
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
     * is not an error there. This client has no UI-language setting of its own,
     * so every call arrives with `uiLang = null` today and takes the same else
     * branch the server takes for `"fr"`; the parameter exists so that a client
     * that grows one later wires it in rather than inventing a rule.
     */
    fun resolveWithUiLang(text: String, requested: String?, uiLang: String? = null): String {
        val fallback = if (uiLang in SUPPORTED) uiLang!! else DEFAULT_LANG
        return resolve(text, requested, fallback = fallback)
    }
}
