package app.inku.mobile.ui.i18n

/**
 * 日本語 -- the source language.
 *
 * The wording here is the canonical one. When a string changes, it changes here
 * first and [InkuStringsEn] follows; the reverse never happens.
 */
object InkuStringsJa : InkuStrings {
    override val code = "ja"
    override val label = "日本語"

    override val settingsLanguageTitle = "言語"
    override val settingsLanguageSubtitle = "画面の文言・歳時記・作品の言葉"

    override val statusStage1 = "Stage 1: DDL生成中..."
    override val statusStage2 = "Stage 2: 画像生成中..."
    override val statusComposingFromDdl = "DDLからScoreを構成しています..."
    override val statusStopped = "停止しました。"
    // Both fallbacks were already written in English before the pack existed.
    // They are kept as they were: translating into the source language would be
    // changing the Japanese, which a translation pass does not do.
    override val statusDrawFailed = "Draw failed."
    override val statusComposeFailed = "Compose failed."
    override val statusSaved: (String) -> String = { hash -> "保存しました $hash" }
    override val statusSaveFailed = "保存に失敗しました。"

    override val batchTooManyItems: (Int, Int) -> String = { max, actual ->
        "バッチは最大 $max 件までです。現在: $actual 件"
    }
    override val batchRunning: (Int, Int) -> String = { done, total -> "Batch running: $done/$total" }
    override val batchCompleted: (Int, Int, Int) -> String = { success, failures, total ->
        "Batch completed: 成功 $success / 失敗 $failures / 全 $total"
    }

    override val demoRunning = "デモ実行中"
    override val demoGeneratingPrompt = "デモ指示文生成中"
    override val demoDrawing = "デモ描画中"
    override val demoDrawn: (String) -> String = { hash -> "デモ描画完了 $hash" }
    override val demoNextIn: (Int) -> String = { seconds -> "次の描画まで ${seconds}秒" }
    override val demoStoppedAtLimit: (Int) -> String = { limit -> "デモ上限 $limit 件で停止しました。" }
    override val demoPromptGenerationEmpty = "デモ指示文生成が空でした。"

    override val refinementInProgress = "推敲の候補を生成中です。"
    override val refinementFailed = "候補の生成に失敗しました。"
    override val refinementTouchWordsRequired = "タッチを変える言葉を入力してください。"
    override val refinementNoOtherCatalog = "別の色カタログがありません。"
    override val refinementTouchFanoutRefusal =
        "同じ言葉は同じタッチ(Seed)になります。1案だけ生成可能です。"
    override val refinementElementLabel: (String) -> String = { id ->
        when (id) {
            "touch" -> "タッチ"
            "layout" -> "配置"
            "reading" -> "読み取り"
            "color" -> "色カタログ"
            "variation" -> "変奏"
            else -> id
        }
    }
    override val variationAmplitudeLabel: (String) -> String = { id ->
        when (id) {
            "small" -> "控えめ"
            "medium" -> "中庸"
            "large" -> "大胆"
            else -> id
        }
    }

    override val comparisonModelSelectPrompt = "比較するモデルを1つ以上選択してください。"
    override val comparisonModelFixedMissing = "固定するモデルを選択してください。"
    override val comparisonModelChoiceBlocked = "対象作品と同じ Stage 1/2 の組み合わせは選べません。"
    override val comparisonLanguageSelectPrompt = "比較する組み合わせを1つ以上選択してください。"
    override val comparisonLanguageComboBlocked = "対象作品と同じ言語の組み合わせは選べません。"
    override val comparisonModeLabel: (String) -> String = { id ->
        when (id) {
            "common" -> "Stage 1/2 共通"
            "stage1_fixed" -> "Stage 1 固定 + Stage 2 比較"
            "stage2_fixed" -> "Stage 1 比較 + Stage 2 固定"
            else -> id
        }
    }
    override val comparisonKindLabel: (String) -> String = { id ->
        when (id) {
            "adjust" -> "調整"
            "model" -> "モデル"
            "language" -> "言語"
            else -> id
        }
    }
    override val comparisonKindDescription: (String) -> String = { id ->
        when (id) {
            "adjust" -> "描画要素を編集する"
            "model" -> "モデルを編集する"
            "language" -> "言語を編集する"
            else -> id
        }
    }

    override val derivationOrigin = "起点"
    override val derivationUnknown = "不明"
    override val derivationLabel: (String) -> String = { kind ->
        when (kind) {
            "age_change" -> "経年"
            "canvas_aspect_change" -> "キャンバス変更"
            "catalog_change" -> "色"
            "ddl_edit" -> "DDL編集"
            "description_edit" -> "記述編集"
            "external_seed_change" -> "外部の種"
            "hacho_change" -> "破調"
            "language_comparison" -> "言語"
            "layout_change" -> "構図"
            "model_comparison" -> "モデル"
            "reinterpretation" -> "解釈"
            "render_engine_change" -> "描画エンジン"
            "renga_reply" -> "連歌の付句"
            "replay" -> "再描画"
            "sketch_grain_change" -> "写生の区切り"
            "touch_change" -> "タッチ"
            "variation" -> "変奏"
            else -> derivationUnknown
        }
    }

    override val modelCatalogRefreshed = "ローカルモデルカタログを更新しました。"
    override val modelListFetchFailed = "モデルリスト取得に失敗しました。"
    override val modelListFetching: (String) -> String = { id -> "$id のモデルリストを取得しています..." }
    override val modelListFetched: (Int, String) -> String = { count, suffix ->
        "${count}件のモデルを取得しました。$suffix"
    }
    override val modelListNvidiaSuffix = " Gemma-4-31bを選択できます。"
    override val modelSettingsSaved = "モデル設定を保存しました。"
    override val modelSettingsSaveFailed = "モデル設定の保存に失敗しました。"
    override val apiKeyDeleted = "APIキーを削除しました。"
    override val apiKeyDeleteFailed = "APIキー削除に失敗しました。"
    override val serviceDeleted = "サービスを削除しました。"
    override val serviceDeleteFailed = "サービス削除に失敗しました。"
    override val modelLicenseFirst: (String) -> String = { name -> "先に${name}のライセンス同意を押してください。" }
    override val modelDownloadAlreadyRunning = "モデル取得はすでに実行中です。"
    override val modelDownloadStarting = "モデル取得を開始しています..."
    override val modelRedownloadStarting = "モデルを再取得しています..."
    override val modelDownloadFinished = "モデル取得が完了しました。"
    override val modelRedownloadFinished = "モデル再取得が完了しました。"
    override val modelDownloadCancelled = "モデル取得を中断しました。"
    override val modelDownloadFailed = "モデル取得に失敗しました。"
    override val modelLocalInfoMissing: (String, String) -> String = { stage, modelId ->
        "$stage のローカルモデル情報がありません: $modelId"
    }
    override val modelNotDownloadedYet: (String, String, String) -> String = { stage, name, state ->
        "$stage の $name は未取得です。モデル設定で取得を完了してください。現在: $state"
    }
    override val modelRecommendationReason: (String) -> String = { id ->
        when (id) {
            "stage1_default" -> "Stage 1 既定推奨。構図と彩色のバランスに優れる"
            "stage1_derived" -> "Stage 1 派生推奨。表現力と安定性が高い"
            "stage2_default" -> "Stage 2 既定推奨。DDL展開の精度が高い"
            else -> id
        }
    }

    override val errorServiceIdFormat = "Service ID は英数字・_・- で入力してください。"
    override val errorServiceNotFound: (String) -> String = { id -> "サービスが見つかりません: $id" }
    override val errorProviderModelsUnsupported: (String) -> String = { name ->
        "$name のモデル取得はAndroid版では未対応です。"
    }
    override val errorProviderNotFoundForModel: (String) -> String = { modelId ->
        "モデルに対応する接続先が見つかりません: $modelId"
    }
    override val errorProviderBaseUrlMissing: (String) -> String = { name -> "$name のBase URLが未設定です。" }
    override val errorProviderApiKeyMissing: (String) -> String = { name -> "$name のAPIキーが未設定です。" }
    override val errorModelInfoMissing: (String) -> String = { modelId -> "モデル情報がありません: $modelId" }
    override val errorModelNotReady: (String) -> String = { name ->
        "$name は未取得です。Settingsで取得を完了してください。"
    }
    override val errorModelPathMissing: (String) -> String = { name -> "$name の保存先がありません。" }
    override val errorModelFileMissing: (String, String) -> String = { name, path ->
        "$name のモデルファイルが見つかりません: $path"
    }
    override val errorBaseUrlInvalid = "Base URLが正しいURLではありません。"
    override val errorBaseUrlInsecure =
        "安全でないBase URLです。HTTPS、または端末内localhost/127.0.0.1のHTTPのみ使用できます。"

    override val exportTemplateBuiltinDescription: (Int) -> String = { px -> "PNG / Y軸 ${px}px" }
}
