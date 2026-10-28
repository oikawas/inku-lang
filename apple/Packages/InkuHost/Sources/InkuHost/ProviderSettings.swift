import Foundation
import Security

public enum ProviderKind: String, Codable, Sendable {
    case openAICompatible = "openai_compatible"
    case anthropic, gemini
    case chatGPTPlan = "chatgpt"
}

public struct EffectiveProviderRateLimits: Sendable, Equatable {
    public let requestsPerMinute: Int
    public let tokensPerMinute: Int
    public let requestsPerDay: Int
    public init(requestsPerMinute: Int, tokensPerMinute: Int, requestsPerDay: Int) {
        self.requestsPerMinute = requestsPerMinute; self.tokensPerMinute = tokensPerMinute; self.requestsPerDay = requestsPerDay
    }
    public var minuteRequestBudget: Int { requestsPerMinute == 0 ? 0 : max(1, requestsPerMinute * 9 / 10) }
    public var minuteInputTokenBudget: Int { tokensPerMinute == 0 ? 0 : max(1, tokensPerMinute * 9 / 10) }
}

public struct ProviderRateLimits: Codable, Sendable, Equatable {
    public var requestsPerMinute: Int?
    public var tokensPerMinute: Int?
    public var requestsPerDay: Int?
    public init(requestsPerMinute: Int? = nil, tokensPerMinute: Int? = nil, requestsPerDay: Int? = nil) {
        self.requestsPerMinute = requestsPerMinute; self.tokensPerMinute = tokensPerMinute
        self.requestsPerDay = requestsPerDay
    }
    public static func defaults(providerID: String) -> ProviderRateLimits {
        fromCore(providerID: providerID, limits: nil)
    }
    public func effective(providerID: String) -> EffectiveProviderRateLimits {
        let resolved = Self.fromCore(providerID: providerID, limits: self)
        return .init(requestsPerMinute: resolved.requestsPerMinute ?? 0, tokensPerMinute: resolved.tokensPerMinute ?? 0, requestsPerDay: resolved.requestsPerDay ?? 0)
    }
    private static func fromCore(providerID: String, limits: ProviderRateLimits?) -> ProviderRateLimits {
        var input: [String: Int] = [:]
        if let value = limits?.requestsPerMinute { input["rpm"] = value }
        if let value = limits?.tokensPerMinute { input["tpm"] = value }
        if let value = limits?.requestsPerDay { input["rpd"] = value }
        let result = (try? ProviderCoreSettings.call("rate_limits", ["provider": providerID, "value": input])["rate_limits"] as? [String: Int]) ?? [:]
        return .init(requestsPerMinute: result["rpm"] ?? 0, tokensPerMinute: result["tpm"] ?? 0, requestsPerDay: result["rpd"] ?? 0)
    }
}

/// Secrets are separate Keychain items; this value is safe to persist in app settings.
public struct ProviderSettings: Codable, Sendable, Equatable, Identifiable {
    public var id: String
    public var label: String?
    public var kind: ProviderKind
    public var baseURL: URL
    public var apiProfile: String?
    public var requiresAPIKey: Bool
    public var credentialID: String
    public var rateLimits: ProviderRateLimits?
    public var models: [ProviderModelSettings]?
    public var enabledModels: [String: Bool]?
    public var memo: String?
    public var displayName: String {
        if let label, !label.isEmpty { return label }
        return id
    }
    public var effectiveRateLimits: EffectiveProviderRateLimits {
        (rateLimits ?? ProviderRateLimits.defaults(providerID: id)).effective(providerID: id)
    }
    public init(id: String, kind: ProviderKind = .openAICompatible, baseURL: URL,
                apiProfile: String? = nil, requiresAPIKey: Bool = true,
                credentialID: String? = nil, rateLimits: ProviderRateLimits? = nil, label: String? = nil,
                models: [ProviderModelSettings]? = nil, enabledModels: [String: Bool]? = nil, memo: String? = nil) {
        self.id = id; self.kind = kind; self.baseURL = baseURL; self.apiProfile = apiProfile
        self.requiresAPIKey = requiresAPIKey; self.credentialID = credentialID ?? id
        self.rateLimits = rateLimits
        self.label = label
        self.models = models; self.enabledModels = enabledModels; self.memo = memo
    }

    public func validate() throws {
        if kind == .chatGPTPlan {
            guard id == "chatgpt", baseURL.absoluteString == "https://api.openai.com/v1",
                  !requiresAPIKey, apiProfile == nil, credentialID == "chatgpt", rateLimits == nil else {
                throw HostError("chatgpt_provider_settings_invalid")
            }
        }
        guard !credentialID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw HostError("provider_base_url_invalid") }
        if kind == .chatGPTPlan { return }
        let defaults = ProviderRateLimits.defaults(providerID: id)
        let rates: [String: Int] = ["rpm": rateLimits?.requestsPerMinute ?? defaults.requestsPerMinute ?? 0,
            "tpm": rateLimits?.tokensPerMinute ?? defaults.tokensPerMinute ?? 0,
            "rpd": rateLimits?.requestsPerDay ?? defaults.requestsPerDay ?? 0]
        let result = try ProviderCoreSettings.call("validate_settings", ["host": "macos", "provider": id,
            "base_url": baseURL.absoluteString, "rate_limits": rates, "models": (models ?? []).map(\.coreCatalogRecord)])
        guard result["provider_valid"] as? Bool == true, result["url_valid"] as? Bool == true else { throw HostError("provider_base_url_invalid") }
        guard result["rate_limits_valid"] as? Bool == true else { throw HostError("invalid_provider_rate_limits") }
        guard (result["duplicate_models"] as? [String] ?? []).isEmpty else { throw HostError("duplicate_provider_model") }
    }
    public static var personalPlan: ProviderSettings {
        .init(id: "chatgpt", kind: .chatGPTPlan, baseURL: URL(string: "https://api.openai.com/v1")!, requiresAPIKey: false)
    }
}

public protocol CredentialStore: Sendable {
    func key(for credentialID: String) async throws -> String?
}

public protocol ProviderCredentialStore: CredentialStore {
    func isConfigured(for credentialID: String) async throws -> Bool
    func setKey(_ key: String?, for credentialID: String) async throws
}

public actor KeychainCredentialStore: ProviderCredentialStore {
    private let service: String
    public init(service: String = "app.inku.provider-credentials") { self.service = service }
    public func isConfigured(for credentialID: String) throws -> Bool {
        var query = baseQuery(credentialID)
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        let status = SecItemCopyMatching(query as CFDictionary, nil)
        if status == errSecItemNotFound { return false }
        guard status == errSecSuccess else { throw HostError("credentials_unavailable") }
        return true
    }
    public func key(for credentialID: String) throws -> String? {
        var query = baseQuery(credentialID)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let bytes = result as? Data,
              let value = String(data: bytes, encoding: .utf8) else { throw HostError("credentials_unavailable") }
        return value
    }
    public func setKey(_ key: String?, for credentialID: String) throws {
        let query = baseQuery(credentialID)
        guard let key, !key.isEmpty else {
            let status = SecItemDelete(query as CFDictionary)
            guard status == errSecSuccess || status == errSecItemNotFound else { throw HostError("credentials_write_failed") }
            return
        }
        let attributes: [String: Any] = [kSecValueData as String: Data(key.utf8)]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var newItem = query
            newItem[kSecValueData as String] = Data(key.utf8)
            newItem[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(newItem as CFDictionary, nil) == errSecSuccess else { throw HostError("credentials_write_failed") }
        } else if status != errSecSuccess { throw HostError("credentials_write_failed") }
    }
    private func baseQuery(_ credentialID: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
         kSecAttrAccount as String: credentialID, kSecAttrSynchronizable as String: false]
    }
}

public struct HostSettings: Codable, Sendable, Equatable {
    public var providers: [ProviderSettings]
    public var models: ModelSelection
    public var operationalLimits: [String: UInt32]?
    public var plugins: PluginPreferences?
    public var drawingLimits: [String: UInt32]?
    public var svgLimitMiB: Int?
    public var providerDefaultsInstalled: Bool?
    /// Built-ins explicitly removed on this installation, kept inactive across normalization.
    public var inactiveBuiltinProviderIDs: [String]?
    public init(providers: [ProviderSettings] = [], models: ModelSelection = .init(), operationalLimits: [String: UInt32]? = nil,
                plugins: PluginPreferences? = nil, drawingLimits: [String: UInt32]? = nil,
                providerDefaultsInstalled: Bool? = nil, svgLimitMiB: Int? = nil) {
        self.providers = providers; self.models = models
        self.operationalLimits = operationalLimits
        self.plugins = plugins
        self.drawingLimits = drawingLimits
        self.svgLimitMiB = svgLimitMiB
        self.providerDefaultsInstalled = providerDefaultsInstalled
    }
}

public actor ProviderSettingsStore {
    public nonisolated let url: URL
    public init(url: URL) { self.url = url }
    private func readRaw() throws -> HostSettings {
        guard FileManager.default.fileExists(atPath: url.path) else { return .init() }
        let settings = try JSONDecoder().decode(HostSettings.self, from: Data(contentsOf: url))
        _ = try SVGGenerationLimit.bytes(settings.svgLimitMiB)
        return settings
    }
    public func load() throws -> HostSettings {
        let before = try readRaw()
        let settings = try ProviderCoreSettings.normalize(before)
        if settings != before { try write(settings) }
        return settings
    }
    public func loadNormalized() throws -> HostSettings { try load() }
    @discardableResult public func save(_ settings: HostSettings) throws -> HostSettings {
        try settings.providers.forEach { try $0.validate() }
        _ = try SVGGenerationLimit.bytes(settings.svgLimitMiB)
        guard Set(settings.providers.map(\.id)).count == settings.providers.count else { throw HostError("duplicate_provider") }
        let before = try readRaw()
        let normalized = try ProviderCoreSettings.update(before, to: settings)
        try write(normalized)
        return normalized
    }
    private func write(_ settings: HostSettings) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONEncoder().encode(settings).write(to: url, options: .atomic)
    }

    public func svgLimitBytes() throws -> UInt64 { try SVGGenerationLimit.bytes(load().svgLimitMiB) }
}
