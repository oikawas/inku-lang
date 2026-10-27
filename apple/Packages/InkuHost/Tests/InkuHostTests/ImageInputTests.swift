import XCTest
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
@testable import InkuHost

final class ImageInputTests: XCTestCase {
    func testOrientationAndTransparentPaper() throws {
        let context = try XCTUnwrap(CGContext(data: nil, width: 200, height: 100, bitsPerComponent: 8,
            bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.clear(CGRect(x: 0, y: 0, width: 200, height: 100))
        let sourceImage = try XCTUnwrap(context.makeImage())
        let bytes = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(bytes, UTType.tiff.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, sourceImage, [kCGImagePropertyOrientation: 6] as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let prepared = try ImageInput.prepare(bytes as Data)
        XCTAssertEqual(prepared.originalWidth, 100)
        XCTAssertEqual(prepared.originalHeight, 200)
        let decoded = try XCTUnwrap(CGImageSourceCreateWithData(prepared.jpeg as CFData, nil))
        let jpeg = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoded, 0, nil))
        let sample = try XCTUnwrap(CGContext(data: nil, width: 1, height: 1, bitsPerComponent: 8,
            bytesPerRow: 4, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        sample.draw(jpeg, in: CGRect(x: 0, y: 0, width: 1, height: 1))
        let pixel = try XCTUnwrap(sample.data).assumingMemoryBound(to: UInt8.self)
        XCTAssertGreaterThan(pixel[0], 245); XCTAssertGreaterThan(pixel[1], 245); XCTAssertGreaterThan(pixel[2], 245)
    }
    func testLandscapeIsPreparedUsingCoreCanvas() throws {
        let context = try XCTUnwrap(CGContext(data: nil, width: 4000, height: 3000, bitsPerComponent: 8,
                                               bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                               bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 4000, height: 3000))
        let image = try XCTUnwrap(context.makeImage())
        let bytes = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(bytes, UTType.jpeg.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let prepared = try ImageInput.prepare(bytes as Data)
        XCTAssertEqual(prepared.originalWidth, 4000)
        XCTAssertEqual(prepared.originalHeight, 3000)
        XCTAssertEqual(prepared.width, 1568)
        XCTAssertEqual(prepared.height, 1176)
        XCTAssertEqual(prepared.nearestFormatID, "sd_monitor")
        XCTAssertLessThanOrEqual(prepared.jpeg.count, 4 * 1024 * 1024)
        func jpegAtQuality(_ quality: Double) throws -> Data {
            let output = NSMutableData()
            let encoder = try XCTUnwrap(CGImageDestinationCreateWithData(output, UTType.jpeg.identifier as CFString, 1, nil))
            CGImageDestinationAddImage(encoder, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
            XCTAssertTrue(CGImageDestinationFinalize(encoder))
            return output as Data
        }
        XCTAssertEqual(try quantizationTables(prepared.jpeg), try quantizationTables(jpegAtQuality(0.9)))
        XCTAssertNotEqual(try quantizationTables(prepared.jpeg), try quantizationTables(jpegAtQuality(0.75)))
    }

    private func quantizationTables(_ data: Data) throws -> [Data] {
        let bytes = [UInt8](data)
        var offset = 2, tables: [Data] = []
        while offset + 4 <= bytes.count, bytes[offset] == 0xff {
            let marker = bytes[offset + 1]
            if marker == 0xda || marker == 0xd9 { break }
            let length = Int(bytes[offset + 2]) * 256 + Int(bytes[offset + 3])
            guard length >= 2, offset + 2 + length <= bytes.count else { throw HostError("invalid_jpeg") }
            if marker == 0xdb { tables.append(Data(bytes[(offset + 4)..<(offset + 2 + length)])) }
            offset += 2 + length
        }
        XCTAssertFalse(tables.isEmpty)
        return tables
    }
}
