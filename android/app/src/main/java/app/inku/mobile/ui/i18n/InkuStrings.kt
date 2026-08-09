package app.inku.mobile.ui.i18n

import androidx.compose.runtime.compositionLocalOf

/**
 * Every word the interface says, in one language.
 *
 * This is the Kotlin shape of the web's `types.ts` `LangPack`, and the two
 * implementations below it are `ja.ts` and `en.ts`. Japanese is the source
 * language: write it first, then translate, and never "improve" the Japanese
 * while translating (`GLOSSARY.md` §0).
 *
 * ## Why an interface and not `res/values-en/`
 *
 * A resource folder follows the DEVICE locale. The reader's choice is a setting
 * here (ruling 2026-08-09), and following the locale is a behaviour the web does
 * not have, so a client that grew it would be inventing one. An interface also
 * makes a missing key a compile error rather than a silent fallback to the
 * Japanese string.
 *
 * ## What does NOT belong here
 *
 * - **Prompts sent to a model.** Their words are the model's input, and a
 *   translated prompt makes this client judge the same description differently
 *   from the server (conventions §2-4).
 * - **The DDL vocabulary.** It comes from `SaijikiGenerated.kt`.
 * - **The default description and batch text.** The web keeps one Japanese
 *   `DEFAULT_INPUT` in both languages (`+page.svelte:324`): it is content the
 *   author may overwrite, not wording the interface speaks.
 *
 * Parameterised entries are functions, as they are in `en.ts`
 * (`errorModelGone: (stage) => ...`).
 */
interface InkuStrings {
    val code: String
    val label: String

    // --- Settings: language -------------------------------------------------
    val settingsLanguageTitle: String
    val settingsLanguageSubtitle: String

    // --- Drawing status -----------------------------------------------------
    val statusStage1: String
    val statusStage2: String
    val statusComposingFromDdl: String
    val statusStopped: String
    val statusDrawFailed: String
    val statusComposeFailed: String
    val statusSaved: (String) -> String
    val statusSaveFailed: String

    // --- Batch --------------------------------------------------------------
    val batchTooManyItems: (Int, Int) -> String
    val batchRunning: (Int, Int) -> String
    val batchCompleted: (Int, Int, Int) -> String

    // --- Demo ---------------------------------------------------------------
    val demoRunning: String
    val demoGeneratingPrompt: String
    val demoDrawing: String
    val demoDrawn: (String) -> String
    val demoNextIn: (Int) -> String
    val demoStoppedAtLimit: (Int) -> String
    val demoPromptGenerationEmpty: String

    // --- Refinement ---------------------------------------------------------
    val refinementInProgress: String
    val refinementFailed: String
    val refinementTouchWordsRequired: String
    val refinementNoOtherCatalog: String
    val refinementTouchFanoutRefusal: String
    val refinementElementLabel: (String) -> String
    val variationAmplitudeLabel: (String) -> String

    // --- Comparison ---------------------------------------------------------
    val comparisonModelSelectPrompt: String
    val comparisonModelFixedMissing: String
    val comparisonModelChoiceBlocked: String
    val comparisonLanguageSelectPrompt: String
    val comparisonLanguageComboBlocked: String
    val comparisonModeLabel: (String) -> String
    val comparisonKindLabel: (String) -> String
    val comparisonKindDescription: (String) -> String

    // --- Lineage ------------------------------------------------------------
    val derivationOrigin: String
    val derivationUnknown: String
    val derivationLabel: (String) -> String

    // --- Models and providers ----------------------------------------------
    val modelCatalogRefreshed: String
    val modelListFetchFailed: String
    val modelListFetching: (String) -> String
    val modelListFetched: (Int, String) -> String
    val modelListNvidiaSuffix: String
    val modelSettingsSaved: String
    val modelSettingsSaveFailed: String
    val apiKeyDeleted: String
    val apiKeyDeleteFailed: String
    val serviceDeleted: String
    val serviceDeleteFailed: String
    val modelLicenseFirst: (String) -> String
    val modelDownloadAlreadyRunning: String
    val modelDownloadStarting: String
    val modelRedownloadStarting: String
    val modelDownloadFinished: String
    val modelRedownloadFinished: String
    val modelDownloadCancelled: String
    val modelDownloadFailed: String
    val modelLocalInfoMissing: (String, String) -> String
    val modelNotDownloadedYet: (String, String, String) -> String
    val modelRecommendationReason: (String) -> String

    // --- Errors thrown below the screen -------------------------------------
    val errorServiceIdFormat: String
    val errorServiceNotFound: (String) -> String
    val errorProviderModelsUnsupported: (String) -> String
    val errorProviderNotFoundForModel: (String) -> String
    val errorProviderBaseUrlMissing: (String) -> String
    val errorProviderApiKeyMissing: (String) -> String
    val errorModelInfoMissing: (String) -> String
    val errorModelNotReady: (String) -> String
    val errorModelPathMissing: (String) -> String
    val errorModelFileMissing: (String, String) -> String
    val errorBaseUrlInvalid: String
    val errorBaseUrlInsecure: String

    // --- Export -------------------------------------------------------------
    val exportTemplateBuiltinDescription: (Int) -> String
}

/**
 * The pack the composition is being drawn with.
 *
 * `compositionLocalOf`, not the static one: the static variant does not
 * recompose its readers, so switching would only take effect on the next launch.
 */
val LocalStrings = compositionLocalOf<InkuStrings> { InkuStringsJa }

/** The pack for [language]. The only place the two implementations are chosen between. */
fun stringsFor(language: UiLanguage): InkuStrings =
    when (language) {
        UiLanguage.Ja -> InkuStringsJa
        UiLanguage.En -> InkuStringsEn
    }
