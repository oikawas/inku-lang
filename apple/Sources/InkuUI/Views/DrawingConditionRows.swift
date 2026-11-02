import SwiftUI

/// Shared by the next-work and batch condition panels.
@MainActor
struct DrawingConditionRow: View {
    let display: DisplaySettings
    let label: String
    let value: String
    let help: String
    var showsPlan = false
    let action: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 8) {
                Text(label).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Button(display.webCopy("editButton", "変更"), action: action)
                    .buttonStyle(InkuGhostButtonStyle()).inkuTooltip(help)
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(value).inkuFont(14).lineLimit(2).truncationMode(.middle)
                    .inkuTooltip(display.tooltipValue(value))
                if showsPlan {
                    Link(display.webCopy("chatgptPlanLabel", "ChatGPTプラン"), destination: URL(string: "https://chatgpt.com/settings/usage")!)
                        .inkuFont(11).inkuTooltip(display.tooltip("ChatGPTプランの使用状況を開きます。", serverKey: "chatgptManageUsage"))
                }
                Spacer(minLength: 0)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.padding(.vertical, 7)
    }
}

@MainActor
struct DrawingCompactConditions: View {
    @Bindable var model: AppModel
    let wild: Bool?
    let canvasID: String?
    @Binding var showPaperPicker: Bool
    private var display: DisplaySettings { model.display }
    private var canvas: String {
        guard let canvasID else { return display.localized("未記録") }
        return model.canvases.first { $0.id == canvasID }?.label ?? canvasID
    }
    var body: some View {
        WrappingHStack(spacing: 6) {
            HStack(spacing: 8) {
                Text(display.label("オプション", "Options")).inkuFont(11).foregroundStyle(.tertiary)
                DrawSwitchChip(title: display.webCopy("wildButton", "筆致制限を外す"), on: wild == true) { model.wild.toggle() }
                    .accessibilityValue(display.localized(wild.map { $0 ? "オン" : "オフ" } ?? "未記録"))
                    .inkuTooltip(display.tooltip("次の作品の筆致を規則から外します。", serverKey: "tooltipInputWild"))
                if wild == nil { Text(display.localized("未記録")).inkuFont(11).foregroundStyle(.secondary) }
            }
            Button { showPaperPicker = true } label: {
                Text(display.webCopy("canvasAspectButton", "キャンバス") + (display.preferences.language == "ja" ? "：" : ": ") + canvas)
            }
            .buttonStyle(InkuGhostButtonStyle())
            .inkuTooltip(display.tooltip("用紙の形と意図を見て、次の作品の用紙を選びます。", serverKey: "tooltipInputCanvas"))
            .popover(isPresented: $showPaperPicker) {
                CreationPaperPicker(model: model) { showPaperPicker = false }.environment(display)
            }
            .accessibilityValue(canvas)
        }.padding(.top, 2)
    }
}
