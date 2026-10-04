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
            credentialConfigured = false
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
    public var error: String?
    private var discoveredModelCatalog: [ProviderModelInfo] = []
    private var modelCatalogProvider: ProviderSettings?
    @ObservationIgnored private let credentials = KeychainCredentialStore()
    @ObservationIgnored private var discovery: Task<Void, Never>?
    public init() {}

    public var providerIndex: Int? { host.providers.firstIndex { $0.id == selectedProviderID && $0.kind != .chatGPTPlan } }
    public var selectedProvider: ProviderSettings? { providerIndex.map { host.providers[$0] } }

    public func availableModels(for provider: ProviderSettings, configuredReferences: [String] = [],
                                discoveredModels: [ProviderModelInfo]? = nil) -> [ProviderModelInfo] {
        let catalog = ModelGuidanceCatalog.bundled
        let prefix = provider.id + ":"
        let configured = ([host.models.stage1Model, host.models.stage2Model] + configuredReferences)
            .filter { $0.hasPrefix(prefix) && $0.count > prefix.count }
        let configuredIDs = Set(configured)
        let discovered = discoveredModels ?? (modelCatalogProvider == provider ? discoveredModelCatalog : [])
        let offered = discovered.filter {
            $0.id.hasPrefix(prefix) && $0.id.count > prefix.count
                && (configuredIDs.contains($0.id) || catalog?.guidance(for: $0.id, providers: [provider])?.endOfLife != true)
        }
        let retained = configured.map {
            ProviderModelInfo(id: $0, name: catalog?.guidance(for: $0, providers: [provider])?.label ?? String($0.dropFirst(prefix.count)),
                              contextLimit: nil, capabilities: [])
        }
        var seen: Set<String> = []
        // Advertised metadata takes precedence; saved references remain selectable.
        return (offered + (catalog?.registeredModels(for: provider) ?? []) + retained)
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
        if providerIndex == nil { selectedProviderID = host.providers.first(where: { $0.kind != .chatGPTPlan })?.id }
        await inspectCredential()
    }
    public func inspectCredential() async {
        credentialDraft = ""
        guard let provider = selectedProvider else { credentialConfigured = false; return }
        do { credentialConfigured = try await credentials.key(for: provider.credentialID)?.isEmpty == false }
        catch { self.error = "APIキーの状態を確認できません。" }
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
        guard !model.isBusy else { return }
        do {
            try host.providers.forEach { try $0.validate() }
            if let provider = selectedProvider, !credentialDraft.isEmpty {
                try await credentials.setKey(credentialDraft, for: provider.credentialID)
                credentialDraft = ""
            }
            var latest = await model.hostSettings()
            latest.providers = host.providers.filter { $0.kind != .chatGPTPlan } + latest.providers.filter { $0.kind == .chatGPTPlan }
            latest.models = host.models
            try await model.updateHostSettings(latest)
            host = latest
            await inspectCredential()
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
            credentialConfigured = false
        } catch { self.error = "APIキーを削除できませんでした。" }
    }

    public func discoverModels() async {
        guard !isLoadingModels, let provider = selectedProvider else { return }
        guard provider.kind != .chatGPTPlan else {
            error = "Personal ChatGPTのモデルは専用の設定画面で取得してください。"
            return
        }
        discoveredModelCatalog = []
        modelCatalogProvider = nil
        isLoadingModels = true
        error = nil
        let operation = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let url = try Self.modelCatalogURL(for: provider)
                var request = URLRequest(url: url)
                request.timeoutInterval = 30
                let key = provider.requiresAPIKey ? try await self.credentials.key(for: provider.credentialID) : nil
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
                let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
                let rows = (json["data"] ?? json["models"]) as? [[String: Any]] ?? []
                let catalog = rows.compactMap { row -> ProviderModelInfo? in
                    guard let raw = (row["id"] ?? row["name"]) as? String else { return nil }
                    let slug = raw.hasPrefix("models/") ? String(raw.dropFirst(7)) : raw
                    return ProviderModelInfo(id: provider.id + ":" + slug,
                        name: (row["displayName"] ?? row["display_name"]) as? String ?? slug,
                        contextLimit: row["inputTokenLimit"] as? Int,
                        capabilities: row["supportedGenerationMethods"] as? [String] ?? [])
                }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
                guard self.selectedProvider == provider, !Task.isCancelled else { return }
                self.modelCatalogProvider = provider
                self.discoveredModelCatalog = catalog
                self.status = "\(catalog.count)個のモデルを取得しました。"
            } catch {
                guard self.selectedProvider == provider, !Task.isCancelled else { return }
                self.error = "モデル一覧を取得できませんでした: \(error.localizedDescription)"
            }
        }
        discovery = operation
        await operation.value
        isLoadingModels = false
        discovery = nil
    }
    public func cancelDiscovery() { discovery?.cancel() }
}

private final class ModelCatalogRedirectPolicy: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
