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
            ModelLabelsView(labels: entry.resolvedLabels, display: display, endOfLifeDate: entry.eolDate)
            VStack(alignment: .leading, spacing: 2) {
                Text(display.preferences.language == "en" ? "Use" : "用途").foregroundStyle(.secondary)
                ModelPurposeBadgesView(entry: entry, language: display.preferences.language)
            }
            if purpose == "vision" {
                row("オススメ度", ModelGuidance.recommendation(entry.recommendationVision ?? entry.recommendationLevel))
            } else if entry.recommendationStage1 != nil || entry.recommendationStage2 != nil {
                row("オススメ度 / Stage 1", ModelGuidance.recommendation(entry.recommendationStage1 ?? entry.recommendationLLM ?? entry.recommendationLevel))
                row("オススメ度 / Stage 2", ModelGuidance.recommendation(entry.recommendationStage2 ?? entry.recommendationLLM ?? entry.recommendationLevel))
            } else {
                row("オススメ度", ModelGuidance.recommendation(entry.recommendationLLM ?? entry.recommendationLevel))
            }
            let guidance = ModelGuidanceCatalog.bundled?.guidance(for: provider.id + ":" + entry.id, providers: [provider])
            row(display.preferences.language == "en" ? "Est. cost" : "概算コスト",
                ModelMetadataPresentation.cost(entry, language: display.preferences.language))
            row("速度", ModelMetadataPresentation.speed(entry, hidden: guidance?.speedHidden == true, language: display.preferences.language))
            let comments = display.preferences.language == "en" ? [entry.commentEN, entry.commentJA] : [entry.commentJA, entry.commentEN]
            row(display.preferences.language == "en" ? "Comment" : "評価", comments.compactMap { $0 }.first { !$0.isEmpty } ?? "—")
        }.font(.caption).padding(.top, 6)
    }

    private func row(_ key: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(display.localized(key)).foregroundStyle(.secondary)
            Text(value).textSelection(.enabled)
        }
    }
}

/// The catalog reports availability per purpose; missing measurements remain absent.
public enum ModelMetadataPresentation {
    public static func supports(_ entry: ProviderModelSettings, purpose: String) -> Bool {
        entry.purposes.contains(purpose) && !(entry.unsupportedPurposes ?? []).contains(purpose)
    }

    public static func speed(_ entry: ProviderModelSettings, hidden: Bool = false, language: String) -> String {
        guard !hidden else { return "—" }
        let values = [("LLM", entry.speedLLMSeconds), ("Vision", entry.speedVisionSeconds)].compactMap { purpose, value -> String? in
            guard let value, value.isFinite, value >= 0 else { return nil }
            let seconds = value < 100 ? String(format: "%.1f", value) : String(format: "%.0f", value)
            return language == "en" ? "\(purpose) mean \(seconds) s" : "\(purpose) 平均 \(seconds)秒"
        }
        if !values.isEmpty { return values.joined(separator: " / ") + (language == "en" ? " (reference)" : "（参考値）") }
        return entry.speedLabel.flatMap { $0.isEmpty ? nil : $0 } ?? "—"
    }

    public static func cost(_ entry: ProviderModelSettings, language: String) -> String {
        let values = [("LLM", entry.costUSDLLM), ("Vision", entry.costUSDVision)].compactMap { purpose, value -> String? in
            guard let value, value.isFinite, value >= 0 else { return nil }
            let dollars = value == 0 ? "$0" : value < 0.0001 ? "<$0.0001" : "$" + String(format: "%.2g", value)
            let unit = language == "en" ? (purpose == "LLM" ? " per drawing" : " per picture") : (purpose == "LLM" ? "（描画1回）" : "（画像1枚）")
            return purpose + " " + dollars + unit
        }
        return values.isEmpty ? "—" : values.joined(separator: " / ")
    }
}

struct ModelPurposeBadgesView: View {
    let entry: ProviderModelSettings
    let language: String

    var body: some View {
        HStack(spacing: 4) {
            ForEach(["llm", "vision"], id: \.self) { purpose in
                let supported = ModelMetadataPresentation.supports(entry, purpose: purpose)
                Text(purpose == "llm" ? "LLM" : "Vision")
                    .font(.caption).padding(.horizontal, 7).padding(.vertical, 2)
                    .foregroundStyle(supported ? Color.primary : Color.secondary)
                    .overlay(Capsule().stroke(.secondary.opacity(0.3)))
                    .opacity(supported ? 1 : 0.45)
                    .accessibilityLabel((purpose == "llm" ? "LLM" : "Vision") + (supported ? "" : language == "en" ? " (not selectable)" : "（選べません）"))
            }
        }
    }
}

/// Units and purpose IDs remain identical in both interface languages.
struct ModelMeasurementView: View {
    let llmSeconds: Double?
    let visionSeconds: Double?
    let llmCost: Double?
    let visionCost: Double?
    var language = "ja"

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if llmCost != nil || visionCost != nil {
                Text(ModelMetadataPresentation.cost(entry, language: language))
            }
            if llmSeconds != nil || visionSeconds != nil {
                Text(ModelMetadataPresentation.speed(entry, language: language))
            }
        }.font(.caption).textSelection(.enabled)
    }

    private var entry: ProviderModelSettings {
        ProviderModelSettings(id: "measurement", speedLLMSeconds: llmSeconds, speedVisionSeconds: visionSeconds,
                              costUSDLLM: llmCost, costUSDVision: visionCost)
    }
}
