import Foundation
import CoreGraphics
import ImageIO
import InkuHost
import UniformTypeIdentifiers
import XCTest
@testable import InkuUI

/// The iPhone tab bar's camera draws with the image defaults, not the image tab's choice (author 2026-11-13).
@MainActor final class CameraDrawTests: XCTestCase {
    private func makeApp() async throws -> (AppModel, URL) {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-camera-\(UUID())")
        let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"))
        await app.initialize()
        let service = ProviderSettings(id: "camera", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false,
            models: [.init(id: "drawing"), .init(id: "default-eye", purposes: ["vision"]), .init(id: "tab-eye", purposes: ["vision"])])
        try await app.updateHostSettings(HostSettings(providers: [service], models: .init(stage1Model: "camera:drawing", stage2Model: "camera:drawing")))
        return (app, directory)
    }

    private func setDefaultVision(_ reference: String, app: AppModel) throws {
        var defaults = app.drawDefaults
        defaults["image"]?.models.vision = reference
        try app.saveDrawDefaults(defaults)
    }

    private func photo() throws -> Data {
        let context = try XCTUnwrap(CGContext(data: nil, width: 30, height: 20, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        let jpeg = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(jpeg, UTType.jpeg.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, try XCTUnwrap(context.makeImage()), nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        return jpeg as Data
    }

    func testCameraDrawsWithTheImageDefaultsNotTheTabChoice() async throws {
        let (app, directory) = try await makeApp()
        defer { try? FileManager.default.removeItem(at: directory) }
        try setDefaultVision("camera:default-eye", app: app)
        let defaults = try XCTUnwrap(app.drawDefaults["image"])
        // The image tab chose another model and paper before the camera was pressed.
        app.activeDrawTab = "image"; app.inputMode = "image"
        app.selectImageVisionModel("camera:tab-eye")
        app.imageCanvasID = try XCTUnwrap(app.canvases.first { $0.id != defaults.canvasAspect }?.id)
        XCTAssertNotEqual(app.drawSelections["image"], defaults)

        let refusal = await app.cameraDrawRefusal(otherRunActive: false)
        XCTAssertNil(refusal)
        let prepared = try app.preparedImage(data: photo(), fileName: nil)
        app.prepareCameraDraw(prepared.image, provenance: prepared.provenance)

        XCTAssertEqual(app.drawSelections["image"], defaults)
        XCTAssertTrue(app.canGenerate)
        let request = try app.requestForImage(try XCTUnwrap(app.imageInput), provenance: app.imageProvenance)
        XCTAssertEqual(request.models.stage1Model, "camera:default-eye")
        XCTAssertEqual(request.models.stage2Model, "camera:default-eye")
    }

    func testCameraRefusesBeforeThePhotoWhenTheDefaultCannotDraw() async throws {
        let (app, directory) = try await makeApp()
        defer { try? FileManager.default.removeItem(at: directory) }
        // The core fills an empty default with the release one, whose service is not connected here.
        try setDefaultVision("", app: app)
        let filled = try XCTUnwrap(app.drawDefaults["image"]?.models.vision)
        XCTAssertFalse(filled.isEmpty)
        XCTAssertFalse(filled.hasPrefix("camera:"))
        let empty = await app.cameraDrawRefusal(otherRunActive: false)
        XCTAssertEqual(empty, .modelUnavailable(filled))
        // A model the image tab can still pick does not make the camera's default drawable.
        app.activeDrawTab = "image"
        app.selectImageVisionModel("camera:tab-eye")
        try setDefaultVision("camera:gone-eye", app: app)
        XCTAssertEqual(app.drawDefaults["image"]?.models.vision, "camera:gone-eye")
        let gone = await app.cameraDrawRefusal(otherRunActive: false)
        XCTAssertEqual(gone, .modelUnavailable("camera:gone-eye"))
        try setDefaultVision("camera:default-eye", app: app)
        let busy = await app.cameraDrawRefusal(otherRunActive: true)
        XCTAssertEqual(busy, .busy)
    }
}
