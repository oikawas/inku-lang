import Foundation
import InkuHost
import InkuUI

@MainActor func runModelGuidanceChecks() async throws {
    // The missing native guidance must map the generated Server evaluations to
    // the actual selected ID, without turning unknown services into rated ones.
    let catalog = try ModelGuidanceCatalog.loadBundled()
    let endpoint = URL(string: "http://127.0.0.1:1/v1")!
    let local = ProviderSettings(id: "ollama", baseURL: endpoint, requiresAPIKey: false,
                                 credentialID: "guidance-check-\(UUID().uuidString)")
    let nvidia = ProviderSettings(id: "nvidia", baseURL: endpoint, requiresAPIKey: false)
    let cloud = ProviderSettings(id: "ollama-cloud", baseURL: endpoint, requiresAPIKey: false)
    let openAI = ProviderSettings(id: "openai", baseURL: endpoint, requiresAPIKey: false)
    let custom = ProviderSettings(id: "guidance-custom", baseURL: endpoint, requiresAPIKey: false)
    let configured = [local, nvidia, cloud, openAI, custom]
    let selected = "ollama:qwen3.5:4b-q4_K_M"
    guard let qwen = catalog.guidance(for: selected, providers: configured),
          qwen.modelID == "qwen3.5:4b-q4_K_M", qwen.purposes == ["llm"],
          qwen.hasStageRecommendations, qwen.stage1Level == 5, qwen.stage2Level == 2, qwen.bothStagesLevel == 2,
          qwen.speedHidden, qwen.speedLabel == nil, qwen.speedClass == nil,
          qwen.comment(language: "ja")?.contains("第二段階では被覆 9/28") == true,
          qwen.comment(language: "en")?.contains("Stage 2 coverage is 9 of 28") == true,
          qwen.comment(language: "en") != qwen.comment(language: "ja") else {
        throw CheckFailure.message("Native guidance lost the Server's stage-specific/localized Qwen evaluation or exposed developer-only speed")
    }
    guard let gemma = catalog.guidance(for: "nvidia:google/gemma-4-31b-it", providers: configured),
          !gemma.hasStageRecommendations, gemma.bothStagesLevel == 4, gemma.visionLevel == 5,
          gemma.purposes == ["llm", "vision"], !gemma.speedHidden, gemma.speedLabel != nil,
          let cloudModel = catalog.guidance(for: "ollama-cloud:gemma4:31b", providers: configured),
          cloudModel.speedHidden, cloudModel.speedLabel == nil,
          let unscored = catalog.guidance(for: "openai:gpt-5.1", providers: configured),
          !unscored.hasEvaluation, unscored.bothStagesLevel == nil, unscored.visionLevel == nil else {
        throw CheckFailure.message("Native guidance confused LLM and Vision ratings, release speed visibility, or unrated registered models")
    }
    let wrongKind = ProviderSettings(id: "ollama", kind: .anthropic, baseURL: endpoint, requiresAPIKey: false)
    guard catalog.guidance(for: "guidance-custom:qwen3.5:4b-q4_K_M", providers: configured) == nil,
          catalog.guidance(for: "ollama:qwen3.5:4b", providers: configured) == nil,
          catalog.guidance(for: selected, providers: [wrongKind]) == nil,
          catalog.guidance(for: selected, providers: []) == nil,
          catalog.guidance(for: "qwen3.5:4b-q4_K_M", providers: configured) == nil else {
        throw CheckFailure.message("Native guidance inferred an evaluation for an unknown model, custom provider, wrong wire kind or unqualified reference")
    }

    // Use the real fresh-request capture and on-disk defaults boundary, rather
    // than checking only a picker assignment or a view's local properties.
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-model-guidance-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let transport = ModelGuidanceNoCallProvider()
    let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"), transport: transport)
    await app.initialize()
    guard app.errorText == nil, !app.catalogs.isEmpty, !app.canvases.isEmpty else {
        throw CheckFailure.message("Model guidance fixture could not load the bundled Bootstrap: \(app.errorText ?? app.status)")
    }
    let savedDefault = "ollama:ministral-3:8b-instruct-2512-q4_K_M"
    try await app.updateHostSettings(HostSettings(providers: [local], models: ModelSelection(stage1Model: savedDefault, stage2Model: savedDefault)))
    app.inputMode = "description"
    app.descriptionText = "one red circle at center"
    app.language = "en"
    app.seedText = "42"
    app.selectNextDrawingModel(selected)
    let captured = try app.requestForCurrentInput()
    let defaultsURL = directory.appendingPathComponent("providers.json")
    let savedBytes = try Data(contentsOf: defaultsURL)
    let settings = SettingsModel()
    await settings.load(model: app)
    guard catalog.guidance(for: app.nextDrawingModelReference, providers: settings.host.providers)?.bothStagesLevel == 2,
          catalog.guidance(for: settings.host.models.stage1Model, providers: settings.host.providers)?.stage2Level == 5 else {
        throw CheckFailure.message("Creation and Settings selected IDs did not resolve to their respective Server evaluations")
    }
    app.selectNextDrawingModel(savedDefault)
    _ = catalog.guidance(for: app.nextDrawingModelReference, providers: settings.host.providers)
    let fresh = try app.requestForCurrentInput()
    let authoritative = await app.hostSettings()
    let unchangedBytes = try Data(contentsOf: defaultsURL)
    guard captured.models.stage1Model == selected, captured.models.stage2Model == selected,
          fresh.models.stage1Model == savedDefault, fresh.models.stage2Model == savedDefault,
          authoritative.models.stage1Model == savedDefault, authoritative.models.stage2Model == savedDefault,
          app.nextDrawingModelReference == savedDefault, unchangedBytes == savedBytes,
          app.works.isEmpty, await transport.calls == 0 else {
        throw CheckFailure.message("Reading model guidance changed selection, saved defaults, an earlier request snapshot, or invoked a provider")
    }
    print("Model guidance passed: bundled Server stage 5/2/both 2 and JA/EN comments; LLM/Vision separate; release speed visibility; unknown boundaries; Creation/Settings IDs map independently; selected models, saved defaults and earlier request snapshot preserved; zero provider calls. Temporary DB only.")
}

private actor ModelGuidanceNoCallProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw HostError("model_guidance_check_must_not_invoke_provider")
    }
}
