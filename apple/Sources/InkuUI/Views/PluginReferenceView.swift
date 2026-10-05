import Foundation
import InkuHost
import SwiftUI

@MainActor
public struct PluginReferenceView: View {
    @Bindable var model: AppModel
    public let text: String
    @State private var names: Set<String> = []
    @State private var firesOn: [PluginFiringPhrase] = []
    @State private var error: String?
    public init(model: AppModel, text: String) { self.model = model; self.text = text }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let error { Text(model.display.localized(error)).inkuFont(12).foregroundStyle(.orange) }
            ForEach(references) { reference in
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: reference.known ? "checkmark.circle" : "questionmark.circle")
                    VStack(alignment: .leading, spacing: 3) {
                        Text(reference.text + model.display.localized(reference.known ? " · 使用可能" : " · この設定では使えません"))
                            .inkuFont(12, design: .monospaced).textSelection(.enabled)
                        if !reference.known {
                            if let hint = reference.firesAs {
                                Text(model.display.localizedFormat("名前空間を付けない表現では「%@」に対応します。指定名を確認してください。", hint))
                                    .inkuFont(11)
                            }
                            Text(model.display.localized("共通コアが保持しない指定名は、描画時に周囲の文とともに省略される場合があります。"))
                                .inkuFont(11)
                        }
                    }
                }.foregroundStyle(reference.known ? Color.secondary : Color.orange)
            }
        }
        .task(id: model.macroDiagnostics + "\n" + (model.importedMacroNames + model.authoringMacroNames).sorted().joined(separator: "\n")) { await refresh() }
    }

    private var references: [PluginReferenceState] { unique(PluginReferences.scan(text: text, names: names, firesOn: firesOn)) }

    private func unique(_ values: [PluginReferenceState]) -> [PluginReferenceState] {
        var seen: Set<String> = []
        return values.filter { seen.insert($0.text).inserted }
    }

    private func refresh() async {
        let settings = await model.hostSettings()
        let enabled = model.pluginWords.filter { word in
            guard let package = word.packageID else { return false }
            return settings.plugins?.isEnabled(package) ?? true
        }
        do {
            guard let url = Bundle.module.url(forResource: "plugin-words", withExtension: "json"),
                  let entries = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [[String: Any]] else {
                throw HostError("plugin_reference_vocabulary_unavailable")
            }
            let pinnedNames = Set(model.authoringMacroNames)
            let enabledIDs = Set(enabled.map(\.id)).union(pinnedNames)
            var phrases: [PluginFiringPhrase] = []
            for entry in entries where (entry["id"] as? String).map(enabledIDs.contains) == true {
                guard let id = entry["id"] as? String, let fires = entry["fires_on"] as? [String: [String]] else { continue }
                let local = id.split(separator: ".", maxSplits: 1).last.map(String.init) ?? id
                for phrase in (fires["ja"] ?? []) + (fires["en"] ?? []) {
                    let phrase = phrase.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !phrase.isEmpty { phrases.append(PluginFiringPhrase(phrase: phrase, word: local)) }
                }
            }
            guard !Task.isCancelled else { return }
            names = Set(enabled.flatMap { [$0.id] + $0.aliases })
                .union(model.importedMacroNames).union(pinnedNames)
            firesOn = phrases; error = nil
        } catch {
            guard !Task.isCancelled else { return }
            names = Set(model.importedMacroNames).union(model.authoringMacroNames)
            firesOn = []; self.error = "プラグインの語を読み込めませんでした。"
        }
    }
}
