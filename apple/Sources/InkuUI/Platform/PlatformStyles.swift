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

    /// No navigation bar over a view that draws its own heading (iOS).
    @ViewBuilder
    func inkuHidesNavigationBar() -> some View {
        #if os(iOS)
        toolbar(.hidden, for: .navigationBar)
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

    /// An iPhone sheet (ios-app step 7c): the whole height, its own width; no Web box and no fitted size.
    @ViewBuilder
    func inkuPhoneSheet() -> some View {
        #if os(iOS)
        presentationDetents([.large])
        #else
        self
        #endif
    }

    /// A popover's contents. On an iPhone the popover becomes a sheet that stops at half and at the whole height
    /// (ios-app step 7c); elsewhere it stays a popover.
    func inkuPopoverContent() -> some View { modifier(InkuPopoverContent()) }

    /// A fixed width on the Mac and the iPad; on an iPhone the width it is given (ios-app step 7c).
    func inkuFixedWidth(_ width: CGFloat, alignment: Alignment = .center) -> some View {
        modifier(InkuFixedWidth(width: width, alignment: alignment))
    }

    /// A button or link that takes only its own taps inside an iOS form row, where a plain button makes the whole row
    /// one target and a tap fires every button in it (ios-app step 7c: the license button also opened the repository).
    @ViewBuilder
    func inkuOwnTapInFormRow() -> some View {
        #if os(iOS)
        buttonStyle(.borderless)
        #else
        self
        #endif
    }

    /// A row of buttons that slides sideways on an iPhone when it is wider than the screen (ios-app step 7c).
    func inkuPhoneSlidesSideways() -> some View { modifier(InkuPhoneSlidesSideways()) }

    /// A minimum and ideal size on the Mac and the iPad; none on an iPhone, whose sheet is the screen (ios-app step 7c).
    func inkuWideFrame(minWidth: CGFloat? = nil, idealWidth: CGFloat? = nil,
                       minHeight: CGFloat? = nil, idealHeight: CGFloat? = nil) -> some View {
        modifier(InkuWideFrame(minWidth: minWidth, idealWidth: idealWidth, minHeight: minHeight, idealHeight: idealHeight))
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

// MARK: - iPhone sheets and fixed widths (ios-app step 7c)

private struct InkuPhoneLayoutKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// Whether the window takes the iPhone layout. Set by the main view and handed into its sheets, where the size
    /// classes describe the sheet (an iPad form sheet reads as narrow) rather than the window.
    var inkuPhoneLayout: Bool {
        get { self[InkuPhoneLayoutKey.self] }
        set { self[InkuPhoneLayoutKey.self] = newValue }
    }
}

private struct InkuPopoverContent: ViewModifier {
    @Environment(\.inkuPhoneLayout) private var phone
    func body(content: Content) -> some View {
        #if os(iOS)
        if phone {
            content.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
        } else {
            content
        }
        #else
        content
        #endif
    }
}

private struct InkuFixedWidth: ViewModifier {
    @Environment(\.inkuPhoneLayout) private var phone
    let width: CGFloat
    let alignment: Alignment
    func body(content: Content) -> some View {
        if phone { content.frame(maxWidth: .infinity, alignment: alignment) } else { content.frame(width: width, alignment: alignment) }
    }
}

private struct InkuWideFrame: ViewModifier {
    @Environment(\.inkuPhoneLayout) private var phone
    let minWidth: CGFloat?
    let idealWidth: CGFloat?
    let minHeight: CGFloat?
    let idealHeight: CGFloat?
    func body(content: Content) -> some View {
        if phone { content } else { content.frame(minWidth: minWidth, idealWidth: idealWidth, minHeight: minHeight, idealHeight: idealHeight) }
    }
}

private struct InkuPhoneSlidesSideways: ViewModifier {
    @Environment(\.inkuPhoneLayout) private var phone
    func body(content: Content) -> some View {
        if phone {
            ScrollView(.horizontal, showsIndicators: false) { content }.scrollBounceBehavior(.basedOnSize, axes: .horizontal)
        } else {
            content
        }
    }
}

/// A label and its value: side by side on the Mac and the iPad, the label above the value on an iPhone
/// (ios-app step 7c, the generation information's 190-point label column).
func inkuLabelValueLayout(phone: Bool, alignment: VerticalAlignment = .firstTextBaseline) -> AnyLayout {
    phone ? AnyLayout(VStackLayout(alignment: .leading, spacing: 3)) : AnyLayout(HStackLayout(alignment: alignment, spacing: 16))
}
