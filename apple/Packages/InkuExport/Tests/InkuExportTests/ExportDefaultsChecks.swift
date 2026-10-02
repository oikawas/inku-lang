import CoreGraphics
import Foundation
import ImageIO
import InkuPersistence
import XCTest
@testable import InkuExport

final class ExportDefaultsChecks: XCTestCase, @unchecked Sendable {
    // Failure: persisted animation/card/profile/template defaults reset, or the PNG white-background choice preserves transparent pixels.
    func testPersistedDefaultsAndWhitePNGKeepTheirActualBehavior() throws {
        var options = ExportOptions()
        options.format = .gif; options.svgProfile = "compat"; options.pngAlphaWhite = true
        options.cardLayout = "portrait"; options.cardSeal = false; options.transition = "slide"
        options.holdSeconds = 4.2; options.layerFrameCount = 29; options.layerIntervalSeconds = 0.7; options.layerReplay = "reverse"
        options.title = "詞書e\u{301}"; options.subtitle = "試作"
        var configuration = ExportConfiguration(options: options, resolution: 0, customHeight: 12000).normalized()
        configuration.destinationBookmark = Data([1, 2, 3]); configuration.destinationName = "作品"
        XCTAssertEqual(try JSONDecoder().decode(ExportConfiguration.self, from: JSONEncoder().encode(configuration)), configuration)
        let partial = try JSONDecoder().decode(ExportConfiguration.self, from: Data("{\"options\":{\"layerFrameCount\":999,\"svgProfile\":\"unknown\"}}".utf8))
        XCTAssertEqual(partial.options.layerFrameCount, 120); XCTAssertEqual(partial.options.svgProfile, "display")
        XCTAssertNil(partial.destinationBookmark)
        XCTAssertEqual(ExportTemplate.normalized([.init(id: "png-1024", pixelHeight: 1024), .init(id: "png-2048", pixelHeight: 2048)]), ExportTemplate.defaults)
        let template = ExportTemplate(name: "小さい絵", description: "透明", pixelHeight: 67)
        XCTAssertEqual(try JSONDecoder().decode(ExportTemplate.self, from: JSONEncoder().encode(template)), template)
        let svg = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"2\"><rect width=\"1\" height=\"1\" fill=\"red\"/></svg>"
        let work = SavedWork(id: "white-choice", at: 1, input: "透明", score: "{}", svg: svg)
        options.format = .png; options.pixelHeight = 64
        let bytes = try ExportService.render(sources: [ExportSource(work: work)], options: options)[0].data
        let decoder = try XCTUnwrap(CGImageSourceCreateWithData(bytes as CFData, nil))
        let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoder, 0, nil))
        let context = try ExportRaster.bitmap(width: image.width, height: image.height)
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        let canonicalPixels = try XCTUnwrap(context.makeImage()?.dataProvider?.data) as Data
        XCTAssertEqual(Array(canonicalPixels.suffix(4)), [255, 255, 255, 255])
        XCTAssertEqual(work.svg, svg)
    }
}
