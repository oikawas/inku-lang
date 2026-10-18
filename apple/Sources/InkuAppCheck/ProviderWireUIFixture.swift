import Foundation
import InkuHost
import InkuUI

/// Failure: a real key-based smoke test changes author settings or silently chooses another model.
/// Preparation makes no provider request; drawing and the author-operated Vision run follow in the app.
@MainActor
func makeProviderWireUIFixture(folder: URL) async throws {
    let url = folder.appendingPathComponent("works.sqlite")
    guard !FileManager.default.fileExists(atPath: url.path) else { throw CheckFailure.message("Use a fresh provider-wire fixture") }
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let app = AppModel(databaseURL: url)
    await app.initialize()
    var settings = await app.hostSettings()
    settings.providers = settings.providers.filter { $0.id == "gemini" && $0.kind == .gemini }
    guard settings.providers.count == 1 else { throw CheckFailure.message("Missing canonical Gemini provider") }
    let reference = "gemini:gemma-4-31b-it"
    guard SettingsModel.isRegisteredModelAvailable(reference, purpose: "vision", settings: settings),
          SettingsModel.isBatchModelAvailable(reference, settings: settings) else {
        throw CheckFailure.message("The approved Gemini model is not registered for drawing and Vision")
    }
    settings.models.stage1Model = reference; settings.models.stage2Model = reference
    try await app.updateHostSettings(settings)
    app.language = "ja"
    app.display.preferences.uiMode = "full"
    app.display.preferences.visionModelReference = reference
    app.display.preferences.aiRefine = AIRefineChoices(generations: 1,
        kinds: ["catalog_change"], direction: "赤い円と余白の関係を観察してください。")
    print("Provider-wire GUI fixture ready: empty isolated DB; Gemini API / gemma-4-31b-it for both stages and Vision; 1 Vision generation, color catalog only. Existing Keychain is used only when the app sends. Preparation HTTP=0.")
}
