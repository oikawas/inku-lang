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
        let word: [String: Any] = ["definition": definition, "summary_ja": "星を散らす。", "example_ja": "5個のSky.星。", "example_en": "5 Sky.Stars."]
        let file = folder.appendingPathComponent("package.json")
        try JSONSerialization.data(withJSONObject: ["schema": "inku.plugin-package.v1", "namespace": "Sky", "name": "night", "version": "1.0.0", "words": [word]]).write(to: file)
        let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: NoPackageProvider())
        await app.initialize()
        let settings = PluginSettingsModel()
        await settings.load(model: app)
        await settings.choose(file, model: app)
        XCTAssertEqual(settings.check?.ok, true)
        await settings.install(model: app)
        XCTAssertTrue(settings.packages.contains { $0.id == "Sky.night" && $0.installed && $0.words.count == 1 })
        XCTAssertEqual(app.pluginWords.first { $0.id == "Sky.Stars" }?.exampleJapanese, "5個のSky.星。")
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
    }
}

private struct NoPackageProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data { throw HostError("provider_forbidden") }
}
