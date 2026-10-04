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
