import InkuHost
import SwiftUI
#if os(macOS)
import AppKit
import UniformTypeIdentifiers

@MainActor
struct DDLImportButton: View {
    @Bindable var model: AppModel
    @State private var isReading = false
    @State private var message = ""
    @State private var error: String?
    @State private var operation: Task<Void, Never>?
    var body: some View {
        HStack {
            Button(model.display.localized(isReading ? "読み込んでいます…" : "DDLファイルを読み込む…")) { read() }
                .disabled(isReading || model.isBusy)
            if !message.isEmpty { Text(model.display.message(message)).font(.caption).foregroundStyle(.secondary) }
        }
        .alert(model.display.localized("DDLを読み込めませんでした"), isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) {
            Button(model.display.localized("閉じる"), role: .cancel) { error = nil }
        } message: { Text(error ?? "") }
        .onDisappear { operation?.cancel() }
    }
    private func read() {
        let panel = NSOpenPanel()
        panel.title = model.display.localized("DDLファイルを読み込む")
        panel.allowedContentTypes = [.json, .plainText, .text]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        isReading = true; error = nil
        operation = Task { @MainActor in
            defer { isReading = false; operation = nil }
            do {
                let worker = Task.detached(priority: .userInitiated) { try DDLPackageImport.read(url: url) }
                let imported = try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
                try Task.checkCancellation()
                try model.applyDDLImport(imported)
                message = imported.names.isEmpty ? "DDLを読み込みました。" : "この新しい作品に定義を持ち込みます: " + imported.names.joined(separator: ", ")
            } catch is CancellationError { message = "読み込みを中止しました。" }
            catch {
                if let failure = error as? HostError {
                    switch failure.code {
                    case "ddl_import_too_large": self.error = model.display.localized("DDLファイルは4MiB以下で読み込んでください。")
                    case "ddl_import_invalid_utf8": self.error = model.display.localized("UTF-8のテキストファイルを選択してください。")
                    case "ddl_export_without_ddl": self.error = model.display.localized("このDDL packageには指示書がありません。")
                    case "ddl_export_too_many_plugins": self.error = model.display.localized("持ち込めるプラグイン定義は64件までです。")
                    case "ddl_export_invalid_plugin", "imported_macro_catalog_incomplete": self.error = model.display.localized("プラグイン定義を確認できませんでした。元の作品からもう一度書き出してください。")
                    case "authoring_busy": self.error = model.display.localized("描画が完了してから読み込んでください。")
                    default: self.error = model.display.localizedFormat("DDLファイルを読み込めませんでした: %@", failure.localizedDescription)
                    }
                } else { self.error = error.localizedDescription }
            }
        }
    }
}
#endif
