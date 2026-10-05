import Foundation
import InkuHost
import InkuUI

@MainActor func runModelSelectionChecks() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-model-selection-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }

    let transport = ModelSelectionNoCallProvider()
    let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"), transport: transport)
    await app.initialize()
    guard app.errorText == nil, !app.catalogs.isEmpty, !app.canvases.isEmpty else {
        throw CheckFailure.message("Model selection fixture did not load its bundled Bootstrap: \(app.errorText ?? app.status)")
    }
    let provider = ProviderSettings(id: "selection-check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false)
    let configured = "selection-check:settings-default"
    let chosen = "selection-check:next-drawing"
    let subsequent = "selection-check:later-drawing"
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: configured, stage2Model: configured)))
    app.inputMode = "description"
    app.descriptionText = "one red circle at center"
    app.language = "en"
    app.seedText = "42"

    // A picker choice must reach the same fresh request that batch and demo capture.
    app.selectNextDrawingModel(chosen)
    let captured = try app.requestForCurrentInput()
    guard case .description = captured.authoring,
          captured.models.stage1Model == chosen, captured.models.stage2Model == chosen,
          captured.providers == [provider] else {
        throw CheckFailure.message("Fresh generation template sent the Settings default instead of the selected drawing model")
    }
    let authoritative = await app.hostSettings()
    guard authoritative.models.stage1Model == configured, authoritative.models.stage2Model == configured else {
        throw CheckFailure.message("The next drawing-model choice changed authoritative Settings defaults")
    }

    app.selectNextDrawingModel(subsequent)
    app.descriptionText = "one blue circle at center"
    let demo = try app.makeDemoRequest(template: captured, description: "two red circles", randomizeSeed: false)
    guard captured.models.stage1Model == chosen, captured.models.stage2Model == chosen,
          demo.models.stage1Model == chosen, demo.models.stage2Model == chosen else {
        throw CheckFailure.message("A captured batch/demo template adopted a later UI model choice")
    }
    let fresh = try app.requestForCurrentInput()
    guard fresh.models.stage1Model == subsequent, fresh.models.stage2Model == subsequent else {
        throw CheckFailure.message("A fresh generation request did not adopt the new next-model choice")
    }

    app.selectNextDrawingModel("unconfigured-provider:rejected")
    let afterInvalidChoice = try app.requestForCurrentInput()
    let persisted = try JSONDecoder().decode(HostSettings.self, from: Data(contentsOf: directory.appendingPathComponent("providers.json")))
    guard app.nextDrawingModelReference == subsequent,
          afterInvalidChoice.models.stage1Model == subsequent, afterInvalidChoice.models.stage2Model == subsequent,
          persisted.models.stage1Model == configured, persisted.models.stage2Model == configured,
          app.works.isEmpty, await transport.calls == 0 else {
        throw CheckFailure.message("An invalid provider changed the selection, defaults were persisted, or request capture invoked a provider")
    }
    print("Model selection passed: selected Stage1=Stage2 in fresh generation; Settings defaults unchanged; captured batch/demo template pinned; fresh request adopts new selection; invalid provider ignored; zero provider calls. Isolated DB and bundled Bootstrap only.")
}

private actor ModelSelectionNoCallProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw HostError("model_selection_check_must_not_invoke_provider")
    }
}
