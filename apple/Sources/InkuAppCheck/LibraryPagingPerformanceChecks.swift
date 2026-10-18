#if os(macOS)
import AppKit
import CoreGraphics
import Darwin
import Foundation
import ImageIO
import InkuHost
import InkuPersistence
import InkuUI
import UniformTypeIdentifiers

/// Off-screen measurement of library page turns (review-20261018 PLAN §3, stage B). A disposable SQLite holds 600
/// works whose cards differ in height (title length, model lines, comments) and a stored PNG for each; the library
/// is hosted with the hidden lineage view in a window that is never ordered in. Nothing here opens the author's
/// database, a provider or the fixed app, and nothing is shown on screen.
///
/// Usage: `InkuAppCheck --library-paging-perf-only [--json <path>] [--size <width>x<height>] [--view-parents]`
@MainActor
func runLibraryPagingPerformance(arguments: [String]) async throws {
    func value(_ flag: String) -> String? {
        guard let index = arguments.firstIndex(of: flag), arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }
    let size: CGSize = try {
        guard let text = value("--size") else { return CGSize(width: 2172, height: 1010) }
        let parts = text.split(separator: "x").compactMap { Double($0) }
        guard parts.count == 2, parts[0] > 0, parts[1] > 0 else { throw CheckFailure.message("--size takes <width>x<height>") }
        return CGSize(width: parts[0], height: parts[1])
    }()
    let jsonURL = value("--json").map { URL(fileURLWithPath: $0) }

    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-library-paging-perf-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    let fixtureStart = ContinuousClock.now
    try await PagingFixture.write(databaseURL: databaseURL)
    print("Fixture: \(PagingFixture.count) works, \(PagingFixture.count) stored PNGs, lineage of \(PagingFixture.lineageMembers.count) nodes in \(PagingFixture.seconds(fixtureStart.duration(to: .now))) s")

    let app = AppModel(databaseURL: databaseURL, transport: PagingNoProvider())
    await app.initialize()
    guard app.errorText == nil else { throw CheckFailure.message("AppModel did not open the fixture: \(app.errorText ?? "")") }
    await app.thumbnails.passFinished()
    let pass = await app.thumbnails.currentStatistics()
    guard pass.bakedInBackground == 0, pass.failed == 0 else {
        throw CheckFailure.message("The launch pass baked or failed on a fixture whose PNGs are all current: \(pass)")
    }
    let library = app.library
    // The lineage beneath the library: the root of the fixture's tree, whose members lie on many pages.
    let root = try await app.library.fullWork(id: PagingFixture.id(PagingFixture.lineageRoot))
    await library.loadLineage(work: root)
    guard let graph = library.lineageDisplayGraph, graph.nodes.count >= 10 else {
        throw CheckFailure.message("The fixture lineage did not load beneath the library")
    }

    _ = NSApplication.shared
    NSApp.setActivationPolicy(.prohibited)
    let preview = LibraryPreviewModel()
    let window = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.titled, .resizable],
                          backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    let host = LibraryPerformanceProbe.hostingView(model: app, preview: preview)
    host.frame = NSRect(origin: .zero, size: size)
    window.contentView = host
    defer { window.contentView = nil; window.close() }

    LibraryPerformanceProbe.reset()
    LibraryPerformanceProbe.counting = true
    defer { LibraryPerformanceProbe.counting = false }
    let meter = PagingMeter(host: host, app: app)
    let opening = try await meter.settle()
    guard LibraryPerformanceProbe.cardBodies > 0, !library.works.isEmpty else {
        throw CheckFailure.message("The off-screen library built no cards (page size \(library.pageSize), works \(library.works.count))")
    }
    print("Opened: page size \(library.pageSize), works \(library.works.count), NSViews \(meter.viewCount()), "
          + "\(PagingMeter.ms(opening.wall)) ms to settle")
    let classes = meter.viewClasses()
    print("NSView classes: " + classes.prefix(12).map { "\($0.0) \($0.1)" }.joined(separator: ", "))
    if arguments.contains("--view-parents") {
        for (name, count) in meter.viewParents().prefix(30) { print("  \(count)\t\(name)") }
    }
    // SwiftUI builds its accessibility tree only for a connected AX client; in-process reads see none.
    print("AX probe: hosting view children \(host.accessibilityChildren()?.count ?? 0) (no AX client, so the turns below are without AX)")

    // L7, before any turn: a revision-marked lineage node that the first page does not list.
    let offPage = PagingFixture.revisionMarkedLineageMembers.map(PagingFixture.id)
        .filter { id in !library.works.contains { $0.id == id } && graph.nodes.contains { $0.work?.id == id } }
    let lineageMarksBefore = offPage.filter { library.annotation(for: $0).forRevision }.count

    var turns: [PagingTurn] = []
    for (label, target) in [("2nd page", 1), ("3rd page", 2), ("4th page", 3), ("back to 3rd", 2), ("4th again", 3)] {
        turns.append(try await meter.turn(label: label, to: target))
    }
    let lineageMarksAfter = offPage.filter { library.annotation(for: $0).forRevision }.count
    print("L7 lineage marks: \(offPage.count) revision-marked lineage nodes off the first page; marked before paging \(lineageMarksBefore), after \(lineageMarksAfter)")

    print("")
    print("turn                  refresh lineage cards  nodes  NSViews decodes mem/store  first_ms  settle_ms  main_cpu_ms  layout_ms  works")
    for turn in turns {
        print(turn.row)
    }
    func median(_ values: [Double]) -> Double {
        let sorted = values.sorted(); return sorted.isEmpty ? 0 : sorted[sorted.count / 2]
    }
    let second = turns[0]
    print("Plan table: refresh per turn max \(turns.map(\.refreshes).max() ?? 0); NSViews \(turns.last?.viewCount ?? 0); "
          + "card bodies per turn median \(Int(median(turns.map { Double($0.cardBodies) }))); concurrent decodes max \(turns.map(\.maxDecodes).max() ?? 0); "
          + "2nd page memory hits \(second.memoryHits)/\(second.memoryHits + second.storeHits); "
          + "main CPU median \(PagingMeter.format(median(turns.map(\.mainCPU)))) ms")
    print("Medians: settle \(PagingMeter.format(median(turns.map(\.settle)))) ms, first paint \(PagingMeter.format(median(turns.map(\.firstPaint)))) ms, "
          + "layout+display \(PagingMeter.format(median(turns.map(\.layout)))) ms, lineage node bodies \(Int(median(turns.map { Double($0.lineageNodeBodies) })))")

    if let jsonURL {
        let document: [String: Any] = [
            "window": ["width": size.width, "height": size.height],
            "page_size": library.pageSize,
            "fixture_works": PagingFixture.count,
            "opening_settle_ms": PagingMeter.ms(opening.wall),
            "lineage_marks": ["off_page": offPage.count, "before": lineageMarksBefore, "after": lineageMarksAfter],
            "nsview_classes": Dictionary(uniqueKeysWithValues: classes),
            "turns": turns.map(\.json),
        ]
        try FileManager.default.createDirectory(at: jsonURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: document, options: [.prettyPrinted, .sortedKeys]).write(to: jsonURL)
        print("Wrote \(jsonURL.path)")
    }
    print("Library paging measurement finished: \(turns.count) turns, provider0, author database0, on-screen windows0.")
}

private struct PagingTurn {
    let label: String
    let refreshes: Int
    let lineageReads: Int
    let cardBodies: Int
    let lineageNodeBodies: Int
    let viewCount: Int
    let maxDecodes: Int
    let memoryHits: Int
    let storeHits: Int
    let firstPaint: Double
    let settle: Double
    let mainCPU: Double
    let layout: Double
    let pageSize: Int
    let shownFrom: Int
    let shownTo: Int

    var row: String {
        func pad(_ text: String, _ width: Int) -> String { text.count >= width ? text : text + String(repeating: " ", count: width - text.count) }
        func left(_ value: CustomStringConvertible, _ width: Int) -> String {
            let text = value.description; return text.count >= width ? text : String(repeating: " ", count: width - text.count) + text
        }
        return pad(label, 20) + left(refreshes, 9) + left(lineageReads, 8) + left(cardBodies, 7) + left(lineageNodeBodies, 7)
            + left(viewCount, 9) + left(maxDecodes, 8) + left("\(memoryHits)/\(storeHits)", 11)
            + left(PagingMeter.format(firstPaint), 10) + left(PagingMeter.format(settle), 11)
            + left(PagingMeter.format(mainCPU), 13) + left(PagingMeter.format(layout), 11)
            + "  \(shownFrom)-\(shownTo)/\(pageSize)"
    }

    var json: [String: Any] {
        ["label": label, "refreshes": refreshes, "lineage_reads": lineageReads,
         "card_bodies": cardBodies, "lineage_node_bodies": lineageNodeBodies, "nsviews": viewCount,
         "max_concurrent_decodes": maxDecodes, "memory_hits_at_publish": memoryHits, "store_hits": storeHits,
         "first_paint_ms": firstPaint, "settle_ms": settle, "main_thread_cpu_ms": mainCPU,
         "layout_display_ms": layout, "page_size": pageSize, "shown_from": shownFrom, "shown_to": shownTo]
    }
}

@MainActor
private final class PagingMeter {
    struct Settled {
        var wall: Duration
        var mainCPU: Duration
        var layout: Duration
        var firstPaint: Duration?
    }

    private struct Signature: Equatable {
        var refreshesStarted: Int
        var refreshesFinished: Int
        var lineageReads: Int
        var cardBodies: Int
        var lineageNodeBodies: Int
        var memoryHits: Int
        var storeHits: Int
        var baked: Int
        var failed: Int
        var works: [String]
        var page: Int
        var pageSize: Int
        var loading: Bool
    }

    let host: NSView
    let app: AppModel

    init(host: NSView, app: AppModel) {
        self.host = host
        self.app = app
    }

    /// One turn as the pager button does it, measured until nothing changes for 400 ms.
    func turn(label: String, to target: Int) async throws -> PagingTurn {
        let library = app.library
        let before = (refreshes: LibraryPerformanceProbe.refreshesStarted, lineage: LibraryPerformanceProbe.lineageReads,
                      cards: LibraryPerformanceProbe.cardBodies, nodes: LibraryPerformanceProbe.lineageNodeBodies)
        await app.thumbnails.resetPeaks()
        let statistics = await app.thumbnails.currentStatistics()
        let start = ContinuousClock.now
        let cpuStart = Self.threadCPU()
        await library.setPage(target)
        // The refresh has published the page and no view has drawn it yet: what memory already holds.
        let memoryHits = library.works.filter { app.thumbnails.cachedImage(for: $0) != nil }.count
        let published = library.works.map(\.id)
        let settled = try await settle(start: start, cpuStart: cpuStart, published: published)
        let after = await app.thumbnails.currentStatistics()
        return PagingTurn(
            label: label,
            refreshes: LibraryPerformanceProbe.refreshesStarted - before.refreshes,
            lineageReads: LibraryPerformanceProbe.lineageReads - before.lineage,
            cardBodies: LibraryPerformanceProbe.cardBodies - before.cards,
            lineageNodeBodies: LibraryPerformanceProbe.lineageNodeBodies - before.nodes,
            viewCount: viewCount(), maxDecodes: after.maxDecodesInFlight, memoryHits: memoryHits,
            storeHits: after.storeHits - statistics.storeHits,
            firstPaint: settled.firstPaint.map(Self.ms) ?? -1, settle: Self.ms(settled.wall),
            mainCPU: Self.ms(settled.mainCPU), layout: Self.ms(settled.layout),
            pageSize: library.pageSize, shownFrom: library.shownFrom, shownTo: library.shownTo)
    }

    /// Pumps the run loop, laying out and drawing the hosting view as a display cycle would, until the library has
    /// no refresh or thumbnail read in flight and nothing has changed for `quiet`.
    func settle(start: ContinuousClock.Instant = .now, cpuStart: UInt64 = threadCPU(), published: [String]? = nil,
                quiet: Duration = .milliseconds(400), timeout: Duration = .seconds(30)) async throws -> Settled {
        var last = await signature()
        var lastActivity = ContinuousClock.now
        var cpuAtActivity = Self.threadCPU()
        var layout: Duration = .zero
        var firstPaint: Duration?
        while true {
            try await Task.sleep(for: .milliseconds(4))
            let drawStart = ContinuousClock.now
            host.layoutSubtreeIfNeeded()
            host.displayIfNeeded()
            let spent = drawStart.duration(to: .now)
            layout += spent
            let now = await signature()
            // A measured shrink can drop the last row of the published page before the first tick.
            if firstPaint == nil, let published, !now.works.isEmpty, published.starts(with: now.works), !now.loading {
                firstPaint = start.duration(to: .now)
            }
            if now != last || spent > .milliseconds(1) {
                last = now
                lastActivity = .now
                cpuAtActivity = Self.threadCPU()
            }
            let statistics = await app.thumbnails.currentStatistics()
            let idle = now.refreshesStarted == now.refreshesFinished && statistics.loadsInFlight == 0
                && statistics.decodesInFlight == 0
            if idle, lastActivity.duration(to: .now) >= quiet { break }
            if start.duration(to: .now) > timeout {
                throw CheckFailure.message("The library did not settle in \(timeout): \(now), \(statistics)")
            }
        }
        return Settled(wall: start.duration(to: lastActivity),
                       mainCPU: .nanoseconds(Int64(cpuAtActivity &- cpuStart)), layout: layout, firstPaint: firstPaint)
    }

    private func signature() async -> Signature {
        let statistics = await app.thumbnails.currentStatistics()
        let library = app.library
        return Signature(
            refreshesStarted: LibraryPerformanceProbe.refreshesStarted, refreshesFinished: LibraryPerformanceProbe.refreshesFinished,
            lineageReads: LibraryPerformanceProbe.lineageReads, cardBodies: LibraryPerformanceProbe.cardBodies,
            lineageNodeBodies: LibraryPerformanceProbe.lineageNodeBodies, memoryHits: statistics.memoryHits,
            storeHits: statistics.storeHits, baked: statistics.bakedOnDisplay, failed: statistics.failed,
            works: library.works.map(\.id), page: library.page, pageSize: library.pageSize, loading: library.loading)
    }

    func viewCount() -> Int {
        func count(_ view: NSView) -> Int { view.subviews.reduce(1) { $0 + count($1) } }
        return count(host) - 1
    }

    /// NSView classes under the hosting view, most frequent first.
    func viewClasses() -> [(String, Int)] {
        var counts: [String: Int] = [:]
        func visit(_ view: NSView) {
            for child in view.subviews {
                counts[String(describing: type(of: child)), default: 0] += 1
                visit(child)
            }
        }
        visit(host)
        return counts.sorted { ($0.value, $1.key) > ($1.value, $0.key) }
    }

    /// For each NSView class, the class of its superview, most frequent first.
    func viewParents() -> [(String, Int)] {
        var counts: [String: Int] = [:]
        func visit(_ view: NSView) {
            for child in view.subviews {
                let name = String(describing: type(of: child)).prefix(48) + " < " + String(describing: type(of: view)).prefix(48)
                counts[String(name), default: 0] += 1
                visit(child)
            }
        }
        visit(host)
        return counts.sorted { ($0.value, $1.key) > ($1.value, $0.key) }
    }

    nonisolated static func threadCPU() -> UInt64 { clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID) }
    nonisolated static func ms(_ duration: Duration) -> Double {
        Double(duration.components.seconds) * 1000 + Double(duration.components.attoseconds) / 1e15
    }
    nonisolated static func format(_ value: Double) -> String { String(format: "%.1f", value) }
}

/// 600 works, newest first. Card heights grow over the first pages so that a turn meets taller cards than any
/// seen before: one-line titles on the first page, then three-line titles, two model lines and comments.
private enum PagingFixture {
    static let count = 600
    /// One lineage tree whose members are spread over every page; four children per node.
    static let lineageMembers = Array(stride(from: 5, to: count, by: 13))
    static var lineageRoot: Int { lineageMembers.max()! }
    static var revisionMarkedLineageMembers: [Int] { lineageMembers.filter { $0 % 2 == 1 } }

    static func id(_ index: Int) -> String { String(format: "paging-%04d", index) }
    static func seconds(_ duration: Duration) -> String { String(format: "%.1f", PagingMeter.ms(duration) / 1000) }

    private static let phrase = "春の野に霞たなびきうら悲しこの夕かげに鶯鳴くも遠き山の端に月のかかれる夜の静けさ"

    static func title(_ index: Int) -> String {
        let length: Int
        if index < 56 { length = index % 3 == 0 ? 14 : 6 }
        else if index % 5 == 0 { length = 70 }
        else if index % 3 == 0 { length = 32 }
        else { length = index % 2 == 0 ? 16 : 7 }
        let characters = Array(phrase)
        return String((0..<length).map { characters[($0 + index) % characters.count] })
    }

    static func work(_ index: Int) -> SavedWork {
        let at = Int64(1_800_000_000_000 - index * 60_000)
        let twoModels = index >= 112 && index % 4 == 1
        return SavedWork(id: id(index), at: at, input: title(index), score: "{}", svg: "",
                         stage1Model: twoModels ? "lmstudio:qwen3-32b-instruct" : "openai:gpt-6",
                         stage2Model: "openai:gpt-6", renderHash: "rh3:paging-\(index)",
                         starred: index % 9 == 0, lineageNodeID: id(index) + "-node")
    }

    static func write(databaseURL: URL) async throws {
        let database = try InkuDatabase(url: databaseURL)
        let store = try ThumbnailStore(url: ThumbnailStore.url(besideDatabase: databaseURL))
        let members = lineageMembers.sorted(by: >)  // oldest first, so a parent is saved before its children
        let rootNode = id(members[0]) + "-node"
        var parentOf: [Int: Int] = [:]
        for (order, member) in members.enumerated() where order > 0 { parentOf[member] = members[(order - 1) / 4] }
        for index in stride(from: count - 1, through: 0, by: -1) {
            let work = work(index)
            let member = members.contains(index)
            let node = LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at,
                                   renderHash: work.renderHash, rootNodeID: member ? rootNode : work.lineageNodeID)
            let edge = parentOf[index].map {
                LineageEdge(id: "edge-\(index)", parentNodeID: id($0) + "-node", childNodeID: node.id, derivationKind: "variation", at: work.at)
            }
            try await database.save(work, node: node, edge: edge)
        }
        for index in 0..<count where (index >= 168 && index % 6 == 2) || revisionMarkedLineageMembers.contains(index) || index % 11 == 0 {
            let note = index >= 168 && index % 6 == 2 ? "作品へのコメント \(index)：線の重なりを見直す" : nil
            try await database.setAnnotation(id: id(index), note: note,
                                             forRevision: revisionMarkedLineageMembers.contains(index) || index % 11 == 0)
        }
        let pngs = try thumbnails()
        for index in 0..<count {
            try await store.put(historyID: id(index), scale: ArtworkThumbnails.scale, png: pngs[index], sourceRenderHash: work(index).renderHash)
        }
    }

    /// One distinct PNG per work at the stored 512px width, with enough strokes to cost a real decode.
    private static func thumbnails() throws -> [Data] {
        nonisolated(unsafe) var results = [Data?](repeating: nil, count: count)
        let lock = NSLock()
        DispatchQueue.concurrentPerform(iterations: count) { index in
            let width = 512, height = [362, 512, 724, 384][index % 4]
            guard let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                                          space: CGColorSpaceCreateDeviceRGB(),
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return }
            var seed = UInt64(index &* 2_654_435_761 &+ 1)
            func next() -> Double {
                seed = seed &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
                return Double(seed >> 11) / Double(1 << 53)
            }
            context.setFillColor(red: 0.96, green: 0.95, blue: 0.92, alpha: 1)
            context.fill(CGRect(x: 0, y: 0, width: width, height: height))
            for _ in 0..<160 {
                context.setStrokeColor(red: next(), green: next() * 0.6, blue: next(), alpha: 0.35 + next() * 0.5)
                context.setLineWidth(1 + next() * 9)
                context.move(to: CGPoint(x: next() * Double(width), y: next() * Double(height)))
                context.addCurve(to: CGPoint(x: next() * Double(width), y: next() * Double(height)),
                                 control1: CGPoint(x: next() * Double(width), y: next() * Double(height)),
                                 control2: CGPoint(x: next() * Double(width), y: next() * Double(height)))
                context.strokePath()
            }
            guard let image = context.makeImage() else { return }
            let data = NSMutableData()
            guard let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil) else { return }
            CGImageDestinationAddImage(destination, image, nil)
            guard CGImageDestinationFinalize(destination) else { return }
            lock.lock(); results[index] = data as Data; lock.unlock()
        }
        let pngs = results.compactMap { $0 }
        guard pngs.count == count else { throw CheckFailure.message("Only \(pngs.count) of \(count) fixture PNGs were encoded") }
        return pngs
    }
}

private actor PagingNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw CheckFailure.message("The paging measurement must not call a provider")
    }
}
#endif
