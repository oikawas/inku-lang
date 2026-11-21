import SwiftUI
import InkuHost

@MainActor struct PhoneDrawSheet: View {
    @Bindable var model: AppModel
    let onDetails: () -> Void
    let onDraw: () -> Void
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            VStack(alignment: .trailing) {
                TextEditor(text: $model.phoneDrawText)
                    .font(.system(size: 20 * model.display.preferences.textScale))
                    .focused($focused)
                    .accessibilityLabel(model.display.localized("記述"))
                DescriptionMeterView(model: model, text: model.phoneDrawText)
            }
            .padding()
            .safeAreaInset(edge: .bottom) {
                Button(action: onDraw) {
                    Text(model.display.label("描画する", "Draw")).frame(maxWidth: .infinity).padding(12)
                        .contentShape(Rectangle())
                }
                    .buttonStyle(.borderedProminent)
                    .disabled(!DescriptionLabels.hasDrawableText(model.phoneDrawText))
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button { dismiss() } label: { Image(systemName: "xmark") } }
                ToolbarItem(placement: .primaryAction) { Button(model.display.localized("詳しく描く"), action: onDetails) }
            }
        }
        .onAppear { focused = true }
    }
}
