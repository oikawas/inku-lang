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
}
