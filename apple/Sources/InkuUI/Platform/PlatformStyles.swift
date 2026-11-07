import SwiftUI

private struct InkuSearchFieldHeight: ViewModifier {
    @Environment(\.inkuTextScale) private var scale
    @ViewBuilder func body(content: Content) -> some View {
        #if os(macOS)
        content.frame(height: 26 * max(1, scale))
        #else
        content
        #endif
    }
}

extension View {
    /// One control high: 26 points, taller with a larger text size.
    func inkuSearchFieldHeight() -> some View { modifier(InkuSearchFieldHeight()) }

    @ViewBuilder
    func inkuFocusSection() -> some View {
        #if os(macOS)
        focusSection()
        #else
        self
        #endif
    }

    @ViewBuilder
    func inkuChoicePickerStyle(segmentedOnIOS: Bool = false) -> some View {
        #if os(macOS)
        pickerStyle(.radioGroup)
        #else
        if segmentedOnIOS { pickerStyle(.segmented) } else { self }
        #endif
    }

    @ViewBuilder
    func inkuCheckboxStyle(switchOnIOS: Bool = false) -> some View {
        #if os(macOS)
        toggleStyle(.checkbox)
        #else
        if switchOnIOS { toggleStyle(.switch).fixedSize() } else { self }
        #endif
    }

    @ViewBuilder
    func inkuBorderlessMenu(hideIndicator: Bool = false, includingIOS: Bool = false) -> some View {
        #if os(macOS)
        if hideIndicator { menuStyle(.borderlessButton).menuIndicator(.hidden) }
        else { menuStyle(.borderlessButton) }
        #else
        if includingIOS {
            if hideIndicator { menuStyle(.borderlessButton).menuIndicator(.hidden) }
            else { menuStyle(.borderlessButton) }
        } else { self }
        #endif
    }

    /// Web `onblur`: while `isActive`, a press outside this view calls `end`, and the press still reaches what was
    /// pressed. A browser blurs a focused field on any press outside it; macOS keeps editing when the press falls on a
    /// place that takes no focus. On iOS a tap outside does not end editing either; nothing is decided there yet.
    @ViewBuilder
    func inkuEndsEditingOnOutsidePress(isActive: Bool, end: @escaping () -> Void) -> some View {
        #if os(macOS)
        background(MacOutsidePressWatcher(isActive: isActive, end: end))
        #else
        self
        #endif
    }

    @ViewBuilder
    func inkuOnEscape(_ action: @escaping () -> Void) -> some View {
        #if os(macOS)
        onExitCommand(perform: action)
        #else
        self
        #endif
    }

    @ViewBuilder
    func inkuDialogFrame(width: CGFloat? = nil, height: CGFloat? = nil,
                         minWidth: CGFloat? = nil, idealWidth: CGFloat? = nil,
                         minHeight: CGFloat? = nil, idealHeight: CGFloat? = nil,
                         iOSMaxWidth: CGFloat? = nil) -> some View {
        #if os(macOS)
        if width != nil || height != nil { frame(width: width, height: height) }
        else { frame(minWidth: minWidth, idealWidth: idealWidth, minHeight: minHeight, idealHeight: idealHeight) }
        #else
        if let iOSMaxWidth { frame(maxWidth: iOSMaxWidth) } else { self }
        #endif
    }
}
