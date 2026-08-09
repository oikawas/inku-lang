package app.inku.mobile.ui.i18n

/**
 * English -- a translation of [InkuStringsJa], not a second original.
 *
 * The words come from `web/src/lib/i18n/GLOSSARY.md`, which is the source of
 * truth for every English word inku says. In particular: `color catalog` (never
 * palette), `work` (never artwork), `sway` (never fluctuation or jitter),
 * `instructions` always plural, `reading` and `interpretation` are two different
 * things, `Saijiki` / `renga` / `hacho` keep their romaji, and none of
 * generate / prompt / create / image / AI-powered appears (§5).
 *
 * Style is `GLOSSARY.md` §4: sentence case, the single character `…` for an
 * ellipsis, no exclamation marks.
 */
object InkuStringsEn : InkuStrings {
    override val code = "en"
    override val label = "English"

    override val settingsLanguageTitle = "Language"
    override val settingsLanguageSubtitle = "Interface wording, Saijiki, and the language of a work"

    // 生成 is not "generating": Stage 1 interprets and Stage 2 performs, which is
    // what those stages are called throughout (GLOSSARY §2).
    override val statusStage1 = "Stage 1: interpreting…"
    override val statusStage2 = "Stage 2: performing…"
    override val statusComposingFromDdl = "Composing the score from the instructions…"
    override val statusStopped = "Stopped."
    override val statusDrawFailed = "Drawing failed."
    override val statusComposeFailed = "Composing failed."
    override val statusSaved: (String) -> String = { hash -> "Saved $hash" }
    override val statusSaveFailed = "Saving failed."

    override val batchTooManyItems: (Int, Int) -> String = { max, actual ->
        "A batch holds at most $max lines. There are $actual."
    }
    override val batchRunning: (Int, Int) -> String = { done, total -> "Batch running: $done/$total" }
    override val batchCompleted: (Int, Int, Int) -> String = { success, failures, total ->
        "Batch completed: $success drawn / $failures failed / $total in all"
    }

    override val demoRunning = "Demo running"
    override val demoGeneratingPrompt = "Writing a demo description"
    override val demoDrawing = "Demo drawing"
    override val demoDrawn: (String) -> String = { hash -> "Demo drawn $hash" }
    override val demoNextIn: (Int) -> String = { seconds -> "Next drawing in ${seconds}s" }
    override val demoStoppedAtLimit: (Int) -> String = { limit -> "Stopped at the demo limit of $limit." }
    override val demoPromptGenerationEmpty = "The demo description came back empty."

    override val refinementInProgress = "Making refinement candidates."
    override val refinementFailed = "The candidates could not be made."
    override val refinementTouchWordsRequired = "Write the words that change the performance."
    override val refinementNoOtherCatalog = "No other color catalog is available."
    override val refinementTouchFanoutRefusal =
        "The same words give the same performance (seed). Only one option can be made."
    override val refinementElementLabel: (String) -> String = { id ->
        // The nouns of the five "Another …" operations (GLOSSARY §3).
        when (id) {
            "touch" -> "Performance"
            "layout" -> "Composition"
            "reading" -> "Reading"
            "color" -> "Color catalog"
            "variation" -> "Variation"
            else -> id
        }
    }
    override val variationAmplitudeLabel: (String) -> String = { id ->
        // Fixed values (GLOSSARY §3, ruling 2026-07-25). `Moderate` is reserved
        // for the middle amplitude and is not used for speed.
        when (id) {
            "small" -> "Subtle"
            "medium" -> "Moderate"
            "large" -> "Sweeping"
            else -> id
        }
    }

    override val comparisonModelSelectPrompt = "Select one or more models to compare."
    override val comparisonModelFixedMissing = "Select the model to hold fixed."
    override val comparisonModelChoiceBlocked =
        "The target work's own Stage 1/2 pairing cannot be chosen."
    override val comparisonLanguageSelectPrompt = "Select one or more pairings to compare."
    override val comparisonLanguageComboBlocked =
        "The target work's own language pairing cannot be chosen."
    override val comparisonModeLabel: (String) -> String = { id ->
        when (id) {
            "common" -> "Stage 1/2 shared"
            "stage1_fixed" -> "Stage 1 fixed + Stage 2 compared"
            "stage2_fixed" -> "Stage 1 compared + Stage 2 fixed"
            else -> id
        }
    }
    override val comparisonKindLabel: (String) -> String = { id ->
        when (id) {
            "adjust" -> "Adjust"
            "model" -> "Model"
            "language" -> "Language"
            else -> id
        }
    }
    override val comparisonKindDescription: (String) -> String = { id ->
        when (id) {
            "adjust" -> "Edit the drawing elements"
            "model" -> "Edit the models"
            "language" -> "Edit the languages"
            else -> id
        }
    }

    // 起点 = origin (GLOSSARY :93). web answers "Root" here (`derivation.ts:50`),
    // which its own glossary contradicts; that file is outside what
    // `lint:i18n` reads, so the divergence has never been reported.
    override val derivationOrigin = "Origin"
    override val derivationUnknown = "Unknown"
    override val derivationLabel: (String) -> String = { kind ->
        // The twelve web already names come from `web/src/lib/derivation.ts:34-47`
        // verbatim. The five below it are kinds the server knows (`db.py:62`) and
        // web has no label for; `hacho` and `renga` keep their romaji, which
        // GLOSSARY.md §6 states is the correct English for both.
        when (kind) {
            "age_change" -> "Age"
            "canvas_aspect_change" -> "Canvas change"
            "catalog_change" -> "Color"
            "ddl_edit" -> "DDL edit"
            "description_edit" -> "Description edit"
            "external_seed_change" -> "External seed"
            "hacho_change" -> "Hacho"
            "language_comparison" -> "Language"
            "layout_change" -> "Layout"
            "model_comparison" -> "Model"
            "reinterpretation" -> "Reading"
            "render_engine_change" -> "Render engine"
            "renga_reply" -> "Renga reply"
            "replay" -> "Replay"
            "sketch_grain_change" -> "Sketch grain"
            "touch_change" -> "Touch"
            "variation" -> "Variation"
            else -> derivationUnknown
        }
    }

    override val modelCatalogRefreshed = "The local model catalog is up to date."
    override val modelListFetchFailed = "The model list could not be fetched."
    override val modelListFetching: (String) -> String = { id -> "Fetching the model list for $id…" }
    override val modelListFetched: (Int, String) -> String = { count, suffix ->
        "Fetched $count model${if (count == 1) "" else "s"}.$suffix"
    }
    override val modelListNvidiaSuffix = " Gemma-4-31b can be selected."
    override val modelSettingsSaved = "Model settings saved."
    override val modelSettingsSaveFailed = "The model settings could not be saved."
    override val apiKeyDeleted = "API key deleted."
    override val apiKeyDeleteFailed = "The API key could not be deleted."
    override val serviceDeleted = "Service deleted."
    override val serviceDeleteFailed = "The service could not be deleted."
    override val modelLicenseFirst: (String) -> String = { name ->
        "Accept the $name license first."
    }
    override val modelDownloadAlreadyRunning = "A model download is already running."
    override val modelDownloadStarting = "Starting the model download…"
    override val modelRedownloadStarting = "Downloading the model again…"
    override val modelDownloadFinished = "The model download finished."
    override val modelRedownloadFinished = "The model was downloaded again."
    override val modelDownloadCancelled = "The model download was cancelled."
    override val modelDownloadFailed = "The model download failed."
    override val modelLocalInfoMissing: (String, String) -> String = { stage, modelId ->
        "No local model information for $stage: $modelId"
    }
    override val modelNotDownloadedYet: (String, String, String) -> String = { stage, name, state ->
        "$name for $stage has not been downloaded. Finish the download in model settings. Currently: $state"
    }
    override val modelRecommendationReason: (String) -> String = { id ->
        when (id) {
            "stage1_default" -> "Recommended default for Stage 1. Balances composition and color well"
            "stage1_derived" -> "Recommended alternative for Stage 1. Expressive and stable"
            "stage2_default" -> "Recommended default for Stage 2. Expands the instructions precisely"
            else -> id
        }
    }

    override val errorServiceIdFormat = "A Service ID may hold letters, digits, _ and - only."
    override val errorServiceNotFound: (String) -> String = { id -> "Service not found: $id" }
    override val errorProviderModelsUnsupported: (String) -> String = { name ->
        "Fetching the model list from $name is not supported on Android."
    }
    override val errorProviderNotFoundForModel: (String) -> String = { modelId ->
        "No service is configured for this model: $modelId"
    }
    override val errorProviderBaseUrlMissing: (String) -> String = { name ->
        "$name has no Base URL set."
    }
    override val errorProviderApiKeyMissing: (String) -> String = { name ->
        "$name has no API key set."
    }
    override val errorModelInfoMissing: (String) -> String = { modelId ->
        "No model information: $modelId"
    }
    override val errorModelNotReady: (String) -> String = { name ->
        "$name has not been downloaded. Finish the download in Settings."
    }
    override val errorModelPathMissing: (String) -> String = { name ->
        "$name has no download location."
    }
    override val errorModelFileMissing: (String, String) -> String = { name, path ->
        "The model file for $name is missing: $path"
    }
    override val errorBaseUrlInvalid = "The Base URL is not a valid URL."
    override val errorBaseUrlInsecure =
        "That Base URL is not secure. Only HTTPS, or HTTP to localhost / 127.0.0.1 on the device, can be used."

    // --- Screens (InkuApp.kt) ----------------------------------------------
    override val refineOneKindOnly = "Only one kind of change can be made per round of refinement."
    override val providerAdd = "Add a service"
    override val apiKey = "API key"
    override val apiKeyDelete = "Delete the API key"
    override val apiKeySet = "Set the API key"
    override val apiKeyUnset = "No API key"
    override val apiKeySetAlready = "API key set"
    override val baseUrlChange = "Change the Base URL"
    override val drawFromDdl = "Draw from instructions"
    override val ddlOverwriteTitle = "The edited instructions will be lost"
    override val ddlReplaySaveAsNew = "Save a redraw from instructions as a new history entry"
    override val ddlEdit = "DDL edit"
    override val mascotSubtitle = "Incu (cube) or Yuragi (crab)"
    override val mascotIncu = "Incu (cube)"
    override val localModelNote = "Gemma models that run on the device through LiteRT-LM."
    override val promptOptimizationNote = "When on, only LiteRT-LM Stage 1 uses the compressed system instruction. Models that follow the server are unaffected."
    override val exportPngTooLarge = "The PNG is too large to write. Lower the canvas ratio or the output size."
    override val pngAlphaWhite = "White ground behind a transparent PNG"
    override val stagesShared = "Stage 1 / Stage 2 shared"
    override val languageComboNote = "Choose a pairing of Stage 1 and Stage 2 languages."
    override val uiModeSubtitle = "Interface density and layout"
    override val exportSubtitle = "The web export settings"
    override val historySelectionSubtitle = "The web history settings"
    override val svgDisplayNote = "Standard SVG for viewing on the web"
    override val mascotYuragi = "Yuragi (crab)"
    override val exportHeightPx = "Y axis px"
    override val demoRunningButton = "■  Demo running"
    override val runningButton = "■  Running"
    override val drawingButton = "■  Drawing"
    override val drawFromDdlButton = "▶  Draw from instructions"
    override val demoStartButton = "▶  Start the demo"
    override val batchDrawButton = "▶  Draw the batch"
    override val starredOnly = "★ Starred only"
    override val fullScreen = "⛶ Full screen"
    override val exportButton = "⬆ Export"
    override val settingsMisc = "Other"
    override val replaceSuffix = "to replace"
    override val application = "Application"
    override val export = "Export"
    override val catalogDetail = "Catalog detail"
    override val cancel = "Cancel"
    override val canvas = "Canvas"
    override val serviceId = "Service ID"
    override val serviceDeleteAction = "Delete the service"
    override val serviceDeleteTitle = "Delete service"
    override val serviceName = "Service name"
    override val serviceNameChange = "Change the service name"
    override val uiModeSimple = "Simple"
    override val uiModeSimpleLong = "Simple layout"
    override val seedPhrase = "Seed phrase"
    override val touchWords = "Words that change the performance"
    override val download = "Download"
    override val licenseBeforeDownload = "The Gemma license must be accepted before downloading."
    override val templateEdit = "Edit the template"
    override val templateAdd = "Add a template"
    override val restoreDefaults = "Restore the defaults"
    override val demo = "Demo"
    override val demoPromptWriting = "Writing a demo description"
    override val demoView = "Demo"
    override val batch = "Batch"
    override val batchHistory = "Batch description history"
    override val versionInfo = "Version"
    override val uiModeFull = "Full"
    override val uiModeFullLong = "Full layout"
    override val promptLabel = "Description"
    override val searchPlaceholderLong = "Search descriptions, hashes and models"
    override val promptOptimization = "Instruction optimization"
    override val mascotTitle = "Mascot"
    override val model = "Model"
    override val modelListFetch = "Fetch the model list"
    override val modelSearch = "Search models"
    override val modelSettings = "Model settings"
    override val modelSelection = "Model selection"
    override val publishedModels = "Models offered to the reader"
    override val licenseAndDownload = "License / download"
    override val licenseAndDownloaded = "License / downloaded"
    override val licenseAccepted = "The license has been accepted."
    override val licenseAccept = "Accept the license"
    override val licenseRequired = "The license must be accepted"
    override val apiKeyLocalNote = "A local model can often be used with no API key."
    override val localModels = "Local models"
    override val svgPortableNote = "Portable SVG that favours compatibility"
    override val provenanceHash = "The work's provenance hash"
    override val workLineage = "The work's lineage"
    override val save = "Save"
    override val lineageEmpty = "Once a work is saved, its lineage appears here."
    override val saving = "Saving…"
    override val saved = "Saved"
    override val makeCandidates = "Make options"
    override val candidateTapToReplace = "Tap an option to replace"
    override val stop = "Stop"
    override val selectNone = "Clear all"
    override val selectAll = "Select all"
    override val noPublishedModels = "No models have been offered."
    override val noPublishedModelsLong = "No models have been offered. Select models in the service settings."
    override val unifiedModelNote = "Storage and history metadata keep the server’s stage1_model / stage2_model, and this interface applies one model to both stages."
    override val downloadAgain = "Download again"
    override val sketchFromLife = "Sketch from life"
    override val delete = "Delete"
    override val downloading = "Downloading"
    override val downloadable = "Ready to download"
    override val downloaded = "Downloaded"
    override val downloadState = "Download state"
    override val cancelShort = "Cancel"
    override val accepted = "Accepted"
    override val name = "Name"
    override val fixedStage1Model = "Stage 1 model to hold fixed"
    override val fixedStage2Model = "Stage 2 model to hold fixed"
    override val change = "Change"
    override val failedLines = "Lines that failed"
    override val demoSubtitle = "Run / seed phrase / interval"
    override val demoRunAndSeed = "Run and seed phrase"
    override val sameStagePairBlocked = "Only the target work's own Stage 1/2 pairing cannot be chosen."
    override val history = "History"
    override val historyValue = "The history's value"
    override val historySelection = "History selection"
    override val showThinking = "Show the thinking"
    override val openProviderSettings = "Open the service settings"
    override val providerKind = "Connection type"
    override val paint = "Paint"
    override val drawingModel = "Drawing model"
    override val drawing = "Drawing"
    override val renderExpression = "Stroke"
    override val refinementElements = "Refinement elements"
    override val drawingSettings = "Drawing settings"
    override val newApiKey = "New API key"
    override val makeNewOrigin = "Make this a new origin"
    override val newWork = "New"
    override val wildToggle = "Wild (unleashed performance)"
    override val latest = "Latest"
    override val tapSaijikiWord = "Tap a Saijiki word in the text"
    override val tapWordToSelect = "Tap a word in the text to select it"
    override val search = "Search"
    override val saijiki = "Saijiki"
    override val svgGeneric = "Generic SVG"
    override val confirm = "OK"
    override val keepCurrentValue = "Keep the current value"
    override val producedInstructions = "Instructions (normalized DDL)"
    override val producedInterpretation = "Interpretation"
    override val working = "Working…"
    override val lineage = "Lineage"
    override val lineageLoading = "Loading the lineage…"
    override val materials = "Materials"
    override val materialsClose = "Close materials"
    override val edit = "Edit"
    override val svgEditable = "Editable SVG"
    override val svgEditableNote = "Carries the editing metadata and ids"
    override val renderExpressionSubtitle = "Letting the stroke off its rules"
    override val colorCatalog = "Color catalog"
    override val uiModeTitle = "Layout"
    override val svgDisplay = "Display SVG"
    override val demoInterval = "Interval"
    override val autoRepair = "Auto-repair"
    override val interpretation = "Interpretation"
    override val awaitingInterpretation = "Waiting for the interpretation…"
    override val language = "Language"
    override val miscSubtitle = "Language, theme and density"
    override val description = "Description"
    override val settings = "Settings"
    override val saijikiTapNote = "Tap a word to insert it into the instructions."
    // 説明 is a template's note, not the 記述 the author writes. Sharing
    // "Description" with it would put two concepts under one word.
    override val descriptionField = "Details"
    override val add = "Add"
    override val ddlOverwriteBody = "Painting normally replaces the current interpretation (the normalized DDL) with what Stage 1 produces."
    override val selected = "Selected"
    override val close = "Close"
    override val sameAsTargetSuffix = " (same as the target)"
    override val renderTabArtwork = "Work"
    override val recommendedStageSuffix: (Int) -> String = { stage -> " (recommended for S$stage)" }
    override val parentSuffix: (String, String) -> String = { hash, catalog -> " parent: $hash / $catalog" }
    override val downloadOf: (String) -> String = { name -> "Download $name" }
    override val choiceSameAsTarget: (String) -> String = { label -> "$label (same as the target)" }
    override val optionCount: (Int) -> String = { count -> "$count option${if (count == 1) "" else "s"}" }
    override val batchFailureLine: (Int, String, String) -> String = { line, input, message -> "line $line  $input  $message" }
    override val filteredOfTotal: (Int, Int) -> String = { filtered, total -> "$filtered of $total" }
    override val groupAlternatives: (String) -> String = { group -> "$group / alternatives" }
    override val lineNumber: (Int) -> String = { line -> "line $line" }
    override val ofOneHundred: (Int) -> String = { count -> "$count of 100" }
    override val apiKeyDeleteBody: (String) -> String = { name -> "Deletes the stored API key for $name." }
    override val serviceDeleteBody: (String) -> String = { name -> "Removes $name from the model services." }
    override val seconds: (Int) -> String = { seconds -> "${seconds}s" }
    override val llmSummary: (String) -> String = { model -> "LLM $model · demo, Stage 1 and Stage 2" }
    override val llmSummaryDot: (String) -> String = { model -> "LLM · $model · demo, Stage 1 and Stage 2" }
    override val qualityTier: (String) -> String = { tier -> "Quality: $tier" }
    override val batchTally: (Int, Int, Int) -> String = { success, failures, total -> "$success drawn / $failures failed / $total in all" }
    override val exportOf: (String) -> String = { hash -> "Export  F$hash" }
    override val latestOf: (String) -> String = { hash -> "Latest F$hash" }
    override val remainingSeconds: (Int) -> String = { seconds -> "$seconds s left" }
    override val modelsToCompare: (Int) -> String = { max -> "Models to compare (at most $max)" }
    override val downloadStateOf: (String, String) -> String = { state, progress -> "State: $state$progress" }
    override val generationOf: (Int) -> String = { n -> "Gen. $n" }
    override val batchElapsedTally: (String, Int, Int) -> String = { elapsed, success, failures -> "$elapsed in all / $success drawn / $failures failed" }
    override val batchProgress: (Int, Int) -> String = { current, total -> "Progress $current / $total" }

    override val exportTemplateBuiltinDescription: (Int) -> String = { px -> "PNG / Y axis ${px}px" }
}
