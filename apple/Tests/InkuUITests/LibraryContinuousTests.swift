import Foundation
import InkuPersistence
import XCTest
@testable import InkuUI

/// The iPhone's library scrolls through every work (author 2026-11-13): the timeline reads on as the end nears, and a
/// read again keeps what was listed.
@MainActor final class LibraryContinuousTests: XCTestCase {
    func testContinuousTimelineReadsOnToTheEndAndKeepsItOnARead() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-library-continuous-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let database = try InkuDatabase(url: root.appendingPathComponent("works.sqlite"))
        let count = LibraryModel.continuousChunk + 5
        for index in 0..<count {
            let work = SavedWork(id: "work-\(index)", at: Int64(index + 1), input: "work \(index)", score: "{}", svg: "<svg/>",
                                 lineageNodeID: "node-\(index)")
            try await database.save(work, node: LineageNode(id: "node-\(index)", historyID: work.id, at: work.at))
        }
        let library = LibraryModel()
        await library.connect(database: database)
        library.continuous = true
        await library.refresh()
        XCTAssertEqual(library.total, count)
        XCTAssertEqual(library.works.count, LibraryModel.continuousChunk)
        XCTAssertEqual(library.works.first?.id, "work-\(count - 1)", "newest first")

        await library.loadMore()
        XCTAssertEqual(library.works.count, count)
        XCTAssertEqual(library.works.last?.id, "work-0")
        XCTAssertEqual(Set(library.works.map(\.id)).count, count)
        await library.loadMore()
        XCTAssertEqual(library.works.count, count, "nothing past the end")

        // A read again (a star, a deletion elsewhere) keeps every listed work, so the scroll stays where it was.
        await library.refresh()
        XCTAssertEqual(library.works.count, count)

        // The paged timeline is untouched by the continuous size.
        library.continuous = false
        await library.refresh()
        XCTAssertEqual(library.works.count, library.pageSize)
    }
}
