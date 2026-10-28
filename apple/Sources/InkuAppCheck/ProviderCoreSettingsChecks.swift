import Foundation
import InkuHost

@MainActor
func runProviderCoreSettingsChecks(url: URL) async throws {
    guard let cases = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any] else { throw CheckFailure.message("Invalid provider cases") }
    func equal(_ actual: Any?, _ expected: Any?, _ context: String) throws {
        let a = try JSONSerialization.data(withJSONObject: actual ?? NSNull(), options: [.sortedKeys, .fragmentsAllowed])
        let b = try JSONSerialization.data(withJSONObject: expected ?? NSNull(), options: [.sortedKeys, .fragmentsAllowed])
        guard a == b else { throw CheckFailure.message("Provider fixture mismatch: \(context)") }
    }
    func rows(_ key: String) -> [[String: Any]] { cases[key] as? [[String: Any]] ?? [] }
    func checkConversion(_ result: [String: Any], _ context: String) throws {
        let host = try ProviderCoreSettings.fromCore(result, preserving: .init())
        let encoded = ProviderCoreSettings.coreInput(host)
        guard let encodedProviders = encoded.settings["providers"] as? [String: [String: Any]] else { throw CheckFailure.message("Missing converted providers: \(context)") }
        for provider in host.providers where provider.kind != .chatGPTPlan {
            guard let record = encodedProviders[provider.id], let switches = record["enabled_models"] as? [String: Bool],
                  (provider.models ?? []).allSatisfy({ switches[$0.id] != nil }), record["api_key"] as? String == "" else {
                throw CheckFailure.message("Incomplete converted switches or leaked key: \(context) \(provider.id)")
            }
        }
    }
    let refSettings = cases["reference_settings"] as? [String: Any] ?? [:]
    let refProviders = refSettings["providers"] as? [String: Any] ?? [:]
    let adaptedReferences = try ProviderCoreSettings.fromCore(["settings": refSettings, "order": refProviders.keys.sorted()], preserving: .init())
    let adaptedProviders = ProviderModelReference.referenceProviders(adaptedReferences.providers)
    for (index, row) in rows("references").enumerated() {
        let split = try ProviderCoreSettings.call("split_ref", ["ref": row["ref"]!, "providers": refProviders])
        try equal([split["provider"] ?? NSNull(), split["model"] ?? NSNull()], row["split"], "references \(index)")
        let adaptedSplit = try ProviderCoreSettings.call("split_ref", ["ref": row["ref"]!, "providers": adaptedProviders])
        try equal([adaptedSplit["provider"] ?? NSNull(), adaptedSplit["model"] ?? NSNull()], row["split"], "adapted references \(index)")
    }
    for (index, row) in rows("resolution_cases").enumerated() {
        let settings = row["settings"] as? [String: Any] ?? [:]
        let result = try ProviderCoreSettings.call("resolve_ref", ["ref": row["ref"]!, "providers": settings["providers"] ?? [:],
            "default_provider": settings["stage1_provider"] ?? "nvidia", "default_model": settings["stage1_model"] ?? ""])
        try equal([result["provider"] ?? NSNull(), result["model"] ?? NSNull()], row["result"], "resolution \(index)")
        let sourceProviders = settings["providers"] as? [String: Any] ?? [:]
        let adapted = try ProviderCoreSettings.fromCore(["settings": settings, "order": sourceProviders.keys.sorted()], preserving: .init())
        let adaptedResult = try ProviderCoreSettings.call("resolve_ref", ["ref": row["ref"]!,
            "providers": ProviderModelReference.referenceProviders(adapted.providers), "default_provider": settings["stage1_provider"] ?? "nvidia",
            "default_model": settings["stage1_model"] ?? ""])
        try equal([adaptedResult["provider"] ?? NSNull(), adaptedResult["model"] ?? NSNull()], row["result"], "adapted resolution \(index)")
    }
    for (index, row) in rows("normalization").enumerated() {
        let input = row["input"] as? [String: Any] ?? [:]
        let order = (input["providers"] as? [String: Any] ?? [:]).keys.sorted()
        let result = try ProviderCoreSettings.call("normalize_settings", ["host":"macos", "settings": input, "order":order, "env":[:]])
        try equal(result["settings"], row["result"], "normalization \(index)")
        try checkConversion(result, "normalization \(index)")
    }
    for (index, row) in rows("updates").enumerated() {
        let patch = row["patch"] as? [String: Any] ?? [:]
        let order = (patch["providers"] as? [String: Any] ?? [:]).keys.sorted()
        let result = try ProviderCoreSettings.call("update_settings", ["host":"macos", "settings": row["input"] ?? NSNull(), "patch":patch,
            "order":[], "patch_order":order, "env":[:]])
        try equal(result["settings"], row["result"], "update \(index)")
        try checkConversion(result, "update \(index)")
    }
    for (index, row) in rows("refresh_cases").enumerated() {
        var previous = row["previous"] as? [String: Any] ?? [:]
        let previousModels = previous["models"] as? [[String: Any]] ?? []
        previous["models"] = try previousModels.map { try ProviderCoreSettings.model($0).coreCatalogRecord }
        let prepared = try ProviderCoreSettings.call("refresh_prepare", ["provider": row["provider"]!, "models": row["models"]!, "previous": previous])
        let result = try ProviderCoreSettings.call("refresh_finish", ["models": prepared["models"]!, "previous": previous, "today": row["today"]!])
        try equal(result["models"], (row["result"] as? [String: Any])?["models"], "refresh models \(index)")
        try equal(result["enabled_models"], (row["result"] as? [String: Any])?["enabled_models"], "refresh enabled \(index)")
    }
    for (index, row) in rows("access_cases").enumerated() {
        let result = try ProviderCoreSettings.call("access_probe", ["stage":row["stage"]!, "status":row["status"]!, "text":row["text"] ?? "", "today":row["today"] ?? ""])
        try equal(result["answer"], row["answer"], "access \(index)")
    }
    for (index, row) in rows("validation_cases").enumerated() {
        var input = row["input"] as? [String: Any] ?? [:]; input["host"] = "macos"
        let models = input["models"] as? [[String: Any]] ?? []
        input["models"] = try models.map { try ProviderCoreSettings.model($0).coreCatalogRecord }
        let result = try ProviderCoreSettings.call("validate_settings", input)
        let expected = row["result"] as? [String: Any] ?? [:]
        for key in expected.keys { try equal(result[key], expected[key], "validation \(index) \(key)") }
    }
    for (index, row) in rows("fetch_plan_cases").enumerated() {
        // Fixture-only placeholder; production passes an empty key to the core.
        let result = try ProviderCoreSettings.call("model_list_start", ["kind":row["kind"]!, "base_url":row["base_url"]!, "api_key":row["api_key"] ?? ""])
        for key in ["url", "headers", "items_key", "query"] { try equal(result[key], row[key], "fetch \(index) \(key)") }
        let next = try ProviderCoreSettings.call("model_list_next", ["kind":row["kind"]!, "page":row["next_page"]!])
        try equal(next["query"], row["next_query"], "fetch next \(index)")
    }
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-provider-core-check-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let nvidia = ProviderSettings(id: "nvidia", baseURL: URL(string: "https://example.invalid/v1")!, models: [
        ProviderModelSettings(id:"model-a"), ProviderModelSettings(id:"model-b"), ProviderModelSettings(id:"model-c")],
        enabledModels: ["model-a":true, "model-b":true, "model-c":false])
    let mlx = ProviderSettings(id: "custom-mlx", baseURL: URL(string: "http://localhost:8080/v1")!, apiProfile: "mlx", requiresAPIKey: false,
        credentialID: "local-test", models: [.init(id: "local", label: "Local")])
    var old = HostSettings(providers:[nvidia, mlx], providerDefaultsInstalled:true)
    let normalized = try ProviderCoreSettings.normalize(old)
    guard let new = normalized.providers.first(where: { $0.id == "nvidia" }),
          (new.models ?? []).allSatisfy({ new.enabledModels?[$0.id] != nil }),
          Set((new.models ?? []).filter { new.enabledModels?[$0.id] == true }.map(\.id)) == Set(["model-a", "model-b"]),
          !normalized.providers.contains(where: { $0.id == "openai" }),
          normalized.inactiveBuiltinProviderIDs?.contains("openai") == true else { throw CheckFailure.message("Normalization changed published models or restored a removed provider: \(normalized.providers.map(\.id)); \(normalized.providers.first(where: { $0.id == "nvidia" })?.enabledModels ?? [:]); inactive \(normalized.inactiveBuiltinProviderIDs ?? [])") }
    guard let normalizedMLX = normalized.providers.first(where: { $0.id == "custom-mlx" }),
          normalizedMLX.apiProfile == "mlx", normalizedMLX.credentialID == "local-test",
          try ProviderCoreSettings.connection(normalizedMLX).kind == .openAICompatible,
          try ProviderCoreSettings.connection(normalizedMLX).apiProfile == "mlx" else { throw CheckFailure.message("MLX connection or credential ID changed") }
    let catalog = try JSONSerialization.jsonObject(with: SharedModelCatalog.catalogData) as? [String: Any] ?? [:]
    let cloud = (catalog["providers"] as? [String: [String: Any]])?["ollama-cloud"] ?? [:]
    guard let blocked = (cloud["models"] as? [[String: Any]])?.first(where: { ($0["labels"] as? [String] ?? []).contains("subscription") }),
          let blockedID = blocked["id"] as? String else { throw CheckFailure.message("Missing subscription migration fixture") }
    let legacyCloud = ProviderSettings(id: "ollama-cloud", baseURL: URL(string: "https://ollama.com/v1")!, models: [.init(id: blockedID)])
    let migratedCloud = try ProviderCoreSettings.normalize(HostSettings(providers: [legacyCloud], providerDefaultsInstalled: true))
    guard migratedCloud.providers.first(where: { $0.id == "ollama-cloud" })?.enabledModels?[blockedID] == false else {
        throw CheckFailure.message("Legacy subscription-only catalog model became published")
    }
    let store = ProviderSettingsStore(url: folder.appendingPathComponent("providers.json"))
    old = try await store.save(old)
    let reopened = try await store.loadNormalized()
    guard old.providers == reopened.providers, reopened.inactiveBuiltinProviderIDs?.contains("openai") == true else {
        let before = old.providers.first { $0.id == "nvidia" }, after = reopened.providers.first { $0.id == "nvidia" }
        throw CheckFailure.message("Provider settings round trip failed: before \(old.providers.map(\.id)), after \(reopened.providers.map(\.id)), inactive \(reopened.inactiveBuiltinProviderIDs ?? []), models \(before?.models?.count ?? -1)/\(after?.models?.count ?? -1), enabled \(before?.enabledModels?.filter(\.value).keys.sorted() ?? [])/\(after?.enabledModels?.filter(\.value).keys.sorted() ?? [])")
    }
    print("Shared provider core settings cases and isolated migration passed. No provider calls or Keychain access.")
}
