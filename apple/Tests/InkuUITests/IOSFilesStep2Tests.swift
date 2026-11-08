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
        XCTAssertTrue(fromFile.contains("カメラ: Inku Test"), fromFile)

        // A photo has no file name: only the camera fields remain.
        let photo = ImageProvenance.text(data: data, fileName: nil, includeFileName: true, includeExif: true, language: "ja")
        XCTAssertEqual(photo, fromFile.split(separator: "\n").dropFirst().joined(separator: "\n"))
    }

    func testBackupGenerationDefaultOnThisPlatform() {
        #if os(macOS)
        XCTAssertEqual(BackupSchedule().maxGenerations, 4)
        #else
        XCTAssertEqual(BackupSchedule().maxGenerations, 1)
        #endif
        XCTAssertFalse(DisplayPreferences().automaticBackup)
    }

    private static func jpegWithExif() throws -> Data {
        let context = try XCTUnwrap(CGContext(data: nil, width: 4, height: 3, bitsPerComponent: 8, bytesPerRow: 0,
                                              space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(CGColor(red: 1, green: 0, blue: 0, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 4, height: 3))
        let image = try XCTUnwrap(context.makeImage())
        let data = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil))
        let properties: [CFString: Any] = [
            kCGImagePropertyTIFFDictionary: [kCGImagePropertyTIFFMake: "Inku", kCGImagePropertyTIFFModel: "Test"],
            kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2026:11:08 18:30:00", kCGImagePropertyExifFNumber: 2.8],
        ]
        CGImageDestinationAddImage(destination, image, properties as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        return data as Data
    }
}
