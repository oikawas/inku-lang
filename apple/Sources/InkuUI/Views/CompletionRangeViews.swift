import SwiftUI
import InkuHost

/// Web `completion-range-tags.ts` and `completionWordsHint`: the ranges a completion wrote, marked by how the author
/// has left them. Web puts a tag at each range's end; a native editor cannot place one without editing the text,
/// so each state is a dotted underline in its own colour, named with its count below the text.
enum CompletionRangeStyle {
    static func label(_ state: CompletionRangeState.State) -> String {
        switch state { case .completed: "補完"; case .numbersChanged: "数を直した"; case .wordsChanged: "言葉を直した" }
    }
    static func color(_ state: CompletionRangeState.State) -> Color {
        switch state { case .completed: .blue; case .numbersChanged: .green; case .wordsChanged: .orange }
    }

    static func marks(_ states: [CompletionRangeState]) -> [InkuEditorMark] {
        states.map { InkuEditorMark(range: NSRange(location: $0.utf16Start, length: $0.utf16End - $0.utf16Start), style: .completion($0.state)) }
    }

}

@MainActor
struct CompletionRangeSummary: View {
    let display: DisplaySettings
    let states: [CompletionRangeState]

    var body: some View {
        let counts = [CompletionRangeState.State.completed, .numbersChanged, .wordsChanged].compactMap { state -> (CompletionRangeState.State, Int)? in
            let count = states.filter { $0.state == state }.count
            return count > 0 ? (state, count) : nil
        }
        if !counts.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 10) {
                    ForEach(counts, id: \.0) { state, count in
                        HStack(spacing: 4) {
                            Rectangle().fill(CompletionRangeStyle.color(state)).frame(width: 12, height: 2)
                            Text(display.localized(CompletionRangeStyle.label(state)) + " \(count)").inkuFont(11).foregroundStyle(.secondary)
                        }
                    }
                }
                let words = states.filter { $0.state == .wordsChanged }.count
                if words > 0 {
                    Text(words == 1 && display.preferences.language == "en"
                         ? display.localized("言葉を直した範囲が 1 つあります。描くと補完がその範囲の数を書き直し、承認を求めます。")
                         : display.localizedFormat("言葉を直した範囲が %ld つあります。描くと補完がその範囲の数を書き直し、承認を求めます。", words))
                        .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.updatesFrequently)
                }
            }
        }
    }
}

