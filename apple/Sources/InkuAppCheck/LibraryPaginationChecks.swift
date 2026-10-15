import Foundation
import InkuPersistence
import InkuUI

@MainActor
func runLibraryPaginationChecks() async throws {
    // Failure: omitting list SVG loses size, serves an empty/wrong drawing on cache miss,
    // or hands an incomplete record to a work action. Paging also reloaded an unrelated tree.
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-library-page-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    let works = [
        SavedWork(id: "page-a", at: 2, input: "春A", score: "{}",
                  svg: "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"100\" height=\"50\"><rect width=\"100\" height=\"50\" fill=\"red\"/><!--春--></svg>",
                  ddl: "A", renderHash: "a", lineageNodeID: "node-a"),
        SavedWork(id: "page-b", at: 1, input: "秋B", score: "{}",
                  svg: "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"50\" height=\"100\"><rect width=\"50\" height=\"100\" fill=\"blue\"/></svg>",
                  ddl: "B", renderHash: "b", lineageNodeID: "node-b")
    ]
    for work in works {
        try await database.save(work, node: LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at))
    }
    try await database.setAnnotation(id: works[0].id, note: "A note")
    let page = try await database.libraryPage(limit: 2, includeSVG: false)
    guard page.total == 2, page.items.map(\.id) == works.map(\.id) else { throw CheckFailure.message("Lightweight page order/count changed") }
    for (item, full) in zip(page.items, works) {
        var expected = full; expected.svg = ""
        guard item.work == expected, item.svgBytes == Int64(full.svg.utf8.count) else {
            throw CheckFailure.message("Lightweight list lost metadata or UTF-8 byte size")
        }
    }
    let grouped = try await database.libraryGroups(limit: 2, includeSVG: false)
    guard grouped.groups.map(\.representative) == page.items else {
        throw CheckFailure.message("Grouped representatives lost the lightweight projection")
    }
    let store = try ThumbnailStore(url: folder.appendingPathComponent("thumbs.sqlite"))
    let baked = ArtworkThumbnails()
    await baked.connect(store: store, database: database)
    _ = try await baked.image(for: works[0])
    let next = ArtworkThumbnails()
    await next.connect(store: store, database: database)
    let cached = try await next.image(for: page.items[0].work)
    let missing = try await next.image(for: page.items[1].work)
    let stats = await next.currentStatistics()
    guard cached.width == 512, cached.height == 256, missing.width == 512, missing.height == 1024,
          stats.storeHits == 1, stats.bakedOnDisplay == 1, stats.failed == 0 else {
        throw CheckFailure.message("Light list did not use PNG / fetch precisely the missing drawing: \(stats)")
    }
    let reader = PaginationLineageReader(database: database)
    let history = LibraryModel()
    await history.connect(database: database)
    guard history.works == works else {
        throw CheckFailure.message("The history strip's full-record listing contract changed")
    }
    let library = LibraryModel(lineageReader: reader, includeListSVG: false)
    library.pageSize = 1
    await library.connect(database: database)
    await library.loadLineage(work: works[0])
    let reads = await reader.reads
    await library.setPage(1)
    guard library.errorText == nil, library.works.first?.id == works[1].id, library.works.first?.svg == "",
          library.svgSizes[works[1].id] == Int64(works[1].svg.utf8.count),
          try await library.fullWork(id: works[1].id) == works[1], await reader.reads == reads else {
        throw CheckFailure.message("Paging lost its target or reloaded the background lineage")
    }
    await library.refresh()
    guard await reader.reads > reads, try await database.list() == works else {
        throw CheckFailure.message("Explicit refresh stopped updating lineage or browsing changed saved work")
    }
    print("Library pagination passed: SVG-free list retains UTF-8 size/metadata; PNG hit1, missing drawing1; exact full action target; paging lineage reads0, explicit refresh reloads; history unchanged.")
}

private actor PaginationLineageReader: LineageReading {
    let database: InkuDatabase
    private(set) var reads = 0
    init(database: InkuDatabase) { self.database = database }
    func read(focusNodeID: String, depth: Int, pathOnly: Bool) async throws -> LineageGraph? {
        reads += 1
        return try await database.lineage(focusNodeID: focusNodeID, descendantDepth: depth, pathOnly: pathOnly)
    }
    func readBranch(nodeID: String) async throws -> LineageGraph? { try await read(focusNodeID: nodeID, depth: 1, pathOnly: false) }
    func readOverview(focusNodeID: String) async throws -> LineageGraph? { try await read(focusNodeID: focusNodeID, depth: 200, pathOnly: false) }
}

/// Use a disposable Backup API copy, never the author's live canonical database.
@MainActor
func runLibraryPaginationBenchmark(url: URL) async throws {
    let database = try InkuDatabase(url: url)
    let store = try ThumbnailStore(url: ThumbnailStore.url(besideDatabase: url))
    print("offset,include_svg,median_list_ms,svg_bytes_copied,thumbnail_ms,store_hits,memory_hits,baked")
    for offset in [0, 56, 112, 168] {
        for includeSVG in [true, false] {
            var times: [Double] = []
            var items: [InkuPersistence.LibraryItem] = []
            for _ in 0..<7 {
                let start = ContinuousClock.now
                items = try await database.libraryPage(limit: 56, offset: offset, includeSVG: includeSVG).items
                times.append(milliseconds(start.duration(to: .now)))
            }
            let thumbnails = ArtworkThumbnails()
            await thumbnails.connect(store: store, database: database)
            let start = ContinuousClock.now
            try await withThrowingTaskGroup(of: Void.self) { group in
                for item in items { group.addTask { _ = try await thumbnails.image(for: item.work) } }
                try await group.waitForAll()
            }
            let elapsed = milliseconds(start.duration(to: .now))
            let stats = await thumbnails.currentStatistics()
            print("\(offset),\(includeSVG),\(times.sorted()[3]),\(items.reduce(0) { $0 + $1.work.svg.utf8.count }),\(elapsed),\(stats.storeHits),\(stats.memoryHits),\(stats.bakedOnDisplay)")
        }
    }
}

private func milliseconds(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1000 + Double(duration.components.attoseconds) / 1e15
}
