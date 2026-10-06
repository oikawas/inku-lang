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

    /// Web CanvasPanel.svelte:567-569,587-598: a 400px base in the canvas proportion (width / height), fitted with
    /// `min((W − 120) / base W, (H − 96) / base H)` within 0.25–10 and rounded to hundredths. The area has no outer margin.
    public static func webFit(area: CGSize, ratio: CGFloat) -> (box: CGSize, zoom: CGFloat) {
        let ratio = ratio.isFinite && ratio > 0 ? max(0.05, ratio) : 1
        let base = ratio >= 1 ? CGSize(width: 400, height: 400 / ratio) : CGSize(width: 400 * ratio, height: 400)
        let available = CGSize(width: max(120, area.width - 120), height: max(120, area.height - 96))
        let zoom = (max(0.25, min(10, min(available.width / base.width, available.height / base.height))) * 100).rounded() / 100
        return (CGSize(width: base.width * zoom, height: base.height * zoom), zoom)
    }

    public static func supportsVerticalCaption(_ text: String) -> Bool {
        text.unicodeScalars.contains { (0x3040...0x30FF).contains($0.value) || (0x3400...0x9FFF).contains($0.value) }
    }
}
