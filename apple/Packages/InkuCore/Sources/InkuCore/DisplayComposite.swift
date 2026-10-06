import CoreGraphics
import Foundation
import InkuCoreBindings
import os

/// A window being joined in the core: each tile is drawn and copied there, so tile pixels never
/// cross into Swift. Tiles may be drawn on several threads at once; call `finish` after the last.
public struct DisplayComposite: @unchecked Sendable {
    private let composite: InkuCoreBindings.DisplayComposite
    init(_ composite: InkuCoreBindings.DisplayComposite) { self.composite = composite }

    public func renderTile(_ tile: DisplayRegion) throws {
        do { try composite.renderTile(tile: tile.binding) }
        catch let failure as InkuCoreBindings.DisplayFailure { throw CoreFailure(failure) }
    }

    /// The pixels joined so far, copied once in the core.
    public func snapshot() throws -> CGImage {
        try Self.image { try composite.snapshot() }
    }

    /// The joined pixels themselves, not copied. Later tiles and a second finish are refused.
    public func finish() throws -> CGImage {
        try Self.image { try composite.finish() }
    }

    private static func image(_ body: () throws -> InkuCoreBindings.DisplayImage) throws -> CGImage {
        let pixels: InkuCoreBindings.DisplayImage
        do { pixels = try body() }
        catch let failure as InkuCoreBindings.DisplayFailure { throw CoreFailure(failure) }
        guard let image = DisplayPixels.makeCGImage(pixels) else { throw ImageUnavailable() }
        return image
    }

    /// CoreGraphics could not make the image: a host failure, not one of the core's.
    private struct ImageUnavailable: Error {}
}

/// The bridge from the core's immutable pixel allocation to a `CGImage` without copying it. The
/// provider keeps the core's image object alive until CoreGraphics releases the provider; the
/// address goes nowhere else.
enum DisplayPixels {
    private final class Lease {
        let pixels: InkuCoreBindings.DisplayImage
        init(_ pixels: InkuCoreBindings.DisplayImage) {
            self.pixels = pixels
            DisplayPixels.leases.withLock { $0 += 1 }
        }
        deinit { DisplayPixels.leases.withLock { $0 -= 1 } }
    }

    static let leases = OSAllocatedUnfairLock(initialState: 0)

    static func makeCGImage(_ pixels: InkuCoreBindings.DisplayImage) -> CGImage? {
        let width = Int(pixels.width()), height = Int(pixels.height()), stride = Int(pixels.stride())
        let count = Int(pixels.byteCount())
        guard pixels.pixelFormat() == "rgba8-premultiplied", width > 0, height > 0, stride == width * 4,
              count == stride * height, let address = UnsafeRawPointer(bitPattern: UInt(pixels.pixelBufferAddress())),
              let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        let lease = Unmanaged.passRetained(Lease(pixels)).toOpaque()
        guard let provider = CGDataProvider(dataInfo: lease, data: address, size: count, releaseData: { info, _, _ in
            if let info { Unmanaged<Lease>.fromOpaque(info).release() }
        }) else {
            Unmanaged<Lease>.fromOpaque(lease).release()
            return nil
        }
        // A failed CGImage releases the provider, and the provider releases the lease.
        return CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: stride,
                       space: colorSpace,
                       bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue).union(.byteOrder32Big),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }
}

extension InkuCore {
    /// How many core pixel allocations images still hold. For checks.
    public static var displayPixelLeases: Int { DisplayPixels.leases.withLock { $0 } }

    /// The visible part of a zoomed picture at `pixelScale` pixels per unit, within `limits`.
    /// Both rectangles are in the same units; the host has already intersected them.
    public static func displayDetailRegion(zoomed: CGRect, visible: CGRect, pixelScale: Double,
                                           limits: DisplayLayout) -> DisplayRegion? {
        func rect(_ value: CGRect) -> InkuCoreBindings.DisplayRect {
            InkuCoreBindings.DisplayRect(x: value.minX, y: value.minY, width: value.width, height: value.height)
        }
        return InkuCoreBindings.displayDetailRegion(zoomed: rect(zoomed), visible: rect(visible), pixelScale: pixelScale,
                                                    limits: limits.binding).map(DisplayRegion.init)
    }
}
