import Foundation
import InkuHost
import InkuUI

/// One local fixture checks the settings affected by the Web-aligned editor.
@MainActor
func runModelSettingsUIChecks() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-model-settings-ui-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let databaseURL = directory.appendingPathComponent("works.sqlite")
    let settingsURL = directory.appendingPathComponent("providers.json")
    let transport = ModelSettingsNoCallTransport()
    let credentials = ModelSettingsNoSecretStore()
    let app = AppModel(databaseURL: databaseURL, transport: transport)
    await app.initialize()
    guard app.errorText == nil else { throw CheckFailure.message("Model settings fixture could not initialize") }
    let first = ProviderSettings(id: "model-ui-a", baseURL: URL(string: "http://127.0.0.1:1/v1")!,
        apiProfile: "mlx", requiresAPIKey: false, credentialID: "fixture-a", label: "Service A")
    let second = ProviderSettings(id: "model-ui-b", baseURL: URL(string: "http://127.0.0.1:2/v1")!,
        requiresAPIKey: false, credentialID: "fixture-b", label: "Service B")
    let original = HostSettings(providers: [first, second, .personalPlan],
        models: .init(stage1Model: "model-ui-a:ready", stage2Model: "model-ui-a:ready", stage1MaxTokens: 4096, holeMaxTokens: 1024),
        operationalLimits: try app.operationalLimitDefaults(), plugins: .init(disabledPackageIDs: ["fixture-package"]),
        drawingLimits: try app.drawingLimits(), providerDefaultsInstalled: true)
    try await app.updateHostSettings(original)
    // The two connections have no new optional fields, exercising legacy decoding.
    guard try JSONDecoder().decode(HostSettings.self, from: Data(contentsOf: settingsURL)) == original else {
        throw CheckFailure.message("Legacy optional-less connection fields did not round-trip")
    }
    let editor = SettingsModel(credentials: credentials)
    await editor.load(model: app)
    var expected = await app.hostSettings()
    @MainActor func expectSettings(_ message: String) async throws {
        guard await app.hostSettings() == expected,
              try JSONDecoder().decode(HostSettings.self, from: Data(contentsOf: settingsURL)) == expected else {
            throw CheckFailure.message(message)
        }
    }

    try await editor.saveProviderLabel(providerID: first.id, label: "Renamed A", model: app)
    expected.providers[0].label = "Renamed A"
    try await expectSettings("Name save changed unrelated settings")
    try await editor.saveProviderMemo(providerID: first.id, memo: "Author memo", model: app)
    expected.providers[0].memo = "Author memo"
    try await expectSettings("Memo save changed unrelated settings")
    try await editor.saveProviderURL(providerID: first.id, value: "http://127.0.0.1:3/v1", model: app)
    expected.providers[0].baseURL = URL(string: "http://127.0.0.1:3/v1")!
    try await expectSettings("URL save changed unrelated settings")
    let rates = ProviderRateLimits(requestsPerMinute: 7, tokensPerMinute: 9000, requestsPerDay: 19)
    try await editor.saveProviderRateLimits(providerID: first.id, limits: rates, model: app)
    expected.providers[0].rateLimits = rates
    try await expectSettings("Rate save changed unrelated settings")
    let beforeInvalidURL = try Data(contentsOf: settingsURL)
    do {
        try await editor.saveProviderURL(providerID: first.id, value: "https://example.invalid/v1?credential=fixture", model: app)
        throw CheckFailure.message("Invalid URL was saved")
    } catch let error as HostError {
        guard error.code == "provider_base_url_invalid" else { throw error }
    }
    guard try Data(contentsOf: settingsURL) == beforeInvalidURL else { throw CheckFailure.message("Rejected URL rewrote settings") }

    let catalog: [ProviderModelSettings] = [
        .init(id: "ready", label: "Ready", purposes: ["llm"], recommendationLevel: 3),
        .init(id: "hidden", label: "Hidden", purposes: ["llm"]),
        .init(id: "vision:local", label: "Vision", purposes: ["vision"]),
        .init(id: "retired", label: "Retired", purposes: ["llm"], eol: true),
        .init(id: "plan-only", label: "Plan only", purposes: ["llm"], requiresSubscription: true),
    ]
    let initialDraft = ProviderModelsDraft(models: catalog, enabled: ["hidden": false])
    guard initialDraft.filteredModels(search: "vision", filter: .all).map(\.id) == ["vision:local"],
          initialDraft.filteredModels(search: "", filter: .vision).map(\.id) == ["vision:local"],
          !initialDraft.isDirty else { throw CheckFailure.message("Searching or filtering mutated the draft") }
    var discarded = initialDraft
    discarded.setEnabled(modelID: "ready", enabled: false)
    discarded.togglePurpose(modelID: "ready", purpose: "vision")
    guard discarded.isDirty, initialDraft == ProviderModelsDraft(models: catalog, enabled: ["hidden": false]) else {
        throw CheckFailure.message("A discarded draft changed its source")
    }
    try await expectSettings("Editing without saving changed persistent settings")
    var saved = initialDraft
    saved.setVisible(models: catalog, enabled: true)
    saved.setEnabled(modelID: "hidden", enabled: false)
    saved.togglePurpose(modelID: "ready", purpose: "vision")
    var evaluated = saved.model(modelID: "ready")!
    evaluated.recommendationLevel = 5
    evaluated.commentJA = "確認済み"
    evaluated.commentEN = "Checked"
    evaluated.speedClass = "author-defined"
    evaluated.speedLabel = "local measurement"
    saved.updateModel(evaluated)
    guard !saved.isEnabled(modelID: "retired"), !saved.isEnabled(modelID: "plan-only") else {
        throw CheckFailure.message("Bulk selection enabled a blocked model")
    }
    try await editor.saveProviderModels(providerID: first.id, models: saved.models, enabled: saved.enabled, model: app)
    expected.providers[0].models = saved.models
    expected.providers[0].enabledModels = saved.enabled
    try await expectSettings("Model save changed unrelated settings")
    guard editor.publishedModels(for: expected.providers[0], purpose: "llm").map(\.id) == ["ready"],
          !editor.isModelAvailable("model-ui-a:vision:local"), !editor.isModelAvailable("model-ui-a:retired"),
          !editor.isModelAvailable("model-ui-a:plan-only"), !editor.isModelAvailable("model-ui-a:hidden"),
          app.nextDrawingModelReference == "model-ui-a:ready" else {
        throw CheckFailure.message("Drawing candidates ignored usage, purpose or blocked status")
    }
    saved.setEnabled(modelID: "ready", enabled: false)
    try await editor.saveProviderModels(providerID: first.id, models: saved.models, enabled: saved.enabled, model: app)
    expected.providers[0].enabledModels = saved.enabled
    app.inputMode = "description"
    app.descriptionText = "a green square"
    app.selectNextDrawingModel("model-ui-a:vision:local")
    guard app.nextDrawingModelReference == "model-ui-a:ready", !app.canGenerate,
          editor.availableModels(for: expected.providers[0]).contains(where: { $0.id == "model-ui-a:ready" }) else {
        throw CheckFailure.message("Disabling a model erased its saved reference or allowed new drawing")
    }
    do {
        _ = try app.requestForCurrentInput()
        throw CheckFailure.message("Request construction accepted a disabled drawing model")
    } catch let error as HostError {
        guard error.code == "drawing_model_not_available" else { throw error }
    }
    app.inputMode = "ddl"
    guard app.canGenerate else { throw CheckFailure.message("Model usage unexpectedly blocked direct DDL") }

    try await editor.addProvider(id: "custom-ui", label: "Custom", kind: .openAICompatible,
        baseURL: "http://127.0.0.1:4/v1", model: app)
    expected.providers.append(.init(id: "custom-ui", baseURL: URL(string: "http://127.0.0.1:4/v1")!,
        requiresAPIKey: false, label: "Custom", models: [], enabledModels: [:]))
    try await expectSettings("Keyless custom service changed another connection")
    try await editor.deleteProvider(providerID: "custom-ui", model: app)
    expected.providers.removeLast()
    try await expectSettings("Unrelated service deletion changed drawing defaults")

    let reopened = AppModel(databaseURL: databaseURL, transport: transport)
    await reopened.initialize()
    guard reopened.errorText == nil, await reopened.hostSettings() == expected, reopened.works.isEmpty,
          expected.providers[0].models?.first?.commentEN == "Checked" else {
        throw CheckFailure.message("Restart lost model settings or changed works")
    }
    try await editor.deleteProvider(providerID: first.id, model: app)
    expected.providers.removeFirst()
    expected.models.stage1Model = ""
    expected.models.stage2Model = ""
    try await expectSettings("Deleting the selected service failed to clear only its model references")
    guard await credentials.reads == 0, await credentials.writes == 0, await transport.calls == 0 else {
        throw CheckFailure.message("Settings-only checks touched a secret or called a provider")
    }
    print("Model settings UI passed: scoped saves and rejected URL; legacy decode; draft discard, filter and bulk selection; persisted purposes/evaluation/usage; disabled/Vision/EOL/subscription drawing guards with saved references retained; keyless add/delete and restart. Temporary settings/SQLite only, zero secret reads/writes and provider calls.")
}

private actor ModelSettingsNoSecretStore: ProviderCredentialStore {
    private(set) var reads = 0
    private(set) var writes = 0
    func isConfigured(for credentialID: String) -> Bool { false }
    func key(for credentialID: String) throws -> String? {
        reads += 1
        throw HostError("model_settings_check_must_not_read_secret")
    }
    func setKey(_ key: String?, for credentialID: String) throws {
        writes += 1
        throw HostError("model_settings_check_must_not_write_secret")
    }
}

private actor ModelSettingsNoCallTransport: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw HostError("model_settings_check_must_not_call_provider")
    }
}
