import InkuHost
import SwiftUI

@MainActor
public struct DescriptionFeedbackView: View {
    @Environment(\.locale) private var locale
    public let description: String
    public let ddl: String
    public init(description: String, ddl: String) { self.description = description; self.ddl = ddl }
    public var body: some View {
        if !parts.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text(InkuLocalization.string("解釈フィードバック", locale: locale)).font(.caption.weight(.semibold))
                feedbackText.font(.callout).textSelection(.enabled)
                Text(InkuLocalization.string("濃い表示: 語やカテゴリが対応・中間: 歳時記の語や言い換え・薄い表示: 直接の対応が未確認", locale: locale))
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
    private var parts: [FeedbackPart] {
        (try? DescriptionFeedback.parts(description: description, ddl: ddl)) ?? []
    }
    private var feedbackText: Text {
        var result = Text("")
        for part in parts { result = result + Text(part.text).foregroundColor(color(part.tone)) }
        return result
    }
    private func color(_ tone: FeedbackTone) -> Color {
        switch tone { case .strong: .primary; case .medium: .secondary; case .weak: Color.secondary.opacity(0.5) }
    }
}
