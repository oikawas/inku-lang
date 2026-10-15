import InkuHost
import SwiftUI
import UniformTypeIdentifiers

@MainActor
struct DdlAuthoringEditorSheet: View {
    @Bindable var model: AppModel
    @Bindable var session: DdlEditingSession
    @Environment(\.dismiss) private var dismiss
    @State private var showModels = false
    @State private var drawingModel = ""
    @State private var providers: [ProviderSettings] = []
    @State private var inheritedWild = false
    @State private var wildOverride: Bool?
    @State private var insertion: InkuEditorInsertion?
    @State private var rangeBlocked = false
    @State private var confirmingDiscard = false

    var body: some View {
        DdlEditorDialogLayout(model: model, title: model.display.localized("指示書エディタ"),
            subtitle: model.display.webCopy("ddlEditDialogSubtitle", "描画すると、選択した作品の子として系譜へ保存します。"),
            work: session.work ?? model.displayedWork, text: $session.draft, insertion: $insertion,
            disabled: model.isBusy, onClose: { session.cancel(); dismiss() }, onRangeBlocked: { rangeBlocked = $0 }) {
            DdlDialogFooter {
                HStack(spacing: 18) {
                    DdlDrawingModelCard(model: model, reference: drawingModel, providers: providers) { showModels = true }
                    HStack(spacing: 8) {
                        Text(model.display.localized(wildOverride == nil ? "筆致制限（継承）" : "筆致制限")).inkuFont(12).foregroundStyle(.secondary)
                        Button(model.display.localized("暴れる")) { wildOverride = !(wildOverride ?? inheritedWild) }
                            .buttonStyle(InkuGhostButtonStyle(active: wildOverride ?? inheritedWild))
                            .accessibilityValue(model.display.localized((wildOverride ?? inheritedWild) ? "オン" : "オフ"))
                    }.fixedSize()
                }.disabled(model.isBusy)
            } actions: {
                VStack(alignment: .trailing, spacing: 8) {
                    if let error = model.errorText {
                        Text(model.display.message(error)).inkuFont(12).foregroundStyle(.red).textSelection(.enabled)
                    }
                    if model.isBusy {
                        // DdlEditorDialog.svelte:219: the drawing indicator replaces the footer actions.
                        RunStatusView(display: model.display, label: model.status, variant: .inline,
                                      onStop: { Task { await model.cancel() } })
                    } else {
                        HStack(spacing: 8) {
                            if let target = session.discardTarget {
                                // DdlEditorDialog: back to saved instructions as one undoable step; the box keeps its draft.
                                Button(model.display.localized("編集を破棄")) { confirmingDiscard = true }
                                    .disabled(session.draft == target)
                                    .confirmationDialog(model.display.localized("この作品を描いたときの指示書に戻します。編集した内容は失われます。"),
                                                        isPresented: $confirmingDiscard, titleVisibility: .visible) {
                                        Button(model.display.localized("破棄する"), role: .destructive) {
                                            guard !model.isBusy, session.draft != target else { return }
                                            insertion = InkuEditorInsertion(text: target, replacesAll: true)
                                        }
                                        Button(model.display.localized("キャンセル"), role: .cancel) {}
                                    }
                            }
                            Button(model.display.localized("キャンセル")) { session.cancel(); dismiss() }
                                .keyboardShortcut(.cancelAction)
                                .inkuTooltip(tip("編集中の変更を破棄して閉じます。"))
                            Button(model.display.webCopy("submitBtn", "描画する")) {
                                Task { if await session.commit(to: model, wildOverride: wildOverride) { dismiss() } }
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(!session.canSubmit(to: model) || rangeBlocked)
                            .keyboardShortcut(.defaultAction)
                            .inkuTooltip(tip("このDDLを確定して、新しい作品として描画します。"))
                        }
                    }
                }
            }
        }
        .interactiveDismissDisabled(model.isBusy)
        .task {
            let settings = await model.hostSettings()
            providers = settings.providers
            drawingModel = SettingsModel.isBatchModelAvailable(settings.models.stage2Model, settings: settings) ? settings.models.stage2Model : ""
            inheritedWild = (session.work ?? model.displayedWork)?.renderWild ?? false
        }
        .sheet(isPresented: $showModels) {
            BatchModelPickerView(model: model, initialReference: drawingModel, immediateSelection: true, title: "描画モデル") { reference in
                try await model.selectDdlDrawingModel(reference)
                drawingModel = reference
            }
        }
    }

    private func tip(_ key: String) -> String {
        model.display.tooltip(key)
    }
}

/// The new-instructions dialog owns its input and imports until drawing succeeds.
@MainActor
struct NewDdlAuthoringSheet: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""
    @State private var drawingModel = ""
    @State private var providers: [ProviderSettings] = []
    @State private var importedDocument: DDLPackageImport?
    @State private var showImport = false
    @State private var showModels = false
    @State private var importTask: Task<Void, Never>?
    @State private var importing = false
    @State private var importError: String?
    @State private var insertion: InkuEditorInsertion?
    @State private var rangeBlocked = false

    init(model: AppModel, initialImport: DDLPackageImport? = nil) {
        self.model = model
        _draft = State(initialValue: initialImport?.source ?? "")
        _importedDocument = State(initialValue: initialImport)
    }

    var body: some View {
        DdlEditorDialogLayout(model: model, title: model.display.webCopy("ddlNewDialogTitle", "指示書から新規作成"),
            subtitle: model.display.webCopy("ddlNewDialogSubtitle", "指示書を直接書いて、独立した作品として描画します。"),
            work: nil, text: $draft, insertion: $insertion, disabled: model.isBusy || importing,
            onClose: { dismiss() }, onRangeBlocked: { rangeBlocked = $0 }) {
            DdlDialogFooter {
                HStack(spacing: 18) {
                    DdlDrawingModelCard(model: model, reference: drawingModel, providers: providers) { showModels = true }
                    VStack(alignment: .leading, spacing: 5) {
                        Button(model.display.localized("DDLファイルを読み込む…"), systemImage: "doc.badge.arrow.up") { showImport = true }
                        if let importedDocument, !importedDocument.names.isEmpty {
                            Text(model.display.localized("この新しい作品に定義を持ち込みます: ") + importedDocument.names.joined(separator: ", "))
                                .inkuFont(12).textSelection(.enabled)
                        }
                    }
                }.disabled(model.isBusy || importing)
            } actions: {
                VStack(alignment: .trailing, spacing: 8) {
                    if let error = importError ?? model.errorText {
                        Text(model.display.message(error)).inkuFont(12).foregroundStyle(.red).textSelection(.enabled)
                    }
                    HStack(spacing: 8) {
                        if importing {
                            ProgressView().controlSize(.small)
                            Button(model.display.localized("停止")) { importTask?.cancel() }
                        } else if model.isBusy {
                            RunStatusView(display: model.display, label: model.status, variant: .inline,
                                          onStop: { Task { await model.cancel() } })
                        } else {
                            Button(model.display.localized("キャンセル")) { dismiss() }.keyboardShortcut(.cancelAction)
                            Button(model.display.webCopy("submitBtn", "描画する")) {
                                Task { if await model.drawNewDDL(draft, imported: importedDocument) { dismiss() } }
                            }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                                .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || rangeBlocked)
                        }
                    }
                }
            }
        }
        .interactiveDismissDisabled(model.isBusy || importing)
        .task {
            let settings = await model.hostSettings()
            providers = settings.providers
            drawingModel = SettingsModel.isBatchModelAvailable(settings.models.stage2Model, settings: settings) ? settings.models.stage2Model : ""
        }
        .sheet(isPresented: $showModels) {
            BatchModelPickerView(model: model, initialReference: drawingModel, immediateSelection: true, title: "描画モデル") { reference in
                try await model.selectDdlDrawingModel(reference)
                drawingModel = reference
            }
        }
        .fileImporter(isPresented: $showImport,
            allowedContentTypes: [.json, .plainText, UTType(filenameExtension: "ddl") ?? .text], allowsMultipleSelection: false) { result in
                switch result {
                case .success(let urls): if let url = urls.first { read(url) }
                case .failure(let error):
                    if (error as NSError).code != NSUserCancelledError { importError = error.localizedDescription }
                }
        }
        .onDisappear { importTask?.cancel() }
    }

    private func read(_ url: URL) {
        guard !importing, !model.isBusy else { return }
        importing = true
        importError = nil
        importTask = Task {
            defer { importing = false; importTask = nil }
            do {
                let worker = Task.detached(priority: .userInitiated) { try DDLPackageImport.read(url: url) }
                let document = try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
                try Task.checkCancellation()
                importedDocument = document
                draft = document.source
            } catch is CancellationError { }
            catch { importError = error.localizedDescription }
        }
    }
}
