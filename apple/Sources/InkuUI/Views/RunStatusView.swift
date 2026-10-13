import SwiftUI

/// Web `RunStatus.svelte`: the single "drawing in progress" indicator. Every drawing run shows the chosen mascot,
/// its label, the run's facts and the stop button in one shape. `bar` is a framed block inside a panel; `inline`
/// sits at the end of an existing button row (dialog footers) without a frame of its own.
@MainActor
struct RunStatusView<Info: View>: View {
    enum Variant { case bar, inline }
    let display: DisplaySettings
    let label: String
    var variant = Variant.bar
    var stopping = false
    var stopTooltip = ""
    var stopsWithEscape = false
    var onStop: (() -> Void)?
    @ViewBuilder var info: () -> Info

    var body: some View {
        let mascot = display.preferences.mascot == "yuragi" ? "yuragi" : "incu"
        HStack(alignment: .center, spacing: 10) {
            MascotView(kind: mascot, accessibilityText: display.localized(mascot == "yuragi" ? "Yuragiが描画中" : "Incuが描画中"))
            VStack(alignment: variant == .inline ? .trailing : .leading, spacing: 2) {
                Text(display.message(label)).inkuFont(12, weight: .medium).lineLimit(variant == .inline ? 1 : 2)
                info()
            }
            .frame(maxWidth: variant == .inline ? nil : .infinity, alignment: variant == .inline ? .trailing : .leading)
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
    @State private var started: [Bool] = []

    var body: some View {
        if states.count > 1 {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: named ? 96 : 48), spacing: 6)], spacing: 6) {
                ForEach(states.indices, id: \.self) { index in lane(index) }
            }
            .padding(.top, 6)
            .task(id: states.count) { await stagger(states.count) }
        }
    }

    private func lane(_ index: Int) -> some View {
        let state = states[index]
        let label = index < labels.count ? labels[index] : ""
        let other = display.preferences.mascot == "yuragi" ? "incu" : "yuragi"
        return VStack(spacing: 2) {
            Group {
                switch state {
                case .done: Text("✓").inkuFont(18).foregroundStyle(Color.accentColor)
                case .waiting: Text("·").inkuFont(18).foregroundStyle(.tertiary)
                case .running:
                    if index < started.count ? started[index] : true { MascotView(kind: other) } else { Color.clear.frame(width: 32, height: 32) }
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

    private func stagger(_ count: Int) async {
        started = Array(repeating: false, count: count)
        await withTaskGroup(of: Int?.self) { group in
            for index in 0..<count {
                group.addTask {
                    try? await Task.sleep(for: .milliseconds(Int.random(in: 0..<900)))
                    return Task.isCancelled ? nil : index
                }
            }
            for await index in group {
                if let index, index < started.count { started[index] = true }
            }
        }
    }
}
