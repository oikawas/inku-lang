package app.inku.mobile.ui.i18n

import androidx.compose.runtime.compositionLocalOf

/**
 * Which language the interface speaks.
 *
 * This is the client's own `ui_lang`. It is deliberately a different thing from
 * [app.inku.mobile.pipeline.InstructionLanguage], which is the language a work
 * is drawn in: on the server the two are separate too, and `ui_lang` only ever
 * reaches the pipeline as the fallback that `_resolve_instruction_lang` consults
 * when the request asked for `auto`. Collapsing them here would make the client
 * decide something the server decides in two steps.
 */
enum class UiLanguage(val code: String, val label: String) {
    /**
     * [label] is each language's name in itself, never translated: that is
     * `ja.ts:5` / `en.ts:5`, which the web rail reads straight out of the pack
     * so that a reader who cannot read the current language can still find
     * their own (`AppRail.svelte:172-174`).
     */
    Ja("ja", "日本語"),
    En("en", "English"),
    ;

    val isEnglish: Boolean get() = this == En

    companion object {
        /**
         * `index.svelte.ts:10` -- the web starts in Japanese and does not read
         * the device locale. Following the locale would be a behaviour this
         * client invented, so the default is fixed instead (ruling 2026-08-09).
         */
        val DEFAULT: UiLanguage = Ja

        /**
         * An unrecognised code is not an error, it is Japanese.
         *
         * This is the same judgement as the server's, which lets an unknown
         * `ui_lang` fall through to `"ja"` rather than rejecting it
         * (`api_core/common.py:68-70`, ported at `InstructionLanguages.resolveWithUiLang`).
         */
        fun fromCode(code: String?): UiLanguage =
            entries.firstOrNull { it.code == code } ?: DEFAULT
    }
}

/**
 * The language the composition is being drawn in.
 *
 * `compositionLocalOf` rather than `staticCompositionLocalOf`: the static one
 * does not recompose readers when the value changes, so the setting would only
 * take effect on the next process start.
 */
val LocalUiLanguage = compositionLocalOf { UiLanguage.DEFAULT }
