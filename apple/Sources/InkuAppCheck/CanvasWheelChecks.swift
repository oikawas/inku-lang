import CoreGraphics
import InkuCore
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
func runCanvasDetailChecks() throws {
    // Failure (C3): a zoomed canvas enlarges the fitted whole instead of drawing the visible window at the screen's
    // density, the window lands off its place, or a deep zoom asks the core for more than it draws.
    let limits = InkuCore.displayLayout
    let area = CGSize(width: 818, height: 597)
    let picture = CanvasInteraction.fittedPicture(aspect: 1, in: CGRect(x: 159, y: 48.5, width: 500, height: 500))
    let plan = CanvasInteraction.detailPlan(picture: picture, area: area, scale: 5, offset: CGSize(width: 300, height: 0),
                                            pixelScale: 2, limits: limits)
    guard picture == CGRect(x: 159, y: 48.5, width: 500, height: 500),
          CanvasInteraction.detailPlan(picture: picture, area: area, scale: 1, offset: .zero, pixelScale: 2, limits: limits) == nil,
          let plan, plan.fullWidth == 5_000, plan.fullHeight == 5_000,
          plan.width == 1_636, plan.height == 1_194, plan.x == 1_082, plan.y == 1_903 else {
        throw CheckFailure.message("Zoomed canvas window is not drawn at the screen density: \(String(describing: plan))")
    }
    // A large screen at 1000%: still the screen's density, inside the core's limits.
    let wide = CGSize(width: 2_560, height: 1_600)
    let large = CanvasInteraction.fittedPicture(aspect: 1, in: CGRect(x: 530, y: 50, width: 1_500, height: 1_500))
    guard let deep = CanvasInteraction.detailPlan(picture: large, area: wide, scale: 10, offset: .zero, pixelScale: 2, limits: limits),
          deep.fullWidth == 30_000, deep.fullWidth <= limits.maxCanvasSide, deep.width == 5_120, deep.height == 3_200,
          deep.width <= limits.maxWindowSide, UInt64(deep.width) * UInt64(deep.height) <= limits.maxWindowPixels,
          abs(CanvasDetailPlan.unit(of: deep.region).width - wide.width / (large.width * 10)) < 0.001,
          abs(CanvasDetailPlan.unit(of: deep.region).height - wide.height / (large.height * 10)) < 0.001 else {
        throw CheckFailure.message("A deep zoom's window leaves the core's limits or stops covering the screen")
    }
    print("Canvas detail passed: 818×597, 500pt picture at 500% panned 300pt on a 2× display → 1636×1194 window of 5000×5000 (2 px/pt); none at 100%; 2560×1600 at 1000% → \(deep.width)×\(deep.height) of \(deep.fullWidth)×\(deep.fullHeight), inside the core's limits.")
}
