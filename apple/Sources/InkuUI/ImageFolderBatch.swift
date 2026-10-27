import Foundation
import Observation
import CryptoKit
import InkuHost

private struct ImageFolderRow: Codable, Identifiable {
    var id: String { path }
    var path: String
    var size: UInt64
    var modified: Double
    var state = "waiting"
    var workID: String?
    var error: String?
}
private struct ImageFolderJournal: Codable {
    var folder: String
    var rows: [ImageFolderRow]
}

@MainActor @Observable final class ImageFolderBatch {
    private var journal: ImageFolderJournal?
    private var journalURL: URL?
    private(set) var folder = ""
    private(set) var total = 0
    private(set) var completed = 0
    private(set) var failed = 0
    private(set) var uncertain = 0
    private(set) var failures: [String] = []
    private(set) var running = false
    private(set) var status = ""
    private(set) var error: String?
    private var stopRequested = false
    var hasJournal: Bool { journal != nil }

    func select(_ url: URL, app: AppModel) throws {
        guard !running, let root = app.localDataDirectory() else { throw HostError("batch_journal_unavailable") }
        let folder = url.standardizedFileURL.path
        let folderDigest = SHA256.hash(data: Data(folder.utf8)).map { String(format: "%02x", $0) }.joined()
        let journalURL = root.appendingPathComponent("image-folder-\(folderDigest).json")
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .fileSizeKey, .contentModificationDateKey, .isHiddenKey]
        var enumerationError: Error?
        guard let enumerator = FileManager.default.enumerator(at: url, includingPropertiesForKeys: Array(keys), options: [.skipsHiddenFiles],
            errorHandler: { _, error in enumerationError = error; return false }) else {
            throw HostError("image_folder_unavailable")
        }
        let files = enumerator.compactMap { $0 as? URL }
            .filter { ["jpg", "jpeg", "png", "gif", "tif", "tiff"].contains($0.pathExtension.lowercased()) }
            .sorted { $0.path.localizedStandardCompare($1.path) == .orderedAscending }
        if let enumerationError { throw enumerationError }
        var rows = try files.compactMap { file -> ImageFolderRow? in
            let values = try file.resourceValues(forKeys: keys)
            guard values.isRegularFile == true, values.isHidden != true, let size = values.fileSize,
                  let modified = values.contentModificationDate else { return nil }
            return ImageFolderRow(path: file.standardizedFileURL.path, size: UInt64(size), modified: modified.timeIntervalSince1970)
        }
        if FileManager.default.fileExists(atPath: journalURL.path) {
            let saved = try JSONDecoder().decode(ImageFolderJournal.self, from: Data(contentsOf: journalURL))
            guard saved.folder == folder else { throw HostError("image_folder_journal_mismatch") }
            for index in rows.indices {
                if let previous = saved.rows.first(where: { $0.path == rows[index].path && $0.size == rows[index].size && $0.modified == rows[index].modified }) {
                    rows[index] = previous
                    if rows[index].state == "running" { rows[index].state = "uncertain" }
                }
            }
        }
        self.journalURL = journalURL
        journal = ImageFolderJournal(folder: folder, rows: rows)
        self.folder = folder; error = nil; refresh()
        try persist()
    }

    func run(app: AppModel, restart: Bool, provenance: @escaping @MainActor (URL) -> String) async {
        guard !running, var current = journal else { return }
        if restart {
            for index in current.rows.indices { current.rows[index].state = "waiting"; current.rows[index].workID = nil; current.rows[index].error = nil }
        } else {
            for index in current.rows.indices where current.rows[index].state == "failed" {
                current.rows[index].state = "waiting"; current.rows[index].error = nil
            }
        }
        journal = current
        running = true; stopRequested = false; error = nil
        defer { running = false; refresh() }
        do {
            try persist()
            for index in current.rows.indices {
                guard !stopRequested, !Task.isCancelled else { break }
                guard journal?.rows[index].state == "waiting" else { continue }
                journal?.rows[index].state = "running"; try persist()
                let url = URL(fileURLWithPath: current.rows[index].path)
                status = "\(index + 1) / \(current.rows.count): \(url.lastPathComponent)"
                do {
                    let values = try url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
                    guard values.fileSize.map(UInt64.init) == current.rows[index].size,
                          values.contentModificationDate?.timeIntervalSince1970 == current.rows[index].modified else {
                        throw HostError("image_changed")
                    }
                    let image = try ImageInput.prepare(Data(contentsOf: url))
                    let request = try app.requestForImage(image, provenance: provenance(url))
                    let pinned = try await app.pinPersonalPlanRequests([request])[0]
                    let work = await app.runAutomation(request: pinned, image: image, allowsBrowsing: true)
                    if stopRequested || Task.isCancelled { journal?.rows[index].state = "uncertain" }
                    else if let work { journal?.rows[index].state = "succeeded"; journal?.rows[index].workID = work.id }
                    else { journal?.rows[index].state = "failed"; journal?.rows[index].error = app.automationFailureMessage ?? "生成できませんでした。" }
                } catch {
                    journal?.rows[index].state = stopRequested || Task.isCancelled ? "uncertain" : "failed"
                    journal?.rows[index].error = app.failureMessage(error)
                }
                try persist(); refresh()
            }
            status = stopRequested ? "停止しました。" : "画像フォルダの処理が終わりました。"
        } catch { self.error = error.localizedDescription }
    }
    func stop(app: AppModel) async { stopRequested = true; await app.cancel() }
    private func persist() throws {
        guard let journal, let journalURL else { throw HostError("batch_journal_unavailable") }
        try JSONEncoder().encode(journal).write(to: journalURL, options: .atomic)
    }
    private func refresh() {
        let rows = journal?.rows ?? []
        total = rows.count; completed = rows.filter { $0.state == "succeeded" }.count
        failed = rows.filter { $0.state == "failed" }.count; uncertain = rows.filter { $0.state == "uncertain" }.count
        failures = rows.filter { $0.state == "failed" }.map { URL(fileURLWithPath: $0.path).lastPathComponent + ": " + ($0.error ?? "") }
    }
}
