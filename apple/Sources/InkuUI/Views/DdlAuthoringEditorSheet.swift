import InkuHost
import SwiftUI
import UniformTypeIdentifiers

@MainActor
struct DdlAuthoringEditorSheet: View {
    @Bindable var model: AppModel
    @Bindable var session: DdlEditingSession
    @Environment(\.dismiss) private var dismiss
    @State private var showSaijiki = false
    @State private var showModels = false
    @State private var drawingModel = ""
    @State private var inheritedWild = false
    @State private var wildOverride: Bool?
    @State private var insertion: InkuEditorInsertion?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.display.localized("DDLを編集")).inkuFont(16, weight: .semibold)
                    Text(model.display.localized("取消すると、表示中の作品と指示書は変わりません。"))
                        .inkuFont(12).foregroundStyle(.secondary)
                }
                Spacer()
                Button { session.cancel(); dismiss() } label: { Image(systemName: "xmark") }
                    .accessibilityLabel(model.display.localized("閉じる")).disabled(model.isBusy)
            }.padding(16)
            Divider()
            HStack(spacing: 16) {
                Button { showModels = true } label: {
                    Label(drawingModel.isEmpty ? model.display.localized("描画モデルを選択") : drawingModel, systemImage: "cpu")
                }
                Button {
                    wildOverride = !(wildOverride ?? inheritedWild)
                } label: {
                    Text(model.display.localized("暴れる") + " " + model.display.localized((wildOverride ?? inheritedWild) ? "入" : "切"))
                }.buttonStyle(.bordered).tint((wildOverride ?? inheritedWild) ? .accentColor : .secondary)
                if wildOverride == nil { Text(model.display.localized("元の作品から継承")).inkuFont(12).foregroundStyle(.secondary) }
            }.padding(.horizontal, 16).padding(.vertical, 10).disabled(model.isBusy)
            DdlEditorPane(model: model, text: $session.draft, disabled: model.isBusy, insertion: $insertion,
                          onShowSaijiki: { showSaijiki = true })
                .padding(.horizontal, 18).padding(.vertical, 14)
            Divider()
            HStack {
                if let error = model.errorText {
                    Text(model.display.message(error)).inkuFont(12).foregroundStyle(.red).textSelection(.enabled)
                }
                Spacer()
                if model.isBusy {
                    ProgressView().controlSize(.small)
                    Button(model.display.localized("停止")) { Task { await model.cancel() } }
                } else {
                    Button(model.display.localized("取消")) { session.cancel(); dismiss() }
                        .keyboardShortcut(.cancelAction)
                        .inkuTooltip(tip("編集中の変更を破棄して閉じます。"))
                    Button(model.display.localized("変更を確定・描画")) {
                        Task { if await session.commit(to: model, wildOverride: wildOverride) { dismiss() } }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!session.canSubmit(to: model))
                    .keyboardShortcut(.defaultAction)
                    .inkuTooltip(tip("このDDLを確定して、新しい作品として描画します。"))
                }
            }.padding(16)
        }
        #if os(macOS)
        .frame(minWidth: 620, idealWidth: 800, minHeight: 480, idealHeight: 620)
        #endif
        .interactiveDismissDisabled(model.isBusy)
        .task {
            let settings = await model.hostSettings()
            drawingModel = SettingsModel.isBatchModelAvailable(settings.models.stage2Model, settings: settings) ? settings.models.stage2Model : ""
            inheritedWild = (session.work ?? model.displayedWork)?.renderWild ?? false
        }
        .sheet(isPresented: $showModels) {
            BatchModelPickerView(model: model, initialReference: drawingModel, immediateSelection: true, title: "描画モデル") { reference in
                try await model.selectDdlDrawingModel(reference)
                drawingModel = reference
            }
        }
        .sheet(isPresented: $showSaijiki) {
            VStack(spacing: 0) {
                HStack { Spacer(); Button(model.display.localized("閉じる")) { showSaijiki = false } }.padding(12)
                SaijikiView(model: model, onInsertWord: { insertion = InkuEditorInsertion(text: $0) },
                            wordLanguage: model.instructionLanguage(for: session.draft))
            }.frame(minWidth: 560, minHeight: 620)
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
    @State private var importedDocument: DDLPackageImport?
    @State private var showImport = false
    @State private var showModels = false
    @State private var importTask: Task<Void, Never>?
    @State private var importing = false
    @State private var importError: String?
    @State private var insertion: InkuEditorInsertion?
    @State private var showSaijiki = false

    init(model: AppModel, initialImport: DDLPackageImport? = nil) {
        self.model = model
        _draft = State(initialValue: initialImport?.source ?? "")
        _importedDocument = State(initialValue: initialImport)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(model.display.localized("指示書の新規作成")).inkuFont(16, weight: .semibold)
                Spacer()
                Button { dismiss() } label: { Image(systemName: "xmark") }
                    .accessibilityLabel(model.display.localized("閉じる")).disabled(model.isBusy || importing)
            }.padding(16)
            Divider()
            HStack {
                Button { showModels = true } label: {
                    Label(drawingModel.isEmpty ? model.display.localized("描画モデルを選択") : drawingModel, systemImage: "cpu")
                }
                Spacer()
                Button(model.display.localized("DDLファイルを読み込む…"), systemImage: "doc.badge.arrow.up") { showImport = true }
            }.padding(16).disabled(model.isBusy || importing)
            DdlEditorPane(model: model, text: $draft, disabled: model.isBusy || importing, insertion: $insertion,
                          onShowSaijiki: { showSaijiki = true })
                .padding(.horizontal, 18).padding(.vertical, 14)
            if let importedDocument, !importedDocument.names.isEmpty {
                Text(model.display.localized("この新しい作品に定義を持ち込みます: ") + importedDocument.names.joined(separator: ", "))
                    .inkuFont(12).textSelection(.enabled).padding(.horizontal, 16)
            }
            if let error = importError ?? model.errorText {
                Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled).padding(.horizontal, 16)
            }
            Divider()
            HStack {
                if importing {
                    ProgressView().controlSize(.small)
                    Button(model.display.localized("停止")) { importTask?.cancel() }
                } else if model.isBusy {
                    ProgressView().controlSize(.small)
                    Button(model.display.localized("停止")) { Task { await model.cancel() } }
                } else {
                    Spacer()
                    Button(model.display.localized("取消")) { dismiss() }.keyboardShortcut(.cancelAction)
                    Button(model.display.localized("描く")) {
                        Task { if await model.drawNewDDL(draft, imported: importedDocument) { dismiss() } }
                    }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                        .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }.padding(16)
        }
        #if os(macOS)
        .frame(minWidth: 620, idealWidth: 800, minHeight: 480, idealHeight: 620)
        #endif
        .interactiveDismissDisabled(model.isBusy || importing)
        .task {
            let settings = await model.hostSettings()
            drawingModel = SettingsModel.isBatchModelAvailable(settings.models.stage2Model, settings: settings) ? settings.models.stage2Model : ""
        }
        .sheet(isPresented: $showModels) {
            BatchModelPickerView(model: model, initialReference: drawingModel, immediateSelection: true, title: "描画モデル") { reference in
                try await model.selectDdlDrawingModel(reference)
                drawingModel = reference
            }
        }
        .sheet(isPresented: $showSaijiki) {
            VStack(spacing: 0) {
                HStack { Spacer(); Button(model.display.localized("閉じる")) { showSaijiki = false } }.padding(12)
                SaijikiView(model: model, onInsertWord: { insertion = InkuEditorInsertion(text: $0) },
                            wordLanguage: model.instructionLanguage(for: draft))
            }.frame(minWidth: 560, minHeight: 620)
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
