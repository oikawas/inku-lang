import CoreGraphics
import Foundation
import InkuCore
import InkuUI

private enum RasterCheckFailure: Error { case failed(String) }

/// Failure: resizing reparses a work, an uncachable frame evicts thumbnails, or cancellation retains output.
func runRasterChecks(fixtureURL: URL) async throws {
    let svg = try String(contentsOf: fixtureURL, encoding: .utf8)
    let renderer = ArtworkRenderer(byteLimit: 1024 * 1024, sceneCostLimit: 1024 * 1024, sceneCountLimit: 2, imageCountLimit: 4)
    let first = try await renderer.image(svg: svg, targetWidth: 96, targetHeight: 96)
    _ = try await renderer.image(svg: svg, targetWidth: 384, targetHeight: 384)
    let large = try await renderer.image(svg: svg, targetWidth: 768, targetHeight: 768)
    let reused = try await renderer.image(svg: svg, targetWidth: 96, targetHeight: 96)
    let stats = await renderer.cacheStatistics()
    guard first === reused, large.width > first.width, stats.scenePreparations == 1,
          stats.sceneHits == 2, stats.imageHits == 1, stats.imageCount == 2,
          stats.imageBytes <= 1024 * 1024, stats.sceneCount == 1, stats.sceneCostBytes <= 1024 * 1024 else {
        throw RasterCheckFailure.failed("Prepared scene/image reuse or cache budget changed")
    }
    let cancelled = Task {
        withUnsafeCurrentTask { $0?.cancel() }
        return try await renderer.image(svg: svg, targetWidth: 512, targetHeight: 512)
    }
    do { _ = try await cancelled.value; throw RasterCheckFailure.failed("Cancelled request produced an image") }
    catch is CancellationError {}
    let after = await renderer.cacheStatistics()
    guard after.imageCount == stats.imageCount, after.scenePreparations == stats.scenePreparations else {
        throw RasterCheckFailure.failed("Cancelled request entered the render/cache path")
    }
    await renderer.purge()
    let purged = await renderer.cacheStatistics()
    guard purged.imageCount == 0, purged.sceneCount == 0, purged.imageBytes == 0, purged.sceneCostBytes == 0 else {
        throw RasterCheckFailure.failed("Purge retained derived caches")
    }
    print("Prepared native cache passed: one parse, resolution reuse, unchanged image identity, bounded caches, cancellation, purge.")
}
