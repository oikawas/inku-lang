import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import InkuHost
import InkuPersistence
import InkuUI

/// A missing or changed image must never become a description or persisted image bytes.
@MainActor
func runImageChecks(realOpus: Bool = false) async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-image-check-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let url = folder.appendingPathComponent("works.sqlite")
    let transport = ImageCheckProvider()
    let app = AppModel(databaseURL: url, transport: realOpus ? nil : transport)
    await app.initialize()
    var settings = await app.hostSettings()
    let providerID = realOpus ? "anthropic" : "fixture"
    let modelID = realOpus ? "claude-opus-5-5" : "vision"
    let reference = providerID + ":" + modelID
    settings.providers = [ProviderSettings(id: providerID, kind: .anthropic,
        baseURL: URL(string: realOpus ? "https://api.anthropic.com" : "https://example.invalid")!, requiresAPIKey: realOpus,
        models: [ProviderModelSettings(id: modelID, purposes: ["vision"])])]
    settings.models.stage1Model = reference; settings.models.stage2Model = reference
    try await app.updateHostSettings(settings)
    app.display.preferences.visionModelReference = reference
    let canvas = try XCTImage.context(width: 4000, height: 3000)
    canvas.setFillColor(CGColor(gray: 1, alpha: 1)); canvas.fill(CGRect(x: 0, y: 0, width: 4000, height: 3000))
    canvas.setFillColor(CGColor(red: 0.8, green: 0.1, blue: 0.1, alpha: 1))
    canvas.fillEllipse(in: CGRect(x: 1500, y: 1000, width: 1000, height: 1000))
    guard let image = canvas.makeImage() else { throw CheckFailure.message("image fixture") }
    let bytes = NSMutableData()
    guard let destination = CGImageDestinationCreateWithData(bytes, UTType.jpeg.identifier as CFString, 1, nil) else { throw CheckFailure.message("image fixture encoder") }
    CGImageDestinationAddImage(destination, image, [
        kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2026:10:27 12:34:56"],
        kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 35.1234, kCGImagePropertyGPSLongitude: 139.1234]
    ] as CFDictionary)
    guard CGImageDestinationFinalize(destination) else { throw CheckFailure.message("image fixture encoding") }
    let imageURL = folder.appendingPathComponent("example.jpg")
    try (bytes as Data).write(to: imageURL)
    let prepared = try ImageInput.prepare(bytes as Data)
    guard prepared.width == 1568, prepared.height == 1176, prepared.nearestFormatID == "sd_monitor" else { throw CheckFailure.message("image canvas") }
    app.newWork(); app.inputMode = "image"; app.canvasID = "square"
    guard app.imageCanvasID == "image" else { throw CheckFailure.message("image paper default") }
    app.setImageInput(prepared, fileName: imageURL.lastPathComponent)
    guard app.canvasID == "square" else { throw CheckFailure.message("image changed description paper") }
    let automatic = try app.requestForImage(prepared, provenance: "")
    guard try ExactJSON(data: automatic.renderOptions)["canvas_aspect_id"].string == "sd_monitor" else {
        throw CheckFailure.message("automatic image paper")
    }
    app.imageCanvasID = "square"
    let fixed = try app.requestForImage(prepared, provenance: "")
    guard try ExactJSON(data: fixed.renderOptions)["canvas_aspect_id"].string == "square" else {
        throw CheckFailure.message("fixed image paper")
    }
    app.imageCanvasID = "image"
    app.imageProvenance = ImageProvenance.text(url: imageURL, includeFileName: true, includeExif: true, language: "ja")
    guard app.imageProvenance.contains("撮影日時: 2026:10:27 12:34:56"),
          app.imageProvenance.contains("ファイル名: example.jpg"), !app.imageProvenance.contains("35.1234"),
          !app.imageProvenance.contains("139.1234") else { throw CheckFailure.message("image Exif provenance") }
    await app.generate()
    guard let work = app.selectedWork, let ddl = work.ddl, ddl.contains("画面比4:3"), work.effectiveSourceText.isEmpty,
          work.renderCanvasAspectID == "sd_monitor" else {
        throw CheckFailure.message("image run: \(app.errorText ?? app.status)")
    }
    let context = try await app.savedConfiguration(workID: work.id)
    guard context.authority == "ddl_authoritative", context.imageProvenance == app.imageProvenance,
          let record = context.imageDDL, !String(decoding: record, as: UTF8.self).contains("data:image"),
          try ExactJSON(data: record)["image"]["sent"]["sha256"].string == prepared.sha256 else {
        throw CheckFailure.message("image saved context")
    }
    let calls = await transport.tags
    if !realOpus, calls != ["write_image_ddl", "review_image_ddl"] { throw CheckFailure.message("image provider stages: \(calls)") }
    if !realOpus, await transport.provenanceLeaked { throw CheckFailure.message("image provenance entered provider action") }
    if !realOpus {
        let imageRecord = try ExactJSON(data: record)
        guard let before = imageRecord["before_review"].string, before == ddl else { throw CheckFailure.message("pre-review same-DDL fixture") }
        app.canvasFitChoiceHandler = { _ in .contain }
        guard await app.drawEditedDDL(work: work, source: before, paperID: "square", forceEdit: true),
              let child = app.selectedWork, child.id != work.id, let node = child.lineageNodeID else {
            throw CheckFailure.message("pre-review DDL child: \(app.errorText ?? app.status)")
        }
        let db = try InkuDatabase(url: url)
        let edge = try await db.edge(childNodeID: node)
        let childContext = try await app.savedConfiguration(workID: child.id)
        guard edge?.derivationKind == "ddl_edit", childContext.imageProvenance == context.imageProvenance,
              childContext.imageDDL == context.imageDDL, try await db.work(id: work.id) == work else {
            throw CheckFailure.message("pre-review child did not preserve its parent and provenance")
        }
    }
    print(realOpus ? "Opus image run: one synthetic image, saved image metadata and 4:3 declaration." :
          "Image run: 1568×1176, nearest 4:3 paper, image write/review and saved metadata; no external provider.")
}

private enum XCTImage {
    static func context(width: Int, height: Int) throws -> CGContext {
        guard let value = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { throw CheckFailure.message("image context") }
        return value
    }
}
private actor ImageCheckProvider: ProviderTransport {
    var tags: [String] = []
    var provenanceLeaked = false
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let value = try ExactJSON(data: action)
        if String(decoding: action, as: UTF8.self).contains("2026:10:27 12:34:56") { provenanceLeaked = true }
        let actionTag = try value.requiredString("tag"); tags.append(actionTag)
        let tag = actionTag == "write_image_ddl" ? "image_ddl_written" : "image_ddl_reviewed"
        return ExactJSON.object(["tag": .string(tag), "identity": value["identity"],
            "response": .string(#"{"ddl":"赤い円を1個置く。"}"#), "elapsed_ms": .string("1")]).data
    }
}
