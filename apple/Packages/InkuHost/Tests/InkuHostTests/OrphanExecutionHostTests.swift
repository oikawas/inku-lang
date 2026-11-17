import Foundation
import SQLite3
import Testing
import InkuPersistence
@testable import InkuHost

struct OrphanExecutionHostTests {
    @Test func discardedCandidateCannotBeSaved() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-host-cleanup-\(UUID())")
        defer { try? FileManager.default.removeItem(at: folder) }
        let database = try InkuDatabase(url: folder.appendingPathComponent("db.sqlite"))
        let host = PipelineHost(database: database)
        _ = try await database.compareAndSwapExecution(id: "gone", expectedRevision: nil, snapshot: Data("{}".utf8))
        #expect(try await host.discardUnsavedExecution(id: "gone") == .discarded)
        do { _ = try await host.saveCandidate(executionID: "gone"); Issue.record("saved a deleted candidate") }
        catch let error as HostError { #expect(error.code == "candidate_not_found") }
        #expect(try await database.list().isEmpty)
    }

    @Test func readingWhileDiscardIsWaitingReturnsBusy() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-host-busy-\(UUID())")
        defer { try? FileManager.default.removeItem(at: folder) }
        let url = folder.appendingPathComponent("db.sqlite"), database = try InkuDatabase(url: url)
        let host = PipelineHost(database: database)
        _ = try await database.compareAndSwapExecution(id: "waiting", expectedRevision: nil, snapshot: Data("{}".utf8))
        var connection: OpaquePointer?
        #expect(sqlite3_open(url.path, &connection) == SQLITE_OK)
        defer { sqlite3_close(connection) }
        #expect(sqlite3_exec(connection, "BEGIN IMMEDIATE", nil, nil, nil) == SQLITE_OK)
        let task = Task { try await host.discardUnsavedExecution(id: "waiting") }
        for _ in 0..<1000 {
            if await host.discardingExecutionIDs.contains("waiting") { break }
            await Task.yield()
        }
        #expect(await host.discardingExecutionIDs.contains("waiting"))
        do { _ = try await host.restore(executionID: "waiting"); Issue.record("restored during discard") }
        catch let error as HostError { #expect(error.code == "busy") }
        #expect(sqlite3_exec(connection, "ROLLBACK", nil, nil, nil) == SQLITE_OK)
        #expect(try await task.value == .discarded)
    }
}
