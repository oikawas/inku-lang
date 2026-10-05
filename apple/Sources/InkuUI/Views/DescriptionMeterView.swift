import InkuHost
import SwiftUI

/// Web `DescriptionMeter.svelte`: the length of a description and the verse form it is, e.g. 「音数 17/17（俳句/川柳）」.
/// Until the dictionary first answers, or when it cannot, the meter estimates; while the author types it keeps
/// the last answer instead of falling back on each keystroke.
@MainActor
public struct DescriptionMeterView: View {
    @Bindable var model: AppModel
    public let text: String
    @State private var mora: DescriptionMoraAnswer?
    @State private var syllableLines: [Int]?
    @State private var resourceError = false
    public init(model: AppModel, text: String) { self.model = model; self.text = text }

    public var body: some View {
        VStack(alignment: .trailing, spacing: 3) {
            Text(reading.label(language: model.display.preferences.language))
                .inkuFont(12).monospacedDigit().foregroundStyle(.tertiary)
                .multilineTextAlignment(.trailing)
            // Native only: the bundled dictionary itself could not be read (the Web has no such failure).
            if resourceError {
                Text(model.display.localized("計数用の辞書を読み込めませんでした。")).inkuFont(11).foregroundStyle(.orange)
            }
        }
        .frame(minWidth: 54, alignment: .trailing)
        .accessibilityHidden(true)
        .task(id: readingKey) { await loadReading() }
    }

    private var reading: DescriptionMeterReading {
        DescriptionMeterModel.describe(text, uiLanguage: model.display.preferences.language,
                                       japaneseEnabled: model.descriptionMeter.japaneseEnabled,
                                       englishEnabled: model.descriptionMeter.englishEnabled,
                                       mora: mora, syllableLines: syllableLines)
    }

    private var readingKey: String {
        text + ":" + model.display.preferences.language + ":" + String(model.descriptionMeter.japaneseEnabled) + ":" + String(model.descriptionMeter.englishEnabled)
    }

    private func loadReading() async {
        let source = text
        let japanese = DescriptionMeterModel.readsAsJapanese(source, uiLanguage: model.display.preferences.language)
        guard japanese ? model.descriptionMeter.japaneseEnabled : model.descriptionMeter.englishEnabled else { return }
        do {
            // The dictionary is asked once the typing pauses.
            try await Task.sleep(for: .milliseconds(300))
            // Web `METER_TEXT_LIMIT` (text.length): a longer description is estimated without asking.
            guard source.utf16.count <= DescriptionMeterModel.dictionaryTextLimit else {
                if japanese { mora = nil } else { syllableLines = nil }
                return
            }
            let result = try await DescriptionMeter.shared.count(text: source, language: japanese ? "ja" : "en")
            try Task.checkCancellation()
            resourceError = false
            if japanese {
                mora = result.mora.map { DescriptionMoraAnswer(total: $0, phrases: result.phrases ?? [], unread: result.unread ?? []) }
            } else {
                syllableLines = result.lines
            }
        } catch is CancellationError {
        } catch {
            guard !Task.isCancelled else { return }
            if japanese { mora = nil } else { syllableLines = nil }
            resourceError = (error as? HostError).map { $0.code.hasPrefix("meter_resources") || $0.code.hasPrefix("meter_dictionary") } ?? true
        }
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
            Text(InkuLocalization.string("Sudachi small 辞書の読みで音数を数えます。切ると文字数だけを表示します。", locale: locale)).inkuFont(12).foregroundStyle(.secondary)
            Toggle(InkuLocalization.string("英語の形式を判定する（行数・音節）", locale: locale), isOn: $meter.englishEnabled)
            Text(InkuLocalization.string("CMUdict の発音と行数で近い形式に名前を付けます。切ると行数だけを表示します。", locale: locale)).inkuFont(12).foregroundStyle(.secondary)
            if let error = meter.settingsError { Text(InkuLocalization.message(error, locale: locale)).inkuFont(12).foregroundStyle(.red) }
        }
    }
}
