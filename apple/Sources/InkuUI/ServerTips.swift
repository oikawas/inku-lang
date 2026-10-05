import Foundation

/// Server copy is bundled at export time. Native-only behavior keeps its own copy.
public enum ServerTips {
    private static let reference: ProductReference? = {
        guard let url = Bundle.module.url(forResource: "ui-reference", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(ProductReference.self, from: data)
    }()

    /// These account and server controls have no equivalent in the single-user app.
    private static let excludedKeys: Set<String> = [
        "tooltipAppRailUser", "userPermissionGroupsHint", "userGroupMembershipHint",
        "settingsUsersHint", "userOwnRowProfileHint", "settingsDbWriteLockHelp",
        "settingsDbBackupTimeHint", "settingsLogRetentionNote", "clipboardInsecure",
        "clipboardUnsupported", "settingsServerHint", "settingsDetailHint",
        "settingsRenderConcurrencyServerHelp", "settingsRenderConcurrencyClientHelp",
        "settingsDescriptionMeterJapaneseHelp",
    ]

    /// The action is shared, while storage, service ownership or sharing is local.
    private static let adaptedKeys: [String: String] = [
        "tooltipSketchToggle": "写生層が書いた文章を表示します。開閉の状態はこのMacに保存されます。",
        "tooltipHistoryForShareOnly": "書き出しの印を付けた作品だけを表示します。ほかの絞り込みと併せると、すべてに該当する作品だけになります。",
        "shareTargetOn": "書き出しの印を外す",
        "shareTargetOff": "書き出しの印を付ける",
        "settingsModelsHint": "このアプリに登録するAIサービスのモデルと接続情報を管理します。",
        "settingsModelSecurityNote": "APIキーはKeychainに保存され、画面には再表示されません。",
        "settingsModelRpmHelp": "このアプリが同じ接続先へ送る1分当たりの要求数です。写生・解釈・カタログ選択・構図読み・再試行を含みます。0は上限なしです。",
        "settingsModelRpdHelp": "このアプリが同じ接続先へ送る1日当たりの要求数です。再試行も含み、Geminiは太平洋時間、その他はUTCの0時にリセットします。0は上限なしです。",
    ]

    // Exact native consumer aliases, rather than a fuzzy match between actions.
    private static let aliases: [String: String] = [
        "次の作品の描画モデルを選びます。": "tooltipInputModel",
        "次のバッチで使う描画モデルを選びます。": "tooltipInputModel",
        "解釈と構造化に使うモデルを選びます。": "tooltipInputModel",
        "次の作品の配色を選びます。": "tooltipInputCatalog",
        "次のバッチで使う配色を選びます。": "tooltipInputCatalog",
        "次の作品の指示書に使う言語を選びます。": "tooltipDdlLang",
        "次の作品の筆致を規則から外します。": "tooltipInputWild",
        "用紙の形と意図を見て、次の作品の用紙を選びます。": "tooltipInputCanvas",
        "歳時記の語と説明を参照します。": "tooltipSaijikiToggle",
        "次の作品で写生を使うかを選びます。": "tooltipInputSketch",
        "入力をクリアして、新しい作品を始めます。": "tooltipInputClear",
        "入力と次の生成条件から作品を描きます。": "tooltipSubmit",
        "生成": "tooltipSubmit",
        "独立した編集画面でDDLを変更します。": "tooltipDdlEdit",
        "ごみ箱の作品を表示・復元できます。": "tooltipHistoryTrashView",
        "同じ系譜の作品をまとめて表示します。": "tooltipHistoryLineageGrouped",
        "お気に入りの作品に絞り込みます。": "tooltipHistoryStarredOnly",
        "推敲の印を付けた作品に絞り込みます。": "tooltipHistoryForRevisionOnly",
        "書き出し用の印を付けた作品に絞り込みます。": "tooltipHistoryForShareOnly",
        "最新の履歴": "tooltipCanvasNavLatest",
        "最古の履歴": "tooltipCanvasNavOldest",
        "新しい作品": "tooltipCanvasNavNewer",
        "古い作品": "tooltipCanvasNavOlder",
        "先頭ページ": "tooltipHistoryLatestPage",
        "前のページ": "tooltipHistoryNewerPage",
        "次のページ": "tooltipHistoryOlderPage",
        "最終ページ": "tooltipHistoryOldestPage",
        "描画ハッシュ全体をコピー": "historyHashCopyTitle",
        "SVG容量": "provenanceHintSvgSize",
        "縮小": "tooltipCanvasZoomOut",
        "拡大": "tooltipCanvasZoomIn",
        "拡大率と位置をリセット": "tooltipCanvasZoomReset",
        "モデル設定": "settingsModelsHint",
        "未保存の変更を保存または取り消してからモデルリストを取得してください。": "settingsModelFetchDisabledWhileDirty",
        "画像を扱える登録モデルから選択します。": "modelSelectionVisionHint",
        "未保存の候補をすべて捨てて閉じます。保存済みの候補は履歴に残ります。": "tooltipRefineDiscardAndClose",
    ]

    private static let exactKeys: [String: String] = {
        let copy = reference?.copy["ja"]?.texts ?? [:]
        let groups = Dictionary(grouping: copy.filter { isHelpKey($0.key) }, by: { $0.value })
        return groups.reduce(into: [:]) { result, entry in
            guard entry.value.count == 1 else { return }
            result[entry.key] = entry.value[0].key
        }
    }()

    private static func isHelpKey(_ key: String) -> Bool {
        key.hasPrefix("tooltip") || key.contains("Tooltip") || key.contains("Hint")
            || key.hasSuffix("Help") || key.hasSuffix("Title") || key.hasSuffix("Tip")
    }

    public static func sourceKey(for fallback: String) -> String? {
        if aliases[fallback] != nil { return aliases[fallback] }
        if reference?.copy["ja"]?.texts[fallback] != nil { return fallback }
        return exactKeys[fallback]
    }

    public static func text(_ key: String, language: String) -> String? {
        guard !excludedKeys.contains(key) else { return nil }
        if let adapted = adaptedKeys[key] { return InkuLocalization.string(adapted, language: language) }
        return reference?.localized(language: language)?.texts[key]
    }

    private static let englishCopy: [String: String] = {
        guard let japanese = reference?.copy["ja"]?.texts, let english = reference?.copy["en"]?.texts else { return [:] }
        let groups = Dictionary(grouping: japanese.filter {
            !excludedKeys.contains($0.key) && adaptedKeys[$0.key] == nil && !$0.value.isEmpty
                && ($0.value.count >= 8 || sharedLabels.contains($0.value))
        }, by: { $0.value })
        return groups.reduce(into: [:]) { result, entry in
            let values = Set(entry.value.compactMap { english[$0.key] })
            guard values.count == 1 else { return }
            result[entry.key] = values.first
        }
    }()

    // Short words can name different controls; only established shared labels opt in.
    private static let sharedLabels: Set<String> = [
        "指示書を編集", "色カタログを変える", "モデルを変える",
        "キャンバス", "思考を表示", "合計",
    ]

    /// Only byte-equal Japanese copy with an unambiguous English pair is shared.
    static func localizedCopy(_ japanese: String, language: String) -> String? {
        language == "en" ? englishCopy[japanese] : nil
    }

    static func template(_ key: String, language: String, argumentCount: Int) -> String? {
        guard !excludedKeys.contains(key),
              let value = reference?.localized(language: language)?.dynamicTexts?[key],
              value.components(separatedBy: "%@").count - 1 == argumentCount,
              !value.replacingOccurrences(of: "%@", with: "").contains("%") else { return nil }
        return value
    }
}

public extension DisplaySettings {
    /// Saved source, model identifiers and metadata stay verbatim.
    func tooltipValue(_ value: String) -> String {
        preferences.showTooltips ? value : ""
    }

    /// Supply a native fallback even for an explicit key, so missing copy never leaks a key.
    func tooltip(_ fallback: String, serverKey: String? = nil) -> String {
        guard preferences.showTooltips else { return "" }
        if let key = serverKey ?? ServerTips.sourceKey(for: fallback),
           let value = ServerTips.text(key, language: preferences.language) { return value }
        return localized(fallback)
    }

    func tooltipFormat(_ fallback: String, serverKey: String? = nil, _ arguments: CVarArg...) -> String {
        guard preferences.showTooltips else { return "" }
        if let key = serverKey ?? ServerTips.sourceKey(for: fallback),
           let value = ServerTips.template(key, language: preferences.language, argumentCount: arguments.count) {
            // Exported function templates use %@ even for numeric counts.
            return String(format: value, locale: Locale(identifier: preferences.language),
                          arguments: arguments.map { String(describing: $0) })
        }
        return String(format: localized(fallback), locale: Locale(identifier: preferences.language), arguments: arguments)
    }
}
