import XCTest
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import InkuHost
import InkuPersistence
@testable import InkuUI

@MainActor final class ImageFolderBatchTests: XCTestCase {
    func testFailureContinuesAndReselectionResumesWithoutRepeatingSuccess() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-image-folder-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let input = root.appendingPathComponent("input")
        try FileManager.default.createDirectory(at: input, withIntermediateDirectories: true)
        let bad = input.appendingPathComponent("1.jpg"), good = input.appendingPathComponent("2.png")
        try Data("invalid".utf8).write(to: bad)
        let png = try makePNG(); try png.write(to: good)
        try png.write(to: input.appendingPathComponent(".hidden.png"))
        let nested = input.appendingPathComponent("nested")
        try FileManager.default.createDirectory(at: nested, withIntermediateDirectories: true)
        try png.write(to: nested.appendingPathComponent("3.png"))
        let hidden = input.appendingPathComponent(".hidden-folder")
        try FileManager.default.createDirectory(at: hidden, withIntermediateDirectories: true)
        try png.write(to: hidden.appendingPathComponent("4.png"))
        let transport = FolderProvider()
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"), transport: transport)
        await app.initialize()
        var settings = await app.hostSettings()
        settings.providers = [ProviderSettings(id: "fixture", kind: .anthropic, baseURL: URL(string: "https://example.invalid")!,
            requiresAPIKey: false, models: [ProviderModelSettings(id: "vision", purposes: ["vision"])])]
        settings.models.stage1Model = "fixture:vision"; settings.models.stage2Model = "fixture:vision"
        try await app.updateHostSettings(settings)
        app.display.preferences.visionModelReference = "fixture:vision"
        let batch = ImageFolderBatch(); try batch.select(input, app: app)
        XCTAssertEqual(batch.total, 3)
        app.imageCanvasID = "square"
        await batch.run(app: app, restart: false) { _ in "fixture" }
        XCTAssertEqual(batch.completed, 2); XCTAssertEqual(batch.failed, 1)
        let db = try InkuDatabase(url: root.appendingPathComponent("works.sqlite"))
        let fixedWorks = try await db.libraryPage(limit: 10).items.map(\.work)
        XCTAssertEqual(fixedWorks.count, 2)
        XCTAssertTrue(fixedWorks.allSatisfy { $0.renderCanvasAspectID == "square" })
        try png.write(to: bad)
        let portrait = try makePNG(width: 48, height: 64)
        try portrait.write(to: input.appendingPathComponent("4.png"))
        let portraitPaper = try ImageInput.prepare(portrait).nearestFormatID
        XCTAssertNotEqual(portraitPaper, "sd_monitor")
        let reopened = ImageFolderBatch(); try reopened.select(input, app: app)
        XCTAssertEqual(reopened.completed, 2)
        app.imageCanvasID = "image"
        await reopened.run(app: app, restart: false) { _ in "fixture" }
        XCTAssertEqual(reopened.completed, 4); XCTAssertEqual(reopened.failed, 0)
        let works = try await db.libraryPage(limit: 10).items.map(\.work)
        XCTAssertEqual(works.filter { $0.renderCanvasAspectID == "sd_monitor" }.count, 1)
        XCTAssertEqual(works.filter { $0.renderCanvasAspectID == portraitPaper }.count, 1)
        let calls = await transport.calls
        XCTAssertEqual(calls, 8)
    }

    private func makePNG(width: Int = 64, height: Int = 48) throws -> Data {
        let context = try XCTUnwrap(CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(CGColor(gray: 1, alpha: 1)); context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        let bytes = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(bytes, UTType.png.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, try XCTUnwrap(context.makeImage()), nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination)); return bytes as Data
    }
}
private actor FolderProvider: ProviderTransport {
    var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        let effect = try ExactJSON(data: action)
        let result = effect["tag"].string == "write_image_ddl" ? "image_ddl_written" : "image_ddl_reviewed"
        return ExactJSON.object(["tag": .string(result), "identity": effect["identity"],
            "response": .string(#"{"ddl":"赤い円を1個置く。"}"#), "elapsed_ms": .string("1")]).data
    }
}
