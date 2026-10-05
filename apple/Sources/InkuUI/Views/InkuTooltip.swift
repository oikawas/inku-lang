import SwiftUI
#if os(macOS)
import AppKit
#endif

/// Web `Tooltip.svelte` placement. The bubble flips to the opposite side when the window has no room.
public enum InkuTooltipPlacement: Sendable {
    case top, bottom, left, right
}

private struct InkuTooltipsCoveredKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// Set on a layer that a full-window overlay (library, settings, presentation) covers. A disabled control there
    /// follows the pointer through AppKit, which does not know the overlay is on top, so its bubble is held back.
    var inkuTooltipsCovered: Bool {
        get { self[InkuTooltipsCoveredKey.self] }
        set { self[InkuTooltipsCoveredKey.self] = newValue }
    }
}

extension View {
    /// Web `Tooltip.svelte`: the bubble fades in over 0.12 s as soon as the pointer enters, also for keyboard
    /// focus (`:focus-visible`, not a click), and also over a control that is disabled — apply it after
    /// `.disabled` so the reason shows. Empty text shows nothing; `DisplaySettings.tooltip` returns "" while
    /// tooltips are off, which is how the rail switch hides every bubble (`.tooltips-disabled .tooltip-bubble`).
    /// Items inside a `Menu` keep `.help`: AppKit draws those as menu item tool tips.
    public func inkuTooltip(_ text: String, placement: InkuTooltipPlacement = .top, wide: Bool = false) -> some View {
        modifier(InkuTooltipModifier(text: text, placement: placement, wide: wide))
    }
}

/// Where the bubble goes, apart from AppKit so it can be checked.
public enum InkuTooltipLayout {
    public struct Placement: Equatable, Sendable {
        public var frame: CGRect
        public var arrowEdge: Edge
        public var arrowOffset: CGFloat
    }

    /// Web `.tooltip-bubble`: 8px from the element, centred on it, flipped when the preferred side has no room,
    /// and kept inside the window. `size` includes the arrow on its side.
    public static func place(size: CGSize, anchor: CGRect, bounds: CGRect, placement: InkuTooltipPlacement, gap: CGFloat) -> Placement {
        func clamp(_ value: CGFloat, _ low: CGFloat, _ high: CGFloat) -> CGFloat { max(low, min(value, max(low, high))) }
        switch placement {
        case .top, .bottom:
            let roomAbove = bounds.maxY - (anchor.maxY + gap) >= size.height
            let roomBelow = (anchor.minY - gap) - bounds.minY >= size.height
            let above = placement == .top ? (roomAbove || !roomBelow) : (!roomBelow && roomAbove)
            let x = clamp(anchor.midX - size.width / 2, bounds.minX, bounds.maxX - size.width)
            let y = above ? anchor.maxY + gap : anchor.minY - gap - size.height
            // The arrow keeps pointing at the element when the bubble is pushed sideways.
            let offset = clamp(anchor.midX - x, 10, size.width - 10)
            return Placement(frame: CGRect(x: x, y: y, width: size.width, height: size.height),
                             arrowEdge: above ? .bottom : .top, arrowOffset: offset)
        case .left, .right:
            let roomRight = bounds.maxX - (anchor.maxX + gap) >= size.width
            let roomLeft = (anchor.minX - gap) - bounds.minX >= size.width
            let right = placement == .right ? (roomRight || !roomLeft) : (!roomLeft && roomRight)
            let x = right ? anchor.maxX + gap : anchor.minX - gap - size.width
            let y = clamp(anchor.midY - size.height / 2, bounds.minY, bounds.maxY - size.height)
            let offset = clamp((y + size.height) - anchor.midY, 10, size.height - 10)
            return Placement(frame: CGRect(x: x, y: y, width: size.width, height: size.height),
                             arrowEdge: right ? .leading : .trailing, arrowOffset: offset)
        }
    }
}

#if os(macOS)
private struct InkuTooltipModifier: ViewModifier {
    let text: String
    let placement: InkuTooltipPlacement
    let wide: Bool
    @Environment(\.inkuTextScale) private var scale
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.inkuTooltipsCovered) private var covered
    @State private var token = InkuTooltipToken()
    @FocusState private var focused: Bool

    func body(content: Content) -> some View {
        content
            .onHover { token.overContent = $0; sync() }
            .background {
                ZStack {
                    // Disabled from outside (`.inkuTooltip(…).disabled(…)`), SwiftUI may report no hover at all,
                    // so the anchor tracks the pointer itself.
                    InkuTooltipAnchor(token: token, tracksPointer: !isEnabled) { token.overTracked = $0; sync() }
                    // Disabled inside (`.disabled(…).inkuTooltip(…)`), the control takes no hover of its own and
                    // this shape behind it does, so the reason shows.
                    Color.clear.contentShape(Rectangle()).onHover { token.overBackground = $0; sync() }
                }
            }
            .focused($focused)
            .accessibilityHint(text)
            .onChange(of: focused) { _, now in
                // `:focus-visible`: focus that arrives with a key, not the focus a click leaves behind.
                token.focusVisible = now && NSApp.currentEvent?.type == .keyDown
                sync()
            }
            .onChange(of: text) { sync() }
            .onChange(of: colorScheme) { sync() }
            .onChange(of: covered) { sync() }
            .onDisappear { InkuTooltipPresenter.shared.deactivate(token) }
    }

    private func sync() {
        token.text = text
        token.placement = placement
        token.wide = wide
        token.scale = scale
        token.dark = colorScheme == .dark
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

    private func present() {
        guard let token = engaged.last(where: { !$0.text.isEmpty && $0.view?.window != nil }),
              let view = token.view, let window = view.window, window.isVisible,
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
#else
private struct InkuTooltipModifier: ViewModifier {
    let text: String
    let placement: InkuTooltipPlacement
    let wide: Bool
    func body(content: Content) -> some View { content.inkuTooltip(text) }
}
#endif
