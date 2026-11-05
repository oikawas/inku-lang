import Foundation
import InkuHost
import InkuPersistence
import XCTest
@testable import InkuUI

@MainActor final class LibraryClickWeightTests: XCTestCase {
    func testMarksAreRecomputedOnlyForTextOrRecipeChange() {
        var cache = InkuEditorMarksCache()
        var calls = 0
        func make(_ source: String) -> [InkuEditorMark] {
            calls += 1
            return [InkuEditorMark(range: NSRange(location: 0, length: source.utf16.count), style: .muted)]
        }
        XCTAssertTrue(cache.update(source: "one", key: .description, make: make))
        XCTAssertFalse(cache.update(source: "one", key: .description, make: make))
        XCTAssertEqual(calls, 1)
        XCTAssertTrue(cache.update(source: "two", key: .description, make: make))
        XCTAssertTrue(cache.update(source: "two", key: .none, make: make))
        let highlighter = DdlHighlighter(saijiki: [])
        XCTAssertTrue(cache.update(source: "two", key: .ddl(highlighter, [], "two"), make: make))
        XCTAssertFalse(cache.update(source: "two", key: .ddl(highlighter, [], "two"), make: make))
        let completion = CompletionRangeState(utf16Start: 0, utf16End: 1, state: .completed)
        XCTAssertTrue(cache.update(source: "two", key: .ddl(highlighter, [completion], "two"), make: make))
        XCTAssertTrue(cache.update(source: "é", key: .description, make: make))
        XCTAssertTrue(cache.update(source: "e\u{301}", key: .description, make: make))
        XCTAssertEqual(calls, 7)
    }

    func testAvailabilityFollowsSelectedModelAndProviderSettings() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-availability-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"))
        await app.initialize()
        var provider = ProviderSettings(id: "test", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false,
            models: [.init(id: "drawing"), .init(id: "vision", purposes: ["llm", "vision"])])
        try await app.updateHostSettings(HostSettings(providers: [provider]))
        app.selectNextDrawingModel("test:drawing")
        XCTAssertTrue(app.hasAvailableNextDrawingModel)
        XCTAssertTrue(app.hasAvailableBatchDrawingModel)
        XCTAssertFalse(app.descriptionCanReview)
        app.selectNextDrawingModel("test:vision")
        XCTAssertTrue(app.hasAvailableNextDrawingModel)
        XCTAssertTrue(app.descriptionCanReview)
        provider.enabledModels = ["vision": false]
        try await app.updateHostSettings(HostSettings(providers: [provider]))
        XCTAssertFalse(app.hasAvailableNextDrawingModel)
        XCTAssertFalse(app.hasAvailableBatchDrawingModel)
        XCTAssertFalse(app.descriptionCanReview)
    }

    func testRecordedOptionsAreIsolatedByWorkAndImage() throws {
        let app = AppModel()
        let first = SavedWork(id: "first", at: 1, input: "one", score: "{}", svg: "<svg/>",
                              stage1Model: "test:one", stage2Model: "test:one", renderWild: true)
        let second = SavedWork(id: "second", at: 2, input: "two", score: "{}", svg: "<svg/>",
                               stage1Model: "test:two", stage2Model: "test:two", renderWild: false)
        XCTAssertNil(app.cachedRecordedOptions(workID: first.id, isImage: false))
        let firstOptions = try app.prepareRecordedOptions(first, isImage: false)
        let secondOptions = try app.prepareRecordedOptions(second, isImage: false)
        XCTAssertEqual(firstOptions["wild"] as? String, "on")
        XCTAssertEqual(secondOptions["wild"] as? String, "off")
        XCTAssertEqual(app.cachedRecordedOptions(workID: first.id, isImage: false)?["wild"] as? String, "on")
        XCTAssertNil(app.cachedRecordedOptions(workID: first.id, isImage: true))
        let image = try app.prepareRecordedOptions(first, isImage: true)
        XCTAssertNotNil(image["models"])
        XCTAssertNotNil(app.cachedRecordedOptions(workID: first.id, isImage: true))
    }
}
