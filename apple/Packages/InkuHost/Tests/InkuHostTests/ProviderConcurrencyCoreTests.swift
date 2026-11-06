import Testing
@testable import InkuHost

@Test func providerConcurrencyMatchesCore() async throws {
    let slots = ProviderConcurrencySlots()
    for id in ["ollama-cloud", "custom-provider"] {
        let core = try ProviderCoreSettings.call("provider_concurrency", ["provider": id])["limit"] as? Int ?? 0
        #expect(await slots.limit(providerID: id) == core)
        #expect(await slots.limit(providerID: id) == core)
    }
}
