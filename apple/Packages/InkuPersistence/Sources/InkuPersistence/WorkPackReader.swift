import Foundation
import InkuCore
import GRDB
import OSLog

public enum WorkPackError: Error, LocalizedError {
    case invalid(String)
    case newerVersion
    case tooLarge
    public var errorDescription: String? { message(language: "ja") }

    public func message(language: String) -> String {
        switch self {
        case .newerVersion:
            return language == "en" ? "This file was exported by a newer version of inku. Update the app."
                : "新しい inku で書き出したファイルです。アプリを更新してください。"
        case .tooLarge:
            return language == "en" ? "The work pack is too large." : "作品パックが大きすぎます。"
        case .invalid(let reason):
            Logger(subsystem: "app.inku", category: "work-pack").error("Invalid work pack: \(reason, privacy: .public)")
            return language == "en" ? "The work pack is damaged." : "作品パックが壊れています。"
        }
    }
}

/// Validates one bounded line at a time and holds payloads in a temporary SQLite database.
public final class WorkPackReader: @unchecked Sendable {
    let queue: DatabaseQueue
    private let temporaryURL: URL
    private(set) var records: [WorkPackRecordIdentity] = []
    public private(set) var counts: [String: Int] = [:]
    private var expectedCounts: [String: Int] = [:]

    public init(url: URL) throws {
        temporaryURL = FileManager.default.temporaryDirectory.appendingPathComponent("inku-workpack-\(UUID().uuidString).sqlite")
        queue = try DatabaseQueue(path: temporaryURL.path)
        do {
            try queue.write { db in
                try db.execute(sql: "CREATE TABLE records (kind TEXT NOT NULL, key TEXT NOT NULL, payload BLOB NOT NULL)")
            }
            try read(url)
        } catch {
            try? queue.close(); try? FileManager.default.removeItem(at: temporaryURL)
            throw error
        }
    }
    deinit { try? queue.close(); try? FileManager.default.removeItem(at: temporaryURL) }

    private func read(_ url: URL) throws {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var buffer = Data(), total = 0, lineNumber: UInt64 = 0
        let decoder = JSONDecoder()
        func accept(_ line: Data) throws {
            lineNumber += 1
            let response = try decoder.decode(WorkPackResponse.self, from: InkuCore.workpackReadLine(line, lineNumber: lineNumber))
            switch response.outcome {
            case "header":
                guard let counts = response.counts else { throw WorkPackError.invalid("header") }
                expectedCounts = counts
            case "record":
                guard let kind = response.kind, let key = response.key, let identity = response.identity else {
                    throw WorkPackError.invalid("record")
                }
                try queue.write { db in
                    try db.execute(sql: "INSERT INTO records VALUES (?, ?, ?)", arguments: [kind, key, line])
                }
                records.append(.init(kind: kind, key: key, identity: identity))
                counts[kind, default: 0] += 1
            case "unknown_kind": break
            default: throw response.error
            }
        }
        while let chunk = try handle.read(upToCount: 65536), !chunk.isEmpty {
            total += chunk.count
            guard total <= 256 * 1024 * 1024 else { throw WorkPackError.tooLarge }
            let previousEnd = buffer.endIndex
            buffer.append(chunk)
            var start = buffer.startIndex
            var search = previousEnd
            while let newline = buffer.range(of: Data([10]), in: search..<buffer.endIndex) {
                try accept(Data(buffer[start..<newline.lowerBound]))
                start = newline.upperBound
                search = start
            }
            buffer.removeSubrange(buffer.startIndex..<start)
            // Keep an unfinished line bounded before handing it to core.
            guard buffer.count <= 64 * 1024 * 1024 else { throw WorkPackError.tooLarge }
        }
        guard buffer.isEmpty, lineNumber > 0 else { throw WorkPackError.invalid("truncated line") }
        _ = try plan()
        try queue.write { db in
            try db.execute(sql: "CREATE UNIQUE INDEX records_kind_key ON records(kind,key)")
        }
    }

    func plan(existing: WorkPackExisting = .init()) throws -> WorkPackDecision {
        // Counts in this request are those declared by the header, not a recount of staged rows.
        try WorkPackWire.plan(counts: expectedCounts, records: records, existing: existing)
    }
}
