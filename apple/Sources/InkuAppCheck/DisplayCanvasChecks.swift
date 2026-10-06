import CoreGraphics
import Foundation
import InkuCore
import InkuUI

private enum DisplayCanvasCheckFailure: Error { case failed(String) }

/// The work area's painter and request flow, on `svg` (a supported work).
/// Failure (C1): the work area silently draws with resvg, or joins its tiles wrongly.
/// Failure (C5): a new work waits behind the one the viewer left, or a cancelled request
/// leaves the progress mark behind.
@MainActor
func runDisplayCanvasChecks(svg: String) async throws {
    func fail(_ message: String) -> DisplayCanvasCheckFailure { .failed(message) }

    // C1: Skia draws the work area, coarse whole first; the tiles join into the one-piece whole.
    let renderer = DisplayRenderer()
    var frames: [DisplayRenderer.Frame] = []
    for try await frame in renderer.whole(svg: svg, width: 1500, height: 1500) { frames.append(frame) }
    guard frames.map(\.coarse) == [true, false], frames.allSatisfy({ $0.painter == .skia }),
          renderer.diagnostics().fallbacks.isEmpty, let joined = frames.last?.image else {
        throw fail("The work area did not draw a coarse and a full whole with Skia: \(frames.map { ($0.coarse, $0.painter) })")
    }
    let display = try InkuCore.prepareDisplay(svg: svg)
    let whole = try display.rasterize(targetWidth: 1500, targetHeight: 1500)
    guard joined.width == Int(whole.width), joined.height == Int(whole.height),
          let joinedPixels = joined.dataProvider?.data as Data? else {
        throw fail("Joined whole is \(joined.width)x\(joined.height), the one-piece whole \(whole.width)x\(whole.height)")
    }
    let tileCount = renderer.diagnostics().tilesDrawn
    let (worstBlock, farShare) = difference(joinedPixels, whole.pixels, width: Int(whole.width), height: Int(whole.height))
    guard tileCount > 1, worstBlock <= 16, farShare <= 0.005 else {
        throw fail("Joined \(tileCount) tiles differ from the one-piece whole: worst block \(worstBlock), far \(farShare)")
    }
    let unsupported = #"<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text>a</text></svg>"#
    var fallback: [DisplayRenderer.Frame] = []
    for try await frame in renderer.whole(svg: unsupported, width: 64, height: 64) { fallback.append(frame) }
    guard fallback.map(\.painter) == [.resvg], renderer.diagnostics().fallbacks == ["element": 1] else {
        throw fail("A work outside the support table was not shown with resvg and counted: \(renderer.diagnostics())")
    }

    // C5: switching works while a large whole is drawing shows the new work without waiting for the old.
    let large: UInt32 = 4096
    let alone = CanvasPicture()
    let started = ContinuousClock.now
    await alone.load(svg: svg, width: large, height: large, renderer: DisplayRenderer())
    let largeAlone = ContinuousClock.now - started
    guard alone.painter == .skia, !alone.loading else { throw fail("The large whole did not finish on its own") }

    let next = ##"<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"><rect width="300" height="200" fill="#2e6b3f"/></svg>"##
    let shared = DisplayRenderer()
    let picture = CanvasPicture()
    let first = Task { await picture.load(svg: svg, width: large, height: large, renderer: shared) }
    try await waitUntil("the coarse whole of the large request") { picture.image != nil }
    first.cancel()
    let switched = ContinuousClock.now
    await picture.load(svg: next, width: 640, height: 640, renderer: shared)
    let nextTook = ContinuousClock.now - switched
    await first.value
    guard picture.imageSVG == next, picture.painter == .skia, !picture.loading, picture.error == nil else {
        throw fail("After the switch the canvas shows \(picture.imageSVG == next ? "the new work" : "another picture"), loading \(picture.loading)")
    }
    // Queued behind the left whole, the new work would take nearly as long as that whole alone.
    guard nextTook < largeAlone / 2 else {
        throw fail("The new work took \(nextTook); the large whole alone takes \(largeAlone)")
    }
    guard shared.diagnostics().skiaWholes == 1 else {
        throw fail("The left work's large whole was finished anyway: \(shared.diagnostics())")
    }

    // C5: a request cancelled with nothing after it leaves no progress mark.
    let lone = Task { await picture.load(svg: svg, width: large - 1, height: large - 1, renderer: shared) }
    try await waitUntil("the progress mark") { picture.loading }
    lone.cancel()
    await lone.value
    guard !picture.loading else { throw fail("The progress mark stayed after the request was cancelled") }

    print("Display canvas passed: Skia, coarse then \(tileCount) tiles (worst block \(worstBlock)), "
        + "resvg fallback counted; new work in \(nextTook) while the left whole takes \(largeAlone) alone; "
        + "no progress mark after cancelling.")
}

@MainActor
private func waitUntil(_ what: String, _ condition: () -> Bool) async throws {
    let deadline = ContinuousClock.now + .seconds(30)
    while !condition() {
        guard ContinuousClock.now < deadline else { throw DisplayCanvasCheckFailure.failed("Timed out waiting for \(what)") }
        try await Task.sleep(for: .milliseconds(5))
    }
}

/// The C1/C4 measure on premultiplied RGBA composited over white: the worst 16px block's mean
/// channel difference, and the share of pixels differing by more than 32.
private func difference(_ a: Data, _ b: Data, width: Int, height: Int) -> (worstBlock: Double, farShare: Double) {
    func white(_ value: UInt8, _ alpha: UInt8) -> Int { Int(value) + 255 - Int(alpha) }
    let blocksX = (width + 15) / 16, blocksY = (height + 15) / 16
    var sums = [Int](repeating: 0, count: blocksX * blocksY), counts = sums
    var far = 0
    a.withUnsafeBytes { a in
        b.withUnsafeBytes { b in
            for y in 0..<height {
                for x in 0..<width {
                    let i = (y * width + x) * 4
                    var worst = 0, total = 0
                    for c in 0..<3 {
                        let d = abs(white(a[i + c], a[i + 3]) - white(b[i + c], b[i + 3]))
                        worst = max(worst, d); total += d
                    }
                    if worst > 32 { far += 1 }
                    let block = (y / 16) * blocksX + x / 16
                    sums[block] += total; counts[block] += 3
                }
            }
        }
    }
    let worstBlock = zip(sums, counts).map { Double($0) / Double(max(1, $1)) }.max() ?? 0
    return (worstBlock, Double(far) / Double(width * height))
}
