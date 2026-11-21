import XCTest
import InkuHost
import InkuPersistence
@testable import InkuUI

@MainActor final class PhoneDrawStateTests: XCTestCase {
    func testEveryStateAndPriority() {
        var cases: [(PhoneDrawState.Facts, PhoneDrawState)] = []
        func add(_ expected: PhoneDrawState, _ mutate: (inout PhoneDrawState.Facts) -> Void) {
            var f = PhoneDrawState.Facts(); mutate(&f); cases.append((f, expected))
        }
        add(.noConnection) { $0.hasConnection = false }
        add(.keyMissing) { $0.keyMissing = true }
        add(.signIn) { $0.chatGPTSelected = true; $0.signedIn = false }
        add(.modelUnavailable) { $0.modelAvailable = false }
        add(.empty) { _ in }
        add(.editing) { $0.editing = true }
        add(.drawing) { $0.activeRun = true; $0.drawing = true; $0.candidate = true }
        add(.otherRun) { $0.activeRun = true }
        add(.needsReview) { $0.needsReview = true; $0.candidate = true }
        add(.candidate) { $0.candidate = true }
        add(.completedHere) { $0.completedHere = true }
        add(.completedElsewhere) { $0.completedElsewhere = true }
        add(.stopped) { $0.stopped = true }
        add(.stoppedInBackground) { $0.stoppedInBackground = true; $0.failed = true }
        add(.failed) { $0.failed = true }
        for (facts, expected) in cases { XCTAssertEqual(PhoneDrawState.resolve(facts), expected) }
    }

    func testPhoneInitialDefaultsAndSignInChoice() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("phone-defaults-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"))
        await app.initialize()
        let release = app.drawDefaults
        app.initializePhoneDrawDefaults()
        XCTAssertEqual(app.drawDefaults["describe"]?.route, "stages")
        XCTAssertEqual(app.drawDefaults["describe"]?.models.stage1, "chatgpt:gpt-6.1-terra")
        XCTAssertEqual(app.drawDefaults["describe"]?.models.stage2, "chatgpt:gpt-6.1-terra")
        XCTAssertEqual(app.drawDefaults["describe"]?.canvasAspect, release["describe"]?.canvasAspect)
        XCTAssertEqual(app.drawDefaults["image"], release["image"])
        XCTAssertTrue(AppModel.shouldAdoptPhoneChatGPTDefault(available: false, keyMissing: false, terraInCatalog: true))
        XCTAssertTrue(AppModel.shouldAdoptPhoneChatGPTDefault(available: true, keyMissing: true, terraInCatalog: true))
        XCTAssertFalse(AppModel.shouldAdoptPhoneChatGPTDefault(available: true, keyMissing: false, terraInCatalog: true))
        XCTAssertFalse(AppModel.shouldAdoptPhoneChatGPTDefault(available: false, keyMissing: false, terraInCatalog: false))
    }

    func testPhoneDrawingUsesDefaultsAndPreservesWorkspace() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("phone-draw-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"), transport: PhoneDrawFixture())
        await app.initialize()
        let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false,
                                        models: [.init(id: "model", purposes: ["llm"])])
        try await app.updateHostSettings(HostSettings(providers: [provider], models: .init(stage1Model: "fixture:model", stage2Model: "fixture:model")))
        var defaults = app.drawDefaults
        defaults["describe"]?.models.stage1 = "fixture:model"; defaults["describe"]?.models.stage2 = "fixture:model"
        defaults["describe"]?.route = "stages"; defaults["describe"]?.sketch = "off"; defaults["describe"]?.wild = "on"
        try app.saveDrawDefaults(defaults)
        app.selectNextDrawingModel("fixture:model"); app.selectDrawRoute("stages"); app.sketchMode = "off"
        app.descriptionText = "a red circle"; await app.generate()
        let original = try XCTUnwrap(app.selectedWorkID)
        app.descriptionText = "draft"; app.ddlText = "other draft"; app.activeDrawTab = "image"
        let selections = app.drawSelections
        let request = try app.requestForPhoneDescription("a blue circle")
        XCTAssertNil(request.parentWorkID); XCTAssertEqual(request.derivationKind, "new")
        XCTAssertEqual(request.models.stage1Model, "fixture:model")
        XCTAssertEqual(try ExactJSON(data: request.renderOptions)["wild"].bool, true)
        app.phoneDrawText = "a blue circle"
        let result = await app.drawPhoneDescription()
        XCTAssertNotNil(result); XCTAssertNotEqual(result?.id, original)
        XCTAssertEqual(app.selectedWorkID, original); XCTAssertEqual(app.descriptionText, "draft")
        XCTAssertEqual(app.ddlText, "other draft"); XCTAssertEqual(app.activeDrawTab, "image")
        XCTAssertEqual(app.drawSelections, selections)
    }
}

private actor PhoneDrawFixture: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let value = try ExactJSON(data: action)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": value["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
}
