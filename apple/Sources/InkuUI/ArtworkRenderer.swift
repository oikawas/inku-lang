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
    private struct SceneEntry {
        let scene: PreparedSVG
        let cost: UInt64
        var use: UInt64
    }
    public struct CacheStatistics: Sendable {
        public let imageCount: Int
        public let imageBytes: Int
        public let sceneCount: Int
        public let sceneCostBytes: UInt64
        public let imageHits: UInt64
        public let sceneHits: UInt64
        public let scenePreparations: UInt64
    }
    private var entries: [String: Entry] = [:]
    private var scenes: [String: SceneEntry] = [:]
    private var clock: UInt64 = 0
    private var retainedBytes = 0
    private var retainedSceneCost: UInt64 = 0
    private var imageHits: UInt64 = 0
    private var sceneHits: UInt64 = 0
    private var scenePreparations: UInt64 = 0
    private let byteLimit: Int
    private let sceneCostLimit: UInt64
    private let sceneCountLimit: Int
    private let imageCountLimit: Int

    public init(byteLimit: Int = 64 * 1024 * 1024, sceneCostLimit: UInt64 = 16 * 1024 * 1024,
                sceneCountLimit: Int = 8, imageCountLimit: Int = 256) {
        self.byteLimit = max(0, byteLimit); self.sceneCostLimit = sceneCostLimit
        self.sceneCountLimit = max(0, sceneCountLimit); self.imageCountLimit = max(0, imageCountLimit)
    }

    public func image(svg: String, targetWidth: UInt32, targetHeight: UInt32? = nil) throws -> CGImage {
        try Task.checkCancellation()
        let digest = SHA256.hash(data: Data(svg.utf8)).map { String(format: "%02x", $0) }.joined()
        let key = "\(InkuCore.rasterAPIVersion):\(digest):\(targetWidth):\(targetHeight ?? 0):srgb"
        clock &+= 1
        if var cached = entries[key] {
            try Task.checkCancellation()
            cached.use = clock
            entries[key] = cached
            imageHits &+= 1
            if var scene = scenes[digest] { scene.use = clock; scenes[digest] = scene }
            return cached.image
        }
        let scene: PreparedSVG
        if var cached = scenes[digest] {
            cached.use = clock; scenes[digest] = cached; scene = cached.scene; sceneHits &+= 1
        } else {
            scene = try InkuCore.prepareSVG(svg: svg)
            scenePreparations &+= 1
            try Task.checkCancellation()
            let cost = scene.cacheCostBytes
            if cost <= sceneCostLimit, sceneCountLimit > 0 {
                while cost > sceneCostLimit - retainedSceneCost || scenes.count >= sceneCountLimit {
                    guard let oldest = scenes.min(by: { $0.value.use < $1.value.use }) else { break }
                    retainedSceneCost -= oldest.value.cost; scenes.removeValue(forKey: oldest.key)
                }
                scenes[digest] = SceneEntry(scene: scene, cost: cost, use: clock); retainedSceneCost += cost
            }
        }
        let raster = try scene.rasterize(targetWidth: targetWidth, targetHeight: targetHeight)
        // A synchronous Rust frame can finish after its Swift caller was cancelled.
        try Task.checkCancellation()
        guard let image = raster.makeCGImage() else {
            throw ArtworkError.imageUnavailable
        }
        let bytes = raster.pixels.count
        if bytes <= byteLimit, imageCountLimit > 0 {
            while (retainedBytes + bytes > byteLimit || entries.count >= imageCountLimit),
                  let oldest = entries.min(by: { $0.value.use < $1.value.use }) {
                retainedBytes -= oldest.value.bytes
                entries.removeValue(forKey: oldest.key)
            }
            entries[key] = Entry(image: image, bytes: bytes, use: clock)
            retainedBytes += bytes
        }
        return image
    }

    public func purge() {
        entries.removeAll()
        scenes.removeAll()
        retainedBytes = 0
        retainedSceneCost = 0
    }

    public func cacheStatistics() -> CacheStatistics {
        CacheStatistics(imageCount: entries.count, imageBytes: retainedBytes, sceneCount: scenes.count,
                        sceneCostBytes: retainedSceneCost, imageHits: imageHits, sceneHits: sceneHits, scenePreparations: scenePreparations)
    }
}

public enum ArtworkError: Error {
    case imageUnavailable
}
