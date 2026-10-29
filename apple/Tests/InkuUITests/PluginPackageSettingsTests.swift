import XCTest
import InkuHost
@testable import InkuUI

@MainActor final class PluginPackageSettingsTests: XCTestCase {
    func testPackageSettingsChooseInstallDisableAndDelete() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plugin-settings-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let spec = try String(contentsOf: root.appendingPathComponent("PLUGIN.ja.md"), encoding: .utf8)
        let section = try XCTUnwrap(spec.range(of: "## 2."))
        let start = try XCTUnwrap(spec.range(of: "```json", range: section.upperBound..<spec.endIndex))
        let end = try XCTUnwrap(spec.range(of: "```", range: start.upperBound..<spec.endIndex))
        let definition = try JSONSerialization.jsonObject(with: Data(spec[start.upperBound..<end.lowerBound].utf8))
        let word: [String: Any] = ["definition": definition, "note_ja": "星を散らす。", "example_ja": "中心に、｛星｝を3個置く。", "example_en": "Place 3 {stars} in the center."]
        let file = folder.appendingPathComponent("package.json")
        try JSONSerialization.data(withJSONObject: ["schema": "inku.plugin-package.v2", "namespace": "Sky", "name": "night", "version": "1.0.0", "words": [word]]).write(to: file)
        let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: NoPackageProvider())
        await app.initialize()
        XCTAssertEqual(app.pluginWords.filter { $0.packageID == "Nature.leaves" }.count, 7)
        XCTAssertNotNil(app.pluginWords.first { $0.displayName(language: "ja") == "｛若葉｝" }?.previewData)
        let typed = "｛わか"
        let completion = app.ddlCompletions.match(text: typed, caret: (typed as NSString).length)
        XCTAssertTrue(completion?.items.contains("｛若葉｝") == true)
        for source in ["｛若葉｝。", "｛わかば｝。", "{young leaves}.", "Nature.YoungLeaves。"] {
            let calls = await app.pluginCalls(source: source)
            XCTAssertEqual(calls.first?.status, "resolved", source)
        }
        let mistyped = await app.pluginCalls(source: "｛若刃｝。")
        XCTAssertEqual(mistyped.first?.status, "plugin_name_mismatch")
        XCTAssertEqual(mistyped.first?.suggestion, "若葉")
        for source in ["｛菖蒲｝。", "Nature.若葉。"] {
            let calls = await app.pluginCalls(source: source)
            XCTAssertEqual(calls.first?.status, "plugin_not_installed", source)
        }
        for source in ["{}", "｛ ｝", "{\"a\":1}"] {
            let calls = await app.pluginCalls(source: source)
            XCTAssertTrue(calls.isEmpty, source)
        }
        var host = await app.hostSettings()
        host.plugins = PluginPreferences(disabledPackageIDs: ["Nature.leaves"])
        try await app.updateHostSettings(host)
        let disabledCalls = await app.pluginCalls(source: "｛若葉｝。")
        XCTAssertEqual(disabledCalls.first?.status, "plugin_disabled")
        host.plugins = PluginPreferences()
        try await app.updateHostSettings(host)
        let settings = PluginSettingsModel()
        await settings.load(model: app)
        await settings.choose(file, model: app)
        XCTAssertEqual(settings.check?.ok, true)
        await settings.install(model: app)
        XCTAssertTrue(settings.packages.contains { $0.id == "Sky.night" && $0.installed && $0.words.count == 1 })
        XCTAssertEqual(app.pluginWords.first { $0.id == "Sky.Stars" }?.exampleJapanese, "中心に、｛星｝を3個置く。")
        await settings.setEnabled(false, packageID: "Sky.night", model: app)
        XCTAssertFalse(settings.preferences.isEnabled("Sky.night"))
        await settings.delete("Sky.night", model: app)
        XCTAssertFalse(settings.packages.contains { $0.id == "Sky.night" })
        XCTAssertNil(settings.error)
        let rejected = folder.appendingPathComponent("plugin-packages/Sky.broken")
        try FileManager.default.createDirectory(at: rejected, withIntermediateDirectories: true)
        try Data("{".utf8).write(to: rejected.appendingPathComponent("package.json"))
        await settings.load(model: app)
        XCTAssertTrue(settings.packages.contains { $0.id == "Sky.broken" && !$0.rejectedProblems.isEmpty })
        await settings.delete("Sky.broken", model: app)
        XCTAssertFalse(settings.packages.contains { $0.id == "Sky.broken" })
        XCTAssertNil(settings.error)
        let oldPackage = folder.appendingPathComponent("plugin-packages/Sky.old")
        try FileManager.default.createDirectory(at: oldPackage, withIntermediateDirectories: true)
        let oldFile = oldPackage.appendingPathComponent("package.json")
        try JSONSerialization.data(withJSONObject: ["schema": "inku.plugin-package.v1", "namespace": "Sky", "name": "old", "version": "1.0.0", "words": [word]]).write(to: oldFile)
        await settings.load(model: app)
        let old = try XCTUnwrap(settings.packages.first { $0.id == "Sky.old" })
        XCTAssertTrue(old.rejectedProblems.contains { $0["code"].string == "rewrite_as_v2" })
        XCTAssertTrue(FileManager.default.fileExists(atPath: oldFile.path))
    }
}

private struct NoPackageProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data { throw HostError("provider_forbidden") }
}
