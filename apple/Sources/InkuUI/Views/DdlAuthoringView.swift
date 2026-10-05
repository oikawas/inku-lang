import SwiftUI

@MainActor
struct DdlAuthoringView: View {
    @Bindable var model: AppModel
    var showsDiagnostics = true
    @State private var output = "diagnostics"
    @State private var detailsExpanded = false
    @State private var editingSession: DdlEditingSession?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(model.display.localized("指示書")).inkuFont(12, weight: .semibold)
                    Spacer()
                    Button(model.display.localized("DDLを編集")) { editingSession = DdlEditingSession(model: model) }
                        .disabled(!model.canEditCurrentDDL)
                        .help(tip("独立した編集画面でDDLを変更します。"))
                }
                if !model.authoringAuthority.isEmpty {
                    Label(model.display.localized(model.sourceLocked ? "DDL確定・記述ロック" : "記述から生成可能"),
                          systemImage: model.sourceLocked ? "lock.fill" : "pencil")
                        .inkuFont(12).foregroundStyle(.secondary)
                }
            }
            if !model.authoringAuthority.isEmpty {
                Text(model.display.localizedFormat("改訂 %@", model.authoringRevision))
                    .inkuFont(12, design: .monospaced).textSelection(.enabled)
            }
            Text(model.visibleDDL).inkuFont(12, design: .monospaced)
                .lineLimit(5).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 10)
                .overlay(alignment: .leading) { Rectangle().fill(.quaternary).frame(width: 2) }
            if showsDiagnostics {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) { checkButton; regenerateButton }.fixedSize(horizontal: true, vertical: false)
                    VStack(alignment: .leading, spacing: 8) { checkButton; regenerateButton }
                }
                .buttonStyle(InkuGhostButtonStyle())
            }
            if showsDiagnostics && model.sourceLocked {
                Text(model.display.localized("確定したDDLの変更後は、この作品の記述を生成元へ戻せません。新規作品では別の記述を使えます。"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
            if !model.holeIDs.isEmpty {
                Text(model.display.localized("補完対象")).inkuFont(12, weight: .semibold)
                ForEach(model.holeIDs, id: \.self) { id in
                    Toggle(id, isOn: Binding(
                        get: { model.selectedHoleIDs.contains(id) },
                        set: { if $0 { model.selectedHoleIDs.insert(id) } else { model.selectedHoleIDs.remove(id) } }
                    )).inkuFont(12, design: .monospaced).disabled(model.isBusy)
                }
                Button(model.display.localized(model.selectedHoleIDs.isEmpty ? "すべての未解決箇所を補完" : "選択した未解決箇所を補完")) {
                    Task { await model.completeHoles() }
                }.disabled(!model.canCompleteHoles)
                Text(model.display.localized("補完はモデルへ送信します。変更案は承認後に確定します。"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
            if !model.patchProposalJSON.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label(model.display.localized("補完案の承認待ち"), systemImage: "checkmark.bubble").inkuFont(14, weight: .semibold)
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 12) {
                            sourcePane("確定済み", model.visibleDDL).frame(width: 250)
                            sourcePane("補完案", model.patchCandidate).frame(width: 250)
                        }
                        VStack(alignment: .leading, spacing: 12) {
                            sourcePane("確定済み", model.visibleDDL)
                            sourcePane("補完案", model.patchCandidate)
                        }
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Button { Task { await model.approvePatch() } } label: {
                            Text(model.display.localized("承認して確定・描画")).frame(maxWidth: .infinity)
                        }.buttonStyle(.borderedProminent)
                        Button(model.display.localized("却下")) { Task { await model.declinePatch() } }
                            .buttonStyle(InkuGhostButtonStyle())
                    }.disabled(model.isBusy)
                    DisclosureGroup(model.display.localized("補完案の詳細")) { sourcePane("", model.patchProposalJSON) }
                }
                .padding(12).background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 8))
            }
            if showsDiagnostics && model.display.visible("diagnostics") {
              DisclosureGroup(model.display.localized("診断・プロンプト・処理記録"), isExpanded: $detailsExpanded) {
                VStack(alignment: .leading, spacing: 8) {
                    Picker(model.display.localized("表示"), selection: $output) {
                        Text(label("診断", "diagnostics")).tag("diagnostics")
                        Text(label("送信プロンプト", "prompt")).tag("prompt")
                        Text(model.display.localized("処理記録")).tag("events")
                        Text(model.display.localized("プラグイン")).tag("plugins")
                    }
                    .onChange(of: output) { _, new in model.markOutputRead(new) }
                    sourcePane("", displayedOutput).onAppear { model.markOutputRead(output) }
                }
              }
            }
        }
        .onChange(of: model.displayedWork?.id) { _, _ in
            if !model.display.preferences.keepGenerationInfo { detailsExpanded = false }
        }
        .sheet(item: $editingSession) { session in
            DdlAuthoringEditorSheet(model: model, session: session).environment(model.display)
        }
    }

    private var checkButton: some View {
        Button(model.display.localized("検査")) { Task { await model.checkDDL() } }
            .disabled(model.isBusy || model.ddlText.isEmpty)
            .help(tip("保存せずに、現在の指示書を検査します。"))
    }

    private func tip(_ key: String) -> String {
        model.display.tooltip(key)
    }

    @ViewBuilder private var regenerateButton: some View {
        if model.canRegenerateDescription {
            Button(model.display.localized("記述から作り直す")) { Task { await model.regenerateDescription() } }
        }
    }

    private func label(_ label: String, _ output: String) -> String {
        model.display.localized(label) + (model.unreadOutputs.contains(output) ? " ●" : "")
    }
    private var displayedOutput: String {
        switch output {
        case "prompt": promptOutput
        case "events": model.eventsJSON
        case "plugins": model.macroDiagnostics
        default: model.diagnosticsJSON
        }
    }
    private var promptOutput: String {
        switch model.promptAvailability {
        case .loading: model.display.localized("送信プロンプトを読み込んでいます。")
        case .recorded: model.promptJSON
        case .notRecorded: model.display.localized("送信プロンプトの記録はありません。")
        case .unavailable: model.display.localized("この保存作品の送信プロンプトを取得できません。")
        }
    }
    private func sourcePane(_ title: String, _ source: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if !title.isEmpty { Text(model.display.localized(title)).inkuFont(12, weight: .semibold) }
            ScrollView {
                Text(source).inkuFont(12, design: .monospaced).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(8)
            }
            .frame(minHeight: 120, maxHeight: 240)
            .background(.background, in: RoundedRectangle(cornerRadius: 6))
        }.frame(maxWidth: .infinity)
    }
}
