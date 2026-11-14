import Foundation
import InkuCore
import InkuHost

/// Sign in with ChatGPT step 1. Failure: the Swift host asked core in another shape than the shared rows, kept
/// appending the ChatGPT connection after the other services, or named it with its own words.
func runSignInChecks(casesURL: URL) throws {
    let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: casesURL)) as? [String: Any]
    guard let cases = fixture?["cases"] as? [[String: Any]], cases.count == 48 else {
        throw CheckFailure.message("Shared sign-in cases unavailable")
    }
    // Each row goes through the binding the app uses, and the whole answer is compared.
    for row in cases {
        guard let name = row["name"] as? String, let request = row["request"] as? [String: Any],
              let answer = row["answer"] as? NSDictionary else { throw CheckFailure.message("Shared sign-in case malformed") }
        let output = InkuCore.modelCatalog(try JSONSerialization.data(withJSONObject: request))
        guard let actual = try JSONSerialization.jsonObject(with: output) as? NSDictionary, actual == answer else {
            throw CheckFailure.message("Sign-in case \(name): \(String(decoding: output, as: UTF8.self))")
        }
    }

    // The host's own request: the sign-in connection goes before every service, the others keep their order.
    var plan = ProviderSettings.personalPlan
    plan.models = [.init(id: "gpt-6.1-sol", label: "GPT-6.1-Sol")]
    let ollama = ProviderSettings(id: "ollama", kind: .openAICompatible, baseURL: URL(string: "http://127.0.0.1:11434/v1")!,
                                  requiresAPIKey: false, label: "Ollama")
    let anthropic = ProviderSettings(id: "anthropic", kind: .anthropic, baseURL: URL(string: "https://api.anthropic.com")!,
                                     label: "Claude API")
    guard ProviderCoreSettings.orderedBySignIn([ollama, anthropic, plan]).map(\.id) == ["chatgpt", "ollama", "anthropic"],
          ProviderCoreSettings.orderedBySignIn([anthropic, plan, ollama]).map(\.id) == ["chatgpt", "anthropic", "ollama"],
          ProviderCoreSettings.orderedBySignIn([anthropic, ollama]).map(\.id) == ["anthropic", "ollama"] else {
        throw CheckFailure.message("The Sign in with ChatGPT connection is not first, or another service moved")
    }
    guard ProviderCoreSettings.signInService("chatgpt", language: "ja")?["label"] as? String == "ChatGPT でサインイン",
          ProviderCoreSettings.signInService("chatgpt", language: "en")?["label"] as? String == "Sign in with ChatGPT",
          ProviderCoreSettings.signInService("chatgpt", language: "fr")?["label"] as? String == "Sign in with ChatGPT",
          ProviderCoreSettings.signInService("chatgpt", language: "ja")?["abbreviation"] as? String == "SIWC" else {
        throw CheckFailure.message("The Sign in with ChatGPT names differ from core's descriptor")
    }
    print("Sign in with ChatGPT passed: \(cases.count) shared rows through the Swift binding; connection first in 3 orders; ja/en names and SIWC. No provider calls.")
}
