#if os(macOS)
import SwiftUI
import AppKit
/// A page of library cards holds hundreds of these, so an idle tooltip keeps no AppKit view and no focus binding it
/// cannot use. The anchor that locates the bubble is placed when the pointer or keyboard focus arrives, and for a
/// control disabled from outside, which needs it to notice the pointer at all.
struct InkuTooltipModifier: ViewModifier {
    let text: String
    let placement: InkuTooltipPlacement
    let wide: Bool
    let focus: InkuTooltipFocus
    init(text: String, placement: InkuTooltipPlacement, wide: Bool, focus: InkuTooltipFocus) {
        self.text = text; self.placement = placement; self.wide = wide; self.focus = focus
    }
    @Environment(\.inkuTextScale) private var scale
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.inkuTooltipsCovered) private var covered
    @State private var token = InkuTooltipToken()
    @State private var engaged = false
    @FocusState private var focused: Bool

    private struct Inputs: Equatable {
        let text: String
        let dark: Bool
        let covered: Bool
        let scale: Double
    }

    private var focusable: Bool {
        switch focus {
        case .text: true
        case .control: NSApp?.isFullKeyboardAccessEnabled ?? false
        case .none: false
        }
    }

    func body(content: Content) -> some View {
        focusTracking(content
            .onHover { token.overContent = $0; sync() }
            .background {
                ZStack {
                    // Disabled from outside (`.inkuTooltip(…).disabled(…)`), SwiftUI may report no hover at all,
                    // so the anchor tracks the pointer itself.
                    if engaged || !isEnabled {
                        InkuTooltipAnchor(token: token, tracksPointer: !isEnabled) { token.overTracked = $0; sync() }
                    }
                    // Disabled inside (`.disabled(…).inkuTooltip(…)`), the control takes no hover of its own and
                    // this shape behind it does, so the reason shows.
                    Color.clear.contentShape(Rectangle()).onHover { token.overBackground = $0; sync() }
                }
            })
            .accessibilityHint(text)
            .onChange(of: Inputs(text: text, dark: colorScheme == .dark, covered: covered, scale: scale)) {
                if token.engaged || engaged { sync() }
            }
            .onDisappear { if token.engaged || engaged { InkuTooltipPresenter.shared.deactivate(token) } }
    }

    @ViewBuilder private func focusTracking(_ view: some View) -> some View {
        if focusable {
            view.focused($focused)
                .onChange(of: focused) { _, now in
                    // `:focus-visible`: focus that arrives with a key, not the focus a click leaves behind.
                    token.focusVisible = now && NSApp.currentEvent?.type == .keyDown
                    sync()
                }
        } else {
            view
        }
    }

    private func sync() {
        token.text = text
        token.placement = placement
        token.wide = wide
        token.scale = scale
        token.dark = colorScheme == .dark
        if engaged != token.engaged { engaged = token.engaged }
        if token.engaged && !covered { InkuTooltipPresenter.shared.activate(token) }
        else { InkuTooltipPresenter.shared.deactivate(token) }
    }
}

@MainActor
final class InkuTooltipToken {
    var text = ""
    var placement = InkuTooltipPlacement.top
    var wide = false
    var scale = 1.0
    var dark = false
    var overContent = false
    var overBackground = false
    var overTracked = false
    var focusVisible = false
    weak var view: NSView?
    var engaged: Bool { overContent || overBackground || overTracked || focusVisible }
}

/// Locates the bubble and, for a disabled control, follows the pointer. It takes no clicks.
private struct InkuTooltipAnchor: NSViewRepresentable {
    let token: InkuTooltipToken
    let tracksPointer: Bool
    let onPointer: (Bool) -> Void

    func makeNSView(context: Context) -> AnchorView {
        let view = AnchorView()
        token.view = view
        return view
    }

    static func dismantleNSView(_ view: AnchorView, coordinator: ()) {
        view.onPointer = nil
    }

    func updateNSView(_ view: AnchorView, context: Context) {
        token.view = view
        view.onPointer = onPointer
        view.tracksPointer = tracksPointer
    }

    final class AnchorView: NSView {
        var onPointer: ((Bool) -> Void)?
        var tracksPointer = false {
            didSet {
                guard tracksPointer != oldValue else { return }
                updateTrackingAreas()
                if !tracksPointer { onPointer?(false) }
            }
        }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        /// Placed after the pointer arrived: the bubble waits for this view to have a window and a frame.
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if window != nil { InkuTooltipPresenter.shared.anchorPlaced() }
        }
        override func setFrameSize(_ newSize: NSSize) {
            super.setFrameSize(newSize)
            if window != nil { InkuTooltipPresenter.shared.anchorPlaced() }
        }
        override func updateTrackingAreas() {
            trackingAreas.forEach(removeTrackingArea)
            if tracksPointer {
                addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                               owner: self, userInfo: nil))
            }
            super.updateTrackingAreas()
        }
        override func mouseEntered(with event: NSEvent) { onPointer?(true) }
        override func mouseExited(with event: NSEvent) { onPointer?(false) }
    }
}

/// One bubble for the whole app, drawn in a borderless child window so no scroll view or panel clips it.
/// The innermost hovered or focused tooltip with text is shown, as nested Web wraps stack the inner bubble on top.
@MainActor
final class InkuTooltipPresenter {
    static let shared = InkuTooltipPresenter()
    private var engaged: [InkuTooltipToken] = []
    private var shown: InkuTooltipToken?
    private var placing = false
    private lazy var panel: NSPanel = {
        let panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: true)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.ignoresMouseEvents = true
        panel.isReleasedWhenClosed = false
        panel.animationBehavior = .none
        panel.collectionBehavior = [.transient, .ignoresCycle, .fullScreenAuxiliary]
        panel.contentView = host
        return panel
    }()
    private let host = NSHostingView(rootView: InkuTooltipBubble.empty)
    private var resignObserver: NSObjectProtocol?

    func activate(_ token: InkuTooltipToken) {
        if !engaged.contains(where: { $0 === token }) { engaged.append(token) }
        present()
    }

    func deactivate(_ token: InkuTooltipToken) {
        engaged.removeAll { $0 === token }
        present()
    }

    /// An anchor placed on arrival reached its window or its frame; a bubble waiting for it can be shown.
    func anchorPlaced() {
        guard let token = engaged.last(where: { !$0.text.isEmpty }), token.view != nil, !placing else { return }
        placing = true
        // After this layout pass, when the anchor has its final frame.
        DispatchQueue.main.async { [weak self] in
            MainActor.assumeIsolated {
                self?.placing = false
                self?.present()
            }
        }
    }

    private func present() {
        // Only the key window shows bubbles, as with native tool tips: ordering the child bubble front would
        // also bring an inactive parent window in front of the window the author is using.
        guard let token = engaged.last(where: { !$0.text.isEmpty }) else { hide(); return }
        // The innermost tooltip's anchor is placed in this update; show nothing else meanwhile.
        if token.view == nil { return }
        guard let view = token.view, let window = view.window, window.isVisible, window.isKeyWindow,
              window.attachedSheet == nil else { hide(); return }
        let anchor = window.convertToScreen(view.convert(view.bounds, to: nil))
        var bounds = window.frame.insetBy(dx: 8, dy: 8)
        if let screen = window.screen { bounds = bounds.intersection(screen.visibleFrame.insetBy(dx: 8, dy: 8)) }

        let maxWidth: CGFloat = token.wide ? 440 : 260
        host.rootView = InkuTooltipBubble(text: token.text, scale: token.scale, dark: token.dark, maxWidth: maxWidth,
                                          edge: nil, arrowOffset: 0)
        let body = host.fittingSize
        // The panel holds the arrow too, on the side that faces the element; a flip keeps the axis.
        let depth = InkuTooltipBubble.arrowDepth
        let vertical = token.placement == .top || token.placement == .bottom
        let size = vertical ? CGSize(width: body.width, height: body.height + depth) : CGSize(width: body.width + depth, height: body.height)
        let placed = InkuTooltipLayout.place(size: size, anchor: anchor, bounds: bounds, placement: token.placement, gap: 8 - depth)

        host.rootView = InkuTooltipBubble(text: token.text, scale: token.scale, dark: token.dark, maxWidth: maxWidth,
                                          edge: placed.arrowEdge, arrowOffset: placed.arrowOffset)
        let appearing = shown == nil || panel.parent !== window
        if panel.parent !== window {
            panel.parent?.removeChildWindow(panel)
            window.addChildWindow(panel, ordered: .above)
            observeResign(of: window)
        }
        panel.setFrame(placed.frame, display: true)
        panel.invalidateShadow()
        shown = token
        if appearing {
            panel.alphaValue = 0
            panel.orderFront(nil)
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.12
                panel.animator().alphaValue = 1
            }
        }
    }

    private func hide() {
        shown = nil
        guard panel.isVisible || panel.parent != nil else { return }
        panel.parent?.removeChildWindow(panel)
        panel.orderOut(nil)
    }

    /// A sheet or another window taking the keyboard leaves no exit event for the control below.
    private func observeResign(of window: NSWindow) {
        if let resignObserver { NotificationCenter.default.removeObserver(resignObserver) }
        resignObserver = NotificationCenter.default.addObserver(forName: NSWindow.didResignKeyNotification, object: window,
                                                                queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.engaged.removeAll()
                self?.hide()
            }
        }
    }
}

/// Web `.tooltip-bubble` with its `::after` arrow: 11px text at line-height 1.45, 6px × 8px padding,
/// a 1px border, radius 4 and the theme's tooltip colors (`+page.svelte:3514-3518, 3558-3562`).
struct InkuTooltipBubble: View {
    static let arrowDepth: CGFloat = 5
    static let empty = InkuTooltipBubble(text: "", scale: 1, dark: false, maxWidth: 260, edge: nil, arrowOffset: 0)
    let text: String
    let scale: Double
    let dark: Bool
    let maxWidth: CGFloat
    /// The bubble side that faces the element; nil measures the bubble alone.
    let edge: Edge?
    /// Distance of the arrow tip from the leading edge (top or bottom arrow) or the top edge (side arrow).
    let arrowOffset: CGFloat

    private var background: Color { dark ? Color(red: 0.047, green: 0.047, blue: 0.043) : .white }
    private var foreground: Color { dark ? .white : Color(red: 0.102, green: 0.098, blue: 0.09) }
    private var border: Color { dark ? Color(red: 0.392, green: 0.455, blue: 0.545) : Color(red: 0.769, green: 0.753, blue: 0.722) }

    var body: some View {
        let size = 11 * scale
        Text(text)
            .font(.system(size: size))
            .lineSpacing(size * 0.45 - 2)
            .foregroundStyle(foreground)
            .multilineTextAlignment(.leading)
            .frame(width: textWidth, alignment: .leading)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.vertical, 6).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 4).fill(background))
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(border, lineWidth: 1))
            .overlay(alignment: .topLeading) { arrow }
            .padding(edge.map(Self.side) ?? .top, edge == nil ? 0 : Self.arrowDepth)
    }

    private static func side(_ edge: Edge) -> Edge.Set {
        switch edge { case .top: .top; case .bottom: .bottom; case .leading: .leading; case .trailing: .trailing }
    }

    /// `width: max-content` up to `max-width`: the longest line, wrapped at the limit.
    private var textWidth: CGFloat {
        let font = NSFont.systemFont(ofSize: 11 * scale)
        let natural = (text as NSString).boundingRect(with: CGSize(width: CGFloat.greatestFiniteMagnitude, height: .greatestFiniteMagnitude),
                                                      options: [.usesLineFragmentOrigin], attributes: [.font: font]).width
        return min(maxWidth - 16, ceil(natural) + 1)
    }

    @ViewBuilder private var arrow: some View {
        let depth = Self.arrowDepth
        if let edge { GeometryReader { proxy in
            Path { path in
                switch edge {
                case .bottom:
                    let y = proxy.size.height - 0.5
                    path.move(to: CGPoint(x: arrowOffset - depth, y: y))
                    path.addLine(to: CGPoint(x: arrowOffset, y: y + depth))
                    path.addLine(to: CGPoint(x: arrowOffset + depth, y: y))
                case .top:
                    path.move(to: CGPoint(x: arrowOffset - depth, y: 0.5))
                    path.addLine(to: CGPoint(x: arrowOffset, y: 0.5 - depth))
                    path.addLine(to: CGPoint(x: arrowOffset + depth, y: 0.5))
                case .leading:
                    let y = arrowOffset
                    path.move(to: CGPoint(x: 0.5, y: y - depth))
                    path.addLine(to: CGPoint(x: 0.5 - depth, y: y))
                    path.addLine(to: CGPoint(x: 0.5, y: y + depth))
                case .trailing:
                    let x = proxy.size.width - 0.5
                    let y = arrowOffset
                    path.move(to: CGPoint(x: x, y: y - depth))
                    path.addLine(to: CGPoint(x: x + depth, y: y))
                    path.addLine(to: CGPoint(x: x, y: y + depth))
                }
                path.closeSubpath()
            }
            .fill(background)
        } }
    }
}
#endif
