import Foundation
import InkuUI
import InkuHost

/// Check the shared core fixture through the same action as the UI.
func runHistoryModelNameChecks() throws {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
    let file = root.appendingPathComponent("core/crates/inku-pipeline/data/model-display-cases.json")
    let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any]
    guard let cases = fixture?["cases"] as? [[String: Any]], cases.count == 21 else {
        throw CheckFailure.message("Shared model display cases unavailable")
    }
    for row in cases {
        guard let owner = row["owner"] as? String, let name = row["name"] as? String,
              let expected = row["strip_label"] as? String else { throw CheckFailure.message("Malformed model display case") }
        let actual = ModelNaming.stripLabel(owner: owner, name: name, abbreviation: row["owner_abbreviation"] as? String)
        guard actual == expected else { throw CheckFailure.message("History model \(owner)/\(name): \(actual) != \(expected)") }
    }
    guard ModelNaming().resolve("chatgpt:gpt-6-luna").provider == "chatgpt" else {
        throw CheckFailure.message("A saved ChatGPT reference lost its explicit provider")
    }
    var plan = ProviderSettings.personalPlan
    plan.models = [.init(id: "gpt-6.1-sol", label: "GPT-6.1-Sol")]
    let naming = ModelNaming(providers: [plan])
    let japanese = ModelNaming(providers: [plan], language: "ja")
    guard naming.displayName("chatgpt:gpt-6.1-sol") == "SIWC / gpt-6.1-sol",
          japanese.displayName("chatgpt:gpt-6.1-sol") == "SIWC / gpt-6.1-sol",
          naming.stripModel("chatgpt:gpt-6.1-sol") == "SIWC GPT6.1So",
          japanese.stripModel("chatgpt:gpt-6.1-sol") == "SIWC GPT6.1So",
          naming.modelShortName("chatgpt:gpt-6.1-sol") == "gpt-6.1-sol",
          ProviderModelReference.resolve("gpt-6.1-sol", providers: [plan]).providerID == "nvidia" else {
        throw CheckFailure.message("Published ChatGPT model naming or bare-reference routing changed")
    }
    print("History model names passed: \(cases.count) shared core cases; SIWC and bare-reference routing. No provider calls.")
}
