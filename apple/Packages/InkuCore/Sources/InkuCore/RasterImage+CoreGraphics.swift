import CoreGraphics
import Foundation

extension RasterImage {
    /// The provider retains the core's immutable allocation for the image lifetime.
    public func makeCGImage() -> CGImage? {
        DisplayPixels.makeCGImage(image)
    }
}
