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

    /// Escape: the Mac's cancel command, or Escape on an iOS hardware keyboard while the view holds the focus.
    @ViewBuilder
    func inkuOnEscape(_ action: @escaping () -> Void) -> some View {
        #if os(macOS)
        onExitCommand(perform: action)
        #else
        onKeyPress(.escape) { action(); return .handled }
        #endif
    }

    /// A sheet whose content has a fixed size from the Web formula. An iPad sheet is form-sized (about 700 points)
    /// unless asked otherwise, which cuts a larger dialog; it takes the content's size instead (iOS 18).
    @ViewBuilder
    func inkuFittedSheet() -> some View {
        #if os(macOS)
        self
        #else
        presentationSizing(.fitted)
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

// MARK: - iPhone layout (ios-app step 7)

/// Hands its content whether the window takes the iPhone layout: a narrow width, or a short height (an iPhone on its
/// side, which a Pro Max reports as a wide width). Never on the Mac; never on an iPad, which runs full screen.
struct InkuPhoneLayoutReader<Content: View>: View {
    @ViewBuilder let content: (Bool) -> Content
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var horizontal
    @Environment(\.verticalSizeClass) private var vertical
    var body: some View { content(horizontal == .compact || vertical == .compact) }
    #else
    var body: some View { content(false) }
    #endif
}

extension View {
    /// A screen that shows a work turns with an iPhone; the others stay upright (STEP7 author's choice 2026-11-09).
    @ViewBuilder
    func inkuAllowsLandscape(_ enabled: Bool = true) -> some View {
        #if os(iOS)
        if enabled { onAppear { InkuOrientationGate.enter() }.onDisappear { InkuOrientationGate.leave() } } else { self }
        #else
        self
        #endif
    }

    /// A small title in the navigation bar (iOS); the Mac's toolbar has no such choice.
    @ViewBuilder
    func inkuInlineNavigationTitle() -> some View {
        #if os(iOS)
        navigationBarTitleDisplayMode(.inline)
        #else
        self
        #endif
    }

    /// The iPhone tab bar's accessory while a run goes on (iOS 26.1 and later); before, a bar above the tabs.
    @ViewBuilder
    func inkuTabRunAccessory<Accessory: View>(visible: Bool, @ViewBuilder accessory: () -> Accessory) -> some View {
        #if os(iOS)
        if #available(iOS 26.1, *) {
            tabViewBottomAccessory(isEnabled: visible, content: accessory)
        } else {
            let row = accessory()
            safeAreaInset(edge: .bottom, spacing: 0) {
                if visible { row.padding(.vertical, 8).background(.bar) }
            }
        }
        #else
        self
        #endif
    }
}
