import SwiftUI

/// Web `BatchRunSummary.svelte` (3e28db5fd): two or three small tiles in a wrapping row, each a small upper-case label
/// over a value with even digits: the line among the plan, the time since the batch started, and, once a work is
/// saved, the average time of a work. Each tile carries the sentence form as its tooltip and spoken name.
@MainActor
struct BatchRunSummaryView: View {
    let summary: BatchRunSummary
    let display: DisplaySettings

    var body: some View {
        if let startedAt = summary.startedAt {
            TimelineView(.periodic(from: startedAt, by: 1)) { context in
                let elapsed = context.date.timeIntervalSince(startedAt)
                // `.batch-run-summary`: flex-wrap with a 4 px row gap and a 12 px column gap.
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) { tiles(elapsed: elapsed) }
                    VStack(alignment: .leading, spacing: 4) { tiles(elapsed: elapsed) }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.bottom, 6)
            }
        }
    }

    @ViewBuilder private func tiles(elapsed: TimeInterval) -> some View {
        tile(display.webCopy("batchTileLine", "行"), value: "\(summary.current) / \(summary.planTotal)",
             sentence: BatchProgressCopy.rowOfTotal(current: summary.current, total: summary.planTotal, display: display))
        tile(display.webCopy("batchTileElapsed", "開始から"), value: BatchProgressCopy.clock(elapsed),
             sentence: BatchProgressCopy.elapsed(elapsed, display: display))
        if let average = summary.averageWork {
            tile(display.webCopy("batchTileAverage", "1 枚の平均"), value: BatchProgressCopy.clock(average),
                 sentence: BatchProgressCopy.average(average, display: display))
        }
    }

    private func tile(_ label: String, value: String, sentence: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(label.uppercased()).inkuFont(10).tracking(0.8).foregroundStyle(.tertiary)
            Text(value).inkuFont(14).monospacedDigit().foregroundStyle(.primary)
        }
        .fixedSize()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(sentence)
        .inkuTooltip(display.tooltipValue(sentence))
    }
}
