#if os(iOS)
import Foundation
import UniformTypeIdentifiers

/// The save destinations the app's own code writes to (Platform/macOS has the panels). iOS has no save panel for a
/// file the app writes itself, so the code writes into a fresh temporary folder and `handOff` then lets the author
/// move it out with the Files mover (iOS plan §3 #6).
@MainActor
enum NativeFilePanels {
    /// One work's export file, in a new temporary folder.
    static func exportFile(title: String, type: UTType, name: String) -> URL? {
        temporaryFile(named: name)
    }

    static func backup(language: String = "ja") -> URL? {
        temporaryFile(named: "inku-backup.sqlite")
    }

    /// Moves files written to `exportFile` or `backup` where the author chooses, then removes their temporary
    /// folder; nil when the author cancels or nothing was written. Other URLs (a chosen folder, the default
    /// destination) are returned as is.
    static func handOff(_ urls: [URL], dialogs: InkuFileDialogs?) async -> [URL]? {
        let folders = Set(urls.map { $0.deletingLastPathComponent().standardizedFileURL }.filter(isTemporaryFolder))
        guard !folders.isEmpty else { return urls }
        defer { for folder in folders { try? FileManager.default.removeItem(at: folder) } }
        let written = urls.filter { FileManager.default.fileExists(atPath: $0.path) }
        guard let dialogs, !written.isEmpty else { return nil }
        return await dialogs.move(written)
    }

    private static let prefix = "inku-export-"

    private static func temporaryFile(named name: String) -> URL? {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(prefix + UUID().uuidString, isDirectory: true)
        do { try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true) } catch { return nil }
        return folder.appendingPathComponent(name.isEmpty ? "inku-export" : name)
    }

    private static func isTemporaryFolder(_ folder: URL) -> Bool {
        folder.lastPathComponent.hasPrefix(prefix)
            && folder.deletingLastPathComponent().standardizedFileURL.path == FileManager.default.temporaryDirectory.standardizedFileURL.path
    }
}
#endif
