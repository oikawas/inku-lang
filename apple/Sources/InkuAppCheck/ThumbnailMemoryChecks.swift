import CoreGraphics
import Foundation
import ImageIO
import InkuPersistence
import InkuUI
import UniformTypeIdentifiers

/// Failure: a visited thumbnail waits for a task again, or a reused card shows another work/hash.
/// Exercise the presentation cache through persisted PNG reads, without rendering or LLMs.
@MainActor
func runThumbnailMemoryChecks() async throws {
    func require(_ condition: Bool, _ message: String) throws {
        if !condition { throw CheckFailure.message(message) }
    }
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-thumbnail-memory-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let database = try InkuDatabase(url: folder.appendingPathComponent("inku.sqlite"))
    let store = try ThumbnailStore(url: folder.appendingPathComponent("thumbs.sqlite"))
    guard let context = CGContext(data: nil, width: 8, height: 8, bitsPerComponent: 8, bytesPerRow: 32,
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue),
          let image = context.makeImage() else { throw CheckFailure.message("No thumbnail fixture image") }
    let data = NSMutableData()
    guard let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil) else {
        throw CheckFailure.message("No PNG encoder")
    }
    CGImageDestinationAddImage(destination, image, nil)
    try require(CGImageDestinationFinalize(destination), "PNG encoding failed")
    let a = SavedWork(id: "memory-a", at: 2, input: "A", score: "{}", svg: "", renderHash: "hash-a", lineageNodeID: "memory-a-node")
    let b = SavedWork(id: "memory-b", at: 1, input: "B", score: "{}", svg: "", renderHash: "hash-b", lineageNodeID: "memory-b-node")
    for work in [a, b] {
        try await database.save(work, node: LineageNode(id: work.id + "-node", historyID: work.id, at: work.at))
        try await store.put(historyID: work.id, scale: ArtworkThumbnails.scale, png: data as Data, sourceRenderHash: work.renderHash)
    }
    let thumbnails = ArtworkThumbnails()
    await thumbnails.connect(store: store, database: database)
    try require(thumbnails.cachedImage(for: a) == nil, "A cold cache must miss without starting work")
    let loaded = try await thumbnails.image(for: a)
    try require(thumbnails.cachedImage(for: a) === loaded, "A decoded PNG is not immediately available to the view")
    try require(thumbnails.cachedImage(for: b) == nil, "Another work inherited A's image")
    let changed = SavedWork(id: a.id, at: a.at, input: a.input, score: a.score, svg: "", renderHash: "hash-a-new")
    try require(thumbnails.cachedImage(for: changed) == nil, "A different render hash inherited the old image")

    let start = ContinuousClock.now
    for _ in 0..<10_000 {
        try require(thumbnails.cachedImage(for: a) === loaded, "A warm lookup lost its image")
    }
    let elapsed = start.duration(to: .now)
    let statistics = await thumbnails.currentStatistics()
    try require(statistics.storeHits == 1 && statistics.bakedOnDisplay == 0 && statistics.failed == 0,
                "Synchronous presentation caused I/O or drawing: \(statistics)")

    let bounded = ArtworkThumbnails(byteLimit: loaded.bytesPerRow * loaded.height)
    await bounded.connect(store: store, database: database)
    _ = try await bounded.image(for: a)
    let other = try await bounded.image(for: b)
    try require(bounded.cachedImage(for: a) == nil && bounded.cachedImage(for: b) === other,
                "The synchronous cache did not obey its byte limit")
    let disabled = ArtworkThumbnails(byteLimit: 0)
    await disabled.connect(store: store, database: database)
    _ = try await disabled.image(for: a)
    try require(disabled.cachedImage(for: a) == nil, "A disabled cache retained an image")

    // No live history in this isolated DB: pruning must drop the same cache the view reads.
    let empty = try InkuDatabase(url: folder.appendingPathComponent("empty.sqlite"))
    await thumbnails.connect(store: store, database: empty)
    _ = await thumbnails.pruneOrphans()
    try require(thumbnails.cachedImage(for: a) == nil, "Pruning left a synchronous orphan image")
    print("Thumbnail memory passed: cold miss; immediate decoded-image hit; work/hash isolation; "
          + "bounded and disabled cache; orphan removal; no display rasterization. 10,000 synchronous hits: \(elapsed).")
    try await checkLimitedLoads(database: database, store: store, png: data as Data, imageBytes: loaded.bytesPerRow * loaded.height)
}

/// Failures: more than four PNGs decode at once; a view that stops waiting leaves a later viewer of the same work with
/// a cancelled read; a prefetch for the next page pushes the shown work out of memory or exceeds the cache.
@MainActor
private func checkLimitedLoads(database: InkuDatabase, store: ThumbnailStore, png: Data, imageBytes: Int) async throws {
    let works = (0..<12).map { SavedWork(id: "limit-\($0)", at: Int64(100 + $0), input: "L\($0)", score: "{}", svg: "",
                                        renderHash: "hash-limit-\($0)", lineageNodeID: "limit-\($0)-node") }
    for work in works {
        try await database.save(work, node: LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at))
        try await store.put(historyID: work.id, scale: ArtworkThumbnails.scale, png: png, sourceRenderHash: work.renderHash)
    }
    let thumbnails = ArtworkThumbnails()
    await thumbnails.connect(store: store, database: database)
    let loaded = try await withThrowingTaskGroup(of: Bool.self) { group in
        for work in works.prefix(10) { group.addTask { try await thumbnails.image(for: work).width == 8 } }
        var count = 0
        for try await ok in group where ok { count += 1 }
        return count
    }
    let peak = await thumbnails.currentStatistics().maxDecodesInFlight
    guard loaded == 10, (1...ArtworkThumbnails.displayDecoders).contains(peak) else {
        throw CheckFailure.message("Ten loads gave \(loaded) images with a decode peak of \(peak)")
    }
    let left = Task { try await thumbnails.image(for: works[10]) }
    left.cancel()
    _ = try? await left.value
    guard try await thumbnails.image(for: works[10]).width == 8 else {
        throw CheckFailure.message("A later viewer did not get the image after the first one stopped waiting")
    }
    // Room for two images: the shown one stays, the other old one makes room, and a third prefetch is dropped.
    let small = ArtworkThumbnails(byteLimit: imageBytes * 2)
    await small.connect(store: store, database: database)
    _ = try await small.image(for: works[0])
    _ = try await small.image(for: works[1])
    await small.prefetch([works[2]], keeping: [works[1]])
    await small.prefetchFinished()
    let afterFirst = (small.cachedImage(for: works[0]) == nil, small.cachedImage(for: works[1]) != nil, small.cachedImage(for: works[2]) != nil)
    await small.prefetch([works[3]], keeping: [works[1], works[2]])
    await small.prefetchFinished()
    let afterSecond = (small.cachedImage(for: works[1]) != nil, small.cachedImage(for: works[2]) != nil, small.cachedImage(for: works[3]) == nil)
    guard afterFirst == (true, true, true), afterSecond == (true, true, true),
          await small.currentStatistics().prefetched == 1 else {
        throw CheckFailure.message("Prefetch kept/dropped the wrong images: \(afterFirst), \(afterSecond)")
    }
    print("Limited loads passed: 10 concurrent loads decoded with a peak of \(peak) (limit \(ArtworkThumbnails.displayDecoders)); "
          + "a later viewer got the image after the first stopped waiting; a prefetch kept the shown work, replaced an old one and dropped what had no room.")
}
