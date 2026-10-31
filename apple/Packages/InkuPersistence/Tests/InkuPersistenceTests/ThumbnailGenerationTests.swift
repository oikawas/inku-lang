import Foundation
import Testing
@testable import InkuPersistence

struct ThumbnailGenerationTests {
    @Test func staleRestoreWorkCannotOverwriteOrDeleteNewThumbnail() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-thumb-generation-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = try ThumbnailStore(url: folder.appendingPathComponent("thumbs.sqlite"))
        await store.advanceWriteGeneration(to: 2)
        #expect(try await store.putIfCurrent(historyID: "one", scale: 2, png: Data([2]), sourceRenderHash: "new", generation: 2))
        await store.advanceWriteGeneration(to: 1)
        #expect(try await !store.putIfCurrent(historyID: "one", scale: 2, png: Data([1]), sourceRenderHash: "old", generation: 1))
        #expect(try await store.deleteIfCurrent(historyIDs: ["one"], generation: 1) == 0)
        let cancelled = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            return try await store.putIfCurrent(historyID: "one", scale: 2, png: Data([3]), sourceRenderHash: "cancelled", generation: 2)
        }
        await #expect(throws: CancellationError.self) { try await cancelled.value }
        let kept = try await store.thumbnail(historyID: "one", scale: 2)
        #expect(kept?.sourceRenderHash == "new")
        #expect(kept?.png == Data([2]))
    }
}
