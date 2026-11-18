import Foundation
import InkuUI

/// The card and strip use shared core names; the grid retains the Web page-size formula.
@MainActor
func runLibraryReleaseChecks() async throws {
    let naming = ModelNaming()
    // (reference, card shortModel, strip abbreviation, modelDisplayName)
    let table: [(String, String, String, String)] = [
        ("gemini:gemini-2.5-flash-lite", "Gemini API / gemini-2.5-flash-lite", "Ge 2.5FlL", "Gemini API / gemini-2.5-flash-lite"),
        ("anthropic:claude-opus-4-7", "Claude API / claude-opus-4-7", "Cl Op4.7", "Claude API / claude-opus-4-7"),
        ("ollama:qwen3.5:4b-q4_K_M", "Ollama / qwen3.5:4b-q4_K_M", "Ol Qw3.5·4BQ4KM", "Ollama / qwen3.5:4b-q4_K_M"),
        ("openai:gpt-5.1-mini", "OpenAI API Platform / gpt-5.1-mini", "Op GPT5.1Mi", "OpenAI API Platform / gpt-5.1-mini"),
        ("nvidia:google/gemma-4-31b-it", "NVIDIA NIM / google/gemma-4-31b-it", "NV Gm4·31BI", "NVIDIA NIM / google/gemma-4-31b-it"),
        ("nvidia:meta/llama-3.3-70b-instruct", "NVIDIA NIM / meta/llama-3.3-70b-instruct", "NV Ll3.3·70BI", "NVIDIA NIM / meta/llama-3.3-70b-instruct"),
        ("ollama:gemma4:e4b-it-q4_K_M", "Ollama / gemma4:e4b-it-q4_K_M", "Ol Gm4E4BIQ4KM", "Ollama / gemma4:e4b-it-q4_K_M"),
        ("ollama-cloud:deepseek-v4-flash", "Ollama Cloud (ollama.com) / deepseek-v4-flash", "Oc DS4Fl", "Ollama Cloud (ollama.com) / deepseek-v4-flash"),
        ("anthropic:claude-haiku-4-5-20251001", "Claude API / claude-haiku-4-5-20251001", "Cl Ha4.5", "Claude API / claude-haiku-4-5-20251001"),
        ("anthropic:claude-sonnet-4-6", "Claude API / claude-sonnet-4-6", "Cl So4.6", "Claude API / claude-sonnet-4-6"),
        ("ollama-cloud:qwen2.5:7b", "Ollama Cloud (ollama.com) / qwen2.5:7b", "Oc Qw2.5·7B", "Ollama Cloud (ollama.com) / qwen2.5:7b"),
        ("openai:gpt-4.1", "OpenAI API Platform / gpt-4.1", "Op GPT4.1", "OpenAI API Platform / gpt-4.1"),
        ("nvidia:thinkingmachines/inkling", "NVIDIA NIM / thinkingmachines/inkling", "NV inkling", "NVIDIA NIM / thinkingmachines/inkling"),
        ("gemini:3d-model", "Gemini API / 3d-model", "Ge 3dmodel", "Gemini API / 3d-model"),
        ("claude-sonnet-4-6", "NVIDIA NIM / claude-sonnet-4-6", "NV ClSo4.6", "NVIDIA NIM / claude-sonnet-4-6"),
        ("mystery-model", "NVIDIA NIM / mystery-model", "NV mysterymodel", "NVIDIA NIM / mystery-model"),
        ("acme:foo", "NVIDIA NIM / acme:foo", "NV acmefoo", "NVIDIA NIM / acme:foo"),
        ("ovms:gemma3-4b-api", "Intel OVMS / gemma3-4b-api", "In Gm3·4Bapi", "Intel OVMS / gemma3-4b-api"),
        ("qwen-api", "Intel OVMS / qwen-api", "In Qwapi", "Intel OVMS / qwen-api"),
        ("chatgpt:gpt-5.1", "SIWC / gpt-5.1", "SIWC GPT5.1", "SIWC / gpt-5.1"),
        ("", "", "-", ""),
    ]
    var compared = 0
    for (reference, card, strip, full) in table {
        let got = (naming.shortModel(reference), naming.stripModel(reference), naming.displayName(reference))
        guard got == (card, strip, full) else {
            throw CheckFailure.message("Model naming differs from Web for \(reference.debugDescription): \(got) != \((card, strip, full))")
        }
        compared += 3
    }

    // Web modelLines: one unlabeled line for one model, a labeled line per stage otherwise.
    let same = naming.cardLines(stage1: "gemini:gemini-2.5-flash-lite", stage2: "gemini:gemini-2.5-flash-lite")
    let split = naming.cardLines(stage1: "anthropic:claude-opus-4-7", stage2: nil)
    guard same.count == 1, same[0].role == nil, same[0].compact == "Gemini API / gemini-2.5-flash-lite",
          split.count == 2, split[0].role == .interpretation, split[0].compact == "Claude API / claude-opus-4-7",
          split[1].role == .drawing, split[1].compact == nil else {
        throw CheckFailure.message("Library model lines differ from Web modelLines: \(same) / \(split)")
    }
    compared += 2

    // (width, height, card heights, Web historyGridPageSize)
    let paging: [(Double, Double, [Double], Int)] = [
        (1300, 700, [], 24), (1300, 700, [190, 300, 0, .nan], 16), (900, 520, [], 18), (100, 100, [], 1), (0, 500, [], 1),
    ]
    for (width, height, heights, expected) in paging {
        let got = LibraryGridPaging.pageSize(width: width, height: height, cardHeights: heights)
        guard got == expected else { throw CheckFailure.message("Library page size \(got) != Web \(expected) for \(width)×\(height) \(heights)") }
        compared += 1
    }
    guard naming.modelShortName("nvidia:google/gemma-4-31b-it") == "google/gemma-4-31b-it" else {
        throw CheckFailure.message("Vendor prefix was lost from the API model ID")
    }
    print("Library release checks passed: \(compared) comparisons (\(table.count) model references × 3 forms, 2 model-line cases, \(paging.count) page sizes); vendor prefix preserved.")
}
