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
        removeExpiredShareFiles()
        return temporaryFile(named: name)
    }

    static func backup(language: String = "ja") -> URL? {
        temporaryFile(named: "inku-backup.sqlite")
    }

    /// Hands files written to `exportFile` or `backup` on, with `share`, through
    /// the share sheet (Photos, Files, AirDrop); otherwise moves them and removes the temporary folder. Nil
    /// when the author cancels or nothing was written. Other URLs (a chosen folder, the default destination) are
    /// returned as is.
    static func handOff(_ urls: [URL], dialogs: InkuFileDialogs?, share: Bool = false) async -> [URL]? {
        let folders = Set(urls.map { $0.deletingLastPathComponent().standardizedFileURL }.filter { isTemporaryFolder($0, prefix: exportPrefix) })
        guard !folders.isEmpty else { return urls }
        func cleanup() { for folder in folders { try? FileManager.default.removeItem(at: folder) } }
        let written = urls.filter { FileManager.default.fileExists(atPath: $0.path) }
        guard !written.isEmpty else { cleanup(); return nil }
        if share {
            return await InkuShareSheet.present(written) ? written : nil
        }
        defer { cleanup() }
        guard let dialogs else { return nil }
        return await dialogs.move(written)
    }

    private static let exportPrefix = "inku-export-"
    private static let shareCardPrefix = "inku-phone-share-"
    private static let minimumRetention: TimeInterval = 30 * 60
    private static var activeShares: [URL: Int] = [:]

    static func beginSharing(_ urls: [URL]) -> Set<URL> {
        let folders = Set(urls.map { $0.deletingLastPathComponent().standardizedFileURL })
        for folder in folders { activeShares[folder, default: 0] += 1 }
        removeExpiredShareFiles()
        return folders
    }

    static func endSharing(_ folders: Set<URL>) {
        for folder in folders {
            if let count = activeShares[folder], count > 1 {
                activeShares[folder] = count - 1
            } else {
                activeShares.removeValue(forKey: folder)
            }
        }
    }

    static func removeExpiredShareFiles() {
        let files = FileManager.default
        let cutoff = Date().addingTimeInterval(-minimumRetention)
        let keys: Set<URLResourceKey> = [.isDirectoryKey, .isSymbolicLinkKey, .creationDateKey]
        let root = files.temporaryDirectory.standardizedFileURL
        guard let entries = try? files.contentsOfDirectory(at: root, includingPropertiesForKeys: Array(keys)) else { return }
        for entry in entries {
            let folder = entry.standardizedFileURL
            guard activeShares[folder] == nil,
                  isTemporaryFolder(folder, prefix: exportPrefix) || isTemporaryFolder(folder, prefix: shareCardPrefix),
                  let values = try? entry.resourceValues(forKeys: keys),
                  values.isDirectory == true, values.isSymbolicLink != true,
                  let created = values.creationDate, created <= cutoff else { continue }
            try? files.removeItem(at: folder)
        }
    }

    static func shareCard(named name: String) throws -> URL {
        try makeTemporaryFile(named: name, prefix: shareCardPrefix)
    }

    private static func temporaryFile(named name: String) -> URL? {
        try? makeTemporaryFile(named: name.isEmpty ? "inku-export" : name, prefix: exportPrefix)
    }

    private static func makeTemporaryFile(named name: String, prefix: String) throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(prefix + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder.appendingPathComponent(name)
    }

    private static func isTemporaryFolder(_ folder: URL, prefix: String) -> Bool {
        folder.lastPathComponent.hasPrefix(prefix)
            && UUID(uuidString: String(folder.lastPathComponent.dropFirst(prefix.count))) != nil
            && folder.deletingLastPathComponent().standardizedFileURL.path == FileManager.default.temporaryDirectory.standardizedFileURL.path
    }
}
#endif
