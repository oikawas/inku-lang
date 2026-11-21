import XCTest
import InkuHost
import InkuPersistence
@testable import InkuUI

@MainActor final class PhoneDrawStateTests: XCTestCase {
    func testCompletionBannerFollowsTheSavedWorkAndClearsAtLifecycleBoundaries() {
        let banner = PhoneDrawingBanner.next(nil, for: .saved(id: "first", watching: false))
        XCTAssertEqual(banner, "first")
        XCTAssertEqual(PhoneDrawingBanner.next(banner, for: .opened("another")), banner)
        XCTAssertNil(PhoneDrawingBanner.next(banner, for: .opened("first")))
        XCTAssertNil(PhoneDrawingBanner.next(banner, for: .started))
        XCTAssertNil(PhoneDrawingBanner.next(banner, for: .stopped))
        XCTAssertNil(PhoneDrawingBanner.next(banner, for: .failed))
        XCTAssertNil(PhoneDrawingBanner.next(banner, for: .saved(id: "second", watching: true)))
    }
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
        let (app, root) = try await configuredDrawingApp(transport: PhoneDrawFixture())
        defer { try? FileManager.default.removeItem(at: root) }
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
        XCTAssertEqual(app.phoneDrawingWait?.completion?.id, result?.id)
        XCTAssertEqual(app.phoneDrawText, "")
        XCTAssertEqual(app.phoneDrawingWait?.description, "a blue circle")
        XCTAssertNotNil(app.phoneDrawingWait?.report["finished"].array?.first)
        XCTAssertEqual(app.selectedWorkID, original); XCTAssertEqual(app.descriptionText, "draft")
        XCTAssertEqual(app.ddlText, "other draft"); XCTAssertEqual(app.activeDrawTab, "image")
        XCTAssertEqual(app.drawSelections, selections)
        let work = try XCTUnwrap(result)
        let lookup = await app.phoneAssemblyContext(work.id)
        let context = try XCTUnwrap(lookup)
        let earlyBytes = try XCTUnwrap(app.phoneDrawingWait?.assemblyRequest)
        var early = try ExactJSON(data: PhoneDrawingAssembly.previewRequest(earlyBytes))
        let saved = try ExactJSON(data: PhoneDrawingAssembly.animationRequest(work: work, context: context))
        XCTAssertEqual(early["saved_svg"].string, "")
        early["saved_svg"] = saved["saved_svg"]
        XCTAssertEqual(early, saved)
        let frames = try PhoneDrawingAssembly.frames(work: work, context: context, pixels: 120)
        XCTAssertGreaterThan(frames.count, 2)
        XCTAssertEqual(frames.first?.image.width, 120)
        XCTAssertTrue(frames.contains { !$0.lines.isEmpty })
    }

    func testFailedPhoneDrawingKeepsTheDescription() async throws {
        let (app, root) = try await configuredDrawingApp(transport: PhoneDrawFixture(fails: true))
        defer { try? FileManager.default.removeItem(at: root) }
        app.phoneDrawText = "a blue circle"

        let result = await app.drawPhoneDescription()

        XCTAssertNil(result)
        XCTAssertNil(app.phoneDrawingWait?.completion)
        XCTAssertNotNil(app.phoneDrawFailure)
        XCTAssertEqual(app.phoneDrawText, "a blue circle")
    }

    func testSavedPhoneDrawingKeepsTextEditedDuringTheRun() async throws {
        let transport = PhoneDrawFixture()
        let (app, root) = try await configuredDrawingApp(transport: transport)
        defer { try? FileManager.default.removeItem(at: root) }
        app.phoneDrawText = "a blue circle"
        await transport.onDraw { [weak app] in
            app?.phoneDrawText = "the next drawing"
            app?.phoneDrawingWait?.visible = false
        }

        let result = await app.drawPhoneDescription()

        let saved = try XCTUnwrap(result)
        XCTAssertEqual(app.phoneDrawingWait?.completion?.id, saved.id)
        XCTAssertEqual(app.phoneDrawingWait?.description, "a blue circle")
        XCTAssertEqual(app.phoneDrawText, "the next drawing")
    }

    private func configuredDrawingApp(transport: PhoneDrawFixture) async throws -> (AppModel, URL) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("phone-draw-\(UUID())")
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"), transport: transport)
        await app.initialize()
        let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false,
                                        models: [.init(id: "model", purposes: ["llm"])])
        try await app.updateHostSettings(HostSettings(providers: [provider], models: .init(stage1Model: "fixture:model", stage2Model: "fixture:model")))
        var defaults = app.drawDefaults
        defaults["describe"]?.models.stage1 = "fixture:model"; defaults["describe"]?.models.stage2 = "fixture:model"
        defaults["describe"]?.route = "stages"; defaults["describe"]?.sketch = "off"; defaults["describe"]?.wild = "on"
        try app.saveDrawDefaults(defaults)
        return (app, root)
    }
}

private actor PhoneDrawFixture: ProviderTransport {
    private let fails: Bool
    private var beforeResponse: (@MainActor @Sendable () -> Void)?

    init(fails: Bool = false) { self.fails = fails }

    func onDraw(_ edit: @escaping @MainActor @Sendable () -> Void) { beforeResponse = edit }

    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        if fails { throw HostError("description_ddl_failed") }
        await beforeResponse?()
        let value = try ExactJSON(data: action)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": value["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center.\nplace one blue circle at left."}"#), "elapsed_ms": .string("1")]).data
    }
}
