import SwiftUI

/// Shared by the next-work and batch condition panels.
@MainActor
struct DrawingConditionRow: View {
    let display: DisplaySettings
    let label: String
    let value: String
    let help: String
    var showsPlan = false
    var unavailable = false
    let action: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Text(label).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
            Text(value).inkuFont(14).lineLimit(1).truncationMode(.middle).foregroundStyle(unavailable ? Color.red : Color.primary)
                .inkuTooltip(display.tooltipValue(value))
            Spacer(minLength: 0)
            if unavailable { Text(display.webCopy("imageVisionUnavailableShort", "画像に使えません")).inkuFont(11).foregroundStyle(.red) }
            if showsPlan {
                Link(display.webCopy("chatgptManageUsage", "利用枠を管理"), destination: display.signInUsageURL() ?? URL(string: "https://chatgpt.com/settings/usage")!)
                    .inkuFont(11).inkuTooltip(display.tooltip("ChatGPTプランの使用状況を開きます。", serverKey: "chatgptManageUsage"))
            }
            Button(display.webCopy("editButton", "変更"), action: action)
                .buttonStyle(InkuGhostButtonStyle()).inkuTooltip(help)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 7)
    }
}

@MainActor
struct DrawingConditionsHeading: View {
    @Bindable var model: AppModel
    let batch: Bool
    let canvasID: String?
    var imageSelection = false
    @Binding var showPaperPicker: Bool
    @Binding var showDetails: Bool
    var hasDetails = true
    @Environment(\.inkuPhoneLayout) private var phone
    private var display: DisplaySettings { model.display }
    private var canvas: String {
        guard let canvasID else { return display.localized("未記録") }
        if imageSelection && canvasID == "image" { return display.localized("画像の縦横比を使う") }
        return model.canvases.first { $0.id == canvasID }?.label ?? canvasID
    }
    var body: some View {
        HStack(spacing: 6) {
            Text(batch ? display.webCopy("batchNextConditionsLabel", "次のバッチの描画条件") : display.webCopy("nextWorkConditions", "次に描く条件"))
                .inkuFont(12).foregroundStyle(.secondary)
            Spacer(minLength: 0)
            Text(display.webCopy("canvasAspectButton", "キャンバス")).inkuFont(11).foregroundStyle(.secondary)
            Text(canvas).inkuFont(12).lineLimit(1).truncationMode(.middle)
            Button(display.webCopy("editButton", "変更")) { showPaperPicker = true }
            .buttonStyle(InkuGhostButtonStyle())
            .inkuTooltip(display.tooltip("用紙の形と意図を見て、次の作品の用紙を選びます。", serverKey: "tooltipInputCanvas"))
            .popover(isPresented: $showPaperPicker) {
                CreationPaperPicker(model: model, imageSelection: imageSelection) { showPaperPicker = false }.environment(display).inkuPopoverContent()
            }
            .accessibilityValue(canvas)
            if hasDetails {
                Button { showDetails = true } label: {
                    Image(systemName: "ellipsis").frame(minWidth: phone ? 24 : nil, minHeight: phone ? 36 : nil)
                }
                    .buttonStyle(InkuGhostButtonStyle())
                    .accessibilityLabel(display.localized("生成条件の詳細"))
            }
        }
    }
}
