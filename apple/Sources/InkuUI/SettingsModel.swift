import Foundation
import InkuHost
import Observation

public struct ProviderModelInfo: Identifiable, Sendable {
    public let id: String
    public let name: String
    public let contextLimit: Int?
    public let capabilities: [String]
    public init(id: String, name: String, contextLimit: Int?, capabilities: [String]) {
        self.id = id; self.name = name; self.contextLimit = contextLimit; self.capabilities = capabilities
    }
}

/// Editable service settings contain no readable credential value.
@MainActor @Observable
public final class SettingsModel {
    public var host = HostSettings()
    public var selectedProviderID: String? {
        didSet {
            guard oldValue != selectedProviderID else { return }
            cancelDiscovery()
            discoveredModelCatalog = []
            modelCatalogProvider = nil
            credentialDraft = ""
            credentialConfigured = selectedProviderID.flatMap { credentialStates[$0] } ?? false
            status = ""
        }
    }
    public var credentialDraft = ""
    public var modelCatalog: [ProviderModelInfo] {
        modelCatalogProvider == selectedProvider ? discoveredModelCatalog : []
    }
    public private(set) var isLoadingModels = false
    public private(set) var status = ""
    public private(set) var credentialConfigured = false
    public private(set) var credentialStates: [String: Bool] = [:]
    public var error: String?
    private var discoveredModelCatalog: [ProviderModelInfo] = []
    private var modelCatalogProvider: ProviderSettings?
    @ObservationIgnored private let credentials: any ProviderCredentialStore
    @ObservationIgnored private var discovery: Task<[ProviderModelInfo], Error>?
    @ObservationIgnored private var discoveryID: UUID?
    @ObservationIgnored private var isSaving = false
    public init(credentials: any ProviderCredentialStore = KeychainCredentialStore()) { self.credentials = credentials }

    public var providerIndex: Int? { host.providers.firstIndex { $0.id == selectedProviderID && $0.kind != .chatGPTPlan } }
    public var selectedProvider: ProviderSettings? { providerIndex.map { host.providers[$0] } }
    public var orderedProviders: [ProviderSettings] {
        host.providers.enumerated().filter { $0.element.kind != .chatGPTPlan }.sorted {
            func priority(_ provider: ProviderSettings) -> Int {
                switch provider.id { case "ollama-cloud": return 0; case "ollama": return 1; default: return 2 }
            }
            let first = priority($0.element), second = priority($1.element)
            return first == second ? $0.offset < $1.offset : first < second
        }.map(\.element)
    }

    public func catalogModels(for provider: ProviderSettings) -> [ProviderModelSettings] {
        provider.models ?? ModelGuidanceCatalog.bundled?.registeredModelSettings(for: provider) ?? []
    }

    public func publishedModels(for provider: ProviderSettings, purpose: String? = nil) -> [ProviderModelSettings] {
        catalogModels(for: provider).filter { entry in
            entry.isSelectable && provider.enabledModels?[entry.id] != false
                && (purpose.map { entry.purposes.contains($0) } ?? true)
        }
    }

    public func isModelAvailable(_ reference: String) -> Bool {
        Self.isModelAvailable(reference, settings: host)
    }

    public nonisolated static func isModelAvailable(_ reference: String, settings: HostSettings) -> Bool {
        let (providerID, modelID) = ProviderModelReference.resolve(reference, providers: settings.providers)
        guard !modelID.isEmpty, let provider = settings.providers.first(where: { $0.id == providerID }) else { return false }
        guard provider.enabledModels?[modelID] != false else { return false }
        let models = provider.models ?? ModelGuidanceCatalog.bundled?.registeredModelSettings(for: provider) ?? []
        guard let model = models.first(where: { $0.id == modelID }) else { return false }
        return model.isSelectable && model.purposes.contains("llm")
    }

    /// Batch pickers offer only registered, enabled LLM entries; saved custom references are not candidates.
    public nonisolated static func batchModels(for provider: ProviderSettings) -> [ProviderModelSettings] {
        registeredModels(for: provider, purpose: "llm")
    }

    public nonisolated static func registeredModels(for provider: ProviderSettings, purpose: String) -> [ProviderModelSettings] {
        let models = provider.models ?? ModelGuidanceCatalog.bundled?.registeredModelSettings(for: provider) ?? []
        return models.filter { $0.purposes.contains(purpose) && provider.enabledModels?[$0.id] != false }
    }

    public nonisolated static func isRegisteredModelAvailable(_ reference: String, purpose: String, settings: HostSettings) -> Bool {
        let (providerID, modelID) = ProviderModelReference.resolve(reference, providers: settings.providers)
        guard let provider = settings.providers.first(where: { $0.id == providerID }) else { return false }
        return registeredModels(for: provider, purpose: purpose).contains { $0.id == modelID && $0.isSelectable }
    }

    public nonisolated static func isBatchModelAvailable(_ reference: String, settings: HostSettings) -> Bool {
        let (providerID, modelID) = ProviderModelReference.resolve(reference, providers: settings.providers)
        guard !modelID.isEmpty, let provider = settings.providers.first(where: { $0.id == providerID }) else { return false }
        return batchModels(for: provider).contains { $0.id == modelID && $0.isSelectable }
    }

    public func availableModels(for provider: ProviderSettings, configuredReferences: [String] = [],
                                discoveredModels: [ProviderModelInfo]? = nil) -> [ProviderModelInfo] {
        let prefix = provider.id + ":"
        let configured = ([host.models.stage1Model, host.models.stage2Model] + configuredReferences)
            .filter { $0.hasPrefix(prefix) && $0.count > prefix.count }
        let savedModels = catalogModels(for: provider)
        let published = publishedModels(for: provider, purpose: "llm")
        let publishedIDs = Set(published.map(\.id))
        let discovered = discoveredModels ?? (modelCatalogProvider == provider ? discoveredModelCatalog : [])
        let offered = discovered.filter {
            guard $0.id.hasPrefix(prefix), $0.id.count > prefix.count else { return false }
            let rawID = String($0.id.dropFirst(prefix.count))
            if provider.models != nil { return publishedIDs.contains(rawID) }
            return provider.enabledModels?[rawID] != false
                && (savedModels.first(where: { $0.id == rawID }).map { $0.isSelectable && $0.purposes.contains("llm") } ?? true)
        }.map { info in
            let rawID = String(info.id.dropFirst(prefix.count))
            return ProviderModelInfo(id: info.id, name: savedModels.first(where: { $0.id == rawID })?.label ?? info.name,
                                     contextLimit: info.contextLimit, capabilities: info.capabilities)
        }
        let registered = published.map {
            ProviderModelInfo(id: prefix + $0.id, name: $0.label, contextLimit: nil, capabilities: [])
        }
        let retained = configured.map { reference in
            let rawID = String(reference.dropFirst(prefix.count))
            return ProviderModelInfo(id: reference, name: savedModels.first(where: { $0.id == rawID })?.label ?? rawID,
                                     contextLimit: nil, capabilities: [])
        }
        var seen: Set<String> = []
        // Saved references remain visible even when their use has been disabled.
        return (offered + registered + retained)
            .filter { seen.insert($0.id).inserted }
    }

    public nonisolated static func modelCatalogURL(for provider: ProviderSettings) throws -> URL {
        try provider.validate()
        let version: String?
        switch provider.kind {
        case .openAICompatible: version = nil
        case .anthropic: version = "v1"
        case .gemini: version = "v1beta"
        case .chatGPTPlan: throw HostError("personal_plan_model_catalog_requires_runtime")
        }
        var base = provider.baseURL
        if let version, base.lastPathComponent != version { base.appendPathComponent(version) }
        let endpoint = base.appendingPathComponent("models")
        guard provider.kind == .gemini else { return endpoint }
        guard var parts = URLComponents(url: endpoint, resolvingAgainstBaseURL: false) else {
            throw HostError("provider_base_url_invalid")
        }
        parts.queryItems = [URLQueryItem(name: "pageSize", value: "1000")]
        guard let url = parts.url else { throw HostError("provider_base_url_invalid") }
        return url
    }

    public func load(model: AppModel) async {
        host = await model.hostSettings()
        if providerIndex == nil { selectedProviderID = orderedProviders.first?.id }
        await inspectAllCredentials()
    }
    public func inspectAllCredentials() async {
        let providers = orderedProviders
        var states: [String: Bool] = [:]
        credentialStates = [:]
        credentialConfigured = false
        do {
            for provider in providers { states[provider.id] = try await credentials.isConfigured(for: provider.credentialID) }
            guard providers == orderedProviders else { return }
            credentialStates = states
            credentialConfigured = selectedProviderID.flatMap { states[$0] } ?? false
        } catch { self.error = "APIキーの状態を確認できません。" }
    }
    public func inspectCredential() async {
        credentialDraft = ""
        guard let provider = selectedProvider else { credentialConfigured = false; return }
        credentialStates.removeValue(forKey: provider.id)
        credentialConfigured = false
        do {
            let configured = try await credentials.isConfigured(for: provider.credentialID)
            guard selectedProvider?.id == provider.id, selectedProvider?.credentialID == provider.credentialID else { return }
            credentialStates[provider.id] = configured
            credentialConfigured = configured
        }
        catch { self.error = "APIキーの状態を確認できません。" }
    }
    public func saveProviderLabel(providerID: String, label: String, model: AppModel) async throws {
        try await saveProvider(providerID: providerID, model: model) { $0.label = label.trimmingCharacters(in: .whitespacesAndNewlines) }
        status = "サービス名を保存しました。"
    }

    public func saveProviderMemo(providerID: String, memo: String, model: AppModel) async throws {
        try await saveProvider(providerID: providerID, model: model) { $0.memo = memo }
        status = "メモを保存しました。"
    }

    public func saveProviderURL(providerID: String, value: String, model: AppModel) async throws {
        let value = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: value), !value.isEmpty else { throw HostError("provider_base_url_invalid") }
        try await saveProvider(providerID: providerID, model: model) { $0.baseURL = url }
        status = "接続設定を保存しました。"
    }

    public func saveProviderRateLimits(providerID: String, limits: ProviderRateLimits, model: AppModel) async throws {
        try await saveProvider(providerID: providerID, model: model) { $0.rateLimits = limits }
        status = "レート制限を保存しました。"
    }

    public func saveProviderModels(providerID: String, models: [ProviderModelSettings], enabled: [String: Bool], model: AppModel) async throws {
        try await saveProvider(providerID: providerID, model: model) {
            $0.models = models
            $0.enabledModels = enabled
        }
        status = "使用するモデルを保存しました。"
    }

    public func addProvider(id: String, label: String, kind: ProviderKind, baseURL: String, apiProfile: String? = nil,
                            apiKey: String = "", model: AppModel) async throws {
        let id = id.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !id.isEmpty, id.range(of: "^[a-z0-9_-]+$", options: .regularExpression) != nil, id != "chatgpt"
        else { throw HostError("provider_id_invalid") }
        guard kind != .chatGPTPlan else { throw HostError("personal_plan_provider_settings_required") }
        guard let url = URL(string: baseURL.trimmingCharacters(in: .whitespacesAndNewlines)) else { throw HostError("provider_base_url_invalid") }
        let key = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        let label = label.trimmingCharacters(in: .whitespacesAndNewlines)
        let provider = ProviderSettings(id: id, kind: kind, baseURL: url, apiProfile: apiProfile,
                                        requiresAPIKey: !key.isEmpty, label: label.isEmpty ? id : label,
                                        models: [], enabledModels: [:])
        try provider.validate()
        try beginSaving(model: model, credentialMutation: !key.isEmpty)
        defer { isSaving = false }
        var latest = await model.hostSettings()
        guard !latest.providers.contains(where: { $0.id == id }) else { throw HostError("duplicate_provider") }
        latest.providers.append(provider)
        try latest.providers.forEach { try $0.validate() }
        // Validate the settings change before writing its optional secret.
        if !key.isEmpty {
            guard !model.isBusy else { throw HostError("settings_busy_or_unavailable") }
            try await credentials.setKey(key, for: provider.credentialID)
        }
        try await model.updateHostSettings(latest)
        host = await model.hostSettings()
        selectedProviderID = id
        if !key.isEmpty {
            credentialStates[id] = true
            credentialConfigured = true
        } else {
            credentialStates.removeValue(forKey: id)
            await inspectCredential()
        }
        credentialDraft = ""
        status = "サービスを追加しました。"
    }

    public func deleteProvider(providerID: String, model: AppModel) async throws {
        try await saveSettings(model: model) { settings in
            _ = try Self.editableProviderIndex(providerID, in: settings)
            settings.providers.removeAll { $0.id == providerID }
            if settings.models.stage1Model.hasPrefix(providerID + ":") { settings.models.stage1Model = "" }
            if settings.models.stage2Model.hasPrefix(providerID + ":") { settings.models.stage2Model = "" }
        }
        credentialStates.removeValue(forKey: providerID)
        if selectedProviderID == providerID { selectedProviderID = orderedProviders.first?.id }
        status = "サービスを削除しました。"
    }

    public func saveProviderCredential(providerID: String, key: String, model: AppModel) async throws {
        let key = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { throw HostError("provider_credentials_missing") }
        try beginSaving(model: model, credentialMutation: true)
        defer { isSaving = false; credentialDraft = "" }
        var latest = await model.hostSettings()
        let index = try Self.editableProviderIndex(providerID, in: latest)
        latest.providers[index].requiresAPIKey = true
        try latest.providers.forEach { try $0.validate() }
        guard !model.isBusy else { throw HostError("settings_busy_or_unavailable") }
        try await credentials.setKey(key, for: latest.providers[index].credentialID)
        try await model.updateHostSettings(latest)
        host = await model.hostSettings()
        credentialStates[providerID] = true
        if selectedProviderID == providerID { credentialConfigured = true }
        status = "APIキーを保存しました。"
    }

    public func clearProviderCredential(providerID: String, model: AppModel) async throws {
        try beginSaving(model: model, credentialMutation: true)
        defer { isSaving = false; credentialDraft = "" }
        let latest = await model.hostSettings()
        let index = try Self.editableProviderIndex(providerID, in: latest)
        guard !model.isBusy else { throw HostError("settings_busy_or_unavailable") }
        try await credentials.setKey(nil, for: latest.providers[index].credentialID)
        host = latest
        credentialStates[providerID] = false
        if selectedProviderID == providerID { credentialConfigured = false }
        status = "APIキーを削除しました。"
    }

    public func saveDrawingDefaults(models: ModelSelection, model: AppModel) async throws {
        let latest = await model.hostSettings()
        guard Self.isBatchModelAvailable(models.stage1Model, settings: latest), models.stage2Model == models.stage1Model else {
            throw HostError("drawing_model_unavailable")
        }
        try await saveSettings(model: model) { $0.models = models }
        status = "通常の描画モデルを保存しました。"
    }

    @discardableResult
    public func fetchProviderModels(providerID: String, model: AppModel) async throws -> [ProviderModelSettings] {
        guard !model.isBrowsingLocked else { throw HostError("settings_busy_or_unavailable") }
        let latest = await model.hostSettings()
        let provider = latest.providers[try Self.editableProviderIndex(providerID, in: latest)]
        let fetched = try await fetchModelCatalog(for: provider)
        try Task.checkCancellation()
        try await saveProvider(providerID: providerID, model: model) { current in
            guard current.baseURL == provider.baseURL, current.kind == provider.kind,
                  current.apiProfile == provider.apiProfile, current.credentialID == provider.credentialID
            else { throw HostError("provider_configuration_changed") }
            var merged = catalogModels(for: current)
            var known = Set(merged.map(\.id))
            let prefix = providerID + ":"
            for model in fetched where model.id.hasPrefix(prefix) {
                let id = String(model.id.dropFirst(prefix.count))
                guard !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, known.insert(id).inserted else { continue }
                merged.append(.init(id: id, label: model.name))
            }
            current.models = merged
        }
        guard let current = host.providers.first(where: { $0.id == providerID }) else { throw HostError("provider_missing") }
        if selectedProviderID == providerID {
            modelCatalogProvider = current
            discoveredModelCatalog = fetched
        }
        status = "\(fetched.count)個のモデルを取得しました。"
        return catalogModels(for: current)
    }

    private func beginSaving(model: AppModel, credentialMutation: Bool = false) throws {
        guard !isSaving, !(credentialMutation ? model.isBusy : model.isBrowsingLocked) else {
            throw HostError("settings_busy_or_unavailable")
        }
        isSaving = true
    }

    private static func editableProviderIndex(_ providerID: String, in settings: HostSettings) throws -> Int {
        guard let index = settings.providers.firstIndex(where: { $0.id == providerID }) else { throw HostError("provider_missing") }
        guard settings.providers[index].kind != .chatGPTPlan else { throw HostError("personal_plan_provider_settings_required") }
        return index
    }

    private func saveProvider(providerID: String, model: AppModel, update: (inout ProviderSettings) throws -> Void) async throws {
        try await saveSettings(model: model) { settings in
            let index = try Self.editableProviderIndex(providerID, in: settings)
            try update(&settings.providers[index])
            try settings.providers[index].validate()
        }
    }

    private func saveSettings(model: AppModel, update: (inout HostSettings) throws -> Void) async throws {
        try beginSaving(model: model)
        defer { isSaving = false }
        var latest = await model.hostSettings()
        try update(&latest)
        try await model.updateHostSettings(latest)
        host = await model.hostSettings()
    }

    public func addProvider() {
        let id = "service-" + UUID().uuidString.prefix(8).lowercased()
        host.providers.append(ProviderSettings(id: id, baseURL: URL(string: "http://localhost:8080/v1")!, requiresAPIKey: false))
        selectedProviderID = id
        credentialDraft = ""
        credentialConfigured = false
        discoveredModelCatalog = []
        modelCatalogProvider = nil
    }
    public func removeProvider() {
        guard let id = selectedProvider?.id else { return }
        discovery?.cancel()
        host.providers.removeAll { $0.id == id }
        if host.models.stage1Model.hasPrefix(id + ":") { host.models.stage1Model = "" }
        if host.models.stage2Model.hasPrefix(id + ":") { host.models.stage2Model = "" }
        selectedProviderID = host.providers.first?.id
        discoveredModelCatalog = []
        modelCatalogProvider = nil
        credentialDraft = ""
    }
    public func save(model: AppModel) async {
        do {
            let draft = host
            try await saveSettings(model: model) { latest in
                latest.providers = draft.providers.filter { $0.kind != .chatGPTPlan } + latest.providers.filter { $0.kind == .chatGPTPlan }
                latest.models = draft.models
            }
            status = "接続設定を保存しました。"
        } catch {
            self.error = (error as? HostError)?.code == "invalid_provider_rate_limits"
                ? "レート制限には0から1,000,000,000までの整数を設定してください。"
                : error.localizedDescription
        }
    }
    public func clearCredential() async {
        guard let provider = selectedProvider else { return }
        do {
            try await credentials.setKey(nil, for: provider.credentialID)
            credentialDraft = ""
            credentialStates[provider.id] = false
            credentialConfigured = false
        } catch { self.error = "APIキーを削除できませんでした。" }
    }

    public func discoverModels() async {
        guard let provider = selectedProvider else { return }
        do {
            let models = try await fetchModelCatalog(for: provider)
            guard selectedProvider == provider else { return }
            modelCatalogProvider = provider
            discoveredModelCatalog = models
            status = "\(models.count)個のモデルを取得しました。"
        } catch is CancellationError { }
        catch { self.error = "モデル一覧を取得できませんでした。" }
    }
    public func cancelDiscovery() { discovery?.cancel() }

    private func fetchModelCatalog(for provider: ProviderSettings) async throws -> [ProviderModelInfo] {
        guard !isLoadingModels else { throw HostError("model_catalog_busy") }
        guard provider.kind != .chatGPTPlan else { throw HostError("personal_plan_model_catalog_requires_runtime") }
        let token = UUID()
        isLoadingModels = true
        discoveryID = token
        error = nil
        let operation = Task { @MainActor in try await self.requestModels(for: provider) }
        discovery = operation
        defer {
            if discoveryID == token { isLoadingModels = false; discovery = nil; discoveryID = nil }
        }
        return try await withTaskCancellationHandler {
            let models = try await operation.value
            try Task.checkCancellation()
            guard !operation.isCancelled else { throw CancellationError() }
            return models
        } onCancel: {
            operation.cancel()
        }
    }

    private func requestModels(for provider: ProviderSettings) async throws -> [ProviderModelInfo] {
        try Task.checkCancellation()
        let url = try Self.modelCatalogURL(for: provider)
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        let key = provider.requiresAPIKey ? try await credentials.key(for: provider.credentialID) : nil
        try Task.checkCancellation()
        if provider.requiresAPIKey && (key == nil || key?.isEmpty == true) { throw HostError("provider_credentials_missing") }
        if let key, !key.isEmpty {
            switch provider.kind {
            case .gemini: request.setValue(key, forHTTPHeaderField: "x-goog-api-key")
            case .anthropic:
                request.setValue(key, forHTTPHeaderField: "x-api-key")
                request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
            case .openAICompatible: request.setValue("Bearer " + key, forHTTPHeaderField: "Authorization")
            case .chatGPTPlan: throw HostError("personal_plan_model_catalog_requires_runtime")
            }
        }
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForResource = 30
        let session = URLSession(configuration: config, delegate: ModelCatalogRedirectPolicy(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw HostError("model_catalog_http_failure") }
        var data = Data()
        for try await byte in bytes {
            try Task.checkCancellation()
            guard data.count < 4 * 1024 * 1024 else { throw HostError("model_catalog_too_large") }
            data.append(byte)
        }
        try Task.checkCancellation()
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        let rows = (json["data"] ?? json["models"]) as? [[String: Any]] ?? []
        var seen: Set<String> = []
        return rows.compactMap { row -> ProviderModelInfo? in
            guard let raw = (row["id"] ?? row["name"]) as? String else { return nil }
            let slug = raw.hasPrefix("models/") ? String(raw.dropFirst(7)) : raw
            guard !slug.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, seen.insert(slug).inserted else { return nil }
            return ProviderModelInfo(id: provider.id + ":" + slug,
                                     name: (row["displayName"] ?? row["display_name"]) as? String ?? slug,
                                     contextLimit: row["inputTokenLimit"] as? Int,
                                     capabilities: row["supportedGenerationMethods"] as? [String] ?? [])
        }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }
}

private final class ModelCatalogRedirectPolicy: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
