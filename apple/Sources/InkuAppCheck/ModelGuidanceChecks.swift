import Foundation
import InkuHost
import InkuUI

@MainActor func runModelGuidanceChecks() async throws {
    // The missing native guidance must map the generated Server evaluations to
    // the actual selected ID, without turning unknown services into rated ones.
    let catalog = try ModelGuidanceCatalog.loadBundled()
    guard let manifest = try JSONSerialization.jsonObject(with: ModelGuidanceCatalog.bundledManifestData()) as? [String: Any],
          let canonical = manifest["model_catalog"] as? [String: Any],
          canonical["schema"] as? String == "inku.model-catalog.v2",
          let records = canonical["providers"] as? [String: [String: Any]] else {
        throw CheckFailure.message("Native guidance canonical v2 records unavailable")
    }
    func sourceRecord(provider: String, model: String) throws -> ProviderModelSettings {
        guard let models = records[provider]?["models"] as? [[String: Any]],
              let record = models.first(where: { $0["id"] as? String == model }) else {
            throw CheckFailure.message("Native guidance canonical record unavailable: \(provider):\(model)")
        }
        return try ModelGuidanceCatalog.modelSettings(recordData: JSONSerialization.data(withJSONObject: record))
    }
    func sourceBothLevel(_ model: ProviderModelSettings) -> Int? {
        [model.recommendationStage1, model.recommendationStage2].compactMap { $0 }.min()
            ?? model.recommendationLLM ?? model.recommendationLevel
    }
    let qwenRecord = try sourceRecord(provider: "ollama", model: "qwen3.5:4b-q4_K_M")
    let ministralRecord = try sourceRecord(provider: "ollama", model: "ministral-3:8b-instruct-2512-q4_K_M")
    let gemmaRecord = try sourceRecord(provider: "nvidia", model: "google/gemma-4-31b-it")
    let cloudRecord = try sourceRecord(provider: "ollama-cloud", model: "gemma4:31b")
    let openAIRecord = try sourceRecord(provider: "openai", model: "gpt-5.1")
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
          qwen.modelID == qwenRecord.id, qwen.purposes == qwenRecord.purposes,
          qwen.hasStageRecommendations == (qwenRecord.recommendationStage1 != nil || qwenRecord.recommendationStage2 != nil),
          qwen.stage1Level == (qwenRecord.recommendationStage1 ?? qwenRecord.recommendationLLM ?? qwenRecord.recommendationLevel),
          qwen.stage2Level == (qwenRecord.recommendationStage2 ?? qwenRecord.recommendationLLM ?? qwenRecord.recommendationLevel),
          qwen.bothStagesLevel == sourceBothLevel(qwenRecord),
          qwen.speedHidden, qwen.speedLabel == nil, qwen.speedClass == nil,
          qwen.comment(language: "ja") == qwenRecord.commentJA,
          qwen.comment(language: "en") == qwenRecord.commentEN else {
        throw CheckFailure.message("Native guidance lost the Server's stage-specific/localized Qwen evaluation or exposed developer-only speed")
    }
    guard let gemma = catalog.guidance(for: "nvidia:google/gemma-4-31b-it", providers: configured),
          gemma.hasStageRecommendations == (gemmaRecord.recommendationStage1 != nil || gemmaRecord.recommendationStage2 != nil),
          gemma.bothStagesLevel == sourceBothLevel(gemmaRecord),
          gemma.visionLevel == (gemmaRecord.recommendationVision ?? gemmaRecord.recommendationLevel),
          gemma.purposes == gemmaRecord.purposes, !gemma.speedHidden,
          gemma.speedLabel == gemmaRecord.speedLabel, gemma.speedClass == gemmaRecord.speedClass,
          gemma.comment(language: "ja") == gemmaRecord.commentJA,
          gemma.comment(language: "en") == gemmaRecord.commentEN,
          let cloudModel = catalog.guidance(for: "ollama-cloud:gemma4:31b", providers: configured),
          cloudModel.speedHidden, cloudModel.speedLabel == nil, cloudModel.purposes == cloudRecord.purposes,
          cloudModel.bothStagesLevel == sourceBothLevel(cloudRecord),
          cloudModel.visionLevel == (cloudRecord.recommendationVision ?? cloudRecord.recommendationLevel),
          cloudModel.speedLLMSeconds == cloudRecord.speedLLMSeconds,
          cloudModel.speedVisionSeconds == cloudRecord.speedVisionSeconds,
          cloudModel.comment(language: "ja") == cloudRecord.commentJA,
          cloudModel.comment(language: "en") == cloudRecord.commentEN,
          let openAIModel = catalog.guidance(for: "openai:gpt-5.1", providers: configured),
          openAIModel.hasEvaluation == openAIRecord.hasCatalogMeasurement,
          openAIModel.bothStagesLevel == sourceBothLevel(openAIRecord),
          openAIModel.visionLevel == (openAIRecord.recommendationVision ?? openAIRecord.recommendationLevel),
          openAIModel.purposes == openAIRecord.purposes,
          openAIModel.speedLLMSeconds == openAIRecord.speedLLMSeconds,
          openAIModel.speedVisionSeconds == openAIRecord.speedVisionSeconds,
          openAIModel.costUSDLLM == openAIRecord.costUSDLLM,
          openAIModel.costUSDVision == openAIRecord.costUSDVision,
          openAIModel.resolvedLabels == openAIRecord.resolvedLabels,
          openAIModel.comment(language: "ja") == openAIRecord.commentJA,
          openAIModel.comment(language: "en") == openAIRecord.commentEN else {
        throw CheckFailure.message("Native guidance differs from canonical v2 ratings, measurements, costs, labels or localized comments")
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
    guard catalog.guidance(for: app.nextDrawingModelReference, providers: settings.host.providers)?.bothStagesLevel == sourceBothLevel(qwenRecord),
          catalog.guidance(for: settings.host.models.stage1Model, providers: settings.host.providers)?.stage2Level
            == (ministralRecord.recommendationStage2 ?? ministralRecord.recommendationLLM ?? ministralRecord.recommendationLevel) else {
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
    print("Model guidance passed: canonical v2 stage/LLM/Vision ratings, measurements, costs, labels and JA/EN comments; release speed visibility; unknown boundaries; Creation/Settings IDs map independently; selected models, saved defaults and earlier request snapshot preserved; zero provider calls. Temporary DB only.")
}

private actor ModelGuidanceNoCallProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw HostError("model_guidance_check_must_not_invoke_provider")
    }
}
