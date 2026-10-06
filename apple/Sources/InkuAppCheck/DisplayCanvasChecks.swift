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

    // C3 (drawn): a window of the zoomed picture, tiles shown as they finish, matches the same pixels of the whole.
    let region = DisplayRegion(fullWidth: 1500, fullHeight: 1500, x: 300, y: 400, width: 1100, height: 700)
    var windowFrames: [DisplayRenderer.WindowFrame] = []
    for try await frame in renderer.window(svg: svg, region: region, progressInterval: .zero) { windowFrames.append(frame) }
    guard let drawnWindow = windowFrames.last, drawnWindow.complete, windowFrames.dropLast().allSatisfy({ !$0.complete }),
          windowFrames.count > 1, let windowPixels = drawnWindow.image.dataProvider?.data as Data? else {
        throw fail("The window was not handed over tile by tile and then complete: \(windowFrames.map(\.complete))")
    }
    let crop = crop(whole, x: 300, y: 400, width: 1100, height: 700)
    let (windowBlock, windowFar) = difference(windowPixels, crop, width: 1100, height: 700)
    guard windowBlock <= 16, windowFar <= 0.005 else {
        throw fail("The window differs from the same pixels of the whole: worst block \(windowBlock), far \(windowFar)")
    }

    // C5 (zoom): switching works while a large window is drawing shows the new work without waiting for the window.
    // A cancelled window still finishes the tiles in flight, at most one round of them: the window is the largest
    // the core draws (64 tiles), so one round is well under half of it, and it is cancelled mid-drawing.
    let deep = DisplayRegion(fullWidth: 12_000, fullHeight: 12_000, x: 4000, y: 4000, width: 4096, height: 4096)
    let deepPlan = CanvasDetailPlan(fullWidth: 12_000, fullHeight: 12_000, x: 4000, y: 4000, width: 4096, height: 4096)
    let windowStarted = ContinuousClock.now
    for try await _ in DisplayRenderer().window(svg: svg, region: deep) {}
    let windowAlone = ContinuousClock.now - windowStarted
    let zoomed = CanvasPicture()
    let zoomRenderer = DisplayRenderer()
    await zoomed.load(svg: svg, width: 1000, height: 1000, renderer: zoomRenderer)
    let deepTask = Task { await zoomed.loadWindow(svg: svg, plan: deepPlan, renderer: zoomRenderer) }
    try await waitUntil("the first tiles of the window") { zoomed.pendingWindow != nil }
    deepTask.cancel()
    zoomed.clear()
    let windowSwitched = ContinuousClock.now
    await zoomed.load(svg: next, width: 640, height: 640, renderer: zoomRenderer)
    let afterWindow = ContinuousClock.now - windowSwitched
    await deepTask.value
    guard zoomed.imageSVG == next, zoomed.window == nil, zoomed.pendingWindow == nil, !zoomed.windowLoading,
          zoomRenderer.diagnostics().skiaWindows == 0 else {
        throw fail("After switching during a window the canvas shows \(zoomed.imageSVG == next ? "the new work" : "another picture"), "
            + "window \(zoomed.window != nil), loading \(zoomed.windowLoading), windows finished \(zoomRenderer.diagnostics().skiaWindows)")
    }
    guard afterWindow < windowAlone / 2 else {
        throw fail("The new work took \(afterWindow); the window alone takes \(windowAlone)")
    }

    // C5 (zoom): after a cancelled window, a new zoom is requested and drawn.
    let shallow = CanvasDetailPlan(fullWidth: 2000, fullHeight: 2000, x: 500, y: 600, width: 900, height: 700)
    await zoomed.load(svg: svg, width: 1000, height: 1000, renderer: zoomRenderer)
    let cancelledWindow = Task { await zoomed.loadWindow(svg: svg, plan: deepPlan, renderer: zoomRenderer) }
    try await waitUntil("the window to start") { zoomed.windowLoading }
    cancelledWindow.cancel()
    await cancelledWindow.value
    guard !zoomed.windowLoading else { throw fail("The progress mark stayed after the window was cancelled") }
    await zoomed.loadWindow(svg: svg, plan: shallow, renderer: zoomRenderer)
    guard let shown = zoomed.window, shown.unit == CanvasDetailPlan.unit(of: shallow.region), zoomed.pendingWindow == nil,
          !zoomed.windowLoading else {
        throw fail("A new zoom after a cancelled window was not drawn")
    }

    print("Display canvas passed: Skia, coarse then \(tileCount) tiles (worst block \(worstBlock)), "
        + "resvg fallback counted; new work in \(nextTook) while the left whole takes \(largeAlone) alone; "
        + "no progress mark after cancelling; window in \(windowFrames.count - 1) steps (worst block \(windowBlock)); "
        + "new work in \(afterWindow) while the window takes \(windowAlone) alone; a new zoom drawn after a cancelled window.")
}

/// The premultiplied RGBA pixels of a rectangle of a raster.
private func crop(_ image: RasterImage, x: Int, y: Int, width: Int, height: Int) -> Data {
    var out = Data(capacity: width * height * 4)
    for row in y..<(y + height) {
        let start = row * Int(image.stride) + x * 4
        out.append(image.pixels[start..<(start + width * 4)])
    }
    return out
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
