import Foundation
import CoreGraphics
import InkuCore
import InkuHost
import InkuPersistence
import Observation
import OSLog

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

    private func recordSave(_ id: String, at instant: ContinuousClock.Instant) {
        guard completion == nil else { return }
        completion = Completion(id: id, savedAt: instant)
        running = false
    }
}

enum PhoneDrawingAssembly {
    struct Frame: Sendable {
        let image: CGImage
        let lines: [ClosedRange<Int>]
    }

    static let preparationLimit: Duration = .milliseconds(1500)
    static let playbackLimit: Duration = .seconds(6)
    static func frameInterval(count: Int) -> Duration {
        min(.milliseconds(260), playbackLimit / max(1, count))
    }

    static func prepare<Instant: InstantProtocol & Sendable>(
        savedAt: Instant, commandCount: Int? = nil, now: @escaping @Sendable () -> Instant,
        sleep: @escaping @Sendable (Instant) async throws -> Void,
        load: @escaping @Sendable () async -> [Frame]
    ) async -> [Frame] where Instant.Duration == Duration {
        let deadline = savedAt.advanced(by: preparationLimit)
        guard commandCount != 1, now() < deadline else { return [] }
        // The core call is synchronous. Cancelling a structured child would still wait for it.
        let (stream, result) = AsyncStream<[Frame]>.makeStream(bufferingPolicy: .bufferingOldest(1))
        let producer = Task.detached(priority: .userInitiated) {
            let frames = await load()
            result.yield(now() < deadline && frames.count > 2 ? frames : [])
            result.finish()
        }
        let timer = Task {
            do { try await sleep(deadline) } catch { return }
            result.yield([])
            result.finish()
        }
        defer { producer.cancel(); timer.cancel(); result.finish() }
        var iterator = stream.makeAsyncIterator()
        return await iterator.next() ?? []
    }

    static func frames(work: SavedWork, context: SavedAuthoringContext, pixels: UInt32) throws -> [Frame] {
        let locks = try context.document.map { try ExactJSON(data: $0)["macro_locks"].array ?? [] } ?? []
        var request = try PipelineHost.lineAnimationRequest(work: work, context: context, locks: locks)
        request["show_ddl"] = .bool(false)
        // The request schema requires a font family even when the DDL panel is disabled.
        request["font_family"] = .string("")
        let response = try ExactJSON(data: InkuCore.lineAnimation(request.data))
        if let error = response["error"].string {
            let message = (response["message"].string ?? "").replacingOccurrences(of: "\n", with: "\\n")
                .replacingOccurrences(of: "\r", with: "\\r")
            Logger(subsystem: "app.inku", category: "drawing").error(
                "Line animation refused work=\(work.id, privacy: .public) error=\(error, privacy: .public) message=\(message, privacy: .public)")
            return []
        }
        guard let raw = response["frames"].array, raw.count > 2 else { return [] }
        let count = min(raw.count, 24)
        return try (0..<count).map { index in
            try Task.checkCancellation()
            let end = index * (raw.count - 1) / (count - 1)
            let begin = index == 0 ? 0 : (index - 1) * (raw.count - 1) / (count - 1) + 1
            let lines = raw[begin...end].flatMap { frame in
                (frame["lines"].array ?? []).compactMap { entry -> ClosedRange<Int>? in
                    guard let values = entry.array, values.count == 2,
                          let first = values[0].number.flatMap(Int.init),
                          let last = values[1].number.flatMap(Int.init), first <= last else { return nil }
                    return first...last
                }
            }
            let scene = try InkuCore.prepareSVG(svg: raw[end].requiredString("svg"))
            let landscape = (work.renderCanvasAspectRatio ?? 1) >= 1
            let raster = try scene.rasterize(targetWidth: landscape ? pixels : nil, targetHeight: landscape ? nil : pixels)
            guard let image = raster.makeCGImage() else { throw HostError("line_animation_frame_unavailable") }
            return Frame(image: image, lines: lines)
        }
    }
}
