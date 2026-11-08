#if os(macOS)
import AppKit
import UniformTypeIdentifiers

/// Save panels whose chosen URL the app's own code writes to (the export writes there, the backup copies a 2.6 GB
/// database there), so SwiftUI's `fileExporter`, which writes a document it is handed, does not fit.
@MainActor
enum NativeFilePanels {
    /// One work's export file.
    static func exportFile(title: String, type: UTType, name: String) -> URL? {
        let panel = NSSavePanel(); panel.title = title
        panel.allowedContentTypes = [type]
        panel.nameFieldStringValue = name
        return panel.runModal() == .OK ? panel.url : nil
    }

    static func backup(language: String = "ja") -> URL? {
        let panel = NSSavePanel()
        panel.title = InkuLocalization.string("バックアップを保存", language: language)
        panel.allowedContentTypes = [UTType(filenameExtension: "sqlite") ?? .data]
        panel.nameFieldStringValue = "inku-backup.sqlite"
        return panel.runModal() == .OK ? panel.url : nil
    }

    /// The panels above already chose the final place (iOS writes to a temporary folder and moves it from there).
    static func handOff(_ urls: [URL], dialogs: InkuFileDialogs?) async -> [URL]? { urls }
}
#endif
