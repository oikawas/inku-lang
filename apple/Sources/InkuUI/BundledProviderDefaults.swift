import Foundation
import InkuHost

/// Public connection presets generated from the same versioned Server source
/// as the bundled model catalog. Credentials remain separate Keychain items.
public enum BundledProviderDefaults {
    public static func loadBundled() throws -> [ProviderSettings] {
        guard let url = Bundle.module.url(forResource: "server-defaults", withExtension: "json") else {
            throw HostError("bundled_resources_unavailable")
        }
        let manifest = try JSONDecoder().decode(ProviderDefaultsManifest.self, from: Data(contentsOf: url))
        let defaults = manifest.providerDefaults
        guard defaults.schema == "inku.provider-defaults.v1", !defaults.providers.isEmpty,
              Set(defaults.providers.map(\.id)).count == defaults.providers.count,
              defaults.providers.allSatisfy({ $0.kind != .chatGPTPlan }) else {
            throw HostError("provider_defaults_invalid")
        }
        try defaults.providers.forEach { try $0.validate() }
        return defaults.providers
    }
}

private struct ProviderDefaultsManifest: Decodable {
    let providerDefaults: ProviderDefaultsDocument
    enum CodingKeys: String, CodingKey { case providerDefaults = "provider_defaults" }
}

private struct ProviderDefaultsDocument: Decodable {
    let schema: String
    let providers: [ProviderSettings]
}
