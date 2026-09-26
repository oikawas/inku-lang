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
    override val settingsDisplayTitle = "表示"
    override val settingsTextSizeTitle = "文字の大きさ"
    override val settingsTextSizeSubtitle = "端末の文字設定に加えて調整します"
    override val settingsTextSizeSample = "言葉から、ひとつの作品へ。"
    override val textSizeStandard = "標準"
    override val textSizeLarge = "大きめ"
    override val textSizeLargest = "最大"
    override val studioTitle = "制作"
    override val worksTitle = "作品"
    override val seriesTitle = "連作"
    override val studioSubtitle = "言葉を記して、描く"
    override val productionTools = "制作ツール"
    override val reviseWork = "この作品を推敲"
    override val interpretationToggle = "解釈を見る"
    override val interpretationHide = "解釈を閉じる"

    override val statusStage1 = "Stage 1: DDL生成中..."
    override val statusStage2 = "Stage 2: 画像生成中..."
    override val statusComposingFromDdl = "DDLからScoreを構成しています..."
    override val statusStopped = "停止しました。"
    // Both were English before the pack existed and were left so by the
    // translation pass; on the Japanese screen they stood out as the only
    // English failure lines.
    override val statusDrawFailed = "描画に失敗しました。"
    override val statusComposeFailed = "DDLからの構成に失敗しました。"
    override val statusSaved: (String) -> String = { hash -> "保存しました $hash" }
    override val statusSaveFailed = "保存に失敗しました。"
    override val restoreDrawingFailed = "前回の描画を復元できませんでした。"
    override val pipelineDeclineFailed = "DDLの変更案を断れませんでした。"
    override val drawingContextUnreadable = "描画の状態を読めませんでした。"
    override val drawingContextMissing = "描画の状態が見つかりません。"
    override val demoFailed = "デモの描画に失敗しました。"
    override val licenseUpdateFailed = "ライセンスへの同意を保存できませんでした。"
    override val pipelineProposal = "DDLの変更案を確認してください。"
    override val pipelineOriginalDdl = "現在のDDL"
    override val pipelineProposedDdl = "変更後のDDL"
    override val pipelineApprove = "変更を承認して描画"
    override val pipelineDecline = "変更しない"
    override val pipelineResume = "描画を続ける"
    override val pipelineDdlAuthority = "この変奏はDDLをもとに描画します。"
    override val pipelineNewDescription = "記述から新しい変奏を作る"
    override val pipelineNewDescriptionNotice = "次の描画は、新しい変奏として保存します。"
    override val pipelineCheckDdl = "DDLと描画の診断を確認してください。"
    override val pipelineDiagnostics = "描画の診断"
    override fun pipelinePluginDiagnostic(reason: String, name: String, suggestion: String?) = when (reason) {
        "plugin_disabled" -> "プラグイン $name は無効になっているため、この文は描かれていません。有効にすると描けます。"
        "plugin_name_mismatch" -> "プラグイン $name は登録名と一致しないため、この文は描かれていません。" +
            (suggestion?.let { "$it のことですか。" } ?: "")
        "plugin_version_mismatch" -> "プラグイン $name の中身が作品の保存時と違うため、この文は描かれていません。"
        else -> "プラグイン $name はこの環境に登録されていないため、この文は描かれていません。"
    }
    override val pipelineOmissions: (Int) -> String = { count -> "省略した配置・関係: $count 件。ほかの部分は描画を続けます。" }
    override val pipelinePartialExecution: (Int, Int) -> String = { requested, executed ->
        "${requested}個の要求のうち、実行可能な${executed}個を描画しました。"
    }

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
            else -> id
        }
    }
    override val comparisonKindDescription: (String) -> String = { id ->
        when (id) {
            "adjust" -> "描画要素を編集する"
            "model" -> "モデルを編集する"
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
            "sketch_grain_change" -> "写生の有無"
            "touch_change" -> "タッチ"
            "variation" -> "変奏"
            else -> derivationUnknown
        }
    }

    override val modelCatalogRefreshed = "ローカルモデルカタログを更新しました。"
    override val modelListFetchFailed = "モデルリスト取得に失敗しました。"
    override val modelListAccessDenied: (Int) -> String = { code -> "モデルリストを取得できませんでした（HTTP $code）。APIキーと利用権限を確認してください。" }
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

    // --- Screens (InkuApp.kt) ----------------------------------------------
    override val refineOneKindOnly = "1 回の推敲で変えられるのは 1 種類だけです。"
    override val providerAdd = "AIサービスを追加"
    override val apiKey = "APIキー"
    override val apiKeyDelete = "APIキーを削除"
    override val apiKeySet = "APIキーを設定"
    override val apiKeyUnset = "APIキー未設定"
    override val apiKeySetAlready = "APIキー設定済み"
    override val baseUrlChange = "Base URLを変更"
    override val drawFromDdl = "DDLから描画"
    override val ddlOverwriteTitle = "DDLの編集結果が失われます"
    override val ddlEdit = "DDL編集"
    override val mascotSubtitle = "Incu (立方体) または Yuragi (蟹)"
    override val mascotIncu = "Incu (立方体)"
    override val localModelNote = "LiteRT-LM でローカル実行する Gemma モデルです。"
    override val exportPngTooLarge = "PNG出力サイズが大きすぎます。キャンバス比率または出力サイズを下げてください。"
    // Web's wording (`settingsPngAlpha`); the earlier label read the opposite way.
    override val pngAlphaWhite = "白背景時アルファチャンネルを有効にする"
    override val stagesShared = "Stage 1 / Stage 2 共通"
    override val uiModeSubtitle = "UIの表示密度・構成"
    override val displaySafeMarginsSubtitle = "全画面表示でカメラ穴や画面端を避けます。用紙の比率は変わりません。"
    override val displaySafeMarginsToggle = "横方向の安全領域を使う"
    override val exportSubtitle = "Web版の出力設定"
    override val svgDisplayNote = "Web表示向けの標準SVG"
    override val mascotYuragi = "Yuragi (蟹)"
    override val exportHeightPx = "Y軸px"
    override val demoRunningButton = "■  デモ実行中"
    override val runningButton = "■  実行中"
    override val drawingButton = "■  描画中"
    override val drawFromDdlButton = "▶  DDLから描画"
    override val demoStartButton = "▶  デモ開始"
    override val batchDrawButton = "▶  バッチ描画"
    override val starredOnly = "★ 星のみ"
    override val fullScreen = "⛶ 全画面"
    override val exportButton = "⬆ 書き出し"
    override val settingsMisc = "その他"
    override val replaceSuffix = "を置換"
    override val application = "アプリケーション"
    override val export = "エクスポート"
    override val catalogDetail = "カタログ詳細"
    override val cancel = "キャンセル"
    override val canvas = "キャンバス"
    override val serviceId = "サービスID"
    override val serviceDeleteAction = "サービスを削除"
    override val serviceDeleteTitle = "サービス削除"
    override val serviceName = "サービス名"
    override val serviceNameChange = "サービス名を変更"
    override val uiModeSimple = "シンプルモード"
    override val uiModeSimpleLong = "シンプルモード表示"
    override val seedPhrase = "シードフレーズ"
    override val touchWords = "タッチを変える言葉"
    override val download = "ダウンロード"
    override val licenseBeforeDownload = "ダウンロード前に Gemma のライセンス同意が必要です。"
    override val templateEdit = "テンプレートを編集"
    override val templateAdd = "テンプレート追加"
    override val restoreDefaults = "デフォルト値に戻す"
    override val demo = "デモ"
    override val demoPromptWriting = "デモ指示文生成"
    override val demoView = "デモ表示"
    override val batch = "バッチ"
    override val batchHistory = "バッチ指示履歴"
    override val versionInfo = "バージョン情報"
    override val uiModeFull = "フルモード"
    override val uiModeFullLong = "フルモード表示"
    override val promptLabel = "プロンプト"
    override val searchPlaceholderLong = "プロンプト・ハッシュ・モデルで検索"
    override val noMatchingWorks = "条件に合う作品はありません。"
    // The trash takes web's words (`historyMoveToTrash`, `confirmTrashMessage`, ...).
    override val moveToTrash = "ごみ箱へ移動"
    override val trashedBadge = "ごみ箱"
    override val trashView: (Int) -> String = { count -> "ごみ箱 ($count)" }
    override val trashEmpty = "ごみ箱は空です。"
    override val restoreWork = "復元"
    override val deleteForGood = "完全削除"
    override val confirmTrash: (Int) -> String = { count -> "${count}件をごみ箱に移動しますか？" }
    override val confirmRestore: (Int) -> String = { count -> "${count}件を復元しますか？" }
    override val confirmDeleteForGood: (Int) -> String = { count -> "${count}件を完全に削除しますか？元に戻せません。" }
    override val confirmRun = "実行"
    override val workTrashed = "ごみ箱に移動しました。"
    override val workRestored = "ごみ箱から戻しました。"
    override val workDeleted = "完全に削除しました。"
    override val trashedWorkNote = "この作品はごみ箱にあります。"
    override val mascotTitle = "マスコット選択"
    override val model = "モデル"
    override val modelListFetch = "モデルリスト取得"
    override val modelListFetchSaveFirst = "取得する前に、モデル選択の変更を保存またはキャンセルしてください。"
    override val modelSearch = "モデル検索"
    override val modelSettings = "モデル設定"
    override val modelSelection = "モデル選択"
    override val publishedModels = "ユーザーに公開するモデル"
    override val licenseAndDownload = "ライセンス/ダウンロード"
    override val licenseAndDownloaded = "ライセンス/取得済み"
    override val licenseAccepted = "ライセンスは同意済みです。"
    override val licenseAccept = "ライセンス同意"
    override val licenseRequired = "ライセンス同意が必要"
    override val apiKeyLocalNote = "ローカルLLMの場合、APIキー無しで利用可能な場合があります。"
    override val localModels = "ローカルモデル"
    override val svgPortableNote = "互換性重視のポータブルSVG"
    override val provenanceHash = "作品の来歴ハッシュ"
    override val workLineage = "作品の系譜"
    override val save = "保存"
    override val lineageEmpty = "作品を選ぶと、ここに系譜が表示されます。"
    override val saving = "保存中…"
    override val saved = "保存済み"
    override val makeCandidates = "候補を作る"
    override val candidateTapToReplace = "候補タップで置換"
    override val stop = "停止"
    override val selectNone = "全解除"
    override val selectAll = "全選択"
    override val noPublishedModels = "公開モデルは未選択です。"
    override val noPublishedModelsLong = "公開モデルは未選択です。接続先設定でモデルを選択してください。"
    override val unifiedModelNote = "内部保存と履歴メタデータはserver互換のstage1_model / stage2_modelを維持し、Android UIでは同じモデルを両Stageへ適用します。"
    override val downloadAgain = "再取得"
    override val sketchFromLife = "写生"
    override val workActionSketchRedraw = "写生なし／ありで描き直す"
    override val workActionSketchWithMode: (String) -> String = { mode -> "写生${mode}で描き直す" }
    override val sketchTextEditLabel = "写生文"
    override val sketchTextRedraw = "直した写生文で描き直す"
    override val delete = "削除"
    override val downloading = "取得中"
    override val downloadable = "取得可能"
    override val downloaded = "取得済み"
    override val downloadState = "取得状況"
    override val cancelShort = "取消"
    override val accepted = "同意済み"
    override val name = "名前"
    override val fixedStage1Model = "固定する Stage 1 モデル"
    override val fixedStage2Model = "固定する Stage 2 モデル"
    override val change = "変更"
    override val failedLines = "失敗した行"
    override val demoSubtitle = "実行 / seed phrase / interval"
    override val demoRunAndSeed = "実行とシードフレーズ"
    override val sameStagePairBlocked = "対象作品と同じ Stage 1/2 の組み合わせだけが選べません。"
    override val history = "履歴"
    override val showThinking = "思考を表示"
    override val openProviderSettings = "接続先設定を開く"
    override val providerKind = "接続形式"
    override val paint = "描画する"
    override val drawingModel = "描画モデル"
    override val drawing = "描画中"
    override val renderExpression = "描画表現"
    override val refinementElements = "描画要素"
    override val drawingSettings = "描画設定"
    override val newApiKey = "新しいAPIキー"
    override val makeNewOrigin = "新しい起点にする"
    override val newWork = "新規作成"
    override val wildToggle = "暴れる（演奏上限の解除） / Wild (unleashed performance)"
    override val latest = "最新"
    override val tapSaijikiWord = "本文の歳時記語をタップ"
    override val tapWordToSelect = "本文の語をタップで選択"
    override val search = "検索"
    override val saijiki = "歳時記"
    override val svgGeneric = "汎用SVG"
    override val confirm = "決定"
    override val producedInstructions = "生成された指示文"
    override val producedInterpretation = "生成された解釈"
    override val working = "生成中…"
    override val lineage = "系譜"
    override val lineageLoading = "系譜を読み込み中…"
    override val materials = "素材"
    override val materialsClose = "素材を閉じる"
    override val edit = "編集"
    override val svgEditable = "編集用SVG"
    override val svgEditableNote = "編集用メタデータとIDを含む"
    override val renderExpressionSubtitle = "脱・規則化"
    override val colorCatalog = "色カタログ"
    override val colorCatalogAuto = "記述から自動選択"
    override val colorCatalogAutoDescription = "描画ごとに記述を読み、合う色カタログを選びます。"
    override val uiModeTitle = "表示モード"
    override val displaySafeMarginsTitle = "端末表示余白"
    override val svgDisplay = "表示用SVG"
    override val demoInterval = "表示間隔"
    override val autoRepair = "補正"
    override val interpretation = "解釈"
    override val awaitingInterpretation = "解釈を待機中..."
    override val miscSubtitle = "言語・文字の大きさ・表示"
    override val description = "記述"
    override val camera = "カメラ"
    override val cameraInputSourceTitle = "画像を選ぶ"
    override val cameraTakePhoto = "撮影する"
    override val cameraShutter = "シャッター"
    override val cameraChoosePhoto = "写真を選ぶ"
    override val cameraOverwriteTitle = "現在の記述を置き換えますか？"
    override val cameraOverwriteBody = "画像の解析が成功すると、現在の記述と解釈は置き換わります。画像入力を取り消した場合は残ります。"
    override val cameraOverwriteAction = "続ける"
    override val cameraCapturing = "撮影中"
    override val cameraPreparingImage = "画像を準備中"
    override val cameraLoadingLocalModel = "ローカルモデルを読み込み中"
    override val cameraAnalyzingLocally = "画像を解析中"
    override val cameraVisionModelTitle = "記述生成モデル"
    override val bundledPluginsTitle = "同梱プラグイン"
    override val ddlImportFile = "読込"
    override val ddlImportInvalid = "DDLファイルを読めませんでした"
    override fun ddlImportedPlugins(names: String) = "DDLと一緒にプラグイン定義を読み込みました（$names）。次の新しい作品だけに使います。"
    override val ddlExportWithPlugins = "DDL（プラグイン定義付き）"
    override val ddlExportWithPluginsNote = "DDLと、それが使うプラグインの定義。別の環境で読み込んでも同じ構図で描けます"
    override val bundledPluginsSubtitle = "Nature.leaves。無効にすると新しい作品で使われず、その語の文は理由を示して描かれません。保存済みの作品は自分の定義で描き直せます。"
    override fun bundledPluginsToggle(words: String) = "使う（$words）"
    override val cameraVisionModelSubtitle = "写真から記述を作るモデル。描画には描画設定のモデル・色カタログ・写生を使います。"
    override fun cameraVisionRemoteNotice(provider: String) = "このモデルを使うと、撮影・選択した写真を${provider}へ送信します。送るのは縮小して再圧縮した画像だけで、位置情報などの撮影情報は含みません。"
    override val cameraReadyToEdit = "編集できます"
    override val cameraCancelled = "画像処理を取り消しました"
    override val cameraModelNotReady = "記述生成に使う端末内モデルが準備されていません。設定のモデルから取得するか、記述生成モデルを変えてください。"
    override val cameraCaptureUnavailable = "カメラを起動できませんでした"
    override val cameraPhotoPickerUnavailable = "写真選択を起動できませんでした"
    override val cameraEmptyImage = "撮影画像を受け取れませんでした"
    override val cameraDecodeFailed = "画像を準備できませんでした"
    override val cameraAnalysisFailed = "画像の解析に失敗しました"
    override val cameraEmptyResult = "画像の解析結果が空でした"
    override val cameraDrawModelNotReady = "描画モデルの設定が完了していません"
    override val cameraDrawFailed = "現像に失敗しました。記述を保ったまま再試行できます。"
    override val retry = "再試行"
    override val menu = "メニュー"
    override val settings = "設定"
    override val saijikiTapNote = "語を押すと DDL 編集欄へ挿入します。"
    override val descriptionField = "説明"
    override val add = "追加"
    override val ddlOverwriteBody = "通常の描画を実行すると、現在の解釈（正規化DDL）は Stage 1 の結果で上書きされます。"
    override val selected = "選択中"
    override val close = "閉じる"
    override val renderTabArtwork = "描画"
    override val generationInfoTitle = "生成情報"
    override val generationInfoInputSection = "入力"
    override val generationInfoSketchSection = "写生"
    override val generationInfoInterpretationSection = "解釈"
    override val generationInfoPerformanceSection = "演奏"
    override val generationInfoIdentitySection = "同一性"
    override val generationInfoRunSection = "実行"
    override val generationInfoInputOrigin = "起点"
    override val generationInfoInputRoute = "経路"
    override val generationInfoVisionProvider = "Vision provider"
    override val generationInfoVisionModel = "Vision model"
    override val generationInfoVisionPromptVersion = "観察指示版"
    override val generationInfoVisionOutputMode = "Output mode"
    override val generationInfoNormalizedImageDimensions = "正規化撮影寸法"
    override val generationInfoInputOriginCamera = "カメラ"
    override val generationInfoInputOriginPhotoPicker = "既存の写真"
    override val generationInfoInputRouteLocalDescriptionToNim = "端末内記述 → NIM"
    override val generationInfoInputRouteLocalDdlToNimStage2 = "端末内DDL → NIM Stage 2"
    override val generationInfoInputRouteDescriptionToPipeline = "写真の記述 → 描画設定"
    override val generationInfoInputRouteDdlToPipelineStage2 = "写真のDDL → 描画設定のStage 2"
    override val generationInfoVisionOutputModeDescription = "記述"
    override val generationInfoVisionOutputModeDdl = "DDL"
    override val generationInfoSketchGrain = "区切り"
    override val generationInfoSketchState = "写生の記録"
    override val generationInfoStage1Model = "Stage 1 モデル"
    override val generationInfoStage2Model = "Stage 2 モデル"
    override val generationInfoLanguageRequested = "要求した言語"
    override val generationInfoLanguageResolved = "解決した言語"
    override val generationInfoInterpretationSeed = "解釈 seed"
    override val generationInfoVariationAmplitude = "変奏"
    override val generationInfoVariationSeed = "変奏 seed"
    override val generationInfoCompositionSeed = "配置 seed"
    override val generationInfoRenderSeed = "render seed"
    override val generationInfoSeedText = "種テキスト"
    override val generationInfoRenderWild = "暴れる"
    override val generationInfoColorCatalog = "色カタログ"
    override val generationInfoColorMap = "色の対応"
    override val generationInfoCanvasAspect = "キャンバス"
    override val generationInfoCanvasRatio = "キャンバスの比率"
    override val generationInfoRenderHash = "作品の来歴ハッシュ"
    override val generationInfoRenderEngineId = "Render engine ID"
    override val generationInfoRenderEngineVersion = "Render engine version"
    override val generationInfoCreated = "作成日"
    override val generationInfoElapsed = "処理時間"
    override val generationInfoOn = "あり"
    override val generationInfoOff = "なし"
    override val recommendedStageSuffix: (Int) -> String = { stage -> " (推奨: S$stage)" }
    override val parentSuffix: (String, String) -> String = { hash, catalog -> " 親: $hash / $catalog" }
    override val downloadOf: (String) -> String = { name -> "$name の取得" }
    override val choiceSameAsTarget: (String) -> String = { label -> "$label（対象と同じ）" }
    override val optionCount: (Int) -> String = { count -> "${count}案" }
    override val batchFailureLine: (Int, String, String) -> String = { line, input, message -> "${line}行目  $input  $message" }
    override val filteredOfTotal: (Int, Int) -> String = { filtered, total -> "$filtered/${total}件" }
    override val groupAlternatives: (String) -> String = { group -> "$group / 代替候補" }
    override val lineNumber: (Int) -> String = { line -> "${line}行目" }
    override val batchHistoryPill: (String, Int) -> String = { first, lines -> "$first（${lines}行）" }
    override val ofOneHundred: (Int) -> String = { count -> "${count}件/100件" }
    override val apiKeyDeleteBody: (String) -> String = { name -> "$name の保存済みAPIキーを削除します。" }
    override val serviceDeleteBody: (String) -> String = { name -> "$name をモデル接続先から削除します。" }
    override val seconds: (Int) -> String = { seconds -> "${seconds}秒" }
    override val llmSummary: (String) -> String = { model -> "LLM $model · 指示文生成/Stage1/2共通" }
    override val llmSummaryDot: (String) -> String = { model -> "LLM · $model · 指示文生成/Stage1/2共通" }
    override val qualityTier: (String) -> String = { tier -> "品質: $tier" }
    override val batchTally: (Int, Int, Int) -> String = { success, failures, total -> "成功 $success / 失敗 $failures / 全 $total" }
    override val exportOf: (String) -> String = { hash -> "書き出し  F$hash" }
    override val latestOf: (String) -> String = { hash -> "最新 F$hash" }
    override val remainingSeconds: (Int) -> String = { seconds -> "残り ${seconds}秒" }
    override val modelsToCompare: (Int) -> String = { max -> "比較するモデル (最大 $max)" }
    override val downloadStateOf: (String, String) -> String = { state, progress -> "状態: $state$progress" }
    override val generationOf: (Int) -> String = { n -> "第${n}世代" }
    override val batchElapsedTally: (String, Int, Int) -> String = { elapsed, success, failures -> "累計 $elapsed / 成功 $success / 失敗 $failures" }
    override val batchProgress: (Int, Int) -> String = { current, total -> "進捗 $current / $total" }

    override val exportTemplateBuiltinDescription: (Int) -> String = { px -> "PNG / Y軸 ${px}px" }

    override val stateExpanded = "展開中"
    override val stateCollapsed = "折りたたみ中"
    override val worksScrollbarDescription = "作品のスクロールバー"
    override val listSeparator = "・"
    override val statusRendered: (String) -> String = { hash -> "描画しました（F$hash）" }
    override val statusComposed: (String) -> String = { hash -> "解釈から描画しました（F$hash）" }
    override val promptEmpty = "記述が空です。"
    override val batchEmpty = "バッチが空です。"
    override val hashCopied = "ハッシュをコピーしました。"
    override val exportPreparing: (String) -> String = { format -> "$format を準備しています…" }
    override val exportDone: (String, String) -> String = { format, hash -> "$format を書き出しました（F$hash）" }
    override val exportFailed: (String) -> String = { format -> "$format の書き出しに失敗しました。" }
    override val copy = "コピー"
    override val providerLabel = "接続先"
}
