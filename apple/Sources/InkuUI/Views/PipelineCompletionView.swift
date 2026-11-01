import Foundation
import SwiftUI

public struct PipelinePatchReview: Equatable {
    public let executionID: String
    public let proposal: String
    public let committedDDL: String
    public let proposedDDL: String
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
