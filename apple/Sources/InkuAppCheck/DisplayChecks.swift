import Foundation
import InkuCore
import os

private enum DisplayCheckFailure: Error { case failed(String) }

/// Failure: the Skia display is missing from the linked core, draws a different size
/// than resvg, cannot draw tiles on several threads, or takes a work outside its table.
func runDisplayChecks(fixtureURL: URL) throws {
    let svg = try String(contentsOf: fixtureURL, encoding: .utf8)
    let display = try InkuCore.prepareDisplay(svg: svg)
    let resvg = try InkuCore.prepareSVG(svg: svg)
    guard display.intrinsicWidth == resvg.intrinsicWidth, display.intrinsicHeight == resvg.intrinsicHeight else {
        throw DisplayCheckFailure.failed("Display and resvg disagree on the work's size")
    }
    let layout = InkuCore.displayLayout
    let coarse = try display.rasterize(targetWidth: layout.coarseSide, targetHeight: layout.coarseSide)
    guard max(coarse.width, coarse.height) == layout.coarseSide, coarse.pixelFormat == "rgba8-premultiplied",
          coarse.pixels.count == Int(coarse.stride * coarse.height) else {
        throw DisplayCheckFailure.failed("Coarse whole has the wrong shape")
    }
    let side = UInt32((display.intrinsicWidth * 2).rounded())
    let window = DisplayRegion(fullWidth: side, fullHeight: UInt32((display.intrinsicHeight * 2).rounded()),
                               x: 0, y: 0, width: side, height: UInt32((display.intrinsicHeight * 2).rounded()))
    let tiles = InkuCore.displayTiles(window: window, side: layout.tileSide)
    let covered = tiles.reduce(0) { $0 + UInt64($1.width) * UInt64($1.height) }
    guard covered == UInt64(window.width) * UInt64(window.height) else {
        throw DisplayCheckFailure.failed("Tiles do not cover the window once")
    }
    let drawn = OSAllocatedUnfairLock(initialState: 0)
    DispatchQueue.concurrentPerform(iterations: tiles.count) { index in
        guard let image = try? display.region(tiles[index]),
              image.width == tiles[index].width, image.height == tiles[index].height else { return }
        drawn.withLock { $0 += 1 }
    }
    guard drawn.withLock({ $0 }) == tiles.count else {
        throw DisplayCheckFailure.failed("Tiles drawn on several threads failed")
    }
    do {
        _ = try InkuCore.prepareDisplay(svg: #"<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text>a</text></svg>"#)
        throw DisplayCheckFailure.failed("A work outside the support table was taken")
    } catch CoreFailure.displayUnsupported(let code, _) where code == "element" {}
    let rewrites = display.rewrites
    print("Display passed: Skia \(InkuCore.displayAPIVersion), \(Int(display.intrinsicWidth))x\(Int(display.intrinsicHeight)), "
        + "coarse \(coarse.width)x\(coarse.height), \(tiles.count) tiles on several threads, "
        + "rewrites href \(rewrites.href) ellipse \(rewrites.ellipse) seed \(rewrites.seed), unsupported work refused.")
}
