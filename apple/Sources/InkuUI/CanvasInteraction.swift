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

    /// The fitted picture at 100%: the picture's proportion fitted into `container` and centered there.
    public static func fittedPicture(aspect: CGFloat, in container: CGRect) -> CGRect {
        guard aspect.isFinite, aspect > 0, container.width > 0, container.height > 0 else { return container }
        let width = min(container.width, container.height * aspect)
        let height = width / aspect
        return CGRect(x: container.midX - width / 2, y: container.midY - height / 2, width: width, height: height)
    }

    /// Where the picture stands on screen: scaled about the canvas center, then moved by the pan offset.
    public static func zoomedPicture(_ picture: CGRect, area: CGSize, scale: CGFloat, offset: CGSize) -> CGRect {
        let center = CGPoint(x: area.width / 2, y: area.height / 2)
        return CGRect(x: center.x + (picture.minX - center.x) * scale + offset.width,
                      y: center.y + (picture.minY - center.y) * scale + offset.height,
                      width: picture.width * scale, height: picture.height * scale)
    }

    /// The visible window of a zoomed picture, to be drawn from the SVG at the screen's own density instead of
    /// enlarging the fitted frame. Nil at 100% or below, where the fitted frame already has that density.
    /// The pixel counts stay inside the core's region limits; past them the density is lowered, never the window.
    public static func detailPlan(picture: CGRect, area: CGSize, scale: CGFloat, offset: CGSize,
                                  pixelScale: CGFloat) -> CanvasDetailPlan? {
        guard scale > 1.001, pixelScale > 0, picture.width > 0, picture.height > 0 else { return nil }
        let zoomed = zoomedPicture(picture, area: area, scale: scale, offset: offset)
        let visible = zoomed.intersection(CGRect(origin: .zero, size: area))
        guard !visible.isNull, visible.width >= 1, visible.height >= 1 else { return nil }
        var density = pixelScale
        density *= min(1, sqrt(144_000_000 / (zoomed.width * density * zoomed.height * density)))
        density *= min(1, 120_000 / (max(zoomed.width, zoomed.height) * density))
        density *= min(1, sqrt(16_000_000 / (visible.width * density * visible.height * density)))
        density *= min(1, 8_000 / (max(visible.width, visible.height) * density))
        let fullWidth = max(1, (zoomed.width * density).rounded()), fullHeight = max(1, (zoomed.height * density).rounded())
        let left = min(fullWidth - 1, max(0, ((visible.minX - zoomed.minX) * density).rounded(.down)))
        let top = min(fullHeight - 1, max(0, ((visible.minY - zoomed.minY) * density).rounded(.down)))
        let right = max(left + 1, min(fullWidth, ((visible.maxX - zoomed.minX) * density).rounded(.up)))
        let bottom = max(top + 1, min(fullHeight, ((visible.maxY - zoomed.minY) * density).rounded(.up)))
        return CanvasDetailPlan(fullWidth: UInt32(fullWidth), fullHeight: UInt32(fullHeight),
                                x: UInt32(left), y: UInt32(top), width: UInt32(right - left), height: UInt32(bottom - top),
                                unit: CGRect(x: left / fullWidth, y: top / fullHeight,
                                             width: (right - left) / fullWidth, height: (bottom - top) / fullHeight))
    }

    public static func supportsVerticalCaption(_ text: String) -> Bool {
        text.unicodeScalars.contains { (0x3040...0x30FF).contains($0.value) || (0x3400...0x9FFF).contains($0.value) }
    }
}

/// A window of the picture in the pixels of the whole picture at one zoom.
public struct CanvasDetailPlan: Hashable, Sendable {
    public let fullWidth: UInt32, fullHeight: UInt32
    public let x: UInt32, y: UInt32, width: UInt32, height: UInt32
    /// The window as a fraction of the picture, so a finished window stays in place under a later zoom or pan.
    public let unit: CGRect
}
