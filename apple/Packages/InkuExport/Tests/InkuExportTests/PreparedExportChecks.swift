import CoreGraphics
import Foundation
import InkuCore
import XCTest
@testable import InkuExport

final class PreparedExportChecks: XCTestCase, @unchecked Sendable {
    // Failure: a prepared tiled export uses viewBox aspect instead of the SVG viewport, or clips filter pixels at a seam.
    func testPreparedTilesUseCoreViewportAndPreserveFilteredPixels() throws {
        let svg = ##"<svg xmlns="http://www.w3.org/2000/svg" width="192" height="128" viewBox="0 0 96 96"><defs><filter id="ink" x="-30%" y="-30%" width="160%" height="160%"><feTurbulence baseFrequency="0.06" numOctaves="2" seed="9" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="3"/><feGaussianBlur stdDeviation="0.5"/></filter><clipPath id="page"><rect x="4" y="3" width="86" height="87"/></clipPath></defs><g clip-path="url(#page)"><path d="M3 5h90v80H3z" fill="#e65932" filter="url(#ink)"/></g></svg>"##
        let baseline = try InkuCore.rasterize(svg: svg, targetHeight: 256)
        let tiled = try ExportRaster.image(svg: svg, height: 256, forcedTileSide: 128)
        XCTAssertEqual(tiled.width, Int(baseline.width)); XCTAssertEqual(tiled.height, Int(baseline.height))
        XCTAssertEqual(tiled.dataProvider?.data as Data?, baseline.makeCGImage()?.dataProvider?.data as Data?)
    }
}
