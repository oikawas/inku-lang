import Foundation
import InkuHost
import XCTest
@testable import InkuUI

@MainActor final class DrawOptionsTests: XCTestCase {
    func testCustomProvidersSurviveSavingAndReading() throws {
        let providers = ["custom-a", "custom-b", "custom-c"].map { id in
            ProviderSettings(id: id, baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                             models: [ProviderModelSettings(id: "model")])
        }
        let settings = HostSettings(providers: providers)
        let preferences = DisplayPreferences()
        var draft = try DrawOptionsCore.normalized(settings: settings, preferences: preferences, colorIDs: ["default"])
        draft["describe"]?.models.stage1 = "custom-a:model"
        draft["batch_text"]?.models.stage1 = "custom-b:model"
        draft["image"]?.models.vision = "custom-c:model"
        let saved = try DrawOptionsCore.update(draft, settings: settings, preferences: preferences, colorIDs: ["default"])
        var reopened = preferences
        reopened.drawDefaults = saved
        let decoded = try JSONDecoder().decode(DisplayPreferences.self, from: JSONEncoder().encode(reopened))
        let restored = try DrawOptionsCore.normalized(settings: settings, preferences: decoded, colorIDs: ["default"])
        XCTAssertEqual(restored["describe"]?.models.stage1, "custom-a:model")
        XCTAssertEqual(restored["batch_text"]?.models.stage1, "custom-b:model")
        XCTAssertEqual(restored["image"]?.models.vision, "custom-c:model")
    }
    func testLegacyDefaultsOnlyCarryModelAndCatalog() throws {
        var preferences = DisplayPreferences()
        preferences.nextCatalogID = "ink"; preferences.nextCatalogMode = "auto"
        preferences.nextCanvasID = "a4"; preferences.defaultWild = true
        preferences.visionModelReference = "custom-c:vision"
        let providers = ["custom-a", "custom-c"].map { ProviderSettings(id: $0, baseURL: URL(string: "http://localhost:1/v1")!) }
        let settings = HostSettings(providers: providers, models: ModelSelection(stage1Model: "custom-a:model"))
        let old = try DrawOptionsCore.normalized(settings: settings, preferences: preferences, colorIDs: ["default", "ink"])
        let fresh = try DrawOptionsCore.normalized(settings: HostSettings(), preferences: DisplayPreferences(), colorIDs: ["default", "ink"])
        XCTAssertEqual(old["describe"]?.models.stage1, "custom-a:model")
        XCTAssertEqual(old["batch_text"]?.models.stage1, "custom-a:model")
        XCTAssertEqual(old["image"]?.models.vision, "custom-c:vision")
        XCTAssertEqual(old["describe"]?.catalog.mode, "auto")
        XCTAssertEqual(old["describe"]?.canvasAspect, DrawOptionsCore.release["describe"]?.canvasAspect)
        XCTAssertEqual(old["describe"]?.wild, DrawOptionsCore.release["describe"]?.wild)
        XCTAssertEqual(fresh, DrawOptionsCore.release)
    }
}
