import CoreGraphics
import CryptoKit
import Foundation
import InkuCore
import os

/// The work area's painter (`ArtworkCanvas`): Skia through the shared core, so the picture
/// matches the Web's. Thumbnails, the saijiki preview and export keep `ArtworkRenderer` (resvg).
///
/// Every request runs on this renderer's own threads, never on Swift's shared pool and never
/// behind another request: one Skia draw cannot be stopped, so a work the viewer left must not
/// hold up the next one. A request yields a coarse whole first, then the whole drawn in tiles on
/// several threads; a cancelled request stops at the next tile.
///
/// A work Skia cannot draw is not drawn another way (the author's ruling, 2026-10-06): the request
/// stops with `Failed`, and the cause is appended to the failure log so the display can be fixed.
public final class DisplayRenderer: Sendable {
    /// The one switch back to resvg for the work area.
    static let drawsWithSkia = true

    public enum Painter: String, Sendable { case skia, resvg }

    public struct Frame: Sendable {
        public let image: CGImage
        /// The first small whole, shown while the full one is drawn.
        public let coarse: Bool
        public let painter: Painter
    }

    /// A window of the zoomed picture at the screen's density.
    public struct WindowFrame: Sendable {
        public let image: CGImage
        public let region: DisplayRegion
        /// False while tiles are still being drawn; the parts not drawn yet are transparent.
        public let complete: Bool
    }

    /// Not shown on screen: what was drawn, and how often Skia failed and why.
    public struct Diagnostics: Sendable, Equatable {
        public var skiaWholes = 0
        public var skiaWindows = 0
        /// Drawn with resvg because `drawsWithSkia` is off, never because Skia failed.
        public var resvgWholes = 0
        public var failures: [String: Int] = [:]
        public var tilesDrawn = 0
    }

    /// A whole or window Skia could not draw. Its cause is in the failure log.
    public struct Failed: LocalizedError, Sendable {
        public let code: String
        public var errorDescription: String? {
            "Skiaで描けませんでした（\(code)）。原因を表示の失敗ログ（display-failures）に書きました。"
        }
    }

    private struct Entry<Value: Sendable>: Sendable {
        let value: Value
        let cost: Int
        var use: UInt64
    }

    private struct State: Sendable {
        var scenes: [String: Entry<PreparedDisplay>] = [:]
        var coarse: [String: Entry<CGImage>] = [:]
        var wholes: [String: Entry<Frame>] = [:]
        var clock: UInt64 = 0
        var diagnostics = Diagnostics()
    }

    private let queue = DispatchQueue(label: "app.inku.display", qos: .userInitiated, attributes: .concurrent)
    private let state = OSAllocatedUnfairLock(initialState: State())
    private let failureLog = OSAllocatedUnfairLock<FailureLog?>(initialState: nil)
    private static let logger = Logger(subsystem: "app.inku", category: "display")
    private let sceneCostLimit: Int
    private let wholeByteLimit: Int

    public init(sceneCostLimit: Int = 256 * 1024 * 1024, wholeByteLimit: Int = 128 * 1024 * 1024) {
        self.sceneCostLimit = sceneCostLimit
        self.wholeByteLimit = wholeByteLimit
    }

    /// The whole work fitted to `width` × `height` pixels: the coarse whole (unless the full one
    /// is kept), then the full one. Ending the iteration cancels the drawing.
    public func whole(svg: String, width: UInt32, height: UInt32) -> AsyncThrowingStream<Frame, Error> {
        AsyncThrowingStream { continuation in
            let cancelled = OSAllocatedUnfairLock(initialState: false)
            continuation.onTermination = { _ in cancelled.withLock { $0 = true } }
            queue.async { [self] in
                do {
                    try draw(svg: svg, width: width, height: height, cancelled: cancelled) { continuation.yield($0) }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    /// A window of the zoomed picture, its tiles drawn from the window's centre outwards on several threads.
    /// The joined pixels so far are yielded every `progressInterval`, then the complete window. A work the Skia
    /// display cannot draw stops with `Failed` and is logged (the enlarged whole stays). Ending the iteration cancels the drawing.
    public func window(svg: String, region: DisplayRegion,
                       progressInterval: Duration = .milliseconds(150)) -> AsyncThrowingStream<WindowFrame, Error> {
        AsyncThrowingStream { continuation in
            let cancelled = OSAllocatedUnfairLock(initialState: false)
            continuation.onTermination = { _ in cancelled.withLock { $0 = true } }
            queue.async { [self] in
                do {
                    guard Self.drawsWithSkia else { return continuation.finish() }
                    let digest = SHA256.hash(data: Data(svg.utf8)).map { String(format: "%02x", $0) }.joined()
                    let scene = try prepared(svg: svg, digest: digest)
                    if cancelled.withLock({ $0 }) { throw CancellationError() }
                    let image = try tiled(scene, window: region, side: InkuCore.displayLayout.tileSide, cancelled: cancelled,
                                          progressInterval: progressInterval) { partial in
                        continuation.yield(WindowFrame(image: partial, region: region, complete: false))
                    }
                    state.withLock { $0.diagnostics.skiaWindows += 1 }
                    continuation.yield(WindowFrame(image: image, region: region, complete: true))
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish(throwing: CancellationError())
                } catch {
                    continuation.finish(throwing: failed(error, svg: svg, stage: "window", request: [
                        "full_width": Int(region.fullWidth), "full_height": Int(region.fullHeight), "x": Int(region.x),
                        "y": Int(region.y), "width": Int(region.width), "height": Int(region.height)]))
                }
            }
        }
    }

    public func diagnostics() -> Diagnostics { state.withLock { $0.diagnostics } }

    /// Failures are appended to `display-failures/failures.jsonl` in `directory`, with one copy of
    /// each failing SVG beside it. Without a directory they go to the system log only.
    public func connectFailureLog(directory: URL) {
        failureLog.withLock { $0 = FailureLog(folder: directory.appendingPathComponent("display-failures", isDirectory: true)) }
    }

    public func purge() {
        state.withLock { state in
            state.scenes.removeAll(); state.coarse.removeAll(); state.wholes.removeAll()
        }
    }

    private func draw(svg: String, width: UInt32, height: UInt32, cancelled: OSAllocatedUnfairLock<Bool>,
                      yield: (Frame) -> Void) throws {
        func checkCancellation() throws { if cancelled.withLock({ $0 }) { throw CancellationError() } }
        let digest = SHA256.hash(data: Data(svg.utf8)).map { String(format: "%02x", $0) }.joined()
        let wholeKey = "\(digest):\(width):\(height)"
        if let kept = state.withLock({ Self.take(&$0.wholes, wholeKey, &$0.clock) }) { yield(kept); return }
        guard Self.drawsWithSkia else {
            return try fallback(svg: svg, width: width, height: height, key: wholeKey, yield: yield)
        }
        do {
            let scene = try prepared(svg: svg, digest: digest)
            try checkCancellation()
            let layout = InkuCore.displayLayout
            let coarse = try state.withLock({ Self.take(&$0.coarse, digest, &$0.clock) }) ?? {
                guard let image = try scene.rasterize(targetWidth: layout.coarseSide, targetHeight: layout.coarseSide).makeCGImage()
                else { throw ArtworkError.imageUnavailable }
                state.withLock { Self.keep(&$0.coarse, digest, image, cost: 1, limit: 32, &$0.clock) }
                return image
            }()
            yield(Frame(image: coarse, coarse: true, painter: .skia))
            try checkCancellation()
            let image = try tiled(scene, window: scene.whole(targetWidth: width, targetHeight: height),
                                  side: layout.tileSide, cancelled: cancelled)
            let frame = Frame(image: image, coarse: false, painter: .skia)
            state.withLock { state in
                state.diagnostics.skiaWholes += 1
                Self.keep(&state.wholes, wholeKey, frame, cost: image.bytesPerRow * image.height, limit: wholeByteLimit, &state.clock)
            }
            yield(frame)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try checkCancellation()
            throw failed(error, svg: svg, stage: "whole", request: ["width": Int(width), "height": Int(height)])
        }
    }

    private func prepared(svg: String, digest: String) throws -> PreparedDisplay {
        if let scene = state.withLock({ Self.take(&$0.scenes, digest, &$0.clock) }) { return scene }
        let scene = try InkuCore.prepareDisplay(svg: svg)
        let cost = Int(clamping: scene.pictureByteCount + scene.sourceByteCount)
        state.withLock { Self.keep(&$0.scenes, digest, scene, cost: cost, limit: sceneCostLimit, &$0.clock) }
        return scene
    }

    /// The window drawn tile by tile on several threads and joined into one image in the core, so the tile
    /// pixels and the finished image are never copied into Swift. With `progress`, the pixels joined so far
    /// are handed over at most once every `progressInterval`.
    private func tiled(_ scene: PreparedDisplay, window: DisplayRegion, side: UInt32, cancelled: OSAllocatedUnfairLock<Bool>,
                       progressInterval: Duration = .zero, progress: (@Sendable (CGImage) -> Void)? = nil) throws -> CGImage {
        let tiles = InkuCore.displayTiles(window: window, side: side)
        let composite = try scene.composite(window: window)
        let failure = OSAllocatedUnfairLock<(any Error)?>(initialState: nil)
        // The time of the last hand-over.
        let handedOver = OSAllocatedUnfairLock(initialState: ContinuousClock.now)
        DispatchQueue.concurrentPerform(iterations: tiles.count) { index in
            guard !cancelled.withLock({ $0 }), failure.withLock({ $0 == nil }) else { return }
            do {
                try composite.renderTile(tiles[index])
                state.withLock { $0.diagnostics.tilesDrawn += 1 }
                guard let progress, handedOver.withLock({ last in
                    guard ContinuousClock.now - last >= progressInterval else { return false }
                    last = .now
                    return true
                }) else { return }
                // A snapshot that cannot be made only skips this hand-over.
                if let image = try? composite.snapshot(), !cancelled.withLock({ $0 }) { progress(image) }
            } catch {
                failure.withLock { if $0 == nil { $0 = error } }
            }
        }
        if cancelled.withLock({ $0 }) { throw CancellationError() }
        if let error = failure.withLock({ $0 }) { throw error }
        return try composite.finish()
    }

    /// Counts and logs a Skia failure, and returns the error the request stops with.
    private func failed(_ error: any Error, svg: String, stage: String, request: [String: Int]) -> Failed {
        let code = Self.code(error)
        state.withLock { $0.diagnostics.failures[code, default: 0] += 1 }
        let message: String = switch error {
        case CoreFailure.displayUnsupported(_, let message), CoreFailure.displayRefused(_, let message): message
        default: String(describing: error)
        }
        Self.logger.error("Skia display failed: \(stage, privacy: .public) \(code, privacy: .public) \(message, privacy: .public)")
        failureLog.withLock { $0?.append(svg: svg, stage: stage, code: code, message: message, request: request) }
        return Failed(code: code)
    }

    /// resvg for the work area while `drawsWithSkia` is off.
    private func fallback(svg: String, width: UInt32, height: UInt32, key: String, yield: (Frame) -> Void) throws {
        guard let image = try InkuCore.prepareSVG(svg: svg).rasterize(targetWidth: width, targetHeight: height).makeCGImage()
        else { throw ArtworkError.imageUnavailable }
        let frame = Frame(image: image, coarse: false, painter: .resvg)
        state.withLock { state in
            state.diagnostics.resvgWholes += 1
            Self.keep(&state.wholes, key, frame, cost: image.bytesPerRow * image.height, limit: wholeByteLimit, &state.clock)
        }
        yield(frame)
    }

    private static func code(_ error: any Error) -> String {
        switch error {
        case CoreFailure.displayUnsupported(let code, _): code
        case CoreFailure.displayRefused(let code, _): "refused_\(code)"
        case CoreFailure.internalInvariant: "internal_invariant"
        default: "image_unavailable"
        }
    }

    private static func take<Value>(_ entries: inout [String: Entry<Value>], _ key: String, _ clock: inout UInt64) -> Value? {
        guard var entry = entries[key] else { return nil }
        clock &+= 1; entry.use = clock; entries[key] = entry
        return entry.value
    }

    /// Least recently used first out. `limit` bounds the summed cost; a value above it is not kept.
    private static func keep<Value>(_ entries: inout [String: Entry<Value>], _ key: String, _ value: Value, cost: Int,
                                    limit: Int, _ clock: inout UInt64) {
        guard cost <= limit else { return }
        entries.removeValue(forKey: key)
        var total = entries.values.reduce(0) { $0 + $1.cost }
        while total + cost > limit, let oldest = entries.min(by: { $0.value.use < $1.value.use }) {
            total -= oldest.value.cost; entries.removeValue(forKey: oldest.key)
        }
        clock &+= 1
        entries[key] = Entry(value: value, cost: cost, use: clock)
    }
}

/// The display's failure log: one JSON line per failure, and one copy of each failing SVG named by
/// its SHA-256, so the work can be drawn again while the display is fixed. A failure repeated in one
/// run (the same SVG, stage and code) is written once.
private struct FailureLog: Sendable {
    let folder: URL
    private var written: Set<String> = []

    init(folder: URL) { self.folder = folder }

    mutating func append(svg: String, stage: String, code: String, message: String, request: [String: Int]) {
        let digest = SHA256.hash(data: Data(svg.utf8)).map { String(format: "%02x", $0) }.joined()
        guard written.insert("\(digest):\(stage):\(code)").inserted else { return }
        let info = Bundle.main.infoDictionary
        let record: [String: Any] = [
            "at": ISO8601DateFormatter().string(from: Date()), "stage": stage, "code": code, "message": message,
            "request": request, "svg_sha256": digest, "svg_bytes": svg.utf8.count, "svg_file": digest + ".svg",
            "display_api_version": InkuCore.displayAPIVersion,
            "app_version": info?["CFBundleShortVersionString"] as? String ?? "", "app_build": info?["CFBundleVersion"] as? String ?? "",
        ]
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let copy = folder.appendingPathComponent(digest + ".svg")
            if !FileManager.default.fileExists(atPath: copy.path) { try Data(svg.utf8).write(to: copy, options: .atomic) }
            var line = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
            line.append(0x0A)
            let log = folder.appendingPathComponent("failures.jsonl")
            if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
            let handle = try FileHandle(forWritingTo: log)
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: line)
        } catch {
            Logger(subsystem: "app.inku", category: "display").error("Display failure log not written: \(error.localizedDescription, privacy: .public)")
        }
    }
}
