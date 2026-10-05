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
