import SwiftUI

/// Web `RunStatus.svelte`: the single "drawing in progress" indicator. Every drawing run shows the chosen mascot,
/// its label, the run's facts and the stop button in one shape. `bar` is a framed block inside a panel; `inline`
/// sits at the end of an existing button row (dialog footers) without a frame of its own.
enum RunStatusVariant { case bar, inline }

/// The fixed action row stays small; the complete journal and batch summary open in a bounded popover.
@MainActor
struct CompactRunStatusView<Details: View>: View {
    let model: AppModel
    let label: String
    var stopping = false
    var startedAt: Date? = nil
    var stopsWithEscape = false
    let onStop: () -> Void
    @ViewBuilder var details: () -> Details
    @State private var showingDetails = false
    @State private var appearedAt = Date()

    var body: some View {
        let display = model.display
        let mascot = display.preferences.mascot == "yuragi" ? "yuragi" : "incu"
        TimelineView(.periodic(from: model.runJournal?.beganAt ?? startedAt ?? appearedAt, by: 1)) { context in
            HStack(spacing: 6) {
                MascotView(kind: mascot, accessibilityText: display.localized(mascot == "yuragi" ? "Yuragiが描画中" : "Incuが描画中"))
                    .fixedSize()
                VStack(alignment: .leading, spacing: 1) {
                    let current = model.runJournal?.report["current"]
                    Text(current.map { RunJournalView.currentLabel($0, label: label, attempt: nil, display: display) } ?? display.message(label))
                        .inkuFont(12, weight: .medium).lineLimit(1)
                    let began = model.runJournal?.beganAt ?? startedAt ?? appearedAt
                    Text(display.webCopyFormat("runStatusElapsed", "経過 %@秒", String(format: "%.1f", max(0, context.date.timeIntervalSince(began)))))
                        .inkuFont(11).foregroundStyle(.secondary).lineLimit(1)
                }.frame(maxWidth: .infinity, alignment: .leading)
                Button(display.label("詳細", "Details")) { showingDetails.toggle() }
                    .buttonStyle(InkuGhostButtonStyle())
                    .popover(isPresented: $showingDetails) {
                        ScrollView { details().frame(maxWidth: .infinity, alignment: .leading).padding(12) }
                            .frame(width: 320, height: 240)
                    }
                if stopsWithEscape {
                    stopButton.keyboardShortcut(.escape, modifiers: [])
                } else { stopButton }
            }
        }
    }

    private var stopButton: some View {
        Button(model.display.localized(stopping ? "停止中" : "停止"), action: onStop)
            .buttonStyle(InkuStopButtonStyle()).disabled(stopping)
    }
}

@MainActor
struct RunStatusView<Info: View>: View {
    typealias Variant = RunStatusVariant
    let display: DisplaySettings
    let label: String
    var variant = Variant.bar
    var stopping = false
    var stopTooltip = ""
    var stopsWithEscape = false
    var onStop: (() -> Void)?
    var journalModel: AppModel? = nil
    var journalActive = true
    @ViewBuilder var info: () -> Info

    var body: some View {
        let mascot = display.preferences.mascot == "yuragi" ? "yuragi" : "incu"
        RunStatusRow(variant: variant) {
            MascotView(kind: mascot, accessibilityText: display.localized(mascot == "yuragi" ? "Yuragiが描画中" : "Incuが描画中"))
        } content: {
            VStack(alignment: variant == .inline ? .trailing : .leading, spacing: 2) {
                if let journalModel, journalActive, let journal = journalModel.runJournal {
                    RunJournalView(model: journalModel, journal: journal, label: label)
                } else {
                    Text(display.message(label)).inkuFont(12, weight: .medium).lineLimit(variant == .inline ? 1 : 2)
                    info()
                }
            }
        } stop: {
            if let onStop {
                stopButton(onStop)
            }
        }
        .padding(.vertical, variant == .bar ? 6 : 0).padding(.horizontal, variant == .bar ? 8 : 0)
        .frame(minHeight: variant == .bar ? 46 : nil)
        .background { if variant == .bar { RoundedRectangle(cornerRadius: 4).fill(InkuColor.panel) } }
        .overlay { if variant == .bar { RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2) } }
    }

    @ViewBuilder private func stopButton(_ onStop: @escaping () -> Void) -> some View {
        let button = Button(display.localized(stopping ? "停止中" : "停止"), action: onStop)
            .buttonStyle(InkuStopButtonStyle())
            .disabled(stopping)
            .inkuTooltip(stopTooltip)
        if stopsWithEscape { button.keyboardShortcut(.escape, modifiers: []) } else { button }
    }
}

@MainActor
struct RunStatusRow<Leading: View, Content: View, Stop: View>: View {
    let variant: RunStatusVariant
    @ViewBuilder var leading: () -> Leading
    @ViewBuilder var content: () -> Content
    @ViewBuilder var stop: () -> Stop

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            leading().fixedSize()
            content().frame(minWidth: 0, maxWidth: .infinity, alignment: variant == .inline ? .trailing : .leading)
            stop().fixedSize().layoutPriority(1)
        }
    }
}

extension RunStatusView where Info == EmptyView {
    init(display: DisplaySettings, label: String, variant: Variant = .bar, stopping: Bool = false,
         stopTooltip: String = "", onStop: (() -> Void)?) {
        self.init(display: display, label: label, variant: variant, stopping: stopping, stopTooltip: stopTooltip,
                  stopsWithEscape: false, onStop: onStop, info: { EmptyView() })
    }
}

/// Web `VariationLanes.svelte`: one lane per candidate of a fan-out. A running lane wears the mascot the user did
/// not choose (the run status above shows the chosen one); a waiting lane is a dot and a landed lane, failed or
/// not, a check. Each lane's mascot appears after its own random delay of up to 0.9 s, so four workers do not
/// beat in unison.
@MainActor
struct VariationLanesView: View {
    enum LaneState: Equatable { case waiting, running, done }
    let display: DisplaySettings
    let states: [LaneState]
    var labels: [String] = []
    /// Model comparison names each lane, since a number does not say which model it is.
    var named = false

    var body: some View {
        if states.count > 1 {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: named ? 96 : 48), spacing: 6)], spacing: 6) {
                ForEach(states.indices, id: \.self) { index in lane(index) }
            }
            .padding(.top, 6)
        }
    }

    private func lane(_ index: Int) -> some View {
        let state = states[index]
        let label = index < labels.count ? labels[index] : ""
        let other = display.preferences.mascot == "yuragi" ? "incu" : "yuragi"
        return VStack(spacing: 2) {
            Group {
                switch state {
                case .done, .waiting, .running:
                    StaggeredLaneMascot(kind: other, state: state)
                }
            }.frame(minHeight: 34)
            Text(named && !label.isEmpty ? label : String(index + 1))
                .inkuFont(named ? 10 : 11)
                .foregroundStyle(state == .done ? Color.secondary : Color.secondary.opacity(0.8))
                .lineLimit(named ? 2 : 1).multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
                .inkuTooltip(display.tooltipValue(label))
        }
        .padding(.vertical, 6).padding(.horizontal, 4)
        .frame(maxWidth: .infinity)
        .background(RoundedRectangle(cornerRadius: 4).fill(InkuColor.panel))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(state == .done ? Color.accentColor : InkuColor.border2))
        .opacity(state == .waiting ? 0.45 : 1)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(display.localizedFormat("候補 %ld", index + 1) + (label.isEmpty ? "" : " " + label))
        .accessibilityValue(display.localized(state == .done ? "準備完了" : state == .running ? "描画中" : "待機中"))
    }

}

/// A lane draws its delay only when it starts running. Removing this view cancels the delay.
struct LaneStaggerTiming {
    private var running = false
    mutating func delay(for state: VariationLanesView.LaneState, draw: () -> Int) -> Int? {
        guard state == .running else { running = false; return nil }
        guard !running else { return nil }
        running = true
        return draw()
    }
}

private struct StaggeredLaneMascot: View {
    let kind: String
    let state: VariationLanesView.LaneState
    @State private var started = false
    @State private var timing = LaneStaggerTiming()

    var body: some View {
        Group {
            switch state {
            case .done: Text("✓").inkuFont(18).foregroundStyle(Color.accentColor)
            case .waiting: Text("·").inkuFont(18).foregroundStyle(.tertiary)
            case .running:
                if started { MascotView(kind: kind) } else { Color.clear.frame(width: 32, height: 32) }
            }
        }
        .task(id: state) {
            guard let delay = timing.delay(for: state, draw: { Int.random(in: 0..<900) }) else {
                if state != .running { started = false }
                return
            }
            started = false
            do { try await Task.sleep(for: .milliseconds(delay)) }
            catch { return }
            guard !Task.isCancelled else { return }
            started = true
        }
    }
}
