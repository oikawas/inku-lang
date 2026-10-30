import Foundation
import InkuCore
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

    func pluginOffers(japanese: Bool) -> [String] {
        guard let data = context?.configuration, let config = try? ExactJSON(data: data) else { return [] }
        return Self.pluginOffers(configuration: config, japanese: japanese)
    }

    static func pluginOffers(configuration config: ExactJSON, japanese: Bool) -> [String] {
        let records = config["plugin_offers"].array ?? []
        guard !records.isEmpty else { return [] }
        let definitions = config["definitions"].array ?? []
        let candidates: [ExactJSON] = definitions.enumerated().map { index, definition in
            .object(["source_id": .string("saved:\(index)"), "definition_json": .string(definition.text), "summary": .string("")])
        }
        let request: ExactJSON = .object(["maximum_entries": .integer(max(1, candidates.count)), "language": .string(japanese ? "ja" : "en"),
            "canonical": .array(candidates), "legacy": .array([]), "bundled_packages": .array([])])
        let catalog = try? ExactJSON(data: InkuCore.resolveMacroCatalog(request.data))
        let entries = catalog?["entries"].array ?? []
        func name(_ item: ExactJSON) -> String {
                let id = item["qualified_name"].string ?? ""
                let saved = entries.first { $0["qualified_name"].string == id }?["definition"]["names"][japanese ? "ja" : "en"].array?.first?.string
                return item[japanese ? "written_ja" : "written_en"].string.flatMap { $0.isEmpty ? nil : $0 }
                    ?? saved.map { japanese ? "｛\($0)｝" : "{\($0)}" } ?? id
        }
        return records.flatMap { record -> [String] in
            let offered = record["offer"]["offered"].array ?? record["offered"].array ?? []
            let omitted = record["offer"]["omitted"].array ?? record["omitted"].array ?? []
            let stage: String = switch record["stage"].string {
            case "generate_normalized_ddl": japanese ? "下絵" : "Underdrawing"
            case "write_description_ddl": japanese ? "書く" : "Writing"
            case "review_description_ddl": japanese ? "見直す" : "Review"
            case "chunk_rewrite": japanese ? "まとまりの書き直し" : "Chunk rewrite"
            default: record["stage"].string ?? ""
            }
            let rendered = offered.map { item in
                let reason: String = switch item["reason"].string {
                case "brace": japanese ? "括弧で書いた" : "written in braces"
                case "ddl": japanese ? "DDL にあった" : "in the DDL"
                case "name": japanese ? "名が記述に現れた" : "name appeared in the description"
                default: ""
                }
                return reason.isEmpty ? name(item) : "\(name(item))（\(reason)）"
            }
            let separator = japanese ? "、" : ", "
            var lines = ["\(stage): " + (rendered.isEmpty ? (japanese ? "提示なし" : "None offered") : rendered.joined(separator: separator))]
            if !omitted.isEmpty { lines.append((japanese ? "上限で落とした語: " : "Omitted by the limit: ") + omitted.map(name).joined(separator: separator)) }
            return lines
        }
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
