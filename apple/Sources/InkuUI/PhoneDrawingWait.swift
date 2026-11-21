import Foundation
import CoreGraphics
import InkuCore
import InkuHost
import InkuPersistence
import Observation
import OSLog
import Synchronization

@MainActor @Observable
final class PhoneDrawingWait {
    struct Completion: Identifiable {
        let id: String
        let savedAt: ContinuousClock.Instant
    }

    let description: String
    let aspect: Double
    let started = Date()
    var visible = true
    var running = true
    var cancelled = false
    var completion: Completion?
    var failure: String?
    var report: ExactJSON = .object([:])
    var material: ExactJSON = .object([:])
    var instructions: String?
    private(set) var beforeReview: String?
    private(set) var layerCount: Int?
    private(set) var support: String?
    var commandCount: Int?
    @ObservationIgnored private(set) var assemblyRequest: Data?
    @ObservationIgnored private(set) var preflight: PhoneDrawingAssembly.Preflight?
    @ObservationIgnored private var assemblyPixels: UInt32?
    private(set) var milestoneTimes: [Int] = []
    private(set) var instructionsAt: Int?
    private(set) var scoreAt: Int?
    private var sequence: UInt64 = 0

    init(description: String, aspect: Double) { self.description = description; self.aspect = aspect }

    func receive(_ progress: PipelineProgress, at instant: ContinuousClock.Instant) {
        let seconds = max(0, Int(Date().timeIntervalSince(started)))
        switch progress {
        case .changed(let view):
            guard let next = UInt64(view.sequence), next >= sequence else { return }
            sequence = next
            if let data = view.phoneProcessJSON, let value = try? ExactJSON(data: data) {
                material = value
                beforeReview = value["before_review"].string ?? beforeReview
                layerCount = value["layers"].number.flatMap(Int.init) ?? layerCount
                support = value["support"].string ?? support
            }
            instructions = view.visibleDDL
            if instructions != nil && instructionsAt == nil { instructionsAt = seconds }
            if let bytes = view.scoreJSON, let score = try? ExactJSON(data: bytes) {
                commandCount = score["instructions"].array?.count ?? score["commands"].array?.count
                if commandCount != nil && scoreAt == nil { scoreAt = seconds }
            }
            if let request = view.phoneAssemblyRequest {
                assemblyRequest = request
                startAssemblyIfReady()
            }
        case .runProgress(_, let data):
            if let envelope = try? ExactJSON(data: data), envelope["run_progress"].object != nil {
                let value = envelope["run_progress"]
                let count = value["finished"].array?.count ?? 0
                if count >= milestoneTimes.count {
                    milestoneTimes.append(contentsOf: repeatElement(seconds, count: count - milestoneTimes.count))
                    report = value
                }
            }
        case .saved(_, let id): recordSave(id, at: instant)
        default: break
        }
    }

    func setAssemblyTarget(_ pixels: UInt32?) {
        assemblyPixels = pixels
        if pixels == nil { cancelPreflight() }
        else { startAssemblyIfReady() }
    }

    func cancelPreflight() {
        preflight?.task.cancel()
        preflight = nil
    }

    private func startAssemblyIfReady() {
        guard preflight == nil, running, completion == nil, visible, !cancelled,
              let bytes = assemblyRequest, let pixels = assemblyPixels else { return }
        let progress = PhoneDrawingAssembly.Progress()
        let aspect = aspect
        let task = Task.detached(priority: .userInitiated) {
            try Task.checkCancellation()
            let request = try PhoneDrawingAssembly.previewRequest(bytes)
            return try PhoneDrawingAssembly.frames(request: request, aspect: aspect, pixels: pixels, progress: progress)
        }
        preflight = .init(task: task, progress: progress)
    }

    private func recordSave(_ id: String, at instant: ContinuousClock.Instant) {
        guard completion == nil else { return }
        completion = Completion(id: id, savedAt: instant)
        running = false
    }
}

enum PhoneDrawingBanner {
    enum Event {
        case started, stopped, failed
        case saved(id: String, watching: Bool)
        case opened(String)
    }

    static func next(_ current: String?, for event: Event) -> String? {
        switch event {
        case .started, .stopped, .failed: return nil
        case .saved(let id, let watching): return watching ? nil : id
        case .opened(let id): return current == id ? nil : current
        }
    }
}

enum PhoneDrawingAssembly {
    struct Preflight {
        let task: Task<[Frame], Error>
        let progress: Progress
    }

    struct Frame: Sendable {
        let image: CGImage
        let lines: [ClosedRange<Int>]
    }

    struct VectorFrame: Decodable, Sendable {
        let svg: String
        let lines: [[Int]]
    }

    private struct CoreResponse: Decodable {
        let frames: [VectorFrame]?
        let error: String?
        let message: String?
    }

    enum Skip: Sendable {
        case deadline, frameCount, settingOff
        case refused(code: String, message: String)
        case preparation(String)

        var logFields: (reason: String, detail: String) {
            switch self {
            case .deadline: ("deadline", "")
            case .frameCount: ("frame_count", "")
            case .settingOff: ("setting_off", "")
            case .refused(let code, let message): ("core_refused", code + " " + message)
            case .preparation(let code): ("preparation_failed", code)
            }
        }
    }

    final class Progress: Sendable {
        private struct Counts: Sendable { var returned: Int?; var rasterized = 0 }
        private let counts = Mutex(Counts())

        func returned(_ count: Int) { counts.withLock { $0.returned = count } }
        func rasterized() { counts.withLock { $0.rasterized += 1 } }

        func logSkip(_ skip: Skip, workID: String, elapsed: Duration) {
            let counts = counts.withLock { $0 }
            let seconds = elapsed.components
            let duration = Double(seconds.seconds) + Double(seconds.attoseconds) / 1e18
            let (reason, detail) = skip.logFields
            let returned = counts.returned.map(String.init) ?? (reason == "deadline" ? "pending" : "0")
            let singleLine = detail.replacingOccurrences(of: "\n", with: "\\n").replacingOccurrences(of: "\r", with: "\\r")
            Logger(subsystem: "app.inku", category: "drawing").notice(
                "Line animation skipped work=\(workID, privacy: .public) reason=\(reason, privacy: .public) seconds=\(duration, format: .fixed(precision: 3)) frames=\(returned, privacy: .public) rasterized=\(counts.rasterized) detail=\(singleLine, privacy: .public)")
        }
    }

    private enum Prepared: Sendable {
        case ready([Frame])
        case skipped(Skip)
    }

    static let preparationLimit: Duration = .milliseconds(1500)
    static let playbackLimit: Duration = .seconds(6)
    static let previewPixels: UInt32 = 600
    static let previewFrameCount = 8
    static func frameInterval(count: Int) -> Duration {
        min(.milliseconds(260), playbackLimit / max(1, count))
    }

    static func prepare<Instant: InstantProtocol & Sendable>(
        savedAt: Instant, commandCount: Int? = nil, showDrawingMotion: Bool = true,
        now: @escaping @Sendable () -> Instant,
        sleep: @escaping @Sendable (Instant) async throws -> Void,
        onSkip: @Sendable (Skip, Duration) -> Void = { _, _ in },
        load: @escaping @Sendable () async throws -> [Frame]
    ) async -> [Frame] where Instant.Duration == Duration {
        let deadline = savedAt.advanced(by: preparationLimit)
        if let skip: Skip = !showDrawingMotion ? .settingOff : commandCount == 1 ? .frameCount : now() >= deadline ? .deadline : nil {
            onSkip(skip, savedAt.duration(to: now()))
            return []
        }
        // The core call is synchronous. Cancelling a structured child would still wait for it.
        let (stream, result) = AsyncStream<Prepared>.makeStream(bufferingPolicy: .bufferingOldest(1))
        let producer = Task.detached(priority: .userInitiated) {
            defer { result.finish() }
            do {
                let frames = try await load()
                if now() >= deadline { result.yield(.skipped(.deadline)) }
                else { result.yield(frames.count > 2 ? .ready(frames) : .skipped(.frameCount)) }
            } catch let Failure.refused(code, message) {
                result.yield(.skipped(.refused(code: code, message: message)))
            } catch {
                if !Task.isCancelled {
                    result.yield(.skipped(.preparation((error as? HostError)?.code ?? String(describing: type(of: error)))))
                }
            }
        }
        let timer = Task {
            do { try await sleep(deadline) } catch { return }
            result.yield(.skipped(.deadline))
            result.finish()
        }
        defer { producer.cancel(); timer.cancel(); result.finish() }
        var iterator = stream.makeAsyncIterator()
        switch await iterator.next() {
        case .ready(let frames): return frames
        case .skipped(let skip):
            if !Task.isCancelled { onSkip(skip, savedAt.duration(to: now())) }
            return []
        case nil: return []
        }
    }

    static func frames(work: SavedWork, context: SavedAuthoringContext, pixels: UInt32, progress: Progress? = nil) throws -> [Frame] {
        let request = try animationRequest(work: work, context: context)
        return try frames(request: request, aspect: work.renderCanvasAspectRatio ?? 1, pixels: pixels, progress: progress)
    }

    static func frames(request: Data, aspect: Double, pixels: UInt32, progress: Progress? = nil) throws -> [Frame] {
        let frames = try coreFrames(for: request)
        progress?.returned(frames.count)
        return try rasterize(frames, aspect: aspect, pixels: pixels, progress: progress)
    }

    static func animationRequest(work: SavedWork, context: SavedAuthoringContext) throws -> Data {
        let locks = try context.document.map { try ExactJSON(data: $0)["macro_locks"].array ?? [] } ?? []
        let request = try PipelineHost.lineAnimationRequest(work: work, context: context, locks: locks)
        return previewRequest(request)
    }

    static func previewRequest(_ request: Data) throws -> Data {
        try previewRequest(ExactJSON(data: request))
    }

    private static func previewRequest(_ request: ExactJSON) -> Data {
        var request = request
        request["show_ddl"] = .bool(false)
        // The request schema requires a font family even when the DDL panel is disabled.
        request["font_family"] = .string("")
        return request.data
    }

    static func coreFrames(for request: Data) throws -> [VectorFrame] {
        try decodeFrames(InkuCore.lineAnimation(request))
    }

    static func decodeFrames(_ bytes: Data) throws -> [VectorFrame] {
        let response = try JSONDecoder().decode(CoreResponse.self, from: bytes)
        if let error = response.error {
            throw Failure.refused(code: error, message: response.message ?? "")
        }
        guard let frames = response.frames else { throw HostError("line_animation_frames_missing") }
        return frames
    }

    enum Failure: Error {
        case refused(code: String, message: String)
    }

    static func rasterize(_ raw: [VectorFrame], aspect: Double, pixels: UInt32, progress: Progress? = nil) throws -> [Frame] {
        guard raw.count > 2 else { return [] }
        let count = min(raw.count, previewFrameCount)
        return try (0..<count).map { index in
            try Task.checkCancellation()
            let end = index * (raw.count - 1) / (count - 1)
            let begin = index == 0 ? 0 : (index - 1) * (raw.count - 1) / (count - 1) + 1
            let lines = raw[begin...end].flatMap { frame in
                frame.lines.compactMap { entry -> ClosedRange<Int>? in
                    guard entry.count == 2, entry[0] <= entry[1] else { return nil }
                    return entry[0]...entry[1]
                }
            }
            let width = aspect >= 1 ? pixels : nil
            let height = aspect >= 1 ? nil : pixels
            let svg = raw[end].svg
            let raster: RasterImage
            if DisplayRenderer.drawsWithSkia {
                let scene = try InkuCore.prepareDisplay(svg: svg)
                raster = try scene.rasterize(targetWidth: width, targetHeight: height)
            } else {
                let scene = try InkuCore.prepareSVG(svg: svg)
                raster = try scene.rasterize(targetWidth: width, targetHeight: height)
            }
            guard let image = raster.makeCGImage() else { throw HostError("line_animation_frame_unavailable") }
            progress?.rasterized()
            return Frame(image: image, lines: lines)
        }
    }
}
