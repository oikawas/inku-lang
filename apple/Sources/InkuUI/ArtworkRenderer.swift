import CoreGraphics
import CryptoKit
import Foundation
import InkuCore

public actor ArtworkRenderer {
    private struct Entry {
        let image: CGImage
        let bytes: Int
        var use: UInt64
    }
    private var entries: [String: Entry] = [:]
    private var clock: UInt64 = 0
    private var retainedBytes = 0
    private let byteLimit: Int

    public init(byteLimit: Int = 64 * 1024 * 1024) { self.byteLimit = byteLimit }

    public func image(svg: String, targetWidth: UInt32, targetHeight: UInt32? = nil) throws -> CGImage {
        let digest = SHA256.hash(data: Data(svg.utf8)).map { String(format: "%02x", $0) }.joined()
        let key = "\(InkuCore.rasterAPIVersion):\(digest):\(targetWidth):\(targetHeight ?? 0):srgb"
        clock &+= 1
        if var cached = entries[key] {
            cached.use = clock
            entries[key] = cached
            return cached.image
        }
        let raster = try InkuCore.rasterize(svg: svg, targetWidth: targetWidth, targetHeight: targetHeight)
        guard let image = raster.makeCGImage() else {
            throw ArtworkError.imageUnavailable
        }
        let bytes = raster.pixels.count
        while retainedBytes + bytes > byteLimit,
              let oldest = entries.min(by: { $0.value.use < $1.value.use }) {
            retainedBytes -= oldest.value.bytes
            entries.removeValue(forKey: oldest.key)
        }
        if bytes <= byteLimit {
            entries[key] = Entry(image: image, bytes: bytes, use: clock)
            retainedBytes += bytes
        }
        return image
    }

    public func purge() {
        entries.removeAll()
        retainedBytes = 0
    }
}

public enum ArtworkError: Error {
    case imageUnavailable
}
