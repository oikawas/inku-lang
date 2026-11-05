import Foundation
import InkuHost
import InkuPersistence
import XCTest
@testable import InkuUI

@MainActor final class DrawOptionsTests: XCTestCase {
    func testCoreKeysReachStripRecordedSelectionSettingsAndReset() throws {
        let keys = Set(DrawOptionsCore.keys)
        XCTAssertEqual(Set(DrawOptionPresentation.keys(isImage: false)), keys)
        XCTAssertEqual(Set(DrawDefaultsSettingsView.optionKeys(tab: "describe")), keys)
        var work = SavedWork(id: "work", at: 1, input: "test", score: "{}", svg: "<svg/>",
                             stage1Model: "nvidia:test", stage2Model: "nvidia:test", catalogID: "default",
                             renderCanvasAspectID: "square", renderWild: true)
        work.drawRoute = "stages"; work.sketchRequested = "1"; work.compositionRequested = "1"; work.catalogMode = "fixed"
        let recorded = try DrawOptionsCore.recorded(work, isImage: false)
        let selected = try DrawOptionsCore.forRecorded(recorded, tab: "describe", defaults: DrawOptionsCore.release)
        let selectedObject = try XCTUnwrap(DrawOptionsCore.object(selected) as? [String: Any])
        for key in keys {
            XCTAssertNotNil(recorded[key], "work record: \(key)")
            XCTAssertNotNil(selectedObject[key], "opening work: \(key)")
            XCTAssertFalse(recorded[key] is NSNull, "work record: \(key)")
        }
        let legacy = SavedWork(id: "legacy", at: 0, input: "test", score: "{}", svg: "<svg/>", renderWild: true)
        let legacyOptions = try DrawOptionsCore.recorded(legacy, isImage: false)
        XCTAssertTrue(legacyOptions["route"] is NSNull)
        XCTAssertTrue(legacyOptions["sketch"] is NSNull)
        XCTAssertTrue(legacyOptions["composition"] is NSNull)
        XCTAssertEqual(legacyOptions["wild"] as? String, "on")
        let legacySelection = try DrawOptionsCore.forRecorded(legacyOptions, tab: "describe", defaults: DrawOptionsCore.release)
        XCTAssertEqual(legacySelection.route, DrawOptionsCore.release["describe"]?.route)
        XCTAssertEqual(legacySelection.sketch, "off")
        XCTAssertEqual(legacySelection.composition, "off")
        XCTAssertEqual(legacySelection.wild, "on")
        let app = AppModel()
        for tab in app.drawDefaults.keys {
            app.activeDrawTab = tab; app.drawRoute = "stages"; app.sketchMode = "off"
            app.descriptionComposition = true; app.wild = true; app.catalogID = "other"; app.canvasID = "a4"
            app.newWork()
            let reset = try XCTUnwrap(app.drawSelections[tab])
            let resetObject = try XCTUnwrap(DrawOptionsCore.object(reset) as? [String: Any])
            let defaultObject = try XCTUnwrap(DrawOptionsCore.object(app.drawDefaults[tab]!) as? [String: Any])
            for key in keys {
                XCTAssertEqual(try JSONSerialization.data(withJSONObject: ["value": resetObject[key]!], options: [.sortedKeys]),
                               try JSONSerialization.data(withJSONObject: ["value": defaultObject[key]!], options: [.sortedKeys]), "new work \(tab): \(key)")
            }
        }
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let web = try String(contentsOf: root.appendingPathComponent("web/src/lib/features/draw-options.ts"), encoding: .utf8)
        let line = try XCTUnwrap(web.split(separator: "\n").first { $0.contains("export const INPUT_PANEL_ORDER =") })
        let regex = try NSRegularExpression(pattern: "'([^']+)'")
        let text = String(line) as NSString
        let webOrder = regex.matches(in: String(line), range: NSRange(location: 0, length: text.length)).map { text.substring(with: $0.range(at: 1)) }
        XCTAssertEqual(DrawOptionPresentation.inputOrder, webOrder)
        let creation = try String(contentsOf: root.appendingPathComponent("apple/Sources/InkuUI/Views/CreationView.swift"), encoding: .utf8)
        let input = try XCTUnwrap(creation.components(separatedBy: "private var nextConditions: some View {").dropFirst().first?.components(separatedBy: "private var catalogSummary:").first)
        XCTAssertLessThan(try XCTUnwrap(input.range(of: "modelButton")?.lowerBound), try XCTUnwrap(input.range(of: "colorCatalogButton")?.lowerBound))
        XCTAssertLessThan(try XCTUnwrap(input.range(of: "colorCatalogButton")?.lowerBound), try XCTUnwrap(input.range(of: "DrawConditionsView")?.lowerBound))
        XCTAssertLessThan(try XCTUnwrap(input.range(of: "DrawConditionsView")?.lowerBound), try XCTUnwrap(input.range(of: "DrawingCompactConditions")?.lowerBound))
        let steps = try String(contentsOf: root.appendingPathComponent("apple/Sources/InkuUI/Views/DrawConditionsView.swift"), encoding: .utf8)
        XCTAssertLessThan(try XCTUnwrap(steps.range(of: "routeButton(")?.lowerBound), try XCTUnwrap(steps.range(of: "DrawSwitchChip(title:")?.lowerBound))
        let compact = try String(contentsOf: root.appendingPathComponent("apple/Sources/InkuUI/Views/DrawingConditionRows.swift"), encoding: .utf8)
        let compactBody = try XCTUnwrap(compact.components(separatedBy: "struct DrawingCompactConditions:").last)
        XCTAssertLessThan(try XCTUnwrap(compactBody.range(of: "wildButton")?.lowerBound), try XCTUnwrap(compactBody.range(of: "canvasAspectButton")?.lowerBound))
    }
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
