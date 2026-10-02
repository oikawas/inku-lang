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
    private(set) var message = ""
    @ObservationIgnored private var operation: Task<Void, Never>?

    func read(app model: AppModel) {
        guard !isReading, !model.isBusy else { return }
        let panel = NSOpenPanel()
        panel.title = model.display.localized("DDLファイルを読み込む")
        panel.allowedContentTypes = [.json, .plainText, .text]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        isReading = true
        defer { if operation == nil { isReading = false } }
        guard panel.runModal() == .OK, let url = panel.url else { return }
        model.errorText = nil
        operation = Task { @MainActor in
            defer { self.isReading = false; self.operation = nil }
            do {
                let worker = Task.detached(priority: .userInitiated) { try DDLPackageImport.read(url: url) }
                let imported = try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
                try Task.checkCancellation()
                try model.applyDDLImport(imported)
                self.message = imported.names.isEmpty ? "DDLを読み込みました。" : "この新しい作品に定義を持ち込みます: " + imported.names.joined(separator: ", ")
            } catch is CancellationError { self.message = "読み込みを中止しました。" }
            catch {
                if let failure = error as? HostError {
                    switch failure.code {
                    case "ddl_import_too_large": model.errorText = model.display.localized("DDLファイルは4MiB以下で読み込んでください。")
                    case "ddl_import_invalid_utf8": model.errorText = model.display.localized("UTF-8のテキストファイルを選択してください。")
                    case "ddl_export_without_ddl": model.errorText = model.display.localized("このDDL packageには指示書がありません。")
                    case "ddl_export_too_many_plugins": model.errorText = model.display.localized("持ち込めるプラグイン定義は64件までです。")
                    case "ddl_export_invalid_plugin", "imported_macro_catalog_incomplete": model.errorText = model.display.localized("プラグイン定義を確認できませんでした。元の作品からもう一度書き出してください。")
                    case "authoring_busy": model.errorText = model.display.localized("描画が完了してから読み込んでください。")
                    default: model.errorText = model.display.localizedFormat("DDLファイルを読み込めませんでした: %@", failure.localizedDescription)
                    }
                } else { model.errorText = error.localizedDescription }
            }
        }
    }

    func cancel() { operation?.cancel() }
}

@MainActor
struct DDLImportButton: View {
    @Bindable var model: AppModel
    @Environment(DDLImportController.self) private var importer
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button(model.display.localized(importer.isReading ? "読み込んでいます…" : "DDLファイルを読み込む…"), systemImage: "doc.badge.arrow.up") { importer.read(app: model) }
                .disabled(importer.isReading || model.isBusy)
            if !importer.message.isEmpty { Text(model.display.message(importer.message)).font(.caption).foregroundStyle(.secondary) }
        }
    }
}
#endif
