import SwiftUI

/// Web AppRail.svelte: a 44pt icon rail that expands to 164pt. The single-user app has no user menu or login.
@MainActor
struct AppRailView: View {
    @Bindable var model: AppModel
    @Binding var expanded: Bool
    let settingsOpen: Bool
    let drawingLogsDisabled: Bool
    let onOpenSettings: () -> Void
    let onOpenDrawingLogs: () -> Void
    let onOpenAbout: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @State private var uiModeOpen = false

    private var display: DisplaySettings { model.display }
    private var showAuxiliary: Bool { display.visible("auxiliary") }
    private var darkMode: Bool { display.colorScheme == .dark || display.colorScheme == nil && colorScheme == .dark }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            brand
            VStack(alignment: .leading, spacing: 6) {
                uiModeMenu
                railButton(display.webCopy(display.preferences.showTooltips ? "tooltipsHide" : "tooltipsShow",
                                           display.preferences.showTooltips ? "ツールチップを非表示" : "ツールチップを表示"),
                           // AppRail.svelte:156: the bubble names what a click does. While tooltips are off it is
                           // hidden with every other bubble (`.tooltips-disabled .tooltip-bubble`), and the label says it.
                           help: display.tooltip(display.preferences.showTooltips ? "ツールチップを非表示" : "ツールチップを表示",
                                                 serverKey: display.preferences.showTooltips ? "tooltipsHide" : "tooltipsShow"),
                           active: false) {
                    display.preferences.showTooltips.toggle()
                } icon: {
                    Image(systemName: display.preferences.showTooltips ? "questionmark" : "questionmark.circle.dashed")
                }
                railButton(display.webCopy("settingsTitle", "設定"),
                           help: display.tooltip("設定を開く", serverKey: "tooltipAppRailSettings"),
                           active: settingsOpen, action: onOpenSettings) { Image(systemName: "gearshape") }
                // Native: the drawing log keeps every success, failure and stop, which the Web has no page for.
                railButton(display.localized("描画ログ"),
                           help: display.tooltip("成功・失敗・停止した描画の記録を確認します。"),
                           active: false, action: onOpenDrawingLogs) { Image(systemName: "list.bullet.rectangle") }
                    .disabled(drawingLogsDisabled)
                if showAuxiliary {
                    railButton(display.webCopy(darkMode ? "themeLight" : "themeDark", darkMode ? "ライトモード" : "ダークモード"),
                               help: display.tooltip("ダークモード / ライトモードの切り替え", serverKey: "tooltipAppRailTheme"),
                               active: false) {
                        display.preferences.theme = darkMode ? "light" : "dark"
                    } icon: {
                        Image(systemName: darkMode ? "sun.max.fill" : "moon.fill")
                            .foregroundStyle(darkMode ? Color(red: 0.85, green: 0.77, blue: 0.42) : Color.primary)
                    }
                    languageButtons
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 10).padding(.horizontal, 6)
        .frame(width: expanded ? 164 : 44, alignment: .leading)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(InkuColor.bg)
        .overlay(alignment: .trailing) { Rectangle().fill(InkuColor.border).frame(width: 1) }
        .animation(.easeOut(duration: 0.16), value: expanded)
    }

    private var brand: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { expanded.toggle() } label: {
                Text(expanded ? "‹" : "›").inkuFont(18)
                    .frame(width: 30, height: 30)
                    .foregroundStyle(.secondary)
                    .background(RoundedRectangle(cornerRadius: 4).fill(InkuColor.panel))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(display.webCopy(expanded ? "railCollapseLabel" : "railExpandLabel",
                                                expanded ? "サイドバーを格納する" : "サイドバーを伸ばす"))
            .inkuTooltip(display.tooltip("サイドバーを展開 / 折りたたむ", serverKey: "tooltipAppRailToggle"), placement: .right)
            // macOS opens About inku only from the app menu; the rail logo stays on iOS.
            #if !os(macOS)
            if showAuxiliary {
                Button(action: onOpenAbout) {
                    HStack(spacing: 0) {
                        Text("inku").lineLimit(1).minimumScaleFactor(0.6).frame(width: 30)
                        if expanded { Text("-lang").padding(.trailing, 9) }
                    }
                    .inkuFont(15, weight: .light)
                    .lineLimit(1)
                    .frame(height: 30)
                    .background(RoundedRectangle(cornerRadius: 4).fill(InkuColor.panel))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .padding(.top, 6)
                .accessibilityLabel(display.localized("inkuについて"))
                .inkuTooltip(display.tooltip("inku-lang について", serverKey: "tooltipAppRailLogo"), placement: .right)
                if expanded {
                    Text(display.webCopy("subtitle", "視覚的な短歌を書く")).inkuFont(10).foregroundStyle(.secondary)
                        .lineLimit(1).padding(.top, 4)
                }
            }
            #endif
        }
        #if !os(macOS)
        .frame(minHeight: 78, alignment: .topLeading)
        #endif
    }

    private var uiModeLabel: String {
        switch display.preferences.uiMode {
        case "full": display.webCopy("uiModeFull", "フルUI")
        case "custom": display.webCopy("uiModeCustom", "カスタムUI")
        default: display.webCopy("uiModeSimple", "シンプルUI")
        }
    }

    /// AppRail.svelte:121-150: the rail button opens a three-item menu to its right.
    private var uiModeMenu: some View {
        Button { uiModeOpen.toggle() } label: {
            railLabel(uiModeLabel, active: uiModeOpen) { UIModeBars(mode: display.preferences.uiMode) }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(display.webCopy("uiModeLabel", "UIモード"))
        .accessibilityValue(uiModeLabel)
        .inkuTooltip(uiModeOpen ? "" : display.tooltip("UIモード", serverKey: "uiModeLabel"), placement: .right)
        .popover(isPresented: $uiModeOpen, arrowEdge: .trailing) {
            VStack(alignment: .leading, spacing: 0) {
                // In the order the icon draws them: one bar, two, three.
                ForEach([("simple", "uiModeSimple", "シンプルUI"), ("custom", "uiModeCustom", "カスタムUI"), ("full", "uiModeFull", "フルUI")], id: \.0) { mode in
                    let selected = display.preferences.uiMode == mode.0
                    Button {
                        display.preferences.uiMode = mode.0
                        uiModeOpen = false
                    } label: {
                        HStack(spacing: 6) {
                            Text("✓").opacity(selected ? 1 : 0)
                            Text(display.webCopy(mode.1, mode.2))
                        }
                        .inkuFont(11, weight: selected ? .semibold : .regular)
                        .foregroundStyle(selected ? Color.primary : Color.secondary)
                        .padding(.vertical, 7).padding(.horizontal, 9)
                        .frame(minWidth: 126, alignment: .leading)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(selected ? .isSelected : [])
                }
            }
            .padding(4)
        }
    }

    private var languageButtons: some View {
        let languages = [("ja", "日本語"), ("en", "English")]
        return Group {
            if expanded {
                HStack(spacing: 4) { ForEach(languages, id: \.0) { languageButton($0.0, label: $0.1, name: $0.1) } }
            } else {
                VStack(spacing: 4) { ForEach(languages, id: \.0) { languageButton($0.0, label: $0.0.uppercased(), name: $0.1) } }
            }
        }
    }

    /// AppRail.svelte:187: the bubble names the pack (`pack.label`), also when the button shows its code.
    private func languageButton(_ code: String, label: String, name: String) -> some View {
        let active = display.preferences.language == code
        return Button { display.preferences.language = code } label: {
            Text(label).inkuFont(10).lineLimit(1)
                .frame(maxWidth: .infinity, minHeight: 20)
                .foregroundStyle(active ? InkuColor.panel : Color.secondary)
                .background(RoundedRectangle(cornerRadius: 4).fill(active ? Color.primary : InkuColor.panel))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(active ? Color.primary : InkuColor.border2))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(active ? .isSelected : [])
        .inkuTooltip(display.preferences.showTooltips ? display.tooltip("表示言語の切り替え", serverKey: "tooltipAppRailLang") + ": " + name : "",
                     placement: .right)
    }

    private func railButton<Icon: View>(_ title: String, help: String, active: Bool, action: @escaping () -> Void,
                                        @ViewBuilder icon: () -> Icon) -> some View {
        Button(action: action) { railLabel(title, active: active, icon: icon) }
            .buttonStyle(.plain)
            .accessibilityLabel(title)
            .inkuTooltip(help, placement: .right)
    }

    private func railLabel<Icon: View>(_ title: String, active: Bool, @ViewBuilder icon: () -> Icon) -> some View {
        HStack(spacing: 8) {
            icon()
                .inkuFont(11)
                .frame(width: 22, height: 22)
                .background(Circle().fill(InkuColor.panel))
                .overlay(Circle().stroke(InkuColor.border2))
            if expanded {
                Text(title).inkuFont(11).lineLimit(1).truncationMode(.tail)
                Spacer(minLength: 0)
            }
        }
        .foregroundStyle(active ? Color.primary : Color.secondary)
        .padding(4)
        .frame(minHeight: 30)
        .frame(maxWidth: expanded ? .infinity : nil, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 4).fill(active ? InkuColor.panel : Color.clear))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(active ? InkuColor.border2 : Color.clear))
        .contentShape(Rectangle())
    }
}

/// How much of the interface is on show, drawn as how much of the mark is drawn (AppRail.svelte:290-305).
private struct UIModeBars: View {
    let mode: String
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            bar(width: 12, faint: false)
            bar(width: 8, faint: mode == "simple")
            bar(width: 5, faint: mode != "full")
        }.frame(width: 12, alignment: .leading)
    }
    private func bar(width: CGFloat, faint: Bool) -> some View {
        RoundedRectangle(cornerRadius: 1).frame(width: width, height: 2).opacity(faint ? 0.3 : 1)
    }
}
