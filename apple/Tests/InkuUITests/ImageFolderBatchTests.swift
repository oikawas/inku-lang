import XCTest
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import InkuHost
import InkuPersistence
@testable import InkuUI

@MainActor final class ImageFolderBatchTests: XCTestCase {
    func testStopDuringPreparationDoesNotSendAndRemainsUncertain() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-image-stop-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let input = root.appendingPathComponent("input")
        try FileManager.default.createDirectory(at: input, withIntermediateDirectories: true)
        try makePNG().write(to: input.appendingPathComponent("one.png"))
        let transport = FolderProvider()
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"), transport: transport)
        await app.initialize()
        let gate = ImagePreparationGate()
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) { gate.release() }
        let batch = ImageFolderBatch(imagePreparer: { try gate.prepare($0) })
        try await batch.select(input, app: app)
        let operation = Task { await batch.run(app: app, restart: false) { _ in "fixture" } }
        for _ in 0..<200 {
            if gate.isWaiting() { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let started = gate.isWaiting()
        await batch.stop(app: app)
        gate.release()
        await operation.value
        XCTAssertTrue(started)
        XCTAssertEqual(batch.uncertain, 1)
        let calls = await transport.calls
        XCTAssertEqual(calls, 0)
        let reopened = ImageFolderBatch()
        try await reopened.select(input, app: app)
        XCTAssertEqual(reopened.uncertain, 1)
    }

    func testOversizedImageIsRejectedBeforeProviderRequest() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-image-large-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let input = root.appendingPathComponent("input")
        try FileManager.default.createDirectory(at: input, withIntermediateDirectories: true)
        let image = input.appendingPathComponent("large.png")
        XCTAssertTrue(FileManager.default.createFile(atPath: image.path, contents: nil))
        let handle = try FileHandle(forWritingTo: image)
        try handle.truncate(atOffset: UInt64(ImageInput.maximumRawBytes + 1))
        try handle.close()
        let transport = FolderProvider()
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"), transport: transport)
        await app.initialize()
        let batch = ImageFolderBatch()
        try await batch.select(input, app: app)
        await batch.run(app: app, restart: false) { _ in "fixture" }
        XCTAssertEqual(batch.failed, 1)
        let calls = await transport.calls
        XCTAssertEqual(calls, 0)
    }

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
        app.activeDrawTab = "batch_image"
        app.selectImageVisionModel("fixture:vision")
        let automation = AutomationModel()
        let batch = automation.imageFolderBatch; try await batch.select(input, app: app)
        XCTAssertEqual(batch.total, 3)
        app.imageCanvasID = "square"
        await transport.blockFirstRequest()
        let operation = Task { await batch.run(app: app, restart: false) { _ in "fixture" } }
        for _ in 0..<500 {
            if await transport.isBlocked { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        let blocked = await transport.isBlocked
        automation.selectInputTab("image", app: app)
        XCTAssertTrue(blocked)
        XCTAssertTrue(automation.inputTabRunning("batch", app: app))
        XCTAssertFalse(automation.inputTabRunning("image", app: app))
        XCTAssertFalse(automation.inputTabRunning("description", app: app))
        await transport.resume()
        await operation.value
        XCTAssertEqual(batch.completed, 2); XCTAssertEqual(batch.failed, 1)
        let db = try InkuDatabase(url: root.appendingPathComponent("works.sqlite"))
        let fixedWorks = try await db.libraryPage(limit: 10).items.map(\.work)
        XCTAssertEqual(fixedWorks.count, 2)
        XCTAssertTrue(fixedWorks.allSatisfy { $0.renderCanvasAspectID == "square" })
        batch.newWork(app: app)
        XCTAssertNil(app.displayedWork)
        XCTAssertNil(app.selectedWorkID)
        XCTAssertTrue(app.currentSVG.isEmpty)
        XCTAssertFalse(batch.hasJournal)
        try png.write(to: bad)
        let portrait = try makePNG(width: 48, height: 64)
        try portrait.write(to: input.appendingPathComponent("4.png"))
        let portraitPaper = try ImageInput.prepare(portrait).nearestFormatID
        XCTAssertNotEqual(portraitPaper, "sd_monitor")
        let reopened = ImageFolderBatch(); try await reopened.select(input, app: app)
        XCTAssertEqual(reopened.completed, 2)
        app.activeDrawTab = "batch_image"
        app.selectImageVisionModel("fixture:vision")
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

private final class ImagePreparationGate: @unchecked Sendable {
    private let lock = NSLock()
    private let semaphore = DispatchSemaphore(value: 0)
    private var waiting = false
    func prepare(_ url: URL) throws -> PreparedImageInput {
        lock.lock(); waiting = true; lock.unlock()
        semaphore.wait()
        return try ImageInput.prepare(Data(contentsOf: url))
    }
    func isWaiting() -> Bool { lock.lock(); defer { lock.unlock() }; return waiting }
    func release() { semaphore.signal() }
}
private actor FolderProvider: ProviderTransport {
    var calls = 0
    var isBlocked = false
    private var shouldBlock = false
    private var continuation: CheckedContinuation<Void, Never>?
    func blockFirstRequest() { shouldBlock = true }
    func resume() { continuation?.resume(); continuation = nil; shouldBlock = false; isBlocked = false }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        if shouldBlock {
            shouldBlock = false; isBlocked = true
            await withCheckedContinuation { continuation = $0 }
        }
        let effect = try ExactJSON(data: action)
        let result = effect["tag"].string == "write_image_ddl" ? "image_ddl_written" : "image_ddl_reviewed"
        return ExactJSON.object(["tag": .string(result), "identity": effect["identity"],
            "response": .string(#"{"ddl":"赤い円を1個置く。"}"#), "elapsed_ms": .string("1")]).data
    }
}
