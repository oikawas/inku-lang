import InkuHost
import SwiftUI

@MainActor
struct ModelGuidanceView: View {
    let reference: String
    let providers: [ProviderSettings]
    let discovered: ProviderModelInfo?
    @Bindable var display: DisplaySettings

    private var catalog: ModelGuidanceCatalog? { ModelGuidanceCatalog.bundled }
    private var guidance: ModelGuidance? { catalog?.guidance(for: reference, providers: providers) }

    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 8) {
                Text(display.localized("登録資料の評価")).inkuFont(12, weight: .semibold)
                if let guidance {
                    Text(guidance.label).inkuFont(13).textSelection(.enabled)
                    row("用途", guidance.purposes.map { $0 == "vision" ? "Vision" : $0 == "llm" ? "LLM" : $0 }.joined(separator: " / "))
                    if guidance.hasStageRecommendations {
                        row("解釈の適性（Stage 1）", ModelGuidance.recommendation(guidance.stage1Level))
                        row("構造化の適性（Stage 2）", ModelGuidance.recommendation(guidance.stage2Level))
                    }
                    row("両段の適性", ModelGuidance.recommendation(guidance.bothStagesLevel))
                    if guidance.purposes.contains("vision") {
                        row("Visionの適性", ModelGuidance.recommendation(guidance.visionLevel))
                    }
                    if guidance.speedHidden {
                        Text(display.localized("速度は実行環境に依存します。")).foregroundStyle(.secondary)
                    } else {
                        row("速度", guidance.speedLabel == "未計測" ? display.localized("未計測") : guidance.speedLabel ?? "—")
                    }
                    if guidance.endOfLife {
                        Text(display.localized("提供終了") + (guidance.endOfLifeDate.map { " (\($0))" } ?? ""))
                            .foregroundStyle(.secondary)
                    } else if guidance.requiresSubscription {
                        Text(display.localized("有料プラン限定")).foregroundStyle(.secondary)
                    }
                    if let comment = guidance.comment(language: display.preferences.language) {
                        row("評価コメント", comment)
                    }
                    if !guidance.hasEvaluation {
                        Text(display.localized("このモデルの評価は登録されていません。")).foregroundStyle(.secondary)
                    }
                } else {
                    Text(display.localized(catalog == nil ? "モデル案内を読み込めません。" : "このモデルの評価は登録されていません。"))
                        .foregroundStyle(.secondary)
                }
                if let catalog {
                    Text(display.localizedFormat("評価資料の更新: %@", catalog.updated)).foregroundStyle(.secondary)
                }
                Text(display.localized("登録資料の評価は、現在の接続先の性能を保証するものではありません。"))
                    .foregroundStyle(.secondary)
                Divider()
                Text(display.localized("接続先から取得した情報")).inkuFont(12, weight: .semibold)
                if let discovered, discovered.id == reference,
                   discovered.contextLimit != nil || !discovered.capabilities.isEmpty {
                    if let limit = discovered.contextLimit {
                        Text(display.localizedFormat("入力上限: %ld tokens", limit))
                    }
                    if !discovered.capabilities.isEmpty {
                        row("対応機能", discovered.capabilities.joined(separator: " · "))
                    }
                } else {
                    Text(display.localized("入力上限・対応機能は接続先から未取得です。")).foregroundStyle(.secondary)
                }
            }
            .inkuFont(12)
            .padding(.top, 6)
        } label: {
            HStack {
                Text(display.localized("モデルの適性・用途"))
                if let level = guidance?.bothStagesLevel {
                    Spacer()
                    Text(ModelGuidance.recommendation(level)).foregroundStyle(.secondary)
                }
            }
        }
    }

    private func row(_ key: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(display.localized(key)).foregroundStyle(.secondary)
            Text(value).textSelection(.enabled)
        }
    }
}
