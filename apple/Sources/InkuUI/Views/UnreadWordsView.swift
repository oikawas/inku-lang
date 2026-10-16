import Foundation
import InkuPersistence
import SwiftUI

@MainActor
public struct UnreadWordsView: View {
    @Bindable var model: AppModel
    @State private var items: [UnreadWord] = []
    @State private var loading = false
    @State private var error: String?
    @State private var requestID = UUID()
    public init(model: AppModel) { self.model = model }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(model.display.localized("未読語台帳")).inkuFont(14, weight: .semibold)
                Image(systemName: "questionmark.circle")
                    // UnreadWordsPanel.svelte:48: the purpose, in the Web's paragraphs.
                    .inkuTooltip(model.display.tooltip("固有名詞・専門語・造語など、記述からDDLへの直接の対応を確認できなかった語を集めます。頻度と文脈を人間が確認し、語彙追加を判断します。辞書への自動追加は行いません。",
                                                       serverKey: "settingsUnreadWordsPurposeTooltip"), wide: true)
                Spacer()
                Button(model.display.localized("再読込")) { Task { await reload() } }.disabled(loading)
            }
            Text(model.display.webCopy("settingsUnreadWordsDescription", "記述からDDLへの解釈で直接対応を確認できなかった語の集計です。この台帳から辞書へ自動昇格することはありません。"))
                .inkuFont(12).foregroundStyle(.secondary)
            Text(model.display.preferences.language == "en" ? "Unread words recorded on this device" : "この端末に記録された未読語")
                .inkuFont(11).foregroundStyle(.secondary)
            if loading { ProgressView(model.display.localized("読み込み中")) }
            if let error { Text(model.display.localized("未読語台帳を読み込めませんでした: ") + error).foregroundStyle(.red).textSelection(.enabled) }
            if items.isEmpty, !loading, error == nil { Text(model.display.localized("記録された未読語はありません。")).foregroundStyle(.secondary) }
            if !items.isEmpty {
                Text(model.display.webCopyFormat("settingsUnreadWordsCount", "%@語", items.count))
                    .inkuFont(11).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .trailing)
                Table(items) {
                    TableColumn(model.display.webCopy("settingsUnreadWordsWord", "語")) { item in
                        Text(item.word).fontWeight(.semibold).textSelection(.enabled)
                    }.width(min: 90, ideal: 140, max: 180)
                    TableColumn(model.display.webCopy("settingsUnreadWordsFrequency", "頻度")) { item in
                        Text(String(item.frequency)).monospacedDigit().frame(maxWidth: .infinity, alignment: .trailing)
                    }.width(60)
                    TableColumn(model.display.webCopy("settingsUnreadWordsLastSeen", "最終記録")) { item in
                        Text(timestamp(item.lastAt)).foregroundStyle(.secondary)
                            .inkuTooltip(model.display.tooltipValue(model.display.webCopy("settingsUnreadWordsFirstSeen", "初回記録") + ": " + timestamp(item.firstAt)))
                    }.width(min: 130, ideal: 160, max: 200)
                    TableColumn(model.display.webCopy("settingsUnreadWordsContexts", "文脈（最大3件）")) { item in
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(item.contexts, id: \.self) { context in
                                Text(context).foregroundStyle(.secondary).lineLimit(1).textSelection(.enabled)
                                    .inkuTooltip(model.display.tooltipValue(context))
                            }
                        }
                    }.width(min: 260, ideal: 360)
                }
                .inkuFont(12).frame(minHeight: 260, maxHeight: 440)
            }
        }.task { await reload() }
    }

    private func date(_ milliseconds: Int64) -> Date { Date(timeIntervalSince1970: Double(milliseconds) / 1000) }
    private func timestamp(_ milliseconds: Int64) -> String {
        guard milliseconds > 0 else { return "—" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: model.display.preferences.language)
        formatter.dateStyle = .short; formatter.timeStyle = .medium
        return formatter.string(from: date(milliseconds))
    }
    private func reload() async {
        let current = UUID(); requestID = current; loading = true; error = nil
        do {
            let result = try await model.auxiliaryDatabase().unreadWords()
            guard requestID == current, !Task.isCancelled else { return }
            items = result; error = nil
        } catch {
            guard requestID == current, !Task.isCancelled else { return }
            items = []
            self.error = error.localizedDescription
        }
        if requestID == current { loading = false }
    }
}
