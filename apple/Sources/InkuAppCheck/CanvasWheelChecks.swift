import CoreGraphics
import InkuUI

@MainActor
func runCanvasWheelChecks() throws {
    // Failure: no wheel interaction; fitting a panned work retained its old offset.
    let enlarged = CanvasInteraction.wheelScale(from: 1, deltaY: 3)
    let reduced = CanvasInteraction.wheelScale(from: 1, deltaY: -3)
    let displaced = CGSize(width: 60, height: -25)
    guard abs(enlarged - 1.15) < 0.000001, abs(reduced - 0.85) < 0.000001,
          CanvasInteraction.wheelScale(from: 9.95, deltaY: 1) == 10,
          CanvasInteraction.wheelScale(from: 0.3, deltaY: -1) == 0.25,
          CanvasInteraction.wheelScale(from: 2, deltaY: 0) == 2,
          CanvasInteraction.offset(for: enlarged, current: displaced) == displaced,
          CanvasInteraction.offset(for: reduced, current: displaced) == .zero else {
        throw CheckFailure.message("Canvas wheel directions, fixed Web scale bounds or fit recentering changed")
    }
    print("Canvas wheel scale passed: ±15 points, 25–1000% bounds, horizontal-only input ignored, fit recenters a panned work. Native event delivery remains a UI check.")
}

@MainActor
func runCanvasFitChecks() throws {
    // Failure: the workspace canvas shrinks again inside an outer margin and frame (346pt at 1320×880),
    // or sizes a wide work from a square box instead of its saved proportion.
    let square = CanvasInteraction.webFit(area: CGSize(width: 818, height: 597), ratio: 1)
    let wide = CanvasInteraction.webFit(area: CGSize(width: 1000, height: 597), ratio: 2)
    guard square.zoom == 1.25, square.box == CGSize(width: 500, height: 500),
          wide.zoom == 2.2, abs(wide.box.width - 880) < 0.001, abs(wide.box.height - 440) < 0.001 else {
        throw CheckFailure.message("Canvas fit no longer follows the Web formula: square \(square), wide \(wide)")
    }
    print("Canvas fit passed: 818×597 square → 500pt (zoom 1.25); 1000×597 at 2:1 → 880×440 (zoom 2.2, width-bound).")
}

@MainActor
func runCanvasDetailChecks() async throws {
    // Failure: a zoomed canvas enlarges the fitted bitmap (capped at 3× and 8M pixels) instead of redrawing the
    // SVG, so 500% on a 2× display showed about 0.5 pixel per screen pixel; or the window lands off its place.
    let area = CGSize(width: 818, height: 597)
    let picture = CanvasInteraction.fittedPicture(aspect: 1, in: CGRect(x: 159, y: 48.5, width: 500, height: 500))
    guard picture == CGRect(x: 159, y: 48.5, width: 500, height: 500),
          CanvasInteraction.detailPlan(picture: picture, area: area, scale: 1, offset: .zero, pixelScale: 2) == nil,
          let plan = CanvasInteraction.detailPlan(picture: picture, area: area, scale: 5, offset: CGSize(width: 300, height: 0), pixelScale: 2),
          plan.fullWidth == 5_000, plan.fullHeight == 5_000,
          plan.width == 1_636, plan.height == 1_194,
          plan.x == 1_082, plan.y == 1_903 else {
        throw CheckFailure.message("Zoomed canvas window is not drawn at the screen density: \(String(describing: CanvasInteraction.detailPlan(picture: picture, area: area, scale: 5, offset: CGSize(width: 300, height: 0), pixelScale: 2)))")
    }
    let svg = ##"<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="#fff"/><circle cx="13" cy="27" r="9" fill="#123456"/><path d="M2 3 L38 31" stroke="#c03" stroke-width="1.5"/></svg>"##
    let renderer = ArtworkRenderer()
    let whole = try await renderer.image(svg: svg, targetWidth: 400, targetHeight: 400)
    let window = try await renderer.region(svg: svg, fullWidth: 400, fullHeight: 400, x: 90, y: 170, width: 120, height: 80)
    // The window's transform differs from the whole picture's, so antialiased edges may move by a few levels;
    // a misplaced window would differ along the whole circle edge.
    let crop = whole.cropping(to: CGRect(x: 90, y: 170, width: 120, height: 80)).map(pixels) ?? []
    let diffs = zip(crop, pixels(window)).map { abs(Int($0) - Int($1)) }
    let differing = diffs.filter { $0 > 0 }.count
    guard crop.count == 38_400, diffs.count == crop.count, diffs.max() ?? 255 <= 64, differing * 100 <= diffs.count else {
        throw CheckFailure.message("A canvas window differs from the same pixels of the whole picture: \(differing)/\(diffs.count) bytes, max \(diffs.max() ?? -1)")
    }
    print("Canvas detail passed: 818×597, 500pt picture at 500% panned 300pt on a 2× display → 1636×1194 window of 5000×5000 (2 px/pt); none at 100%; a 120×80 window matches the whole picture (\(differing)/\(diffs.count) bytes differ, max \(diffs.max() ?? 0)).")
}

private func pixels(_ image: CGImage) -> [UInt8] {
    var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
    let context = CGContext(data: &bytes, width: image.width, height: image.height, bitsPerComponent: 8, bytesPerRow: image.width * 4,
                            space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    context?.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    return bytes
}
