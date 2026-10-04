import SwiftUI

@MainActor
struct CreationPaperPicker: View {
    @Bindable var model: AppModel
    let onClose: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(model.display.localized("用紙を選ぶ")).font(.headline)
                Spacer()
                Button(model.display.localized("閉じる")) { onClose() }
                    .help(tip("用紙を変更せずに閉じます。"))
            }.padding(14)
            Divider()
            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(model.canvases) { option in
                        Button {
                            guard !model.isBusy else { return }
                            model.canvasID = option.id
                            onClose()
                        } label: {
                            HStack(alignment: .top, spacing: 12) {
                                CanvasPaperShape(option: option).frame(width: 44, height: 48).accessibilityHidden(true)
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack(alignment: .firstTextBaseline) {
                                        Text(option.label).font(.callout.weight(.medium))
                                        Text("\(option.widthRatio):\(option.heightRatio)").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                                        Spacer(minLength: 0)
                                        if option.id == model.canvasID { Image(systemName: "checkmark").foregroundStyle(Color.accentColor) }
                                    }
                                    Text(option.category).font(.caption).foregroundStyle(.secondary)
                                    Text(model.display.preferences.language == "en" ? option.intentEn : option.intentJa)
                                        .font(.caption).foregroundStyle(.secondary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                            .background(option.id == model.canvasID ? Color.primary.opacity(0.07) : .clear,
                                        in: RoundedRectangle(cornerRadius: 8))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain).disabled(model.isBusy)
                        .accessibilityElement(children: .combine)
                        .accessibilityValue(option.id == model.canvasID ? model.display.localized("選択中") : "")
                        .help(tip("この用紙を次の作品に使います。保存作品の用紙は変わりません。"))
                    }
                }.padding(6)
            }.frame(maxHeight: 520)
        }.frame(width: 390)
    }

    private func tip(_ key: String) -> String {
        model.display.preferences.showTooltips ? model.display.localized(key) : ""
    }
}

private struct CanvasPaperShape: View {
    let option: CanvasOption
    var body: some View {
        GeometryReader { geometry in
            let ratio = CGFloat(option.widthRatio) / CGFloat(max(1, option.heightRatio))
            let width = min(geometry.size.width, geometry.size.height * ratio)
            let height = min(geometry.size.height, geometry.size.width / ratio)
            Rectangle().fill(Color.primary.opacity(0.04))
                .overlay(Rectangle().stroke(Color.primary.opacity(0.5), lineWidth: 1))
                .frame(width: width, height: height)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}
