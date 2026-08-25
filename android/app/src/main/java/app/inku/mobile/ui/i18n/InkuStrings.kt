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

    // --- Screens (InkuApp.kt) ----------------------------------------------
    val refineOneKindOnly: String
    val providerAdd: String
    val apiKey: String
    val apiKeyDelete: String
    val apiKeySet: String
    val apiKeyUnset: String
    val apiKeySetAlready: String
    val baseUrlChange: String
    val drawFromDdl: String
    val ddlOverwriteTitle: String
    val ddlReplaySaveAsNew: String
    val ddlEdit: String
    val mascotSubtitle: String
    val mascotIncu: String
    val localModelNote: String
    val promptOptimizationNote: String
    val exportPngTooLarge: String
    val pngAlphaWhite: String
    val stagesShared: String
    val languageComboNote: String
    val uiModeSubtitle: String
    val exportSubtitle: String
    val historySelectionSubtitle: String
    val svgDisplayNote: String
    val mascotYuragi: String
    val exportHeightPx: String
    val demoRunningButton: String
    val runningButton: String
    val drawingButton: String
    val drawFromDdlButton: String
    val demoStartButton: String
    val batchDrawButton: String
    val starredOnly: String
    val fullScreen: String
    val exportButton: String
    val settingsMisc: String
    val replaceSuffix: String
    val application: String
    val export: String
    val catalogDetail: String
    val cancel: String
    val canvas: String
    val serviceId: String
    val serviceDeleteAction: String
    val serviceDeleteTitle: String
    val serviceName: String
    val serviceNameChange: String
    val uiModeSimple: String
    val uiModeSimpleLong: String
    val seedPhrase: String
    val touchWords: String
    val download: String
    val licenseBeforeDownload: String
    val templateEdit: String
    val templateAdd: String
    val restoreDefaults: String
    val demo: String
    val demoPromptWriting: String
    val demoView: String
    val batch: String
    val batchHistory: String
    val versionInfo: String
    val uiModeFull: String
    val uiModeFullLong: String
    val promptLabel: String
    val searchPlaceholderLong: String
    val promptOptimization: String
    val mascotTitle: String
    val model: String
    val modelListFetch: String
    val modelSearch: String
    val modelSettings: String
    val modelSelection: String
    val publishedModels: String
    val licenseAndDownload: String
    val licenseAndDownloaded: String
    val licenseAccepted: String
    val licenseAccept: String
    val licenseRequired: String
    val apiKeyLocalNote: String
    val localModels: String
    val svgPortableNote: String
    val provenanceHash: String
    val workLineage: String
    val save: String
    val lineageEmpty: String
    val saving: String
    val saved: String
    val makeCandidates: String
    val candidateTapToReplace: String
    val stop: String
    val selectNone: String
    val selectAll: String
    val noPublishedModels: String
    val noPublishedModelsLong: String
    val unifiedModelNote: String
    val downloadAgain: String
    val sketchFromLife: String
    val delete: String
    val downloading: String
    val downloadable: String
    val downloaded: String
    val downloadState: String
    val cancelShort: String
    val accepted: String
    val name: String
    val fixedStage1Model: String
    val fixedStage2Model: String
    val change: String
    val failedLines: String
    val demoSubtitle: String
    val demoRunAndSeed: String
    val sameStagePairBlocked: String
    val history: String
    val historyValue: String
    val historySelection: String
    val showThinking: String
    val openProviderSettings: String
    val providerKind: String
    val paint: String
    val drawingModel: String
    val drawing: String
    val renderExpression: String
    val refinementElements: String
    val drawingSettings: String
    val newApiKey: String
    val makeNewOrigin: String
    val newWork: String
    val wildToggle: String
    val latest: String
    val tapSaijikiWord: String
    val tapWordToSelect: String
    val search: String
    val saijiki: String
    val svgGeneric: String
    val confirm: String
    val keepCurrentValue: String
    val producedInstructions: String
    val producedInterpretation: String
    val working: String
    val lineage: String
    val lineageLoading: String
    val materials: String
    val materialsClose: String
    val edit: String
    val svgEditable: String
    val svgEditableNote: String
    val renderExpressionSubtitle: String
    val colorCatalog: String
    val colorCatalogAuto: String
    val colorCatalogAutoDescription: String
    val uiModeTitle: String
    val svgDisplay: String
    val demoInterval: String
    val autoRepair: String
    val interpretation: String
    val awaitingInterpretation: String
    val language: String
    val miscSubtitle: String
    val description: String
    val settings: String
    val saijikiTapNote: String
    val descriptionField: String
    val add: String
    val ddlOverwriteBody: String
    val selected: String
    val close: String
    val sameAsTargetSuffix: String
    val renderTabArtwork: String
    val generationInfoTitle: String
    val generationInfoSketchSection: String
    val generationInfoInterpretationSection: String
    val generationInfoPerformanceSection: String
    val generationInfoIdentitySection: String
    val generationInfoRunSection: String
    val generationInfoSketchGrain: String
    val generationInfoSketchState: String
    val generationInfoStage1Model: String
    val generationInfoStage2Model: String
    val generationInfoLanguageRequested: String
    val generationInfoLanguageResolved: String
    val generationInfoInterpretationSeed: String
    val generationInfoVariationAmplitude: String
    val generationInfoVariationSeed: String
    val generationInfoCompositionSeed: String
    val generationInfoRenderSeed: String
    val generationInfoSeedText: String
    val generationInfoRenderWild: String
    val generationInfoColorCatalog: String
    val generationInfoColorMap: String
    val generationInfoCanvasAspect: String
    val generationInfoCanvasRatio: String
    val generationInfoRenderHash: String
    val generationInfoRenderEngineId: String
    val generationInfoRenderEngineVersion: String
    val generationInfoCreated: String
    val generationInfoElapsed: String
    val generationInfoOn: String
    val generationInfoOff: String
    val recommendedStageSuffix: (Int) -> String
    val parentSuffix: (String, String) -> String
    val downloadOf: (String) -> String
    val choiceSameAsTarget: (String) -> String
    val optionCount: (Int) -> String
    val batchFailureLine: (Int, String, String) -> String
    val filteredOfTotal: (Int, Int) -> String
    val groupAlternatives: (String) -> String
    val lineNumber: (Int) -> String
    val ofOneHundred: (Int) -> String
    val apiKeyDeleteBody: (String) -> String
    val serviceDeleteBody: (String) -> String
    val seconds: (Int) -> String
    val llmSummary: (String) -> String
    val llmSummaryDot: (String) -> String
    val qualityTier: (String) -> String
    val batchTally: (Int, Int, Int) -> String
    val exportOf: (String) -> String
    val latestOf: (String) -> String
    val remainingSeconds: (Int) -> String
    val modelsToCompare: (Int) -> String
    val downloadStateOf: (String, String) -> String
    val generationOf: (Int) -> String
    val batchElapsedTally: (String, Int, Int) -> String
    val batchProgress: (Int, Int) -> String

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
