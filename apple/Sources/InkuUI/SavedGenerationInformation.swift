import Foundation
import InkuHost
import InkuPersistence

/// Everything in this projection belongs to the work captured when its pane opened.
/// An older work's absent journal remains absent; current settings never fill it in.
struct SavedGenerationInformation: Sendable {
    let presentation: SavedWorkPresentation?
    let context: SavedAuthoringContext?
    let metrics: [ProviderAttemptMetric]
    let generation: Int?
    let edge: LineageEdge?
    let annotation: LibraryAnnotation

    var prompts: [ExactJSON]? {
        presentation?.promptJSON.flatMap { try? ExactJSON(data: $0).array }
    }

    func prompt(_ action: String) -> ExactJSON? {
        prompts?.last { $0["action"].string == action }?["prompt"]
    }

    func tokenTotal(input: Bool) -> String? {
        let values = metrics.compactMap { input ? $0.usage?.inputTokens : $0.usage?.outputTokens }
        guard !values.isEmpty else { return nil }
        // A partial record does not become an invented aggregate.
        guard values.count == metrics.filter({ $0.sent }).count else { return nil }
        return values.reduce(UInt64(0)) { $0 &+ $1 }.formatted()
    }
}

/// Same definitions as the Server's web/src/lib/svgWeight.ts: containers and
/// annotations are excluded, points tokens plus pairs of path numbers are counted.
struct SavedSVGWeight {
    let bytes: Int
    let objects: Int
    let points: Int

    init(_ source: String) {
        bytes = source.utf8.count
        let text = source as NSString
        func captures(_ pattern: String, in input: NSString) -> [String] {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
            return regex.matches(in: input as String, range: NSRange(location: 0, length: input.length))
                .map { input.substring(with: $0.range(at: 1)) }
        }
        let structure = Set(["svg", "title", "desc", "metadata", "defs"])
        objects = captures(#"<([a-zA-Z][a-zA-Z0-9_-]*)"#, in: text).filter { !structure.contains($0) }.count
        let pointTokens = captures(#"points="([^"]*)""#, in: text)
            .reduce(0) { $0 + $1.split(whereSeparator: \.isWhitespace).count }
        let number = try? NSRegularExpression(pattern: #"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"#)
        let pathPoints = captures(#"\bd="([^"]*)""#, in: text).reduce(0) { count, path in
            count + (number?.numberOfMatches(in: path, range: NSRange(path.startIndex..., in: path)) ?? 0) / 2
        }
        points = pointTokens + pathPoints
    }
}
