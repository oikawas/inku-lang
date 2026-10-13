import InkuHost
import SwiftUI

/// Saved catalog metadata stays consistent across selection and comparison.
@MainActor
struct RegisteredModelMetadataView: View {
    let entry: ProviderModelSettings
    let provider: ProviderSettings
    @Bindable var display: DisplaySettings
    var purpose = "llm"

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ModelLabelsView(labels: entry.resolvedLabels, display: display)
            row("用途", entry.purposes.map { $0 == "vision" ? "Vision" : "LLM" }.joined(separator: " / "))
            if purpose == "vision" {
                row("オススメ度", ModelGuidance.recommendation(entry.recommendationVision ?? entry.recommendationLevel))
            } else if entry.recommendationStage1 != nil || entry.recommendationStage2 != nil {
                row("オススメ度 / Stage 1", ModelGuidance.recommendation(entry.recommendationStage1 ?? entry.recommendationLLM ?? entry.recommendationLevel))
                row("オススメ度 / Stage 2", ModelGuidance.recommendation(entry.recommendationStage2 ?? entry.recommendationLLM ?? entry.recommendationLevel))
            } else {
                row("オススメ度", ModelGuidance.recommendation(entry.recommendationLLM ?? entry.recommendationLevel))
            }
            let guidance = ModelGuidanceCatalog.bundled?.guidance(for: provider.id + ":" + entry.id, providers: [provider])
            row("速度", guidance?.speedHidden == true ? "—" : entry.speedLabel.flatMap { $0.isEmpty ? nil : $0 } ?? "—")
            ModelMeasurementView(llmSeconds: guidance?.speedHidden == true ? nil : entry.speedLLMSeconds,
                                 visionSeconds: guidance?.speedHidden == true ? nil : entry.speedVisionSeconds,
                                 llmCost: entry.costUSDLLM, visionCost: entry.costUSDVision)
            let comments = display.preferences.language == "en" ? [entry.commentEN, entry.commentJA] : [entry.commentJA, entry.commentEN]
            row("評価コメント", comments.compactMap { $0 }.first { !$0.isEmpty } ?? "—")
        }.font(.caption).padding(.top, 6)
    }

    private func row(_ key: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(display.localized(key)).foregroundStyle(.secondary)
            Text(value).textSelection(.enabled)
        }
    }
}

/// Units and purpose IDs remain identical in both interface languages.
struct ModelMeasurementView: View {
    let llmSeconds: Double?
    let visionSeconds: Double?
    let llmCost: Double?
    let visionCost: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            measurement("LLM", seconds: llmSeconds, cost: llmCost)
            measurement("Vision", seconds: visionSeconds, cost: visionCost)
        }.font(.caption).textSelection(.enabled)
    }

    @ViewBuilder private func measurement(_ purpose: String, seconds: Double?, cost: Double?) -> some View {
        let values = [seconds.map { String(format: "%.2f s", $0) }, cost.map { String(format: "$%.6f USD", $0) }].compactMap { $0 }
        if !values.isEmpty { Text(purpose + ": " + values.joined(separator: " · ")) }
    }
}
