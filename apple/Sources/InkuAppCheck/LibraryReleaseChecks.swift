import Foundation
import InkuUI

/// Failure: the library cards and the history strip named models differently from the Web, and the grid page size
/// drifted from the Web formula. Expected values were produced by running the Build1162 Web functions
/// (`shortModel`, `historyModelStage1Short`, `modelDisplayName`, `historyGridPageSize`) under node with the same
/// bundled Server catalog, and are pasted here unchanged.
@MainActor
func runLibraryReleaseChecks() async throws {
    let naming = ModelNaming()
    // (reference, card shortModel, strip abbreviation, modelDisplayName)
    let table: [(String, String, String, String)] = [
        ("gemini:gemini-2.5-flash-lite", "Gemini API/gemini-2", "Ge gem 2.5", "Gemini API / gemini-2.5-flash-lite"),
        ("anthropic:claude-opus-4-7", "Claude API/opus", "Cl Opu 4.7", "Claude API / Claude Opus 4.7"),
        ("ollama:qwen3.5:4b-q4_K_M", "Ollama/qwen3", "Ol qwe 3.5", "Ollama / qwen3.5:4b-q4_K_M (3.4GB)"),
        ("openai:gpt-5.1-mini", "OpenAI API Platform/gpt-5.1-", "Op GPT 5.1", "OpenAI API Platform / GPT-5.1 mini"),
        ("nvidia:google/gemma-4-31b-it", "NVIDIA NIM/gemma", "NV Gem 4", "NVIDIA NIM / Google Gemma 4 31B Instruct"),
        ("anthropic:claude-haiku-4-5-20251001", "Claude API/haiku", "Cl Hai 4.5", "Claude API / Claude Haiku 4.5"),
        ("anthropic:claude-sonnet-4-6", "Claude API/sonnet", "Cl Son 4.6", "Claude API / Claude Sonnet 4.6"),
        ("ollama-cloud:qwen2.5:7b", "Ollama Cloud (ollama.com)/qwen", "Ol qwe 2.5", "Ollama Cloud (ollama.com) / qwen2.5:7b"),
        ("ollama:gemma4:e4b-it-q4_K_M", "Ollama/gemma", "Ol gem 4", "Ollama / gemma4:e4b-it-q4_K_M (9.6GB)"),
        ("nvidia:meta/llama-3.3-70b-instruct", "NVIDIA NIM/llama-3.", "NV Lla 3.3", "NVIDIA NIM / Meta Llama 3.3 70B Instruct"),
        ("openai:gpt-4.1", "OpenAI API Platform/gpt-4.1", "Op GPT 4.1", "OpenAI API Platform / GPT-4.1"),
        ("nvidia:thinkingmachines/inkling", "NVIDIA NIM/inkling", "NV ink", "NVIDIA NIM / thinkingmachines/inkling"),
        ("gemini:3d-model", "Gemini API/3d-model", "Ge mod 3d", "Gemini API / 3d-model"),
        ("claude-sonnet-4-6", "Claude API/sonnet", "Cl Son 4.6", "Claude API / Claude Sonnet 4.6"),
        ("mystery-model", "NVIDIA NIM/mystery-", "NV mys", "NVIDIA NIM / mystery-model"),
        ("acme:foo", "NVIDIA NIM/acme:foo", "NV acm", "NVIDIA NIM / acme:foo"),
        ("ovms:gemma3-4b-api", "Intel OVMS/gemma", "In Gem 3", "Intel OVMS / Google Gemma 3 4B Instruct"),
        ("qwen-api", "Intel OVMS/qwen", "In Qwe 2.5", "Intel OVMS / Qwen2.5 7B Instruct"),
        ("ollama-cloud:deepseek-v4-flash", "Ollama Cloud (ollama.com)/deepseek", "Ol v 4", "Ollama Cloud (ollama.com) / deepseek-v4-flash"),
        ("chatgpt:gpt-5.1", "chatgpt/gpt-5.1", "ch gpt 5.1", "chatgpt / gpt-5.1"),
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
    guard same.count == 1, same[0].role == nil, same[0].compact == "Gemini API/gemini-2",
          split.count == 2, split[0].role == .interpretation, split[0].compact == "Claude API/opus",
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
    print("Library release checks passed: \(compared) comparisons against Build1162 Web outputs (\(table.count) model references × 3 forms, 2 model-line cases, \(paging.count) page sizes).")
}
