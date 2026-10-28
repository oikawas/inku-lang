import Foundation
import ImageIO
import InkuHost
import InkuUI

private struct PackageNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("provider_forbidden_in_plugin_package_test")
    }
}

@MainActor
func checkPluginPackageFile(url: URL) async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plugin-package-check-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let model = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: PackageNoProvider())
    await model.initialize()
    let check = try await model.checkPluginPackage(data: Data(contentsOf: url), isArchive: url.pathExtension.lowercased() == "zip")
    print(check.report.text)
}

@MainActor
func runPluginPackageChecks(specURL: URL) async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plugin-package-test-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let spec = try String(contentsOf: specURL, encoding: .utf8)
    guard let section = spec.range(of: "## 2."), let start = spec.range(of: "```json", range: section.upperBound..<spec.endIndex),
          let end = spec.range(of: "```", range: start.upperBound..<spec.endIndex),
          let definition = try JSONSerialization.jsonObject(with: Data(spec[start.upperBound..<end.lowerBound].utf8)) as? [String: Any]
    else { throw CheckFailure.message("Could not read shared Sky.Stars fixture") }
    let word: [String: Any] = ["definition": definition, "summary_ja": "空の上半分に、黄色の星を散らす。", "summary_en": "Scatters yellow stars over the upper half.", "note_ja": "夜の空に小さな星。", "example_ja": "5個のSky.星。", "example_en": "5 Sky.Stars."]
    func document(_ words: [[String: Any]], name: String = "night") throws -> Data {
        try JSONSerialization.data(withJSONObject: ["schema": "inku.plugin-package.v1", "namespace": "Sky", "name": name, "version": "1.0.0", "description_ja": "夜空の語。", "words": words])
    }
    let model = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: PackageNoProvider())
    await model.initialize()
    let one = try document([word])
    let checked = try await model.checkPluginPackage(data: one, isArchive: false)
    guard checked.ok, checked.id == "Sky.night", let image = checked.preview(at: 0),
          let source = CGImageSourceCreateWithData(image as CFData, nil),
          let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
          properties[kCGImagePropertyPixelWidth] as? Int == 432, properties[kCGImagePropertyPixelHeight] as? Int == 184 else {
        throw CheckFailure.message("Valid package check/preview failed: \(checked.report.text)")
    }
    let installed = try await model.installPluginPackage(data: one, isArchive: false, replace: false)
    guard installed.ok, model.pluginWords.contains(where: { $0.id == "Sky.Stars" }),
          model.ddlCompletions.words(for: "星").contains("Sky.星") else { throw CheckFailure.message("Installed word or completion absent") }
    let previewFolder = folder.appendingPathComponent("plugin-packages/Sky.night/previews")
    let files = try FileManager.default.contentsOfDirectory(at: previewFolder, includingPropertiesForKeys: nil)
    guard let small = files.first(where: { !$0.lastPathComponent.contains("@2x") }),
          let smallSource = CGImageSourceCreateWithURL(small as CFURL, nil),
          let smallProperties = CGImageSourceCopyPropertiesAtIndex(smallSource, 0, nil) as? [CFString: Any],
          smallProperties[kCGImagePropertyPixelWidth] as? Int == 216, smallProperties[kCGImagePropertyPixelHeight] as? Int == 92 else { throw CheckFailure.message("1x preview size mismatch") }
    let reopened = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: PackageNoProvider())
    await reopened.initialize()
    guard reopened.pluginWords.contains(where: { $0.id == "Sky.Stars" }) else { throw CheckFailure.message("Installed package not loaded after restart") }
    model.inputMode = "ddl"; model.ddlText = "5個のSky.星。"; model.language = "ja"
    await model.generate()
    guard let saved = model.selectedWork, model.errorText == nil else { throw CheckFailure.message("Installed package drawing failed: \(model.errorText ?? model.status)") }
    let savedBefore = try await model.savedConfiguration(workID: saved.id)
    let repeatCheck = try await model.checkPluginPackage(data: one, isArchive: false)
    guard repeatCheck.ok, repeatCheck.report["exists"].bool == true else { throw CheckFailure.message("Same ID not marked for replacement") }
    do { _ = try await model.installPluginPackage(data: one, isArchive: false, replace: false); throw CheckFailure.message("Replacement without consent accepted") }
    catch let error as HostError where error.code == "plugin_package_exists" { }
    let replacement = try await model.installPluginPackage(data: one, isArchive: false, replace: true)
    guard replacement.ok else { throw CheckFailure.message("Replacement failed") }
    let conflict = try await model.checkPluginPackage(data: document([word], name: "other"), isArchive: false)
    guard !conflict.ok else { throw CheckFailure.message("Conflicting name accepted") }
    let brokenZip = try await model.checkPluginPackage(data: Data("not a zip at all".utf8), isArchive: true)
    guard !brokenZip.ok else { throw CheckFailure.message("Broken zip accepted") }
    var settings = await model.hostSettings()
    settings.plugins = PluginPreferences(disabledPackageIDs: ["Sky.night"])
    try await model.updateHostSettings(settings)
    model.newWork()
    guard !(try ExactJSON(data: model.requestForCurrentInput(inputMode: "ddl").configuration).text.contains("Sky.Stars")) else { throw CheckFailure.message("Disabled package in new catalog") }
    try await model.deletePluginPackage("Sky.night")
    guard !model.pluginWords.contains(where: { $0.id == "Sky.Stars" }), !(await model.hostSettings()).plugins!.disabledPackageIDs.contains("Sky.night") else { throw CheckFailure.message("Deleted package still present") }
    model.newWork(); model.inputMode = "ddl"; model.ddlText = "5個のSky.星。"
    await model.generate()
    guard model.selectedWork == nil else { throw CheckFailure.message("Deleted package still drew in a new work") }
    guard model.diagnosticsJSON.contains("macro_resolution_missing_lock") else { throw CheckFailure.message("Deleted word diagnostic missing: \(model.diagnosticsJSON)") }
    let savedAfter = try await model.savedConfiguration(workID: saved.id)
    let sources = try await model.prepareExportSources(works: [saved], profile: "editable", requiresPluginDefinitions: true)
    guard savedBefore.configuration == savedAfter.configuration, savedBefore.document == savedAfter.document,
          let source = sources.first, !(try source.svg(profile: "editable")).isEmpty else { throw CheckFailure.message("Saved definition failed after deletion") }
    await model.replay(saved)
    guard model.errorText == nil, model.selectedWork != nil else { throw CheckFailure.message("Saved work replay failed after deletion: \(model.errorText ?? model.status)") }
    guard let savedDDL = saved.ddl, await model.drawEditedDDL(work: saved, source: savedDDL, forceEdit: true) else {
        throw CheckFailure.message("Saved DDL did not draw with its pinned definition after deletion: \(model.errorText ?? model.status)")
    }
    var invalidWord = word; invalidWord["example_ja"] = "意味のない文章。"
    let invalid = try await model.checkPluginPackage(data: document([invalidWord], name: "invalid"), isArchive: false)
    guard !invalid.ok, (invalid.report["words"].array ?? []).contains(where: { !($0["problems"].array ?? []).isEmpty }) else { throw CheckFailure.message("Stopped example accepted: \(invalid.report.text)") }
    var moon = definition; moon["heading"] = "Moon"; moon["aliases"] = ["月"]
    var second = word; second["definition"] = moon; second["example_ja"] = ""; second["example_en"] = ""
    let two = try document([word, second])
    let checkedTwo = try await model.installPluginPackage(data: two, isArchive: false, replace: false)
    guard checkedTwo.ok, model.pluginWords.contains(where: { $0.id == "Sky.Moon" }) else { throw CheckFailure.message("Two-word fixture failed: \(checkedTwo.report.text)") }
    model.newWork(); model.inputMode = "ddl"; model.ddlText = "5個のSky.月。"
    await model.generate()
    guard model.selectedWork != nil, model.errorText == nil else { throw CheckFailure.message("Second package did not draw") }
    settings = await model.hostSettings(); settings.plugins = PluginPreferences(disabledPackageIDs: ["Sky.night"])
    try await model.updateHostSettings(settings)
    guard !model.pluginWords.contains(where: { $0.id == "Sky.Moon" }) else { throw CheckFailure.message("Two-word package did not disable") }
    try await model.deletePluginPackage("Sky.night")
    model.newWork(); model.inputMode = "ddl"; model.ddlText = "5個のSky.月。"
    await model.generate()
    guard model.selectedWork == nil, model.diagnosticsJSON.contains("macro_resolution_missing_lock") else {
        throw CheckFailure.message("Deleted second fixture did not report the missing word")
    }
    print("Plugin package checks passed; provider calls forbidden.")
}
