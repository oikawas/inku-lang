import CoreGraphics
import Foundation
import ImageIO
import InkuCore
import InkuPersistence
import UniformTypeIdentifiers

/// Thumbnails baked once to PNG and kept in the thumbnail store, as Server does (I-718,
/// `api_core/thumbnails.py`). A saved work is baked in the background right after its save; the
/// works already stored are baked in the background after launch; a work shown before either
/// reached it is drawn on the spot and stored. Every bake is resvg, the picture Server keeps.
public actor ArtworkThumbnails {
    /// Server's HiDPI scale: 512px wide, the height following the work.
    public static let scale = 2
    public static let width = UInt32(ThumbnailStore.baseWidth * scale)
    /// Server `INKU_THUMBNAIL_WORKERS` default.
    public static let backgroundWorkers = 4

    public struct Statistics: Sendable, Equatable {
        public var memoryHits = 0
        public var storeHits = 0
        /// Drawn because a shown work had nothing current in the store.
        public var bakedOnDisplay = 0
        /// Drawn after a save or by the launch pass.
        public var bakedInBackground = 0
        public var failed = 0
        public var pruned = 0
        /// Display reads waiting for the store or a decode.
        public var loadsInFlight = 0
        public var decodesInFlight = 0
        /// The most stored PNGs decoded at the same time.
        public var maxDecodesInFlight = 0
    }

    private var store: ThumbnailStore?
    private var database: InkuDatabase?
    private nonisolated let memory: ThumbnailMemoryCache
    private var inFlight: [String: Task<CGImage, Error>] = [:]
    private var pass: Task<Void, Never>?
    private var statistics = Statistics()
    private let display = DispatchQueue(label: "app.inku.thumbnails", qos: .userInitiated, attributes: .concurrent)
    private let background = DispatchQueue(label: "app.inku.thumbnails.bake", qos: .utility, attributes: .concurrent)

    public init(byteLimit: Int = 96 * 1024 * 1024) {
        memory = ThumbnailMemoryCache(byteLimit: max(0, byteLimit))
    }

    /// Without a store, thumbnails are drawn and kept in memory only.
    public func connect(store: ThumbnailStore?, database: InkuDatabase) {
        self.store = store
        self.database = database
    }

    public func image(for work: SavedWork) async throws -> CGImage {
        let key = Self.key(work.id, work.renderHash)
        if let image = memory.image(for: key) {
            statistics.memoryHits += 1
            return image
        }
        if let running = inFlight[key] { return try await running.value }
        let (id, svg, renderHash) = (work.id, work.svg, work.renderHash)
        let task = Task { try await self.load(id: id, svg: svg, renderHash: renderHash) }
        inFlight[key] = task
        statistics.loadsInFlight = inFlight.count
        defer { inFlight[key] = nil; statistics.loadsInFlight = inFlight.count }
        let image = try await task.value
        memory.insert(image, for: key)
        return image
    }

    /// Like Web's cached PNG, a decoded image is available at presentation time without an
    /// actor/task round trip. This only reads memory; a miss does no I/O or rasterization.
    public nonisolated func cachedImage(for work: SavedWork) -> CGImage? {
        memory.image(for: Self.key(work.id, work.renderHash))
    }

    /// Bakes a work just saved, off the caller's path.
    public func bakeSaved(_ work: SavedWork) {
        let (id, svg, renderHash) = (work.id, work.svg, work.renderHash)
        Task(priority: .utility) { await self.bakeAndStore(id: id, svg: svg, renderHash: renderHash) }
    }

    /// Starts the launch pass: drop the thumbnails of works that no longer exist, then bake every
    /// work with no thumbnail or one baked from another SVG (Server `start_rebuild`). A pass already
    /// running is replaced, as after a restore.
    public func synchronize() {
        pass?.cancel()
        pass = Task(priority: .utility) { await self.runPass() }
    }

    /// Waits for the current launch pass. For checks.
    public func passFinished() async { await pass?.value }

    /// Drops the thumbnails of works that are no longer stored (Server `prune_orphans`).
    @discardableResult
    public func pruneOrphans() async -> Int {
        guard let store, let database else { return 0 }
        do {
            // The stored ids are read before the works: a work saved in between is either missing
            // from the first read or present in the second.
            let stored = try await store.storedIDs()
            guard !stored.isEmpty else { return 0 }
            let live = Set(try await database.thumbnailSources().map(\.id))
            let orphans = stored.subtracting(live).sorted()
            let count = try await store.delete(historyIDs: orphans)
            memory.remove(historyIDs: Set(orphans))
            statistics.pruned += count
            return count
        } catch { return 0 }
    }

    public func currentStatistics() -> Statistics { statistics }

    /// Starts the decode peak again from what is running now. For checks.
    public func resetPeaks() { statistics.maxDecodesInFlight = statistics.decodesInFlight }

    private func runPass() async {
        guard let store, let database else { return }
        await pruneOrphans()
        let targets: [(id: String, renderHash: String?)]
        do {
            let stored = try await store.storedHashes(scale: Self.scale)
            targets = try await database.thumbnailSources().filter { work in
                guard let baked = stored[work.id] else { return true }
                return baked != work.renderHash
            }
        } catch { return }
        // Server `_REBUILD_BATCH`: the SVGs are read 32 works at a time.
        for start in stride(from: 0, to: targets.count, by: 32) {
            guard !Task.isCancelled else { return }
            let batch = Array(targets[start..<min(targets.count, start + 32)])
            guard let svgs = try? await database.svgs(ids: batch.map(\.id)) else { return }
            await withTaskGroup(of: Void.self) { group in
                var running = 0
                for work in batch {
                    guard let svg = svgs[work.id] else { continue }
                    if running == Self.backgroundWorkers { await group.next(); running -= 1 }
                    group.addTask { await self.bakeAndStore(id: work.id, svg: svg, renderHash: work.renderHash) }
                    running += 1
                }
            }
        }
    }

    private func bakeAndStore(id: String, svg: String, renderHash: String?) async {
        // A work being drawn for the screen is stored by that drawing.
        guard inFlight[Self.key(id, renderHash)] == nil else { return }
        do {
            let (_, png) = try await Self.bake(svg: svg, on: background)
            try await store?.put(historyID: id, scale: Self.scale, png: png, sourceRenderHash: renderHash)
            statistics.bakedInBackground += 1
        } catch {
            statistics.failed += 1
        }
    }

    private func load(id: String, svg: String, renderHash: String?) async throws -> CGImage {
        if let store, let stored = try? await store.thumbnail(historyID: id, scale: Self.scale),
           stored.sourceRenderHash == renderHash, let image = await countedDecode(stored.png) {
            statistics.storeHits += 1
            return image
        }
        do {
            // A library list deliberately carries no SVG, as Server's include_svg=false does.
            // Read exactly this drawing only if its persisted PNG is missing or stale.
            let source: String
            if !svg.isEmpty { source = svg }
            else if let database, let storedSVG = try await database.svgs(ids: [id])[id] { source = storedSVG }
            else { throw ArtworkError.imageUnavailable }
            let (image, png) = try await Self.bake(svg: source, on: display)
            statistics.bakedOnDisplay += 1
            try? await store?.put(historyID: id, scale: Self.scale, png: png, sourceRenderHash: renderHash)
            return image
        } catch {
            statistics.failed += 1
            throw error
        }
    }

    private func countedDecode(_ png: Data) async -> CGImage? {
        statistics.decodesInFlight += 1
        statistics.maxDecodesInFlight = max(statistics.maxDecodesInFlight, statistics.decodesInFlight)
        defer { statistics.decodesInFlight -= 1 }
        return await Self.decode(png, on: display)
    }

    private nonisolated static func key(_ id: String, _ renderHash: String?) -> String { id + "\u{0}" + (renderHash ?? "") }

    /// Rasterizing is a synchronous Rust call, so it runs on a dispatch queue, not on Swift's shared pool.
    private static func bake(svg: String, on queue: DispatchQueue) async throws -> (CGImage, Data) {
        try await withCheckedThrowingContinuation { continuation in
            queue.async {
                continuation.resume(with: Result {
                    let raster = try InkuCore.rasterize(svg: svg, targetWidth: width)
                    guard let image = raster.makeCGImage() else { throw ArtworkError.imageUnavailable }
                    let data = NSMutableData()
                    guard let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil) else {
                        throw ArtworkError.imageUnavailable
                    }
                    CGImageDestinationAddImage(destination, image, nil)
                    guard CGImageDestinationFinalize(destination) else { throw ArtworkError.imageUnavailable }
                    return (image, data as Data)
                })
            }
        }
    }

    /// Decodes now, off the main thread, rather than at the first draw.
    private static func decode(_ png: Data, on queue: DispatchQueue) async -> CGImage? {
        await withCheckedContinuation { continuation in
            queue.async {
                let source = CGImageSourceCreateWithData(png as CFData, nil)
                let options = [kCGImageSourceShouldCacheImmediately: true] as CFDictionary
                continuation.resume(returning: source.flatMap { CGImageSourceCreateImageAtIndex($0, 0, options) })
            }
        }
    }
}

/// One bounded cache shared by the loading actor and synchronous view lookups. All dictionary,
/// cost and LRU state is protected by the lock; CGImages are immutable once inserted. No I/O,
/// decoding or actor work is performed while holding the lock.
private final class ThumbnailMemoryCache: @unchecked Sendable {
    private struct Entry {
        let image: CGImage
        let bytes: Int
        var use: UInt64
    }
    private let lock = NSLock()
    private let byteLimit: Int
    private var images: [String: Entry] = [:]
    private var retainedBytes = 0
    private var clock: UInt64 = 0

    init(byteLimit: Int) { self.byteLimit = byteLimit }

    func image(for key: String) -> CGImage? {
        lock.lock(); defer { lock.unlock() }
        guard var entry = images[key] else { return nil }
        clock &+= 1
        entry.use = clock
        images[key] = entry
        return entry.image
    }

    func insert(_ image: CGImage, for key: String) {
        let bytes = image.bytesPerRow * image.height
        guard bytes <= byteLimit else { return }
        lock.lock(); defer { lock.unlock() }
        if let previous = images.removeValue(forKey: key) { retainedBytes -= previous.bytes }
        while retainedBytes + bytes > byteLimit, let oldest = images.min(by: { $0.value.use < $1.value.use }) {
            retainedBytes -= oldest.value.bytes
            images.removeValue(forKey: oldest.key)
        }
        clock &+= 1
        images[key] = Entry(image: image, bytes: bytes, use: clock)
        retainedBytes += bytes
    }

    func remove(historyIDs: Set<String>) {
        lock.lock(); defer { lock.unlock() }
        for key in images.keys where historyIDs.contains(String(key.prefix(while: { $0 != "\u{0}" }))) {
            if let entry = images.removeValue(forKey: key) { retainedBytes -= entry.bytes }
        }
    }
}
