import Foundation
import InkuHost
import SwiftUI

public struct PipelinePatchReview: Equatable {
    public let executionID: String
    public let proposal: String
    public let committedDDL: String
    public let proposedDDL: String

    var unreadWordsNotKept: [String] {
        guard let data = proposal.data(using: .utf8), let phase = try? ExactJSON(data: data) else { return [] }
        return (phase["unread_words_not_kept"].array ?? []).flatMap { ($0["words"].array ?? []).compactMap(\.string) }
    }
}

/// Web PipelineStatus: independent of a saved work, because a new execution can await approval.
@MainActor
struct PipelineCompletionView: View {
    @Bindable var model: AppModel

    var body: some View {
        if let review = model.patchReview {
            VStack(alignment: .leading, spacing: 8) {
                Text(model.display.webCopy("pipelinePatchTitle", "DDLの補完候補")).inkuFont(14, weight: .semibold)
                Text(model.display.webCopy("pipelinePatchHint", "候補を採用すると、表示されたDDLを保存します。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) {
                        pane(model.display.webCopy("pipelineCommittedDdl", "保存済みのDDL"), review.committedDDL).frame(width: 180)
                        pane(model.display.webCopy("pipelineProposedDdl", "候補のDDL"), review.proposedDDL).frame(width: 180)
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        pane(model.display.webCopy("pipelineCommittedDdl", "保存済みのDDL"), review.committedDDL)
                        pane(model.display.webCopy("pipelineProposedDdl", "候補のDDL"), review.proposedDDL)
                    }
                }
                if !review.unreadWordsNotKept.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(model.display.webCopy("pipelineUnreadNotKeptTitle", model.display.label("案にそのまま残らない語", "Words not kept as written")))
                            .inkuFont(12, weight: .semibold)
                        Text(model.display.webCopy("pipelineUnreadNotKeptHint", model.display.label("元の DDL で読めなかった語のうち、案に同じ字では残らない語です。消えたか、別の語に書き換わっています。採用の前に案と見比べてください。", "Words the original DDL could not read that the proposal does not keep as written. They were dropped or rewritten. Compare them with the proposal before approving.")))
                            .inkuFont(12).foregroundStyle(.secondary)
                        Text(review.unreadWordsNotKept.joined(separator: model.display.preferences.language == "en" ? ", " : "、"))
                            .inkuFont(12, design: .monospaced).textSelection(.enabled)
                    }
                }
                HStack {
                    Button(model.display.webCopy("pipelineApprove", "この候補を採用する")) { Task { await model.approvePatch() } }
                        .buttonStyle(.borderedProminent)
                    Button(model.display.webCopy("pipelineDecline", "保存済みのDDLを保つ")) { Task { await model.declinePatch() } }
                        .buttonStyle(InkuGhostButtonStyle())
                }.disabled(model.isBusy)
            }.padding(12).background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 8))
        }
        if !model.completionIssues.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(model.display.webCopy("pipelineCompletionIssuesTitle", "補えなかった箇所")).inkuFont(14, weight: .semibold)
                ForEach(model.completionIssues) { issue in
                    VStack(alignment: .leading, spacing: 4) {
                        if !issue.source.isEmpty {
                            Text(issue.source).inkuFont(12, design: .monospaced).textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading).padding(8)
                                .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 6))
                        }
                        Text(HoleCompletionReasons.text(issue.reason, display: model.display)).inkuFont(12).foregroundStyle(.secondary)
                    }
                }
            }.padding(12).background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 8))
        }
    }

    private func pane(_ title: String, _ source: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).inkuFont(12, weight: .semibold)
            ScrollView { Text(source).inkuFont(12, design: .monospaced).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading) }
                .frame(minHeight: 80, maxHeight: 240).padding(8).background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 6))
        }
    }
}
