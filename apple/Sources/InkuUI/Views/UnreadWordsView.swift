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
                Image(systemName: "questionmark.circle").help(model.display.tooltip("固有名詞・専門語・造語など、記述からDDLへの直接の対応を確認できなかった語を集めます。頻度と文脈を人間が確認し、語彙追加を判断します。辞書への自動追加は行いません。"))
                Spacer()
                Button(model.display.localized("再読込")) { Task { await reload() } }.disabled(loading)
            }
            Text(model.display.localized("記述からDDLへの解釈で直接対応を確認できなかった語の集計です。この台帳から辞書へ自動昇格することはありません。"))
                .inkuFont(12).foregroundStyle(.secondary)
            if loading { ProgressView(model.display.localized("読み込み中")) }
            if let error { Text(model.display.localized("未読語台帳を読み込めませんでした: ") + error).foregroundStyle(.red).textSelection(.enabled) }
            if items.isEmpty, !loading, error == nil { Text(model.display.localized("記録された未読語はありません。")).foregroundStyle(.secondary) }
            if !items.isEmpty {
                Text(model.display.localizedFormat("%ld語（最大500語）", items.count)).inkuFont(12).foregroundStyle(.secondary)
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        ForEach(items) { item in
                            VStack(alignment: .leading, spacing: 5) {
                                HStack {
                                    Text(item.word).fontWeight(.semibold).textSelection(.enabled)
                                    Text(model.display.localizedFormat("%ld回記録", item.frequency)).monospacedDigit()
                                    Spacer()
                                    Text(date(item.lastAt), style: .date).inkuFont(12)
                                    Text(date(item.lastAt), style: .time).inkuFont(12)
                                }.help(model.display.tooltipValue(model.display.localized("初回記録: ") + date(item.firstAt).formatted(date: .abbreviated, time: .standard)))
                                ForEach(item.contexts, id: \.self) { context in Text(context).inkuFont(12).foregroundStyle(.secondary).textSelection(.enabled) }
                            }
                            Divider()
                        }
                    }
                }.frame(maxHeight: 440)
            }
        }.task { await reload() }
    }

    private func date(_ milliseconds: Int64) -> Date { Date(timeIntervalSince1970: Double(milliseconds) / 1000) }
    private func reload() async {
        let current = UUID(); requestID = current; loading = true
        do {
            let result = try await model.auxiliaryDatabase().unreadWords()
            guard requestID == current, !Task.isCancelled else { return }
            items = result; error = nil
        } catch {
            guard requestID == current, !Task.isCancelled else { return }
            self.error = error.localizedDescription
        }
        if requestID == current { loading = false }
    }
}
