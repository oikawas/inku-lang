import Foundation
import InkuHost
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
    // A menu projection must accept exactly the same complete authoring records.
    let cases: [(String, String, String, Int, SavedWorkActionState)] = [
        ("summary-description", "stage1_generated", "description_authoritative", 0, .description),
        ("summary-locked", "stage1_generated", "ddl_authoritative", 0, .lockedDescription),
        ("summary-ddl", "user_authored_ddl", "ddl_authoritative", 0, .userDDL),
        ("summary-broken", "stage1_generated", "description_authoritative", 1, .unavailable),
        ("summary-other", "stage1_generated", "description_authoritative", 2, .unavailable),
        ("summary-incomplete", "stage1_generated", "description_authoritative", 3, .unavailable),
    ]
    for (execution, origin, authority, variant, _) in cases {
        _ = try await database.compareAndSwapExecution(id: execution, expectedRevision: nil, snapshot: Data("{}".utf8))
        var performance: [String: Any] = ["configuration": ["large": String(repeating: "x", count: 65_536)],
            "options": [String: String](), "clip": [String: String](),
            "authority": ["origin": origin, "authority": authority, "revision": "1"]]
        if variant == 3 { performance["options"] = nil }
        let ack = variant == 1 ? Data("{broken".utf8) : try JSONSerialization.data(withJSONObject: [
            "work_id": variant == 2 ? "another_0" : execution + "_0", "performance": performance])
        _ = try await database.commitEffect(id: execution, expectedRevision: 0, effectID: "save-render:0",
            snapshot: Data("{}".utf8), acknowledgement: ack)
    }
    let host = PipelineHost(database: database)
    let ids = cases.map { $0.0 + "_0" } + ["missing_0", "legacy"]
    let summaries = try await host.savedAuthoringSummaries(workIDs: ids)
    for id in ids {
        if let full = try? await host.savedAuthoringContext(workID: id) {
            guard summaries[id]?.authority == full.authority, summaries[id]?.origin == full.origin else {
                throw CheckFailure.message("Menu authority projection differs from full context for \(id)")
            }
        } else if summaries[id] != nil { throw CheckFailure.message("Incomplete context became menu-eligible: \(id)") }
    }
    let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"))
    await app.initialize()
    await app.loadWorkActionStates(workIDs: ids)
    for (execution, _, _, _, expected) in cases {
        let work = SavedWork(id: execution + "_0", at: 0, input: "", score: "{}", svg: "")
        guard app.workActionState(for: work) == expected else { throw CheckFailure.message("Batched menu state changed for \(execution)") }
    }
    print("Library pagination passed: SVG-free list retains UTF-8 size/metadata; PNG hit1, missing drawing1; exact full action target; paging lineage reads0, explicit refresh reloads; history unchanged.")
    try await checkMeasuredShrink(folder: folder)
    print("Menu summaries passed: description/locked/user-DDL match full contexts; broken/mismatched/incomplete/missing/legacy records remain unavailable; page state published together.")
}

/// Failure: a shrink measured on the shown page moved its first work, read the page again, skipped the works that no
/// longer fit, or left the newer works before the kept first work out of reach.
@MainActor
private func checkMeasuredShrink(folder: URL) async throws {
    let database = try InkuDatabase(url: folder.appendingPathComponent("shrink.sqlite"))
    let ids = (0..<10).map { String(format: "shrink-%02d", $0) }
    for (index, id) in ids.enumerated() {
        let work = SavedWork(id: id, at: Int64(100 - index), input: id, score: "{}", svg: "", lineageNodeID: id + "-node")
        try await database.save(work, node: LineageNode(id: id + "-node", historyID: id, at: work.at))
    }
    let library = LibraryModel(includeListSVG: false)
    library.pageSize = 4
    await library.connect(database: database)
    await library.setPage(1)
    guard library.works.map(\.id) == Array(ids[4...7]) else { throw CheckFailure.message("Shrink fixture did not open on works 4-7") }
    LibraryPerformanceProbe.reset()
    LibraryPerformanceProbe.counting = true
    defer { LibraryPerformanceProbe.counting = false }
    library.shrinkPageKeepingFirstWork(to: 3)
    let kept = (library.works.map(\.id), library.shownFrom, library.shownTo, LibraryPerformanceProbe.refreshesStarted)
    await library.setPage(library.page + 1)
    let next = library.works.map(\.id)
    await library.setPage(0)
    let first = (library.works.map(\.id), library.hasNewer)
    await library.setPage(library.page - 1)
    let newer = (library.works.map(\.id), library.startOffset, library.hasNewer)
    await library.setPage(2)
    await library.setLatestPage()
    let latest = (library.works.map(\.id), library.startOffset)
    guard kept.0 == Array(ids[4...6]), kept.1 == 5, kept.2 == 7, kept.3 == 0,
          next == Array(ids[7...9]), first.0 == Array(ids[1...3]), first.1,
          newer.0 == Array(ids[0...2]), newer.1 == 0, !newer.2, latest.0 == Array(ids[0...2]), latest.1 == 0 else {
        throw CheckFailure.message("Measured shrink lost its place: kept \(kept), next \(next), first \(first), newer \(newer), latest \(latest)")
    }
    print("Measured shrink passed: 4 to 3 kept works 4-6 with reads0, the next page began at 7, page 0 held 1-3 with newer on, newer reached 0-2, latest returned to 0-2.")
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
    let host = PipelineHost(database: database)
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
        let ids = try await database.libraryPage(limit: 56, offset: offset, includeSVG: false).items.map(\.id)
        let fullStart = ContinuousClock.now
        var fullCount = 0
        for id in ids { if (try? await host.savedAuthoringContext(workID: id)) != nil { fullCount += 1 } }
        let fullMS = milliseconds(fullStart.duration(to: .now))
        let summaryStart = ContinuousClock.now
        let summaries = try await host.savedAuthoringSummaries(workIDs: ids)
        let summaryMS = milliseconds(summaryStart.duration(to: .now))
        guard summaries.count == fullCount else { throw CheckFailure.message("Benchmark summary count changed") }
        print("# menu,offset=\(offset),full_ms=\(fullMS),batch_ms=\(summaryMS),count=\(summaries.count)")
    }
}

private func milliseconds(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1000 + Double(duration.components.attoseconds) / 1e15
}
