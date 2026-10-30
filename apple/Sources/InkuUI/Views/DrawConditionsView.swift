import SwiftUI

/// Web DrawConditions: the selected route, optional stages, and their flow.
@MainActor struct DrawConditionsView: View {
    @Bindable var model: AppModel
    let sketch: String
    let onSketch: (String) -> Void
    private var display: DisplaySettings { model.display }
    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
            GridRow {
                drawLabel(display.label("描き方", "Drawing"))
                HStack(spacing: 2) {
                    routeButton("read_and_draw", display.label("言葉で描く", "In words"))
                    routeButton("stages", display.label("型で描く", "With a plan"))
                }
                .padding(2).background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 7))
                .overlay(RoundedRectangle(cornerRadius: 7).stroke(InkuColor.border2))
                .inkuTooltip(display.preferences.showTooltips ? display.webCopy("tooltipInputRoute", "") : "")
            }
            GridRow {
                drawLabel(display.label("通す段", "Steps"))
                WrappingHStack(spacing: 6) {
                    switchChip(display.label("写生", "Sketch from life"), on: sketch == "on", locked: false) { onSketch(sketch == "on" ? "off" : "on") }
                        .inkuTooltip(display.preferences.showTooltips ? display.webCopy("tooltipInputSketch", "") : "")
                    switchChip(display.label("構図・法則・配色", "Composition, laws, colors"), on: model.drawRoute == "stages" || model.descriptionComposition, locked: model.drawRoute == "stages") { model.descriptionComposition.toggle() }
                        .inkuTooltip(display.preferences.showTooltips ? display.webCopy("tooltipInputComposition", "") : "")
                }
            }
            GridRow {
                drawLabel(display.label("流れ", "Flow"))
                drawingFlow
            }
        }
    }

    private func drawLabel(_ text: String) -> some View {
        Text(text).inkuFont(11).foregroundStyle(.tertiary)
    }
    private func routeButton(_ route: String, _ title: String) -> some View {
        Button { model.selectDrawRoute(route); if route == "read_and_draw" { onSketch("on") } } label: {
            Text(title).inkuFont(12, weight: model.drawRoute == route ? .semibold : .regular)
                .frame(maxWidth: .infinity).frame(height: 26)
                .background(model.drawRoute == route ? InkuColor.bg2 : Color.clear, in: RoundedRectangle(cornerRadius: 5))
        }.buttonStyle(.plain).accessibilityAddTraits(model.drawRoute == route ? .isSelected : [])
    }
    private func switchChip(_ title: String, on: Bool, locked: Bool, action: @escaping () -> Void) -> some View {
        Button { if !locked { action() } } label: {
            HStack(spacing: 6) {
                Image(systemName: locked ? "lock" : on ? "checkmark" : "circle").foregroundStyle(on ? Color.accentColor : Color.secondary)
                Text(title)
            }.inkuFont(12).padding(.horizontal, 9).frame(height: 26)
                .background(on ? Color.accentColor.opacity(0.12) : Color.clear, in: Capsule())
                .overlay(Capsule().stroke(on ? Color.accentColor : InkuColor.border2))
        }.buttonStyle(.plain).accessibilityAddTraits(on ? .isSelected : [])
    }
    private var drawingFlow: some View {
        let steps = DrawPresentation.flow(route: model.drawRoute, sketch: sketch == "on", composition: model.descriptionComposition, japanese: display.preferences.language != "en")
        return steps.enumerated().reduce(Text("")) { result, entry in
            let (index, step) = entry
            let separator = index == 0 ? Text("") : Text("  ›  ").foregroundColor(.secondary)
            let color: Color = step.kind == "switch" ? .accentColor : step.kind == "end" ? .secondary : .primary
            return result + separator + Text(step.label).foregroundColor(color)
        }.inkuFont(11).fixedSize(horizontal: false, vertical: true)
    }

}
