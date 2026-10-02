import InkuHost
import SwiftUI

@MainActor
public struct DescriptionMeterView: View {
    @Bindable var model: AppModel
    public let text: String
    @State private var counted: DictionaryMeterCount?
    @State private var countedText = ""
    @State private var error: String?
    public init(model: AppModel, text: String) { self.model = model; self.text = text }

    public var body: some View {
        HStack {
            Spacer()
            VStack(alignment: .trailing, spacing: 3) {
                Text(label).font(.caption).foregroundStyle(.secondary)
                if let error { Text(model.display.localized(error)).font(.caption2).foregroundStyle(.orange) }
            }
        }
        .task(id: readingKey) { await loadReading() }
    }

    private var readingKey: String {
        text + ":" + model.display.preferences.language + ":" + String(model.descriptionMeter.japaneseEnabled) + ":" + String(model.descriptionMeter.englishEnabled)
    }

    private func loadReading() async {
        error = nil
        let source = text
        let japanese = DescriptionMeterModel.readsAsJapanese(source, uiLanguage: model.display.preferences.language)
        if japanese && !model.descriptionMeter.japaneseEnabled { counted = nil; return }
        if !japanese && !model.descriptionMeter.englishEnabled { counted = nil; return }
        do {
            try await Task.sleep(for: .milliseconds(300))
            let language = japanese ? "ja" : "en"
            let result = try await DescriptionMeter.shared.count(text: source, language: language)
            try Task.checkCancellation()
            counted = result; countedText = source
        } catch is CancellationError { }
        catch {
            guard !Task.isCancelled else { return }
            counted = nil
            self.error = source.unicodeScalars.count > 4000 ? "辞書による形式判定は4000文字までです。" : "計数用の辞書を読み込めませんでした。"
        }
    }

    private var label: String {
        let source = DescriptionMeterModel.pipelineDescription(text).trimmingCharacters(in: .whitespacesAndNewlines)
        let japanese = DescriptionMeterModel.readsAsJapanese(text, uiLanguage: model.display.preferences.language)
        if japanese {
            if !model.descriptionMeter.japaneseEnabled { return model.display.localizedFormat("文字数 %ld", source.unicodeScalars.filter { !CharacterSet.whitespacesAndNewlines.contains($0) }.count) }
            guard countedText == text, let total = counted?.mora, let phrases = counted?.phrases else { return model.display.localized(error == nil ? "音数を確認中" : "音数の判定なし") }
            let form = DescriptionMeterModel.japaneseForm(total: total, phrases: phrases)
            let approximate = counted?.unread?.isEmpty == false ? model.display.localized("約") : ""
            return model.display.localizedFormat("音数 %@%ld", approximate, total) + (form.map { model.display.localizedFormat("/%ld（%@）", $0.length, model.display.localized($0.name)) } ?? "")
        }
        let count = source.components(separatedBy: "\n").filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.count
        guard model.descriptionMeter.englishEnabled, countedText == text, let lines = counted?.lines, let syllables = counted?.syllables else { return model.display.localizedFormat("行数 %ld", count) }
        let form = DescriptionMeterModel.englishForm(lines: lines)
        return model.display.localizedFormat("行数 %ld", count) + (form.map { model.display.localizedFormat("/%ld（%@）", $0.length, model.display.localized($0.name)) } ?? "") + model.display.localizedFormat(" · 音節 %@%ld", counted?.unknown?.isEmpty == false ? model.display.localized("約") : "", syllables)
    }
}

@MainActor
public struct DescriptionMeterSettingsView: View {
    @Environment(\.locale) private var locale
    @Bindable var meter: DescriptionMeterModel
    public init(meter: DescriptionMeterModel) { self.meter = meter }
    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Toggle(InkuLocalization.string("日本語の形式を判定する（読み辞書の音数）", locale: locale), isOn: $meter.japaneseEnabled)
            Text(InkuLocalization.string("Sudachi small 辞書の読みで音数を数えます。切ると文字数だけを表示します。", locale: locale)).font(.caption).foregroundStyle(.secondary)
            Toggle(InkuLocalization.string("英語の形式を判定する（行数・音節）", locale: locale), isOn: $meter.englishEnabled)
            Text(InkuLocalization.string("CMUdict の発音と行数で近い形式に名前を付けます。切ると行数だけを表示します。", locale: locale)).font(.caption).foregroundStyle(.secondary)
            if let error = meter.settingsError { Text(InkuLocalization.message(error, locale: locale)).font(.caption).foregroundStyle(.red) }
        }
    }
}
