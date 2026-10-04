import SwiftUI

@MainActor
struct DdlAuthoringEditorSheet: View {
    @Bindable var model: AppModel
    @Bindable var session: DdlEditingSession
    @Environment(\.dismiss) private var dismiss
    @State private var showSaijiki = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.display.localized("DDLを編集")).font(.title2)
                    Text(model.display.localized("取消すると、表示中の作品と指示書は変わりません。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button(model.display.localized("歳時記を開く"), systemImage: "book") { showSaijiki = true }
                    .disabled(model.isBusy)
                    .help(tip("選んだ語を編集中DDLの末尾に挿入します。"))
            }.padding(16)
            Divider()
            TextEditor(text: $session.draft)
                .font(.system(.body, design: .monospaced))
                .scrollContentBackground(.hidden).padding(12)
                .disabled(model.isBusy)
                .accessibilityLabel(model.display.localized("DDL編集"))
            Divider()
            HStack {
                if let error = model.errorText {
                    Text(model.display.message(error)).font(.caption).foregroundStyle(.red).lineLimit(3)
                }
                Spacer()
                if model.isBusy {
                    ProgressView().controlSize(.small)
                    Button(model.display.localized("停止")) { Task { await model.cancel() } }
                } else {
                    Button(model.display.localized("取消")) { session.cancel(); dismiss() }
                        .keyboardShortcut(.cancelAction)
                        .help(tip("編集中の変更を破棄して閉じます。"))
                    Button(model.display.localized("変更を確定・描画")) {
                        Task { if await session.commit(to: model) { dismiss() } }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!session.canSubmit(to: model))
                    .keyboardShortcut(.defaultAction)
                    .help(tip("このDDLを確定して、新しい作品として描画します。"))
                }
            }.padding(16)
        }
        .frame(minWidth: 620, idealWidth: 800, minHeight: 480, idealHeight: 620)
        .interactiveDismissDisabled(model.isBusy)
        .sheet(isPresented: $showSaijiki) {
            VStack(spacing: 0) {
                HStack { Spacer(); Button(model.display.localized("閉じる")) { showSaijiki = false } }.padding(12)
                SaijikiView(model: model, onInsertWord: { session.insert($0) }, wordLanguage: model.language)
            }.frame(minWidth: 560, minHeight: 620)
        }
    }

    private func tip(_ key: String) -> String {
        model.display.preferences.showTooltips ? model.display.localized(key) : ""
    }
}
