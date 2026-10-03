import Foundation
import InkuHost
import Observation

public struct ProviderModelInfo: Identifiable, Sendable {
    public let id: String
    public let name: String
    public let contextLimit: Int?
    public let capabilities: [String]
}

/// Editable service settings contain no readable credential value.
@MainActor @Observable
public final class SettingsModel {
    public var host = HostSettings()
    public var selectedProviderID: String?
    public var credentialDraft = ""
    public private(set) var modelCatalog: [ProviderModelInfo] = []
    public private(set) var isLoadingModels = false
    public private(set) var status = ""
    public private(set) var credentialConfigured = false
    public var error: String?
    @ObservationIgnored private let credentials = KeychainCredentialStore()
    @ObservationIgnored private var discovery: Task<Void, Never>?
    public init() {}

    public var providerIndex: Int? { host.providers.firstIndex { $0.id == selectedProviderID && $0.kind != .chatGPTPlan } }
    public var selectedProvider: ProviderSettings? { providerIndex.map { host.providers[$0] } }

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
        modelCatalog = []
    }
    public func removeProvider() {
        guard let id = selectedProvider?.id else { return }
        discovery?.cancel()
        host.providers.removeAll { $0.id == id }
        if host.models.stage1Model.hasPrefix(id + ":") { host.models.stage1Model = "" }
        if host.models.stage2Model.hasPrefix(id + ":") { host.models.stage2Model = "" }
        selectedProviderID = host.providers.first?.id
        modelCatalog = []
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
        let id = provider.id
        modelCatalog = []
        isLoadingModels = true
        error = nil
        let operation = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                try provider.validate()
                var url = provider.baseURL.appendingPathComponent("models")
                if provider.kind == .gemini {
                    var parts = URLComponents(url: url, resolvingAgainstBaseURL: false)!
                    parts.queryItems = [URLQueryItem(name: "pageSize", value: "1000")]
                    url = parts.url!
                }
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
                guard self.selectedProviderID == id, !Task.isCancelled else { return }
                self.modelCatalog = catalog
                self.status = "\(catalog.count)個のモデルを取得しました。"
            } catch {
                guard self.selectedProviderID == id, !Task.isCancelled else { return }
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
