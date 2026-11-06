import XCTest
import InkuHost
import InkuPersistence
@testable import InkuUI

@MainActor final class BrowseDuringDrawingTests: XCTestCase {
    func testSelectionDoesNotInterruptOrFollowDrawing() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-browse-run-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let provider = BrowseDuringDrawingProvider()
        let databaseURL = root.appendingPathComponent("works.sqlite")
        let app = AppModel(databaseURL: databaseURL, transport: provider)
        await app.initialize()
        let service = ProviderSettings(id: "fixture", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false,
                                       models: [ProviderModelSettings(id: "model", purposes: ["llm"])])
        try await app.updateHostSettings(HostSettings(providers: [service], models: .init(stage1Model: "fixture:model", stage2Model: "fixture:model")))
        app.selectNextDrawingModel("fixture:model")
        app.selectDrawRoute("stages"); app.sketchMode = "off"
        app.inputMode = "description"; app.descriptionText = "a red circle"; app.seedText = "0"

        // P3: without an intervening selection the saved result is displayed.
        await app.generate()
        let original = try XCTUnwrap(app.selectedWork)
        XCTAssertFalse(app.currentSVG.isEmpty)
        app.newWork()
        app.selectNextDrawingModel("fixture:model")
        app.selectDrawRoute("stages"); app.sketchMode = "off"
        app.descriptionText = "a blue square"
        await provider.blockNext()
        let drawing = Task { await app.generate() }
        for _ in 0..<500 {
            if await provider.blocked { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        let blocked = await provider.blocked
        XCTAssertTrue(blocked)
        XCTAssertTrue(app.isBusy)
        XCTAssertFalse(app.isBrowsingLocked)
        XCTAssertFalse(app.canGenerate)
        XCTAssertFalse(app.canEditCurrentDDL)
        XCTAssertFalse(app.canCommitDDL)
        XCTAssertFalse(app.canCompleteHoles)
        await app.selectWork(original)
        let ddl = app.ddlText, description = app.descriptionText, svg = app.currentSVG
        let execution = app.currentExecutionID, holes = app.holeIDs
        await provider.sendBytes()
        for _ in 0..<200 {
            if app.providerProgress?.receivedBytes == 73 { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertEqual(app.providerProgress?.receivedBytes, 73)
        await provider.resume()
        await drawing.value
        XCTAssertNil(app.errorText)
        XCTAssertEqual(app.selectedWork?.id, original.id)
        XCTAssertEqual(app.ddlText, ddl)
        XCTAssertEqual(app.descriptionText, description)
        XCTAssertEqual(app.currentSVG, svg)
        XCTAssertEqual(app.currentExecutionID, execution)
        XCTAssertEqual(app.holeIDs, holes)
        let database = try InkuDatabase(url: databaseURL)
        let works = try await database.list()
        XCTAssertEqual(works.count, 2)
        XCTAssertTrue(works.contains { $0.id != original.id })
    }
}

private actor BrowseDuringDrawingProvider: ProviderTransport {
    private var shouldBlock = false
    private(set) var blocked = false
    private var continuation: CheckedContinuation<Void, Never>?
    private var callback: (@Sendable (Int) -> Void)?
    func blockNext() { shouldBlock = true }
    func sendBytes() { callback?(73) }
    func resume() { continuation?.resume(); continuation = nil; blocked = false }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let value = try ExactJSON(data: action)
        if shouldBlock {
            shouldBlock = false; blocked = true; callback = onBytes
            await withCheckedContinuation { continuation = $0 }
        }
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": value["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
}
