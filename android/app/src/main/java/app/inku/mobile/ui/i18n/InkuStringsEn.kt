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

    override val derivationOrigin = "Root"
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

    override val exportTemplateBuiltinDescription: (Int) -> String = { px -> "PNG / Y axis ${px}px" }
}
