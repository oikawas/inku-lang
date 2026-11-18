import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import InkuUI

/// iOS plan step 2: a photo's bytes give the same provenance as its file, and the backup default stays the Web's 4
/// where these tests run (macOS); iOS keeps 1 (author, 2026-11-08).
final class IOSFilesStep2Tests: XCTestCase {
    func testProvenanceFromBytesMatchesTheFile() throws {
        let data = try Self.jpegWithExif()
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("inku-provenance-\(UUID().uuidString).jpg")
        try data.write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }

        let fromFile = ImageProvenance.text(url: url, includeFileName: true, includeExif: true, language: "ja")
        let fromBytes = ImageProvenance.text(data: data, fileName: url.lastPathComponent, includeFileName: true, includeExif: true, language: "ja")
        XCTAssertEqual(fromBytes, fromFile)
        XCTAssertEqual(fromFile, "ファイル名: \(url.lastPathComponent) · 2026:10:20 14:32:05\nApple iPhone 15 Pro · f/1.8 · 1/120 s · ISO 64 · 6.9 mm")

        // A photo has no file name: only the camera fields remain.
        let photo = ImageProvenance.text(data: data, fileName: nil, includeFileName: true, includeExif: true, language: "ja")
        XCTAssertEqual(photo, "2026:10:20 14:32:05\nApple iPhone 15 Pro · f/1.8 · 1/120 s · ISO 64 · 6.9 mm")
        XCTAssertEqual(ImageProvenance.text(data: data, fileName: "x.jpg", includeFileName: true, includeExif: false, language: "ja"), "ファイル名: x.jpg")
        XCTAssertEqual(ImageProvenance.text(data: data, fileName: "x.jpg", includeFileName: false, includeExif: false, language: "ja"), "")
        let other = try Self.jpegWithExif(properties: [
            kCGImagePropertyTIFFDictionary: [kCGImagePropertyTIFFMake: "Canon", kCGImagePropertyTIFFModel: "Canon EOS R5",
                                            kCGImagePropertyTIFFDateTime: "2026:10:20 14:32:05"],
            kCGImagePropertyExifDictionary: [kCGImagePropertyExifFNumber: 4.0, kCGImagePropertyExifExposureTime: 2.0,
                                            kCGImagePropertyExifFocalLength: 24.0, kCGImagePropertyExifLensModel: "hidden lens"]
        ])
        XCTAssertEqual(ImageProvenance.text(data: other, fileName: "x.jpg", includeFileName: true, includeExif: true, language: "en"),
                       "File name: x.jpg · 2026:10:20 14:32:05\nCanon EOS R5 · f/4 · 2 s · 24 mm")
    }

    func testBackupGenerationDefaultOnThisPlatform() {
        #if os(macOS)
        XCTAssertEqual(BackupSchedule().maxGenerations, 4)
        #else
        XCTAssertEqual(BackupSchedule().maxGenerations, 1)
        #endif
        XCTAssertFalse(DisplayPreferences().automaticBackup)
    }

    private static func jpegWithExif(properties: [CFString: Any]? = nil) throws -> Data {
        let context = try XCTUnwrap(CGContext(data: nil, width: 4, height: 3, bitsPerComponent: 8, bytesPerRow: 0,
                                              space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(CGColor(red: 1, green: 0, blue: 0, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 4, height: 3))
        let image = try XCTUnwrap(context.makeImage())
        let data = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil))
        let defaults: [CFString: Any] = [
            kCGImagePropertyTIFFDictionary: [kCGImagePropertyTIFFMake: "Apple", kCGImagePropertyTIFFModel: "iPhone 15 Pro"],
            kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2026:10:20 14:32:05", kCGImagePropertyExifFNumber: 1.78,
                                            kCGImagePropertyExifExposureTime: 1.0 / 120.0, kCGImagePropertyExifISOSpeedRatings: [64],
                                            kCGImagePropertyExifFocalLength: 6.86],
        ]
        CGImageDestinationAddImage(destination, image, (properties ?? defaults) as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        return data as Data
    }
}
