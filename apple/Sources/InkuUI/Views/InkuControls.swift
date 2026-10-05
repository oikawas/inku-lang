import SwiftUI
#if os(macOS)
import AppKit
#elseif os(iOS)
import UIKit
#endif

/// Web color tokens (`+page.svelte` :root) mapped onto the system palette, so both themes keep the native contrast.
enum InkuColor {
    #if os(macOS)
    static let bg = Color(nsColor: .windowBackgroundColor)
    static let panel = Color(nsColor: .controlBackgroundColor)
    #else
    static let bg = Color(uiColor: .systemGroupedBackground)
    static let panel = Color(uiColor: .secondarySystemGroupedBackground)
    #endif
    static let bg2 = Color.primary.opacity(0.045)
    static let border = Color.primary.opacity(0.12)
    static let border2 = Color.primary.opacity(0.2)
    static let floating = panel.opacity(0.92)
}

extension DisplaySettings {
    /// Web label copy with a native fallback. Unlike `tooltip`, it stays visible when tooltips are off.
    func webCopy(_ key: String, _ fallback: String) -> String {
        ServerTips.text(key, language: preferences.language) ?? localized(fallback)
    }
}

// MARK: - Window size

private struct InkuWindowSizeKey: EnvironmentKey {
    static let defaultValue: CGSize? = nil
}

extension EnvironmentValues {
    /// The main window's content size. Web dialogs size against the viewport (`100vw`, `100dvh`).
    var inkuWindowSize: CGSize? {
        get { self[InkuWindowSizeKey.self] }
        set { self[InkuWindowSizeKey.self] = newValue }
    }
}

/// Web dialog box: `width: min(W, 100vw − inset)` and `height: min(H, 100dvh − inset)`.
/// A fraction stands for the `vw`/`vh` forms (`min(780px, 96vw)`).
struct InkuDialogSize: Equatable {
    var width: CGFloat
    var widthInset: CGFloat = 40
    var widthFraction: CGFloat = 1
    var height: CGFloat
    var heightInset: CGFloat = 40
    var heightFraction: CGFloat = 1

    func resolved(in window: CGSize) -> CGSize {
        CGSize(width: max(320, min(width, window.width * widthFraction - widthInset)),
               height: max(240, min(height, window.height * heightFraction - heightInset)))
    }

    /// DdlEditorDialog.svelte:206
    static let ddlEditor = InkuDialogSize(width: 1360, height: 940)
    /// ReplayComparisonModal.svelte:82 (`max-height: 100vh − 40px`)
    static let replay = InkuDialogSize(width: 1120, height: 880)
    /// WorkEditDialog.svelte:134 (`min(780px, 96vw)`, `max-height: 92vh`)
    static let workEdit = InkuDialogSize(width: 780, widthInset: 0, widthFraction: 0.96, height: 760, heightInset: 0, heightFraction: 0.92)
    /// LineagePanel.svelte:1029 okugaki-dialog and AIRefineModal (`min(760px, 96vw)`, `max-height: 90vh`)
    static let auxiliary = InkuDialogSize(width: 760, widthInset: 0, widthFraction: 0.96, height: 820, heightInset: 0, heightFraction: 0.9)
    /// refinement-workspace.css:6 candidate grids shown outside the canvas
    static let comparison = InkuDialogSize(width: 1120, height: 940)
    /// CanvasGenerationInfo.svelte:385 (`min(760px, 100% − 72px)`)
    static let generationInfo = InkuDialogSize(width: 760, widthInset: 72, height: 900, heightInset: 90)
    /// ColorCatalogModal.svelte:115 (`min(1180px, 100vw − 32px)`, `max-height: 92vh`)
    static let colorCatalog = InkuDialogSize(width: 1180, widthInset: 32, height: 900, heightInset: 0, heightFraction: 0.92)
    /// settings-modal.css:43 model mode (`min(820px, 100vw − 32px)` × `min(760px, 88vh)`)
    static let modelSelection = InkuDialogSize(width: 820, widthInset: 32, height: 760, heightInset: 0, heightFraction: 0.88)
    /// settings-modal.css:38-39
    static let settings = InkuDialogSize(width: 1240, widthInset: 48, height: 840, heightInset: 48)
    /// Native drawing log, sized like the settings modal.
    static let drawingLogs = InkuDialogSize(width: 1240, widthInset: 48, height: 840, heightInset: 48)
}

private struct InkuDialogFrame: ViewModifier {
    @Environment(\.inkuWindowSize) private var window
    let size: InkuDialogSize
    func body(content: Content) -> some View {
        if let window, window.width > 0 {
            let box = size.resolved(in: window)
            content.frame(width: box.width, height: box.height)
        } else {
            content
        }
    }
}

extension View {
    /// Sizes a sheet with the Web formula for the same dialog. Without a known window it keeps its own size.
    func inkuDialogFrame(_ size: InkuDialogSize) -> some View { modifier(InkuDialogFrame(size: size)) }
}

// MARK: - Buttons

/// Web `.ghost-btn`: 12px, padding 4×10, 1px border2, radius 4, panel background (`+page.svelte` --btn-sm-*).
struct InkuGhostButtonStyle: ButtonStyle {
    var active = false
    var prominent = false
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .inkuFont(12)
            .lineLimit(1)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .foregroundStyle(active || prominent ? Color.white : Color.primary.opacity(0.78))
            .background(RoundedRectangle(cornerRadius: 4, style: .continuous)
                .fill(active || prominent ? Color.accentColor : configuration.isPressed ? InkuColor.bg2 : InkuColor.panel))
            .overlay(RoundedRectangle(cornerRadius: 4, style: .continuous)
                .stroke(active || prominent ? Color.accentColor : InkuColor.border2))
            .opacity(isEnabled ? 1 : 0.55)
            .contentShape(Rectangle())
    }
}

/// Web `.paint-btn.block`: full width, 14px weight 500, padding 9, radius 4, action colors.
struct InkuPaintButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .inkuFont(14, weight: .medium)
            .frame(maxWidth: .infinity)
            .padding(9)
            .foregroundStyle(Color.white.opacity(isEnabled ? 1 : 0.85))
            .background(RoundedRectangle(cornerRadius: 4, style: .continuous)
                .fill(isEnabled ? Color.accentColor.opacity(configuration.isPressed ? 0.8 : 1) : Color.secondary.opacity(0.55)))
            .contentShape(Rectangle())
    }
}

/// Web `.canvas-icon-btn` (34px circle) and `.nav-circle` (38px): floating controls on the canvas.
struct InkuFloatingCircleButtonStyle: ButtonStyle {
    var diameter: CGFloat = 34
    var active = false
    var tint: Color? = nil
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .inkuFont(diameter > 34 ? 20 : 15)
            .foregroundStyle(isEnabled ? (tint ?? Color.primary) : Color.secondary.opacity(0.7))
            .frame(width: diameter, height: diameter)
            .background(Circle().fill(configuration.isPressed || active ? InkuColor.panel : InkuColor.floating))
            .overlay(Circle().stroke(active ? Color.accentColor.opacity(0.45) : InkuColor.border2))
            .shadow(color: .black.opacity(0.1), radius: 3, y: 1)
            .opacity(isEnabled ? 1 : 0.8)
            .contentShape(Circle())
    }
}

/// Web `.nav-latest`: 24px pill, 11px, min width 42.
struct InkuFloatingPillButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .inkuFont(11)
            .lineLimit(1)
            .padding(.horizontal, 8)
            .frame(minWidth: 42, minHeight: 24)
            .foregroundStyle(isEnabled ? Color.primary : Color.secondary.opacity(0.7))
            .background(Capsule().fill(configuration.isPressed ? InkuColor.panel : InkuColor.floating))
            .overlay(Capsule().stroke(InkuColor.border2))
            .shadow(color: .black.opacity(0.1), radius: 3, y: 1)
            .contentShape(Capsule())
    }
}

// MARK: - Tabs

/// Web InputPanel `.panel-tab`: equal halves, 12px, min height 38, selected with a 2px accent underline.
struct InkuPanelTab: View {
    let title: String
    let selected: Bool
    var running = false
    var progress = ""
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(title).lineLimit(1)
                if !progress.isEmpty {
                    Text(progress).inkuFont(11).monospacedDigit().foregroundStyle(.secondary).lineLimit(1)
                }
                if running {
                    Circle().fill(Color.accentColor).frame(width: 6, height: 6)
                        .shadow(color: Color.accentColor.opacity(0.35), radius: 3)
                }
            }
            .inkuFont(12)
            .foregroundStyle(selected || running ? Color.primary : Color.secondary)
            .frame(maxWidth: .infinity, minHeight: 38)
            .background(running ? Color.accentColor.opacity(0.08) : Color.clear)
            .overlay(alignment: .bottom) {
                Rectangle().fill(selected || running ? Color.accentColor : Color.clear).frame(height: 2)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// Web CanvasPanel `.rtab`: 13px text tab, padding 9×16, selected with a 2px underline and weight 500.
struct InkuTextTab: View {
    let title: String
    let selected: Bool
    var compact = false
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            Text(title)
                .inkuFont(13, weight: selected ? .medium : .regular)
                .lineLimit(1)
                .foregroundStyle(selected ? Color.primary : Color.secondary)
                .padding(.horizontal, compact ? 12 : 16).padding(.vertical, 9)
                .overlay(alignment: .bottom) {
                    Rectangle().fill(selected ? Color.primary : Color.clear).frame(height: 2)
                }
                .opacity(isEnabled ? 1 : 0.35)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// Web connected small buttons: 12px, padding 4×10, one border; the selected one takes the panel and weight 500.
struct InkuSegmentedButtons<Value: Hashable>: View {
    let options: [(Value, String)]
    @Binding var selection: Value

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(options.enumerated()), id: \.offset) { index, option in
                Button { selection = option.0 } label: {
                    Text(option.1)
                        .inkuFont(12, weight: selection == option.0 ? .medium : .regular)
                        .lineLimit(1)
                        .foregroundStyle(selection == option.0 ? Color.primary : Color.secondary)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .background(selection == option.0 ? InkuColor.panel : Color.clear)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selection == option.0 ? .isSelected : [])
                if index < options.count - 1 { Rectangle().fill(InkuColor.border2).frame(width: 1) }
            }
        }
        .fixedSize()
        .background(InkuColor.bg2)
        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 4, style: .continuous).stroke(InkuColor.border2))
    }
}
