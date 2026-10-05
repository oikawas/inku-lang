import Foundation
import GRDB
import Testing
@testable import InkuPersistence

struct PersistenceBoundaryTests {
    private func temporaryURL() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("inku-persistence-check-\(UUID().uuidString)", isDirectory: true)
            .appendingPathComponent("test.sqlite")
    }

    private func record(_ id: String, at: Int64 = 1) -> (SavedWork, LineageNode) {
        let nodeID = "node-\(id)"
        let work = SavedWork(
            id: id, at: at, input: "  original\r\ntext  ", score: "{ \"unknown\": [1, null] }",
            svg: "<svg> canonical\r\n </svg>", ddl: "\u{200B}\r\n circle:  one  ",
            renderSeed: "18446744073709551615", compositionSeed: "0007",
            variationSeed: "0", composeFallback: nil, sketchState: "unknown_future_value",
            renderHash: "rh3:opaque-same", descriptionHash: "dh1:opaque", lineageNodeID: nodeID)
        return (work, LineageNode(id: nodeID, historyID: id, at: at, renderHash: work.renderHash))
    }

    @Test func historyCollisionHashAndLineageRollback() async throws {
        let url = temporaryURL()
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        let database = try InkuDatabase(url: url)
        let (first, firstNode) = record("first")
        try await database.save(first, node: firstNode)
        #expect(try await database.work(id: first.id) == first)
        #expect(try await database.work(id: first.id)?.sourceText == nil)
        #expect(first.effectiveSourceText == first.input)
        var collision = first
        collision.svg = "must not overwrite"
        await #expect(throws: (any Error).self) { try await database.save(collision, node: firstNode) }
        #expect(try await database.work(id: first.id) == first)

        let (second, secondNode) = record("second", at: 2)
        try await database.save(second, node: secondNode)
        #expect(try await database.list().map(\.id) == ["second", "first"])

        let (bad, badNode) = record("bad")
        let selfEdge = LineageEdge(id: "bad-edge", parentNodeID: badNode.id, childNodeID: badNode.id,
                                   derivationKind: "replay", at: 3)
        await #expect(throws: (any Error).self) { try await database.save(bad, node: badNode, edge: selfEdge) }
        #expect(try await database.work(id: bad.id) == nil)
        #expect(try await database.node(id: badNode.id) == nil)
    }

    @Test func ddlSelectionPreservesExactTextAndHistoricalNull() {
        let expanded = "  circle: one\r\n"
        #expect(DDLSource.select(ddl: "\u{2028}\u{3000}", legacyExpanded: expanded).ddl == expanded)
        #expect(DDLSource.select(ddl: "\u{2028}\u{3000}", legacyExpanded: expanded).origin == "legacy_expanded")
        #expect(DDLSource.select(ddl: "\u{200B}", legacyExpanded: expanded).ddl == "\u{200B}")
        #expect(DDLSource.select(ddl: nil, legacyExpanded: "\t ").ddl == nil)
        #expect(DDLSource.select(ddl: " \r\n", legacyExpanded: nil).ddl == " \r\n")
    }

    @Test func atomicEffectRetryAndStaleRevision() async throws {
        let url = temporaryURL()
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        let database = try InkuDatabase(url: url)
        let initial = try await database.compareAndSwapExecution(id: "execution", expectedRevision: nil,
                                                                 snapshot: Data([0, 255]))
        #expect(initial.revision == 0)
        let (work, node) = record("effect-work")
        let committed = try await database.commitEffect(
            id: "execution", expectedRevision: 0, effectID: "save", snapshot: Data([1, 255]),
            acknowledgement: Data([2, 255]), work: work, node: node)
        #expect(committed.execution.revision == 1)
        #expect(!committed.wasAlreadyCommitted)
        let retried = try await database.commitEffect(
            id: "execution", expectedRevision: 0, effectID: "save", snapshot: Data([1, 255]),
            acknowledgement: Data([2, 255]), work: work, node: node)
        #expect(retried.wasAlreadyCommitted)
        #expect(retried.acknowledgement == committed.acknowledgement)
        #expect(try await database.list().count == 1)
        var mismatchedWork = work
        mismatchedWork.svg = "different canonical work"
        await #expect(throws: PersistenceError.effectConflict) {
            try await database.commitEffect(
                id: "execution", expectedRevision: 0, effectID: "save", snapshot: Data([1, 255]),
                acknowledgement: Data([2, 255]), work: mismatchedWork, node: node)
        }
        await #expect(throws: PersistenceError.revisionConflict) {
            try await database.compareAndSwapExecution(id: "execution", expectedRevision: 0, snapshot: Data([9]))
        }
        await #expect(throws: (any Error).self) {
            try await database.commitEffect(
                id: "execution", expectedRevision: 1, effectID: "collision", snapshot: Data([3]),
                acknowledgement: Data([4]), work: work, node: node)
        }
        #expect(try await database.loadExecution(id: "execution") == committed.execution)
        #expect(try await database.acknowledgement(executionID: "execution", effectID: "collision") == nil)
        await #expect(throws: PersistenceError.effectConflict) {
            try await database.commitEffect(
                id: "execution", expectedRevision: 0, effectID: "save", snapshot: Data([1, 255]),
                acknowledgement: Data([77]), work: work, node: node)
        }
    }

    @Test func backupIncludesWALAndRestorePreservesSource() async throws {
        let url = temporaryURL()
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        let database = try InkuDatabase(url: url)
        let journal = try DatabaseQueue(path: url.path)
        try await journal.writeWithoutTransaction { try $0.execute(sql: "PRAGMA journal_mode = WAL") }
        try journal.close()
        let (work, node) = record("before-backup")
        try await database.save(work, node: node)
        let backup = url.deletingLastPathComponent().appendingPathComponent("backup.sqlite")
        try await database.backup(to: backup)
        let originalBytes = try Data(contentsOf: backup)
        let (later, laterNode) = record("after-backup")
        try await database.save(later, node: laterNode)
        try await database.restore(from: backup)
        #expect(try await database.list() == [work])
        #expect(try Data(contentsOf: backup) == originalBytes)
        await #expect(throws: PersistenceError.backupAlreadyExists) { try await database.backup(to: backup) }
    }

    @Test func unknownSchemaFailsBeforeWriteOrRestore() async throws {
        let url = temporaryURL()
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let unknown = try DatabaseQueue(path: url.path)
        try await unknown.write { try $0.execute(sql: "CREATE TABLE future_schema (id TEXT); PRAGMA user_version = 99") }
        try unknown.close()
        let bytes = try Data(contentsOf: url)
        #expect(throws: PersistenceError.unknownSchema) { try InkuDatabase(url: url) }
        #expect(try Data(contentsOf: url) == bytes)

        let forgedVersion = try DatabaseQueue(path: url.path)
        try await forgedVersion.write { try $0.execute(sql: "PRAGMA user_version = 1") }
        try forgedVersion.close()
        let forgedBytes = try Data(contentsOf: url)
        #expect(throws: PersistenceError.unknownSchema) { try InkuDatabase(url: url) }
        #expect(try Data(contentsOf: url) == forgedBytes)

        let activeURL = url.deletingLastPathComponent().appendingPathComponent("active.sqlite")
        let active = try InkuDatabase(url: activeURL)
        let (work, node) = record("preserved")
        try await active.save(work, node: node)
        await #expect(throws: PersistenceError.unknownSchema) { try await active.restore(from: url) }
        #expect(try await active.list() == [work])
        #expect(try Data(contentsOf: url) == forgedBytes)
    }
}
