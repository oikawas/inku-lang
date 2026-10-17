import CoreGraphics
import InkuCore

public enum CanvasInteraction {
    public static let minimumScale: CGFloat = 0.25
    public static let maximumScale: CGFloat = 10

    public static func boundedScale(_ value: CGFloat) -> CGFloat { min(maximumScale, max(minimumScale, value)) }

    public static func wheelScale(from scale: CGFloat, deltaY: CGFloat) -> CGFloat {
        guard deltaY != 0 else { return scale }
        return boundedScale(scale + (deltaY > 0 ? 0.15 : -0.15))
    }

    /// Keep the same point on the work at the center of the visible area when changing scale.
    public static func offset(from scale: CGFloat, to nextScale: CGFloat, current: CGSize) -> CGSize {
        let ratio = boundedScale(nextScale) / scale
        return CGSize(width: current.width * ratio, height: current.height * ratio)
    }

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

    /// The visible window of a zoomed picture, drawn from the SVG at the screen's own density instead of
    /// enlarging the fitted whole. Nil at 100% or below, where the fitted whole already has that density.
    /// The pixels stay inside the core's window and canvas limits; past them the density is lowered, never the window.
    public static func detailPlan(picture: CGRect, area: CGSize, scale: CGFloat, offset: CGSize,
                                  pixelScale: CGFloat, limits: DisplayLayout) -> CanvasDetailPlan? {
        guard scale > 1.001, pixelScale > 0, picture.width > 0, picture.height > 0 else { return nil }
        let zoomed = zoomedPicture(picture, area: area, scale: scale, offset: offset)
        let visible = zoomed.intersection(CGRect(origin: .zero, size: area))
        guard !visible.isNull, visible.width >= 1, visible.height >= 1 else { return nil }
        // The core limits the density to its window and canvas and rounds outward (shared with Android).
        guard let region = InkuCore.displayDetailRegion(zoomed: zoomed, visible: visible, pixelScale: Double(pixelScale),
                                                        limits: limits) else { return nil }
        return CanvasDetailPlan(fullWidth: region.fullWidth, fullHeight: region.fullHeight,
                                x: region.x, y: region.y, width: region.width, height: region.height)
    }

    public static func supportsVerticalCaption(_ text: String) -> Bool {
        InkuCore.resolveInstructionLanguage(text: text, requested: "auto", fallback: "en") == "ja"
    }
}

/// A window of the picture in the pixels of the whole picture at one zoom.
public struct CanvasDetailPlan: Hashable, Sendable {
    public let fullWidth: UInt32, fullHeight: UInt32
    public let x: UInt32, y: UInt32, width: UInt32, height: UInt32

    public init(fullWidth: UInt32, fullHeight: UInt32, x: UInt32, y: UInt32, width: UInt32, height: UInt32) {
        self.fullWidth = fullWidth; self.fullHeight = fullHeight; self.x = x; self.y = y; self.width = width; self.height = height
    }

    public var region: DisplayRegion {
        DisplayRegion(fullWidth: fullWidth, fullHeight: fullHeight, x: x, y: y, width: width, height: height)
    }

    /// A rectangle of these pixels as a fraction of the picture, so a drawn window stays in place under a later
    /// zoom or pan until its replacement is ready.
    public static func unit(of region: DisplayRegion) -> CGRect {
        let width = CGFloat(region.fullWidth), height = CGFloat(region.fullHeight)
        return CGRect(x: CGFloat(region.x) / width, y: CGFloat(region.y) / height,
                      width: CGFloat(region.width) / width, height: CGFloat(region.height) / height)
    }
}
