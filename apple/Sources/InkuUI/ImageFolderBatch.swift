import Foundation
import Observation
import CryptoKit
import InkuHost

private struct ImageFolderRow: Codable, Identifiable, Sendable {
    var id: String { path }
    var path: String
    var size: UInt64
    var modified: Double
    var state = "waiting"
    var workID: String?
    var error: String?
}
private struct ImageFolderJournal: Codable, Sendable {
    var folder: String
    var rows: [ImageFolderRow]
}

@MainActor @Observable final class ImageFolderBatch {
    private let imagePreparer: @Sendable (URL) throws -> PreparedImageInput
    private var journal: ImageFolderJournal?
    private var journalURL: URL?
    private(set) var folder = ""
    private(set) var total = 0
    private(set) var completed = 0
    private(set) var failed = 0
    private(set) var uncertain = 0
    private(set) var failures: [String] = []
    private(set) var running = false
    private(set) var drawing = false
    private(set) var selecting = false
    private(set) var status = ""
    private(set) var error: String?
    private var stopRequested = false
    var hasJournal: Bool { journal != nil }

    func clearSelection() {
        guard !running, !selecting else { return }
        journal = nil; journalURL = nil; folder = ""; total = 0; completed = 0
        failed = 0; uncertain = 0; failures = []; status = ""; error = nil
    }
    func newWork(app: AppModel) {
        guard !running, !selecting, !app.isBusy else { return }
        clearSelection()
        app.newWork(resetTab: "batch_image")
    }

    init() { imagePreparer = { try Self.prepareImage(at: $0) } }
    init(imagePreparer: @escaping @Sendable (URL) throws -> PreparedImageInput) { self.imagePreparer = imagePreparer }

    func select(_ url: URL, app: AppModel) async throws {
        guard !running, !selecting, let root = app.localDataDirectory() else { throw HostError("batch_journal_unavailable") }
        selecting = true
        defer { selecting = false }
        let (loaded, journalURL) = try await Task.detached(priority: .userInitiated) {
            try Self.scan(url, root: root)
        }.value
        try Task.checkCancellation()
        self.journalURL = journalURL
        journal = loaded
        self.folder = loaded.folder; error = nil; refresh()
        try await persist()
    }

    private nonisolated static func scan(_ url: URL, root: URL) throws -> (ImageFolderJournal, URL) {
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
            // Keep the first saved row for a key, matching the old linear search.
            struct Identity: Hashable { let path: String; let size: UInt64; let modified: Double }
            var previousRows: [Identity: ImageFolderRow] = [:]
            for previous in saved.rows {
                let key = Identity(path: previous.path, size: previous.size, modified: previous.modified)
                if previousRows[key] == nil { previousRows[key] = previous }
            }
            for index in rows.indices {
                let row = rows[index]
                if let previous = previousRows[Identity(path: row.path, size: row.size, modified: row.modified)] {
                    rows[index] = previous
                    if rows[index].state == "running" { rows[index].state = "uncertain" }
                }
            }
        }
        return (ImageFolderJournal(folder: folder, rows: rows), journalURL)
    }

    func run(app: AppModel, restart: Bool, provenance: @escaping @MainActor (URL) -> String) async {
        guard !running, !selecting, var current = journal else { return }
        if restart {
            for index in current.rows.indices { current.rows[index].state = "waiting"; current.rows[index].workID = nil; current.rows[index].error = nil }
        } else {
            for index in current.rows.indices where current.rows[index].state == "failed" {
                current.rows[index].state = "waiting"; current.rows[index].error = nil
            }
        }
        journal = current
        let options = app.drawSelections["batch_image"]
        running = true; stopRequested = false; error = nil
        defer { running = false; drawing = false; refresh() }
        do {
            try await persist()
            for index in current.rows.indices {
                guard !stopRequested, !Task.isCancelled else { break }
                guard journal?.rows[index].state == "waiting" else { continue }
                journal?.rows[index].state = "running"; try await persist()
                if stopRequested || Task.isCancelled {
                    journal?.rows[index].state = "uncertain"
                    try await persist(); refresh()
                    break
                }
                let url = URL(fileURLWithPath: current.rows[index].path)
                status = "\(index + 1) / \(current.rows.count): \(url.lastPathComponent)"
                do {
                    let values = try url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
                    guard values.fileSize.map(UInt64.init) == current.rows[index].size,
                          values.contentModificationDate?.timeIntervalSince1970 == current.rows[index].modified else {
                        throw HostError("image_changed")
                    }
                    guard current.rows[index].size <= UInt64(ImageInput.maximumRawBytes) else { throw HostError("image_too_large") }
                    let imagePreparer = self.imagePreparer
                    let image = try await Task.detached(priority: .userInitiated) {
                        try imagePreparer(url)
                    }.value
                    let after = try url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
                    guard after.fileSize.map(UInt64.init) == current.rows[index].size,
                          after.contentModificationDate?.timeIntervalSince1970 == current.rows[index].modified else {
                        throw HostError("image_changed")
                    }
                    // Preparation can now yield to Stop. Do not start a provider
                    // request after a stop arrived while the image was decoded.
                    guard !stopRequested, !Task.isCancelled else { throw CancellationError() }
                    let request = try app.requestForImage(image, provenance: provenance(url), options: options)
                    let pinned = try await app.pinPersonalPlanRequests([request])[0]
                    drawing = true
                    let work = await app.runAutomation(request: pinned, image: image, background: true)
                    drawing = false
                    if stopRequested || Task.isCancelled { journal?.rows[index].state = "uncertain" }
                    else if let work { journal?.rows[index].state = "succeeded"; journal?.rows[index].workID = work.id }
                    else { journal?.rows[index].state = "failed"; journal?.rows[index].error = app.automationFailureMessage ?? "生成できませんでした。" }
                } catch {
                    journal?.rows[index].state = stopRequested || Task.isCancelled ? "uncertain" : "failed"
                    journal?.rows[index].error = app.failureMessage(error)
                }
                try await persist(); refresh()
            }
            status = stopRequested ? "停止しました。" : "画像フォルダの処理が終わりました。"
        } catch { self.error = error.localizedDescription }
    }
    func stop(app: AppModel) async { stopRequested = true; await app.cancel() }
    private nonisolated static func prepareImage(at url: URL) throws -> PreparedImageInput {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var raw = Data()
        let maximum = ImageInput.maximumRawBytes
        while raw.count <= maximum {
            let chunk = try handle.read(upToCount: min(1024 * 1024, maximum + 1 - raw.count)) ?? Data()
            if chunk.isEmpty { break }
            raw.append(chunk)
        }
        guard raw.count <= maximum else { throw HostError("image_too_large") }
        return try ImageInput.prepare(raw)
    }
    private func persist() async throws {
        guard let journal, let journalURL else { throw HostError("batch_journal_unavailable") }
        // Each write is awaited before the next transition or provider request.
        try await Task.detached(priority: .utility) {
            try JSONEncoder().encode(journal).write(to: journalURL, options: .atomic)
        }.value
    }
    private func refresh() {
        let rows = journal?.rows ?? []
        var succeeded = 0, failureCount = 0, uncertainCount = 0
        var messages: [String] = []
        for row in rows {
            switch row.state {
            case "succeeded": succeeded += 1
            case "failed":
                failureCount += 1
                messages.append(URL(fileURLWithPath: row.path).lastPathComponent + ": " + (row.error ?? ""))
            case "uncertain": uncertainCount += 1
            default: break
            }
        }
        total = rows.count; completed = succeeded; failed = failureCount
        uncertain = uncertainCount; failures = messages
    }
}
