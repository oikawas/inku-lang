import Foundation
import XCTest
@testable import InkuHost

final class ProviderReferenceParityChecks: XCTestCase, @unchecked Sendable {
    // Failure (D9): a model id holding a colon is split as a provider, or a bare model goes to the only
    // configured provider, where Server's provider_for_model applies its three rules.
    func testReferencesResolveAsServerProviderForModel() {
        func provider(_ id: String, _ models: [String]) -> ProviderSettings {
            .init(id: id, baseURL: URL(string: "http://fixture.invalid/v1")!, requiresAPIKey: false,
                  models: models.map { ProviderModelSettings(id: $0, label: $0) })
        }
        let providers = [provider("ollama", ["gpt-oss:20b", "qwen3:8b"]), provider("ollama-cloud", ["gpt-oss:20b", "gemma4:31b"]),
                         provider("custom", ["m:x"]), provider("nvidia", [])]
        // Captured from Build1162 provider_for_model(ref, stage="stage1") with the same catalog (builtins other
        // than these deleted).
        let server: [(String, String, String)] = [
            ("ollama:gpt-oss:20b", "ollama", "gpt-oss:20b"), ("gpt-oss:20b", "nvidia", "gpt-oss:20b"),
            ("gemma4:31b", "ollama-cloud", "gemma4:31b"), ("qwen3:8b", "ollama", "qwen3:8b"), ("custom:m:x", "custom", "m:x"),
            ("m:x", "custom", "m:x"), ("unknown:model", "nvidia", "unknown:model"), ("ovms:gemma3-4b-api", "ovms", "gemma3-4b-api"),
            ("chatgpt:gpt-5", "chatgpt", "gpt-5"), ("custom:", "nvidia", "custom:"), (":lead", "nvidia", ":lead"),
            ("nvidia:google/gemma-4-31b-it", "nvidia", "google/gemma-4-31b-it"), ("plain", "nvidia", "plain")]
        for (reference, providerID, model) in server {
            let resolved = ProviderModelReference.resolve(reference, providers: providers)
            XCTAssertEqual(resolved.providerID, providerID, reference)
            XCTAssertEqual(resolved.model, model, reference)
        }
        XCTAssertEqual(server.count, 13)
    }
}
