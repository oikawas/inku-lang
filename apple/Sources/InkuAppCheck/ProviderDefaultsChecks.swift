import Foundation
import InkuHost
import InkuUI

@MainActor
func runProviderDefaultsChecks() async throws {
    let defaults = try BundledProviderDefaults.loadBundled()
    let expected: [(String, String, ProviderKind, String, Bool)] = [
        ("openai", "OpenAI API Platform", .openAICompatible, "https://api.openai.com/v1", true),
        ("anthropic", "Claude API", .anthropic, "https://api.anthropic.com", true),
        ("gemini", "Gemini API", .gemini, "https://generativelanguage.googleapis.com", true),
        ("nvidia", "NVIDIA NIM", .openAICompatible, "https://integrate.api.nvidia.com/v1", true),
        ("ollama", "Ollama", .openAICompatible, "http://localhost:11434/v1", false),
        ("ollama-cloud", "Ollama Cloud (ollama.com)", .openAICompatible, "https://ollama.com/v1", true),
    ]
    guard defaults.count == expected.count,
          zip(defaults, expected).allSatisfy({ provider, row in
              provider.id == row.0 && provider.displayName == row.1 && provider.kind == row.2
                  && provider.baseURL.absoluteString == row.3 && provider.requiresAPIKey == row.4
                  && provider.credentialID == row.0 && provider.apiProfile == nil
          }) else { throw CheckFailure.message("Bundled provider presets diverged from the fixed Server's public definitions") }

    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-provider-defaults-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let transport = ProviderDefaultsNoCallTransport()
    let app = AppModel(databaseURL: directory.appendingPathComponent("fresh/works.sqlite"), transport: transport)
    await app.initialize()
    let fresh = await app.hostSettings()
    guard app.errorText == nil, fresh.providers == defaults, fresh.models == ModelSelection(),
          fresh.providerDefaultsInstalled == true, app.works.isEmpty, await transport.calls == 0 else {
        throw CheckFailure.message("Fresh app did not install presets locally without choosing a model or calling a provider: \(app.errorText ?? app.status)")
    }

    let store = ProviderSettingsStore(url: directory.appendingPathComponent("legacy/providers.json"))
    let customOpenAI = ProviderSettings(id: "openai", kind: .openAICompatible,
        baseURL: URL(string: "http://127.0.0.1:18001/v1")!, apiProfile: "mlx", requiresAPIKey: false,
        credentialID: "author-openai", rateLimits: .init(requestsPerMinute: 7, tokensPerMinute: 9000, requestsPerDay: 19))
    let custom = ProviderSettings(id: "custom", baseURL: URL(string: "http://127.0.0.1:18002/v1")!,
                                  requiresAPIKey: false, credentialID: "author-custom", label: "Author connection")
    let legacy = HostSettings(providers: [customOpenAI, custom, .personalPlan],
        models: .init(stage1Model: "custom:original", stage2Model: "custom:original", stage1MaxTokens: 4096, holeMaxTokens: 1024),
        operationalLimits: ["max_input_chars": 1200], plugins: .init(disabledPackageIDs: ["author-package"]),
        drawingLimits: ["max_marks": 400])
    try await store.save(legacy)
    let added = try await store.load(installingDefaults: defaults)
    var expectedLegacy = legacy
    expectedLegacy.providers += defaults.filter { $0.id != "openai" }
    expectedLegacy.providerDefaultsInstalled = true
    guard added == expectedLegacy else { throw CheckFailure.message("Preset installation overwrote an existing connection, model, or other host setting") }
    let bytes = try Data(contentsOf: store.url)
    let modification = try FileManager.default.attributesOfItem(atPath: store.url.path)[.modificationDate] as? Date
    let reloaded = try await store.load(installingDefaults: defaults)
    guard reloaded == added, try Data(contentsOf: store.url) == bytes,
          try FileManager.default.attributesOfItem(atPath: store.url.path)[.modificationDate] as? Date == modification else {
        throw CheckFailure.message("A second preset load duplicated entries or rewrote settings")
    }
    var deleted = added
    deleted.providers.removeAll { $0.id == "nvidia" }
    try await store.save(deleted)
    guard try await store.load(installingDefaults: defaults) == deleted else {
        throw CheckFailure.message("Preset load restored a provider intentionally deleted by the author")
    }

    // Editing through AppModel must preserve the installation marker even when
    // an older caller builds HostSettings without knowing the new optional field.
    var changed = fresh
    changed.providers.removeAll { $0.id == "anthropic" }
    changed.providerDefaultsInstalled = nil
    try await app.updateHostSettings(changed)
    let reopened = AppModel(databaseURL: directory.appendingPathComponent("fresh/works.sqlite"), transport: transport)
    await reopened.initialize()
    let reopenedSettings = await reopened.hostSettings()
    guard reopened.errorText == nil, reopenedSettings.providerDefaultsInstalled == true,
          reopenedSettings.providers == changed.providers, await transport.calls == 0 else {
        throw CheckFailure.message("App settings save lost the preset marker and restored a deleted connection")
    }

    let state = SettingsModel()
    state.host = fresh
    let openAI = defaults[0]
    let candidates = state.availableModels(for: openAI)
    let wrongKind = ProviderSettings(id: "openai", kind: .anthropic, baseURL: openAI.baseURL)
    guard candidates.contains(where: { $0.id == "openai:gpt-5.1" && $0.name == "GPT-5.1" }),
          state.availableModels(for: custom).isEmpty,
          state.availableModels(for: wrongKind).isEmpty else {
        throw CheckFailure.message("Bundled model candidates were missing or applied to a custom/different-kind provider")
    }
    guard try SettingsModel.modelCatalogURL(for: defaults[1]).absoluteString == "https://api.anthropic.com/v1/models",
          try SettingsModel.modelCatalogURL(for: defaults[2]).absoluteString == "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
          try SettingsModel.modelCatalogURL(for: openAI).absoluteString == "https://api.openai.com/v1/models" else {
        throw CheckFailure.message("Standard provider discovery omitted its API version path")
    }
    print("Provider defaults passed: fixed Server six presets; fresh app and missing-only legacy migration; original settings preserved; idempotent load and intentional deletion; offline model candidates and discovery URLs; zero provider calls. Temporary settings/SQLite only, no credential operations.")
}

private actor ProviderDefaultsNoCallTransport: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw HostError("provider_defaults_check_must_not_call_provider")
    }
}
