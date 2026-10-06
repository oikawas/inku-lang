import CoreGraphics
import Foundation
import ImageIO
import InkuPersistence
import InkuUI

private enum ThumbnailCheckFailure: Error { case failed(String) }

/// Thumbnails baked to PNG in the store beside the database (I-718), on `svg` and two small works.
/// Failure: a launch draws the thumbnails again instead of reading them; a work saved, changed or
/// deleted leaves the store behind; the store is kept in memory only.
@MainActor
func runThumbnailChecks(svg: String) async throws {
    func fail(_ message: String) -> ThumbnailCheckFailure { .failed(message) }
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-thumbnails-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let url = folder.appendingPathComponent("inku.sqlite")
    let database = try InkuDatabase(url: url)
    let wide = ##"<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="#2e6b3f"/></svg>"##
    let tall = ##"<svg xmlns="http://www.w3.org/2000/svg" width="100" height="300"><rect width="100" height="300" fill="#6b2e3f"/></svg>"##
    let works = [
        SavedWork(id: "thumb-a", at: 3, input: "A", score: "{}", svg: svg, renderHash: "hash-a", lineageNodeID: "thumb-a-node"),
        SavedWork(id: "thumb-b", at: 2, input: "B", score: "{}", svg: wide, renderHash: "hash-b", lineageNodeID: "thumb-b-node"),
        SavedWork(id: "thumb-c", at: 1, input: "C", score: "{}", svg: tall, lineageNodeID: "thumb-c-node"),
    ]
    for work in works {
        try await database.save(work, node: LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at))
    }

    // Through the app: the store is the file beside the database, and the launch pass bakes every work.
    let app = AppModel(databaseURL: url)
    await app.initialize()
    await app.thumbnails.passFinished()
    let storeURL = folder.appendingPathComponent("thumbs.sqlite")
    guard ThumbnailStore.url(besideDatabase: url) == storeURL, FileManager.default.fileExists(atPath: storeURL.path),
          await app.thumbnails.currentStatistics().bakedInBackground == 3 else {
        throw fail("The launch pass did not bake the three works into thumbs.sqlite: \(await app.thumbnails.currentStatistics())")
    }
    let store = try ThumbnailStore(url: storeURL)
    guard try await store.count(scale: 2) == 3, try await store.storedHashes(scale: 2) == ["thumb-a": "hash-a", "thumb-b": "hash-b", "thumb-c": nil] else {
        throw fail("The store does not hold one 2x thumbnail per work with its render hash: \(try await store.storedHashes(scale: 2))")
    }
    // Server's widths: 512 at scale 2, the height following the work.
    for (id, height) in [("thumb-b", 256), ("thumb-c", 1536)] {
        guard let png = try await store.thumbnail(historyID: id, scale: 2)?.png, let size = pngSize(png),
              size == (512, height) else {
            throw fail("\(id) is not 512 wide and \(height) high")
        }
    }

    // The next launch reads the stored thumbnails and draws none; then they come from memory.
    let next = ArtworkThumbnails()
    await next.connect(store: store, database: database)
    for work in works {
        let image = try await next.image(for: work)
        guard image.width == 512 else { throw fail("\(work.id) shown at \(image.width) wide") }
    }
    for work in works { _ = try await next.image(for: work) }
    var statistics = await next.currentStatistics()
    guard statistics.storeHits == 3, statistics.bakedOnDisplay == 0, statistics.memoryHits == 3 else {
        throw fail("The next launch drew thumbnails instead of reading them: \(statistics)")
    }

    // A thumbnail baked from another SVG is baked again by the launch pass, and only that one.
    try await store.put(historyID: "thumb-b", scale: 2, png: Data([0]), sourceRenderHash: "older")
    await next.synchronize()
    await next.passFinished()
    statistics = await next.currentStatistics()
    guard statistics.bakedInBackground == 1, try await store.thumbnail(historyID: "thumb-b", scale: 2)?.sourceRenderHash == "hash-b" else {
        throw fail("The stale thumbnail was not the one baked again: \(statistics)")
    }

    // A work shown with nothing in the store is drawn there and then, and stored.
    try await store.delete(historyIDs: ["thumb-a"])
    let fresh = ArtworkThumbnails()
    await fresh.connect(store: store, database: database)
    _ = try await fresh.image(for: works[0])
    guard await fresh.currentStatistics().bakedOnDisplay == 1, try await store.thumbnail(historyID: "thumb-a", scale: 2) != nil else {
        throw fail("A shown work missing from the store was not drawn and stored: \(await fresh.currentStatistics())")
    }

    // A work just saved is baked in the background.
    let saved = SavedWork(id: "thumb-d", at: 4, input: "D", score: "{}", svg: wide, renderHash: "hash-d", lineageNodeID: "thumb-d-node")
    try await database.save(saved, node: LineageNode(id: saved.lineageNodeID!, historyID: saved.id, at: saved.at))
    await fresh.bakeSaved(saved)
    let deadline = ContinuousClock.now + .seconds(30)
    while try await store.thumbnail(historyID: "thumb-d", scale: 2) == nil {
        guard ContinuousClock.now < deadline else { throw fail("The saved work was not baked") }
        try await Task.sleep(for: .milliseconds(10))
    }

    // Deleting a work for good drops its thumbnail.
    app.library.selectedIDs = []
    try await database.setTrashed(ids: ["thumb-c"], trashed: true)
    await app.library.permanentlyDelete(ids: ["thumb-c"])
    guard try await store.storedIDs() == ["thumb-a", "thumb-b", "thumb-d"] else {
        throw fail("The deleted work's thumbnail stayed: \(try await store.storedIDs())")
    }

    // The store is derived: a file that is not a database is replaced by an empty store.
    let broken = folder.appendingPathComponent("broken-thumbs.sqlite")
    try Data("not a database".utf8).write(to: broken)
    guard try await ThumbnailStore(url: broken).count(scale: 2) == 0 else { throw fail("A broken store was not replaced") }

    print("Thumbnails passed: launch pass baked 3 works into thumbs.sqlite at 512px wide; next launch read 3 from the store "
        + "and drew none; a stale one baked again; a missing one drawn on display; a saved one baked; a deleted one dropped; "
        + "a broken store replaced.")
}

private func pngSize(_ png: Data) -> (Int, Int)? {
    guard let source = CGImageSourceCreateWithData(png as CFData, nil),
          let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
          let width = properties[kCGImagePropertyPixelWidth] as? Int,
          let height = properties[kCGImagePropertyPixelHeight] as? Int else { return nil }
    return (width, height)
}
