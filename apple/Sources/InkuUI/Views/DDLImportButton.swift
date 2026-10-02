import InkuHost
import Observation
import SwiftUI
#if os(macOS)
import AppKit
import UniformTypeIdentifiers

@MainActor
@Observable
final class DDLImportController {
    private(set) var isReading = false
    private(set) var isCancelling = false
    private(set) var message = ""
    @ObservationIgnored private var operation: Task<Void, Never>?
    @ObservationIgnored private var openPanel: NSOpenPanel?
    @ObservationIgnored private var importedSource: String?
    @ObservationIgnored private var importedNames: [String] = []
    @ObservationIgnored private var appliedNames: Set<String> = []

    func read(app model: AppModel, enabled: Bool = true, onImported: (@MainActor () -> Void)? = nil) {
        guard enabled, !isReading, operation == nil, !model.isBusy else { return }
        let panel = NSOpenPanel()
        panel.title = model.display.localized("DDLファイルを読み込む")
        panel.allowedContentTypes = [.json, .plainText, .text]
        panel.allowsOtherFileTypes = true
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        clearMessage()
        openPanel = panel
        isReading = true
        let response = panel.runModal()
        openPanel = nil
        isReading = false
        guard response == .OK, let url = panel.url else { return }
        _ = read(url: url, app: model, enabled: enabled, onImported: onImported)
    }

    /// Both Finder drops and the file panel enter this bounded, all-or-nothing path.
    @discardableResult
    func read(url: URL, app model: AppModel, enabled: Bool = true, onImported: (@MainActor () -> Void)? = nil) -> Bool {
        guard enabled, !isReading, operation == nil, !model.isBusy else { return false }
        guard url.isFileURL, !url.hasDirectoryPath else {
            rejectDrop(app: model)
            return false
        }
        let context = ImportContext(app: model)
        clearMessage()
        model.errorText = nil
        isReading = true
        isCancelling = false
        operation = Task { @MainActor in
            defer { self.isReading = false; self.isCancelling = false; self.operation = nil }
            do {
                // The existing reader owns the security-scoped access and checks cancellation
                // between bounded chunks, before adopting any source or definitions.
                let worker = Task.detached(priority: .userInitiated) { try DDLPackageImport.read(url: url) }
                let imported = try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
                try Task.checkCancellation()
                guard context == ImportContext(app: model) else { throw HostError("ddl_import_context_changed") }
                try model.applyDDLImport(imported)
                self.importedSource = imported.source
                self.importedNames = imported.names
                self.appliedNames = Set(model.importedMacroNames)
                self.message = imported.names.isEmpty ? "DDLを読み込みました。" : "この新しい作品に定義を持ち込みます: " + imported.names.joined(separator: ", ")
                // Navigation guards include isReading; release it before the success callback.
                self.isReading = false
                onImported?()
            } catch is CancellationError { self.message = "読み込みを中止しました。" }
            catch {
                guard !Task.isCancelled else { self.message = "読み込みを中止しました。"; return }
                if let failure = error as? HostError {
                    switch failure.code {
                    case "ddl_import_too_large": model.errorText = model.display.localized("DDLファイルは4MiB以下で読み込んでください。")
                    case "ddl_import_invalid_utf8": model.errorText = model.display.localized("UTF-8のテキストファイルを選択してください。")
                    case "ddl_export_without_ddl": model.errorText = model.display.localized("このDDL packageには指示書がありません。")
                    case "ddl_export_too_many_plugins": model.errorText = model.display.localized("持ち込めるプラグイン定義は64件までです。")
                    case "ddl_export_invalid_plugin", "imported_macro_catalog_incomplete": model.errorText = model.display.localized("プラグイン定義を確認できませんでした。元の作品からもう一度書き出してください。")
                    case "authoring_busy", "ddl_import_busy_or_unavailable": model.errorText = model.display.localized("描画の準備が完了してから読み込んでください。")
                    case "ddl_import_context_changed": model.errorText = model.display.localized("読み込み中に制作内容が変わったため、取り込みを中止しました。もう一度ファイルを選択してください。")
                    default: model.errorText = model.display.localizedFormat("DDLファイルを読み込めませんでした: %@", failure.localizedDescription)
                    }
                } else { model.errorText = model.display.localizedFormat("DDLファイルを読み込めませんでした: %@", error.localizedDescription) }
            }
        }
        return true
    }

    func rejectDrop(app model: AppModel) {
        guard !isReading else { return }
        clearMessage()
        model.errorText = model.display.localized("DDLのテキストファイルを1つドロップしてください。フォルダや複数ファイルは取り込めません。")
    }

    func cancel() {
        openPanel?.cancel(nil)
        guard let operation else { return }
        isCancelling = true
        operation.cancel()
    }

    func clearMessage() {
        message = ""; importedSource = nil; importedNames = []; appliedNames = []
    }

    func visibleMessage(app model: AppModel) -> String {
        guard let importedSource else { return message }
        guard model.selectedWorkID == nil, !model.isPreview, model.inputMode == "ddl",
              Set(model.importedMacroNames) == appliedNames else { return "" }
        // Definitions remain active while editing this draft. A plain-DDL success is
        // only useful while that imported source is still displayed.
        guard !importedNames.isEmpty || model.ddlText == importedSource else { return "" }
        return message
    }

    private struct ImportContext: Equatable {
        let workID: String?
        let previewID: String?
        let inputMode: String
        let source: String
        let description: String
        let language: String
        let revision: String
        let origin: String
        let names: [String]

        @MainActor init(app: AppModel) {
            workID = app.selectedWorkID; previewID = app.previewWork?.id
            inputMode = app.inputMode; source = app.ddlText; description = app.descriptionText
            language = app.language; revision = app.authoringRevision; origin = app.authoringOrigin
            names = app.importedMacroNames
        }
    }
}

@MainActor
struct DDLImportButton: View {
    @Bindable var model: AppModel
    @Environment(DDLImportController.self) private var importer
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button(model.display.localized(importer.isReading ? "読み込んでいます…" : "DDLファイルを読み込む…"), systemImage: "doc.badge.arrow.up") { importer.read(app: model) }
                .disabled(importer.isReading || model.isBusy)
            if !importer.visibleMessage(app: model).isEmpty {
                Text(model.display.message(importer.visibleMessage(app: model))).font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}
#endif
