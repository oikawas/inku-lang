import CoreGraphics
import Foundation

extension RasterImage {
    /// CoreGraphics retains the CFData-backed provider for the image lifetime.
    public func makeCGImage() -> CGImage? {
        guard pixelFormat == "rgba8-premultiplied",
              width > 0, height > 0,
              UInt64(stride) == UInt64(width) * 4,
              UInt64(pixels.count) == UInt64(stride) * UInt64(height),
              let provider = CGDataProvider(data: pixels as CFData),
              let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)
        else { return nil }

        return CGImage(
            width: Int(width), height: Int(height),
            bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: Int(stride),
            space: colorSpace,
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue)
                .union(.byteOrder32Big),
            provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent
        )
    }
}
