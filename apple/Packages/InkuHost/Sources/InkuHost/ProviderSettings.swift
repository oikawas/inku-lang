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
        providerID == "gemini" ? .init(requestsPerMinute: 30, tokensPerMinute: 16_000, requestsPerDay: 14_400)
            : .init(requestsPerMinute: 0, tokensPerMinute: 0, requestsPerDay: 0)
    }
    /// Older settings saved zero as a missing member in an existing object.
    public func effective(providerID: String) -> EffectiveProviderRateLimits {
        .init(requestsPerMinute: requestsPerMinute ?? 0, tokensPerMinute: tokensPerMinute ?? 0, requestsPerDay: requestsPerDay ?? 0)
    }
}

/// Secrets are separate Keychain items; this value is safe to persist in app settings.
public struct ProviderSettings: Codable, Sendable, Equatable, Identifiable {
    public var id: String
    public var kind: ProviderKind
    public var baseURL: URL
    public var apiProfile: String?
    public var requiresAPIKey: Bool
    public var credentialID: String
    public var rateLimits: ProviderRateLimits?
    public var effectiveRateLimits: EffectiveProviderRateLimits {
        (rateLimits ?? ProviderRateLimits.defaults(providerID: id)).effective(providerID: id)
    }
    public init(id: String, kind: ProviderKind = .openAICompatible, baseURL: URL,
                apiProfile: String? = nil, requiresAPIKey: Bool = true,
                credentialID: String? = nil, rateLimits: ProviderRateLimits? = nil) {
        self.id = id; self.kind = kind; self.baseURL = baseURL; self.apiProfile = apiProfile
        self.requiresAPIKey = requiresAPIKey; self.credentialID = credentialID ?? id
        self.rateLimits = rateLimits
    }

    public func validate() throws {
        if kind == .chatGPTPlan {
            guard id == "chatgpt", baseURL.absoluteString == "https://api.openai.com/v1",
                  !requiresAPIKey, apiProfile == nil, credentialID == "chatgpt", rateLimits == nil else {
                throw HostError("chatgpt_provider_settings_invalid")
            }
        }
        guard !id.isEmpty, !credentialID.isEmpty,
              let parts = URLComponents(url: baseURL, resolvingAgainstBaseURL: false),
              let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.scheme == "https" || parts.scheme == "http"
        else { throw HostError("provider_base_url_invalid") }
        if let limits = rateLimits {
            guard [limits.requestsPerMinute, limits.tokensPerMinute, limits.requestsPerDay].compactMap({ $0 }).allSatisfy({ (0...1_000_000_000).contains($0) })
            else { throw HostError("invalid_provider_rate_limits") }
        }
    }
    public static var personalPlan: ProviderSettings {
        .init(id: "chatgpt", kind: .chatGPTPlan, baseURL: URL(string: "https://api.openai.com/v1")!, requiresAPIKey: false)
    }
}

public protocol CredentialStore: Sendable {
    func key(for credentialID: String) async throws -> String?
}

public actor KeychainCredentialStore: CredentialStore {
    private let service: String
    public init(service: String = "app.inku.provider-credentials") { self.service = service }
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
    public init(providers: [ProviderSettings] = [], models: ModelSelection = .init(), operationalLimits: [String: UInt32]? = nil,
                plugins: PluginPreferences? = nil) {
        self.providers = providers; self.models = models
        self.operationalLimits = operationalLimits
        self.plugins = plugins
    }
}

public actor ProviderSettingsStore {
    public nonisolated let url: URL
    public init(url: URL) { self.url = url }
    public func load() throws -> HostSettings {
        guard FileManager.default.fileExists(atPath: url.path) else { return .init() }
        let settings = try JSONDecoder().decode(HostSettings.self, from: Data(contentsOf: url))
        try settings.providers.forEach { try $0.validate() }
        return settings
    }
    public func save(_ settings: HostSettings) throws {
        try settings.providers.forEach { try $0.validate() }
        guard Set(settings.providers.map(\.id)).count == settings.providers.count else { throw HostError("duplicate_provider") }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONEncoder().encode(settings).write(to: url, options: .atomic)
    }
}
