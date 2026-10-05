import CryptoKit
import Foundation
import ImageIO
import InkuHost
import InkuPersistence
import XCTest
@testable import InkuExport

final class ServerExportParityChecks: XCTestCase, @unchecked Sendable {
    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

    // Failure (D17): an exported PNG carries no capture date; Web writes eXIf and tEXt from the work's time.
    func testPNGCaptureDateMatchesWebBytes() throws {
        let png = Data([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0,
                        0x1f, 0x15, 0xc4, 0x89, 0, 0, 0, 0, 0x49, 0x45, 0x4e, 0x44, 0xae, 0x42, 0x60, 0x82])
        let date = Date(timeIntervalSince1970: 1_791_180_428) // 2026-10-05T06:07:08Z
        // Web pngMetadata.ts withPngCaptureDate under node with TZ set, same input bytes.
        for (zone, expected) in [("Asia/Tokyo", "4d32620078748edfb40d4640a1d821647d2e8c5db460b7e29daa3ede58d8ae5b"),
                                 ("America/Los_Angeles", "def07f46bc08c5df96f2997ff70f6c804edfedc583088df408df2101fa66d1f5")] {
            let stamped = PNGCaptureDate.stamp(png, date: date, timeZone: TimeZone(identifier: zone)!)
            XCTAssertEqual(stamped.count, 257, zone)
            XCTAssertEqual(digest(stamped), expected, zone)
        }
        XCTAssertEqual(PNGCaptureDate.stamp(Data("not a png".utf8), date: date), Data("not a png".utf8))

        // The export path stamps the work's own time, and ImageIO reads it back as EXIF.
        let svg = #"<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 8 8"><rect width="8" height="8" fill="red"/></svg>"#
        let work = SavedWork(id: "stamped", at: 1_791_180_428_000, input: "a drawing", score: "{}", svg: svg)
        var options = ExportOptions(); options.format = .png; options.pixelHeight = 64
        let exported = try XCTUnwrap(ExportService.render(sources: [ExportSource(work: work)], options: options).first).data
        let source = try XCTUnwrap(CGImageSourceCreateWithData(exported as CFData, nil))
        let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        let exif = properties?[kCGImagePropertyExifDictionary] as? [CFString: Any]
        XCTAssertNotNil(exif?[kCGImagePropertyExifDateTimeOriginal])
    }

    // Failure (D17): the DDL export names work_id/render_hash and refuses a malformed saved plugin; Server writes
    // {build_number, render_engine_version} and skips that definition.
    func testDDLExportFollowsServer() throws {
        var work = SavedWork(id: "w", at: 1, input: "a", score: "{}", svg: "<svg/>")
        work.ddl = "地: 白\n[x.dot] 赤"; work.renderEngineVersion = "rust-1"; work.renderHash = "hash"
        let good: ExactJSON = .object(["namespace": .string("x"), "heading": .string("dot")])
        let bad: ExactJSON = .object(["namespace": .integer(1), "heading": .string("dot")])
        let source = ExportSource(work: work, pluginDefinitions: [bad, good], pluginSummaries: ["bad", "good"], language: "ja")
        let value = try ExactJSON(data: ExportService.ddl(source, buildNumber: "7"))
        XCTAssertEqual(value["exported_from"], .object(["build_number": .string("7"), "render_engine_version": .string("rust-1")]))
        XCTAssertEqual(value["plugins"], .array([.object(["definition": good, "summary": .string("good")])]))
        let unset = try ExactJSON(data: ExportService.ddl(source, buildNumber: nil))
        XCTAssertEqual(unset["exported_from"]["build_number"], .null)
    }
}
