import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import InkuUI

final class PlatformImageTests: XCTestCase {
    // Failure: moving preview decoding from platform images loses the PNG's dimensions.
    func testPNGDimensionsSurviveSharedDecode() throws {
        let context = try XCTUnwrap(CGContext(data: nil, width: 7, height: 3, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 7, height: 3))
        let png = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(png, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, try XCTUnwrap(context.makeImage()), nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let image = try XCTUnwrap(PlatformImage.load(data: png as Data))
        XCTAssertEqual(image.width, 7)
        XCTAssertEqual(image.height, 3)
    }
}
