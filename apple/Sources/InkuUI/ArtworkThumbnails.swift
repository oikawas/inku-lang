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
    /// Stored PNGs decoded at once for the screen. A page asks for all its cards together; more decodes than this
    /// only finish later together, and a page left early would still run them all.
    public static let displayDecoders = 4
    /// Of those, the most a prefetch may hold, so a turn's own reads start at once.
    static let prefetchDecoders = 2
    /// Two pages of decoded 512px thumbnails (about 1 MB each) besides the history strip and the lineage, so the
    /// next page can wait in memory without pushing out the page on screen.
    public static let defaultByteLimit = 160 * 1024 * 1024

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
        /// Decoded ahead for the next page and kept in memory.
        public var prefetched = 0
    }

    /// One read shared by every view that shows the same work; the last view to stop waiting cancels it.
    private struct Load {
        let task: Task<CGImage, Error>
        let token: UUID
        var waiters: Int
    }

    private var store: ThumbnailStore?
    private var database: InkuDatabase?
    private nonisolated let memory: ThumbnailMemoryCache
    private var inFlight: [String: Load] = [:]
    private struct BackgroundLoad {
        let token: UUID
        let task: Task<Void, Never>
        var waiters: Int
    }
    private var backgroundInFlight: [String: BackgroundLoad] = [:]
    private var decoding = 0
    private struct DecoderWaiter {
        let id: UUID
        let continuation: CheckedContinuation<Bool, Never>
    }
    private var displayWaiters: [DecoderWaiter] = []
    private var prefetchWaiters: [DecoderWaiter] = []
    private var prefetchTask: Task<Void, Never>?
    private var pass: Task<Void, Never>?
    private var generation: UInt64 = 0
    private var statistics = Statistics()
    private let display = DispatchQueue(label: "app.inku.thumbnails", qos: .userInitiated, attributes: .concurrent)
    private let background = DispatchQueue(label: "app.inku.thumbnails.bake", qos: .utility, attributes: .concurrent)
    private let backgroundBaker: (@Sendable (String) async throws -> (CGImage, Data))?

    public init(byteLimit: Int = ArtworkThumbnails.defaultByteLimit) {
        memory = ThumbnailMemoryCache(byteLimit: max(0, byteLimit))
        backgroundBaker = nil
    }
    init(backgroundBaker: @escaping @Sendable (String) async throws -> (CGImage, Data)) {
        memory = ThumbnailMemoryCache(byteLimit: Self.defaultByteLimit)
        self.backgroundBaker = backgroundBaker
    }

    /// Without a store, thumbnails are drawn and kept in memory only.
    public func connect(store: ThumbnailStore?, database: InkuDatabase) async {
        self.store = store
        self.database = database
        generation = await store?.currentWriteGeneration() ?? 0
    }

    public func image(for work: SavedWork) async throws -> CGImage {
        let key = Self.key(work.id, work.renderHash)
        if let image = memory.image(for: key) {
            statistics.memoryHits += 1
            return image
        }
        // A visible request must not wait for an already running background bake.
        backgroundInFlight[key]?.task.cancel()
        let load: Load
        if var running = inFlight[key], !running.task.isCancelled {
            running.waiters += 1
            inFlight[key] = running
            load = running
        } else {
            let (id, svg, renderHash) = (work.id, work.svg, work.renderHash)
            let token = UUID()
            load = Load(task: Task { try await self.load(id: id, svg: svg, renderHash: renderHash, key: key, token: token) },
                        token: token, waiters: 1)
            inFlight[key] = load
            statistics.loadsInFlight = inFlight.count
        }
        let token = load.token
        return try await withTaskCancellationHandler {
            try await load.task.value
        } onCancel: {
            Task { await self.leave(key: key, token: token) }
        }
    }

    /// A view stopped waiting (its card now shows another work); the last one to go stops the read and its decode.
    private func leave(key: String, token: UUID) {
        guard var load = inFlight[key], load.token == token else { return }
        load.waiters -= 1
        inFlight[key] = load
        if load.waiters <= 0 { load.task.cancel() }
    }

    /// Decodes the stored PNGs of the works the next page turn will show, into memory and behind the screen's own
    /// reads. The works on screen now (`keeping`) are never pushed out for them. A newer prefetch replaces this one.
    public func prefetch(_ works: [SavedWork], keeping shown: [SavedWork]) {
        prefetchTask?.cancel()
        let protected = Set(shown.map { Self.key($0.id, $0.renderHash) })
        let targets = works.filter { !memory.contains(Self.key($0.id, $0.renderHash)) }
        guard store != nil, !targets.isEmpty else { prefetchTask = nil; return }
        prefetchTask = Task(priority: .utility) { await self.runPrefetch(targets, protecting: protected) }
    }

    /// Waits for the current prefetch. For checks.
    public func prefetchFinished() async { await prefetchTask?.value }

    private func runPrefetch(_ works: [SavedWork], protecting protected: Set<String>) async {
        // Entries the screen uses from here on are its own and stay too.
        let since = memory.currentUse()
        await withTaskGroup(of: Void.self) { group in
            var running = 0
            for work in works {
                if Task.isCancelled { break }
                if running == Self.prefetchDecoders { await group.next(); running -= 1 }
                group.addTask { await self.prefetchOne(work, protecting: protected, since: since) }
                running += 1
            }
        }
    }

    private func prefetchOne(_ work: SavedWork, protecting protected: Set<String>, since: UInt64) async {
        let requestedGeneration = generation
        let key = Self.key(work.id, work.renderHash)
        // The screen's reads go first, the store's included.
        while !inFlight.isEmpty, !Task.isCancelled { try? await Task.sleep(for: .milliseconds(15)) }
        guard !Task.isCancelled, !memory.contains(key), let store,
              let stored = try? await store.thumbnail(historyID: work.id, scale: Self.scale),
              stored.sourceRenderHash == work.renderHash, !Task.isCancelled,
              let image = try? await decodeLimited(stored.png, prefetch: true), !Task.isCancelled,
              generation == requestedGeneration else { return }
        if memory.insert(image, for: key, protecting: protected, usedAfter: since) { statistics.prefetched += 1 }
    }

    func acquireDecoder(prefetch: Bool) async throws {
        let id = UUID()
        let acquired = await withTaskCancellationHandler {
            if Task.isCancelled { return false }
            if prefetch {
                if decoding < Self.prefetchDecoders, displayWaiters.isEmpty { decoding += 1; return true }
                return await withCheckedContinuation { prefetchWaiters.append(DecoderWaiter(id: id, continuation: $0)) }
            } else {
                if decoding < Self.displayDecoders { decoding += 1; return true }
                return await withCheckedContinuation { displayWaiters.append(DecoderWaiter(id: id, continuation: $0)) }
            }
        } onCancel: {
            Task { await self.cancelDecoderWaiter(id) }
        }
        guard acquired else { throw CancellationError() }
        if Task.isCancelled { releaseDecoder(); throw CancellationError() }
    }

    private func cancelDecoderWaiter(_ id: UUID) {
        if let index = displayWaiters.firstIndex(where: { $0.id == id }) {
            displayWaiters.remove(at: index).continuation.resume(returning: false)
        } else if let index = prefetchWaiters.firstIndex(where: { $0.id == id }) {
            prefetchWaiters.remove(at: index).continuation.resume(returning: false)
        }
    }
    func decoderWaiterCountForChecks() -> Int { displayWaiters.count + prefetchWaiters.count }

    /// Hands the slot to the screen's next decode, then to a prefetch while few run, else frees it.
    func releaseDecoder() {
        if !displayWaiters.isEmpty { displayWaiters.removeFirst().continuation.resume(returning: true); return }
        if !prefetchWaiters.isEmpty, decoding - 1 < Self.prefetchDecoders { prefetchWaiters.removeFirst().continuation.resume(returning: true); return }
        decoding -= 1
    }

    private func decodeLimited(_ png: Data, prefetch: Bool) async throws -> CGImage? {
        try await acquireDecoder(prefetch: prefetch)
        defer { releaseDecoder() }
        try Task.checkCancellation()
        statistics.decodesInFlight += 1
        statistics.maxDecodesInFlight = max(statistics.maxDecodesInFlight, statistics.decodesInFlight)
        defer { statistics.decodesInFlight -= 1 }
        return await Self.decode(png, on: prefetch ? background : display)
    }

    private func bakeLimited(_ svg: String) async throws -> (CGImage, Data) {
        try await acquireDecoder(prefetch: false)
        defer { releaseDecoder() }
        try Task.checkCancellation()
        return try await Self.bake(svg: svg, on: display)
    }

    /// Like Web's cached PNG, a decoded image is available at presentation time without an
    /// actor/task round trip. This only reads memory; a miss does no I/O or rasterization.
    public nonisolated func cachedImage(for work: SavedWork) -> CGImage? {
        memory.image(for: Self.key(work.id, work.renderHash))
    }

    /// Bakes a work just saved, off the caller's path.
    public func bakeSaved(_ work: SavedWork) {
        _ = startSavedBake(work)
    }
    func startSavedBake(_ work: SavedWork) -> Task<Void, Never> {
        let (id, svg, renderHash) = (work.id, work.svg, work.renderHash)
        let requestedGeneration = generation
        return Task(priority: .utility) { await self.bakeAndStore(id: id, svg: svg, renderHash: renderHash, generation: requestedGeneration) }
    }

    /// Starts the launch pass: drop the thumbnails of works that no longer exist, then bake every
    /// work with no thumbnail or one baked from another SVG (Server `start_rebuild`). A pass already
    /// running is replaced, as after a restore.
    public func synchronize() async {
        generation &+= 1
        let requestedGeneration = generation
        pass?.cancel()
        prefetchTask?.cancel()
        for load in inFlight.values { load.task.cancel() }
        for load in backgroundInFlight.values { load.task.cancel() }
        inFlight.removeAll()
        backgroundInFlight.removeAll()
        statistics.loadsInFlight = 0
        memory.removeAll()
        await store?.advanceWriteGeneration(to: requestedGeneration)
        guard generation == requestedGeneration else { return }
        pass = Task(priority: .utility) { await self.runPass(generation: requestedGeneration) }
    }

    /// Waits for the current launch pass. For checks.
    public func passFinished() async { await pass?.value }

    /// Drops the thumbnails of works that are no longer stored (Server `prune_orphans`).
    @discardableResult
    public func pruneOrphans() async -> Int {
        guard let store, let database else { return 0 }
        let requestedGeneration = generation
        do {
            // The stored ids are read before the works: a work saved in between is either missing
            // from the first read or present in the second.
            let stored = try await store.storedIDs()
            guard !stored.isEmpty else { return 0 }
            let live = Set(try await database.thumbnailSources().map(\.id))
            let orphans = stored.subtracting(live).sorted()
            guard generation == requestedGeneration, !Task.isCancelled else { return 0 }
            let count = try await store.deleteIfCurrent(historyIDs: orphans, generation: requestedGeneration)
            guard generation == requestedGeneration, !Task.isCancelled else { return 0 }
            memory.remove(historyIDs: Set(orphans))
            statistics.pruned += count
            return count
        } catch { return 0 }
    }

    public func currentStatistics() -> Statistics { statistics }

    /// Starts the decode peak again from what is running now. For checks.
    public func resetPeaks() { statistics.maxDecodesInFlight = statistics.decodesInFlight }

    private func runPass(generation requestedGeneration: UInt64) async {
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
                    group.addTask { await self.bakeAndStore(id: work.id, svg: svg, renderHash: work.renderHash, generation: requestedGeneration) }
                    running += 1
                }
            }
        }
    }

    private func bakeAndStore(id: String, svg: String, renderHash: String?, generation requestedGeneration: UInt64) async {
        // A work being drawn for the screen is stored by that drawing.
        let key = Self.key(id, renderHash)
        guard generation == requestedGeneration, inFlight[key] == nil else { return }
        if var existing = backgroundInFlight[key] {
            existing.waiters += 1
            backgroundInFlight[key] = existing
            await existing.task.value
            return
        }
        let token = UUID()
        let task = Task { await self.performBackgroundBake(id: id, svg: svg, renderHash: renderHash, generation: requestedGeneration) }
        backgroundInFlight[key] = BackgroundLoad(token: token, task: task, waiters: 1)
        await task.value
        if backgroundInFlight[key]?.token == token { backgroundInFlight[key] = nil }
    }

    func backgroundWaiterCountForChecks(id: String, renderHash: String?) -> Int {
        backgroundInFlight[Self.key(id, renderHash)]?.waiters ?? 0
    }

    private func performBackgroundBake(id: String, svg: String, renderHash: String?, generation requestedGeneration: UInt64) async {
        do {
            try Task.checkCancellation()
            let baked: (CGImage, Data)
            if let backgroundBaker { baked = try await backgroundBaker(svg) }
            else { baked = try await Self.bake(svg: svg, on: background) }
            let png = baked.1
            try Task.checkCancellation()
            guard generation == requestedGeneration else { return }
            guard try await store?.putIfCurrent(historyID: id, scale: Self.scale, png: png, sourceRenderHash: renderHash,
                                                generation: requestedGeneration) == true else { return }
            statistics.bakedInBackground += 1
        } catch is CancellationError {
            // A newer visible request or restore superseded this bake.
        } catch {
            statistics.failed += 1
        }
    }

    private func load(id: String, svg: String, renderHash: String?, key: String, token: UUID) async throws -> CGImage {
        let requestedGeneration = generation
        defer {
            if inFlight[key]?.token == token { inFlight[key] = nil }
            statistics.loadsInFlight = inFlight.count
        }
        try Task.checkCancellation()
        if let store, let stored = try? await store.thumbnail(historyID: id, scale: Self.scale),
           stored.sourceRenderHash == renderHash, let image = try await decodeLimited(stored.png, prefetch: false) {
            try Task.checkCancellation()
            guard generation == requestedGeneration else { throw CancellationError() }
            statistics.storeHits += 1
            memory.insert(image, for: key)
            return image
        }
        do {
            // A library list deliberately carries no SVG, as Server's include_svg=false does.
            // Read exactly this drawing only if its persisted PNG is missing or stale.
            let source: String
            if !svg.isEmpty { source = svg }
            else if let database, let storedSVG = try await database.svgs(ids: [id])[id] { source = storedSVG }
            else { throw ArtworkError.imageUnavailable }
            let (image, png) = try await bakeLimited(source)
            try Task.checkCancellation()
            guard generation == requestedGeneration else { throw CancellationError() }
            statistics.bakedOnDisplay += 1
            _ = try? await store?.putIfCurrent(historyID: id, scale: Self.scale, png: png, sourceRenderHash: renderHash,
                                               generation: requestedGeneration)
            try Task.checkCancellation()
            guard generation == requestedGeneration else { throw CancellationError() }
            memory.insert(image, for: key)
            return image
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            statistics.failed += 1
            throw error
        }
    }

    private nonisolated static func key(_ id: String, _ renderHash: String?) -> String { id + "\u{0}" + (renderHash ?? "") }

    /// Rasterizing is a synchronous Rust call, so it runs on a dispatch queue, not on Swift's shared pool.
    private static func bake(svg: String, on queue: DispatchQueue) async throws -> (CGImage, Data) {
        let cancellation = ThumbnailCancellation()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async {
                    continuation.resume(with: Result {
                        try cancellation.check()
                        let raster = try InkuCore.rasterize(svg: svg, targetWidth: width)
                        try cancellation.check()
                        guard let image = raster.makeCGImage() else { throw ArtworkError.imageUnavailable }
                        let data = NSMutableData()
                        guard let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil) else {
                            throw ArtworkError.imageUnavailable
                        }
                        CGImageDestinationAddImage(destination, image, nil)
                        try cancellation.check()
                        guard CGImageDestinationFinalize(destination) else { throw ArtworkError.imageUnavailable }
                        return (image, data as Data)
                    })
                }
            }
        } onCancel: { cancellation.cancel() }
    }

    private final class ThumbnailCancellation: @unchecked Sendable {
        private let lock = NSLock()
        private var cancelled = false
        func cancel() { lock.lock(); cancelled = true; lock.unlock() }
        func check() throws {
            lock.lock(); let value = cancelled; lock.unlock()
            if value { throw CancellationError() }
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

    /// Without counting as a use.
    func contains(_ key: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        return images[key] != nil
    }

    func currentUse() -> UInt64 {
        lock.lock(); defer { lock.unlock() }
        return clock
    }

    /// Makes room by dropping the least recently used images. A prefetch passes what must stay: the keys on screen
    /// and anything used after `usedAfter`; if the rest cannot make room, nothing is dropped and nothing kept.
    @discardableResult
    func insert(_ image: CGImage, for key: String, protecting protected: Set<String> = [], usedAfter: UInt64 = .max) -> Bool {
        let bytes = image.bytesPerRow * image.height
        guard bytes <= byteLimit else { return false }
        lock.lock(); defer { lock.unlock() }
        let previous = images[key]?.bytes ?? 0
        if retainedBytes - previous + bytes > byteLimit {
            let candidates = images.filter { $0.key != key && !protected.contains($0.key) && $0.value.use <= usedAfter }
                .sorted { $0.value.use < $1.value.use }
            var freed = 0
            var victims: [String] = []
            for (candidate, entry) in candidates where retainedBytes - previous - freed + bytes > byteLimit {
                victims.append(candidate)
                freed += entry.bytes
            }
            guard retainedBytes - previous - freed + bytes <= byteLimit else { return false }
            for victim in victims { images.removeValue(forKey: victim) }
            retainedBytes -= freed
        }
        if let old = images.removeValue(forKey: key) { retainedBytes -= old.bytes }
        clock &+= 1
        images[key] = Entry(image: image, bytes: bytes, use: clock)
        retainedBytes += bytes
        return true
    }

    func remove(historyIDs: Set<String>) {
        lock.lock(); defer { lock.unlock() }
        for key in images.keys where historyIDs.contains(String(key.prefix(while: { $0 != "\u{0}" }))) {
            if let entry = images.removeValue(forKey: key) { retainedBytes -= entry.bytes }
        }
    }

    func removeAll() {
        lock.lock(); defer { lock.unlock() }
        images.removeAll()
        retainedBytes = 0
    }
}
