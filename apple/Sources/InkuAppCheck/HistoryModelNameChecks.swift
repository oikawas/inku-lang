import InkuUI

/// Failure: old three-letter family/version labels discarded the distinguishing model variant and size.
func runHistoryModelNameChecks() throws {
    // Outputs obtained from Web historyStripFields.ts under node, 2026-10-15 (Build1225).
    let cases = [
        ("ChatGPT plan", "GPT-6-Luna", "Ch GPT6Lu"),
        ("OpenAI API Platform", "GPT-5.1 mini", "Op GPT5.1Mi"),
        ("Claude API", "Claude Opus 4.7", "Cl Op4.7"),
        ("Gemini API", "Gemini 2.5 Flash Lite", "Ge 2.5FlL"),
        ("Ollama", "qwen3.5:4b-q4_K_M (3.4GB)", "Ol Qw3.5·4BQ4KM"),
        ("Ollama Cloud (ollama.com)", "deepseek-v4-flash", "Oc DS4Fl"),
        ("NVIDIA NIM", "Google Gemma 4 31B Instruct", "NV Gm4·31BI"),
        ("NVIDIA NIM", "meta/llama-3.3-70b-instruct", "NV Ll3.3·70BI"),
        ("Ollama", "gemma4:e4b-it-q4_K_M (9.6GB)", "Ol Gm4E4BIQ4KM"),
        ("Acme", "vendor/unknown-reasoning-2-31b-preview", "Ac unknownR2·31BPv"),
        ("", "", ""),
        (" Claude API ", "anthropic Claude Sonnet 4.6", "Cl ClSo4.6"),
        ("Gemini API", "Gemma 4 31B", "Ge Gm4·31B"),
        ("Ollama Cloud", "qwen3-coder-480b-a35b-instruct", "Oc Qw3Cdr480BA35BI")
    ]
    for (owner, name, expected) in cases {
        let actual = ModelNaming.abbreviateStripModel(owner: owner, name: name)
        guard actual == expected else { throw CheckFailure.message("History model \(owner)/\(name): \(actual) != Web \(expected)") }
    }
    guard ModelNaming().stripModel("chatgpt:gpt-6-luna") == "Ch GPT6Lu" else {
        throw CheckFailure.message("A saved ChatGPT model lost its catalog name when its connection was absent")
    }
    print("History model names passed: \(cases.count) current Web outputs, variants/sizes/quantization retained, Ollama Cloud distinguished. No provider calls.")
}
