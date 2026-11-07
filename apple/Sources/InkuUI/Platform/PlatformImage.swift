import CoreGraphics
import Foundation
import ImageIO

/// Decode the first image without introducing a platform image type into shared views.
enum PlatformImage {
    static func load(data: Data) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }
}
