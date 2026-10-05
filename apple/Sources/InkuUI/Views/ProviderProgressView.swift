import SwiftUI

/// The status footer uses the same compact provider facts for drawing and comparison.
@MainActor
public struct ProviderProgressView: View {
    @Bindable private var model: AppModel
    public init(model: AppModel) { self.model = model }

    public var body: some View {
        if let snapshot = model.providerProgress {
            if snapshot.clockRunning {
                TimelineView(.periodic(from: snapshot.stageBeganAt, by: 0.5)) { context in
                    content(snapshot, at: context.date)
                }
            } else {
                content(snapshot, at: snapshot.stageEndedAt ?? snapshot.attemptBeganAt)
            }
        }
    }

    private func content(_ snapshot: ProviderProgressSnapshot, at date: Date) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) { stage(snapshot); requestedModel(snapshot) }
                VStack(alignment: .leading, spacing: 2) { stage(snapshot); requestedModel(snapshot) }
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) { timing(snapshot, at: date); tokens(snapshot) }
                VStack(alignment: .leading, spacing: 2) { timing(snapshot, at: date); tokens(snapshot) }
            }.font(.caption).foregroundStyle(.secondary).monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
        .accessibilityElement(children: .combine)
    }

    private func stage(_ snapshot: ProviderProgressSnapshot) -> some View {
        HStack(spacing: 5) {
            if snapshot.outcome == .running && snapshot.awaitingReply {
                ProgressView().controlSize(.mini)
            } else {
                Image(systemName: symbol(snapshot.outcome)).foregroundStyle(snapshot.outcome == .failed ? Color.red : Color.secondary)
            }
            Text(model.display.localized(snapshot.stageTitleKey)).font(.caption.weight(.semibold))
            if snapshot.comparison { Text(model.display.localized("比較候補")).font(.caption).foregroundStyle(.secondary) }
            if snapshot.outcome != .running {
                Text(model.display.localized(outcomeKey(snapshot.outcome))).font(.caption).foregroundStyle(.secondary)
            }
        }.fixedSize(horizontal: true, vertical: false)
    }

    @ViewBuilder private func requestedModel(_ snapshot: ProviderProgressSnapshot) -> some View {
        if let reference = snapshot.modelReference {
            Text(model.display.localizedFormat("呼出しモデル: %@", reference))
                .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                .help(model.display.preferences.showTooltips ? reference : "")
        }
    }

    private func timing(_ snapshot: ProviderProgressSnapshot, at date: Date) -> some View {
        HStack(spacing: 10) {
            Text(model.display.localizedFormat(snapshot.awaitingReply ? (snapshot.attempt > 1 ? "再試行 %d/%d" : "応答待ち %d/%d") : "試行 %d/%d",
                                               snapshot.attempt, snapshot.maxAttempts))
            Text(model.display.localizedFormat("経過 %.1f秒", snapshot.stageElapsed(at: date)))
            if snapshot.attempt > 1 {
                Text(model.display.localizedFormat("今回 %.1f秒", snapshot.attemptElapsed(at: date)))
            }
            if let elapsed = snapshot.providerElapsedMS {
                Text(model.display.localizedFormat("呼出し %.1f秒", Double(elapsed) / 1_000))
            }
        }.fixedSize(horizontal: true, vertical: false)
    }

    private func tokens(_ snapshot: ProviderProgressSnapshot) -> some View {
        let absent = model.display.localized("記録なし")
        return Text(model.display.localizedFormat("トークン 入力 %@・出力 %@",
            snapshot.tokensIn.map(String.init) ?? absent, snapshot.tokensOut.map(String.init) ?? absent))
            .fixedSize(horizontal: true, vertical: false)
    }

    private func outcomeKey(_ outcome: ProviderProgressSnapshot.Outcome) -> String {
        switch outcome {
        case .running: "応答待ち"
        case .succeeded: "完了"
        case .failed: "失敗"
        case .cancelled: "停止済み"
        case .awaitingReview: "確認待ち"
        }
    }
    private func symbol(_ outcome: ProviderProgressSnapshot.Outcome) -> String {
        switch outcome {
        case .running, .awaitingReview: "clock"
        case .succeeded: "checkmark.circle"
        case .failed: "exclamationmark.circle"
        case .cancelled: "stop.circle"
        }
    }
}
