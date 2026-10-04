import CoreGraphics

public enum CanvasInteraction {
    public static let minimumScale: CGFloat = 0.25
    public static let maximumScale: CGFloat = 10

    public static func boundedScale(_ value: CGFloat) -> CGFloat { min(maximumScale, max(minimumScale, value)) }

    public static func wheelScale(from scale: CGFloat, deltaY: CGFloat) -> CGFloat {
        guard deltaY != 0 else { return scale }
        return boundedScale(scale + (deltaY > 0 ? 0.15 : -0.15))
    }

    public static func offset(for scale: CGFloat, current: CGSize) -> CGSize { scale <= 1 ? .zero : current }
}
