import Foundation

/// Explicit package-bundle lookup works in both SwiftPM and native app hosts.
public enum InkuLocalization {
    private static let englishBundle = Bundle.module.path(forResource: "en", ofType: "lproj").flatMap(Bundle.init(path:))
    public static func string(_ key: String, locale: Locale) -> String {
        string(key, language: locale.language.languageCode?.identifier ?? "ja")
    }
    public static func string(_ key: String, language: String) -> String {
        guard language == "en", let englishBundle else { return key }
        return englishBundle.localizedString(forKey: key, value: key, table: "Localizable")
    }
    public static func format(_ key: String, language: String, _ arguments: CVarArg...) -> String {
        String(format: string(key, language: language), locale: Locale(identifier: language == "en" ? "en" : "ja"), arguments: arguments)
    }

    /// Translate only native status grammar; embedded names and response text stay verbatim.
    public static func message(_ value: String, locale: Locale) -> String {
        message(value, language: locale.language.languageCode?.identifier ?? "ja")
    }
    public static func message(_ value: String, language: String) -> String {
        guard language == "en" else { return value }
        let direct = string(value, language: language)
        if direct != value { return direct }
        for entry in statusFormats {
            guard let regex = try? NSRegularExpression(pattern: entry.pattern),
                  let match = regex.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)) else { continue }
            var arguments: [CVarArg] = []
            for index in 1..<match.numberOfRanges {
                guard let range = Range(match.range(at: index), in: value) else { continue }
                let argument = String(value[range])
                arguments.append(entry.localizedArguments.contains(index) ? string(argument, language: language) : argument)
            }
            return String(format: string(entry.key, language: language), locale: Locale(identifier: language), arguments: arguments)
        }
        return value
    }

    private struct StatusFormat: Sendable {
        let pattern: String
        let key: String
        var localizedArguments: Set<Int> = []
    }
    private static let statusFormats: [StatusFormat] = [
        .init(pattern: #"^画像をコピーしました（Y軸 ([0-9]+)px）$"#, key: "画像をコピーしました（Y軸 %@px）"),
        .init(pattern: #"^モデルの応答待ち（期限 (.+)）$"#, key: "モデルの応答待ち（期限 %@）"),
        .init(pattern: #"^応答を受信中（([0-9]+) bytes）$"#, key: "応答を受信中（%@ bytes）"),
        .init(pattern: #"^比較候補のモデル応答待ち（期限 (.+)）$"#, key: "比較候補のモデル応答待ち（期限 %@）"),
        .init(pattern: #"^比較候補を受信中（([0-9]+) bytes）$"#, key: "比較候補を受信中（%@ bytes）"),
        .init(pattern: #"^([0-9]+)個のモデルを取得しました。$"#, key: "%@個のモデルを取得しました。"),
        .init(pattern: #"^([0-9]+) / ([0-9]+)（元の([0-9]+)行目）・再試行([0-9]+)$"#, key: "%@ / %@（元の%@行目）・再試行%@"),
        .init(pattern: #"^([0-9]+) / ([0-9]+)（元の([0-9]+)行目）$"#, key: "%@ / %@（元の%@行目）"),
        .init(pattern: #"^バッチ完了: ([0-9]+)件成功・([0-9]+)件失敗$"#, key: "バッチ完了: %@件成功・%@件失敗"),
        .init(pattern: #"^([0-9]+)作品を表示しました。次の生成まで([0-9]+)秒$"#, key: "%@作品を表示しました。次の生成まで%@秒"),
        .init(pattern: #"^([0-9]+) / ([0-9]+) 世代: モデルが観察しています$"#, key: "%@ / %@ 世代: モデルが観察しています"),
        .init(pattern: #"^([0-9]+) / ([0-9]+) 世代: (.+)を生成中$"#, key: "%@ / %@ 世代: %@を生成中", localizedArguments: [3]),
        .init(pattern: #"^([0-9]+) 世代の推敲を完了しました。作品の選択は利用者が行います。$"#, key: "%@ 世代の推敲を完了しました。作品の選択は利用者が行います。"),
        .init(pattern: #"^候補 ([0-9]+)/([0-9]+): (.+)$"#, key: "候補 %@/%@: %@"),
        .init(pattern: #"^([0-9]+)件の候補を用意しました。保存する候補を選択してください。$"#, key: "%@件の候補を用意しました。保存する候補を選択してください。"),
        .init(pattern: #"^保存中: (.+)$"#, key: "保存中: %@"),
        .init(pattern: #"^保存を停止しました。保存済み ([0-9]+)件は履歴と系譜に残ります。$"#, key: "保存を停止しました。保存済み %@件は履歴と系譜に残ります。"),
        .init(pattern: #"^選択した([0-9]+)件を保存しました。$"#, key: "選択した%@件を保存しました。"),
        .init(pattern: #"^保存済み ([0-9]+)件$"#, key: "保存済み %@件"),
        .init(pattern: #"^([0-9]+)作品を描画・エンコードしています…$"#, key: "%@作品を描画・エンコードしています…"),
        .init(pattern: #"^([0-9]+)ファイルを書き出しました。$"#, key: "%@ファイルを書き出しました。"),
        .init(pattern: #"^([0-9]+) 件をごみ箱へ移しました$"#, key: "%@ 件をごみ箱へ移しました"),
        .init(pattern: #"^([0-9]+) 件を戻しました$"#, key: "%@ 件を戻しました"),
        .init(pattern: #"^([0-9]+) 件を完全に削除しました$"#, key: "%@ 件を完全に削除しました"),
        .init(pattern: #"^この新しい作品に定義を持ち込みます: (.+)$"#, key: "この新しい作品に定義を持ち込みます: %@"),
        .init(pattern: #"^自動バックアップ: (.+)$"#, key: "自動バックアップ: %@"),
        .init(pattern: #"^生成結果のログを保存できませんでした: (.+)$"#, key: "生成結果のログを保存できませんでした: %@"),
        .init(pattern: #"^表示設定を読み込めませんでした: (.+)$"#, key: "表示設定を読み込めませんでした: %@"),
        .init(pattern: #"^表示設定を保存できませんでした: (.+)$"#, key: "表示設定を保存できませんでした: %@"),
        .init(pattern: #"^形式判定の設定を読み込めませんでした: (.+)$"#, key: "形式判定の設定を読み込めませんでした: %@"),
        .init(pattern: #"^形式判定の設定を保存できませんでした: (.+)$"#, key: "形式判定の設定を保存できませんでした: %@"),
        .init(pattern: #"^保存先を記録できませんでした: (.+)$"#, key: "保存先を記録できませんでした: %@"),
    ]
}

public extension DisplaySettings {
    func localized(_ key: String) -> String { InkuLocalization.string(key, language: preferences.language) }
    func message(_ value: String) -> String { InkuLocalization.message(value, language: preferences.language) }
    func localizedFormat(_ key: String, _ arguments: CVarArg...) -> String {
        String(format: localized(key), locale: Locale(identifier: preferences.language), arguments: arguments)
    }
}
