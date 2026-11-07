import SwiftUI

/// Web `Tooltip.svelte` placement. The bubble flips to the opposite side when the window has no room.
public enum InkuTooltipPlacement: Sendable {
    case top, bottom, left, right
}

/// How keyboard focus can reach what a tooltip describes, for the `:focus-visible` bubble.
public enum InkuTooltipFocus: Sendable {
    /// A control: focusable from the keyboard only while Full Keyboard Access is on.
    case control
    /// A text input, focusable with Tab either way.
    case text
    /// Text, an image or a mark: never focused, so no focus binding.
    case none
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
    public func inkuTooltip(_ text: String, placement: InkuTooltipPlacement = .top, wide: Bool = false,
                            focus: InkuTooltipFocus = .control) -> some View {
        modifier(InkuTooltipModifier(text: text, placement: placement, wide: wide, focus: focus))
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

