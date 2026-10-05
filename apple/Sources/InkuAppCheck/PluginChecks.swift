import Foundation
import InkuHost
import InkuUI

/// Failure: disabling a bundled plugin changes a saved work's pinned definitions or export.
@MainActor
func runPluginChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plugin-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let model = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"))
    await model.initialize()
    model.inputMode = "ddl"
    model.language = "ja"
    model.ddlText = "Nature.若葉 を置く"
    model.seedText = "42"
    await model.generate()
    guard model.errorText == nil, let saved = model.selectedWork else {
        throw CheckFailure.message("Plugin source did not save: \(model.errorText ?? model.status)")
    }
    let before = try await model.savedConfiguration(workID: saved.id)
    let definitions = try ExactJSON(data: before.configuration)["definitions"].array ?? []
    guard !definitions.isEmpty, !model.pluginWords.isEmpty else { throw CheckFailure.message("Plugin fixture has no definitions") }
    var settings = await model.hostSettings()
    settings.plugins = PluginPreferences(disabledPackageIDs: Set(model.pluginWords.compactMap(\.packageID)))
    try await model.updateHostSettings(settings)

    guard model.authoringMacroNames.contains("Nature.若葉") else {
        throw CheckFailure.message("Disabling a plugin hid a saved work's pinned reference vocabulary")
    }

    model.newWork()
    let next = try model.requestForCurrentInput()
    guard try ExactJSON(data: next.configuration)["definitions"].array?.isEmpty == true else {
        throw CheckFailure.message("Disabled plugin leaked into a fresh request")
    }
    let after = try await model.savedConfiguration(workID: saved.id)
    let sources = try await model.prepareExportSources(works: [saved], profile: "editable", requiresPluginDefinitions: true)
    guard before.configuration == after.configuration, before.document == after.document,
          sources.count == 1, sources[0].pluginDefinitions == definitions,
          sources[0].work == saved, !(try sources[0].svg(profile: "editable")).isEmpty else {
        throw CheckFailure.message("Plugin preferences altered a saved definition, document, or export context")
    }
    print("Plugin selection passed: disabled definitions stay out of new requests; saved document, definitions, and editable/DDL export context remain pinned. No provider calls.")
}
