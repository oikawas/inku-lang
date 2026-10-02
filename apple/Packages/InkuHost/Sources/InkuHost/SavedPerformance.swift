import Foundation
import CryptoKit
import InkuCore
import InkuPersistence

enum WorkIdentity {
    static func sha256(_ value: Data) -> String { SHA256.hash(data: value).map { String(format: "%02x", $0) }.joined() }
    static func description(_ text: String) -> String {
        let normalized = text.precomposedStringWithCanonicalMapping.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
        let whitespace = DDLSource.bodyWhitespaceCodepoints.union([28, 29, 30, 31])
        let scalars = normalized.unicodeScalars
        let body = scalars.drop(while: { whitespace.contains($0.value) }).reversed().drop(while: { whitespace.contains($0.value) }).reversed()
        return "dh1:" + sha256(Data(String(String.UnicodeScalarView(body)).utf8))
    }
    static func render(score: ExactJSON, options: ExactJSON, metadata: ExactJSON) -> String {
        let seed = options["render_seed"].string.map(ExactJSON.number) ?? options["render_seed"]
        let payload: ExactJSON = .object(["version": .string("rh3"), "score": score, "render_seed": seed,
                                          "render_wild": .bool(options["wild"].bool ?? false),
                                          "render_engine_id": metadata["render_engine_id"], "render_engine_version": metadata["render_engine_version"],
                                          "render_color_catalog_id": options["catalog_id"]])
        return "rh3:" + sha256(payload.data)
    }
    static func savedID(executionID: String, sequence: String) -> String { executionID + "_" + sequence }
    static func location(_ workID: String) throws -> (executionID: String, effectID: String) {
        guard let separator = workID.lastIndex(of: "_") else { throw HostError("saved_performance_context_unavailable") }
        let id = String(workID[..<separator]); let sequence = String(workID[workID.index(after: separator)...])
        guard !id.isEmpty, !sequence.isEmpty, sequence.utf8.allSatisfy({ (48...57).contains($0) }) else { throw HostError("saved_performance_context_unavailable") }
        return (id, "save-render:" + sequence)
    }
}

enum SavedPerformance {
    static func context(score: ExactJSON, options: ExactJSON, compiler: ExactJSON, clip: ExactJSON) -> ExactJSON {
        .object(["schema": .string("inku.swift-saved-performance.v1"), "score_sha256": .string(WorkIdentity.sha256(score.data)),
                 "options": options, "hard_policy": compiler["hard_resource_policy"],
                 "operational_budget": compiler["operational_resource_budget"], "clip": clip])
    }
    static func acknowledgement(workID: String, context: ExactJSON) -> Data {
        ExactJSON.object(["tag": .string("saved_work_committed"), "work_id": .string(workID), "performance": context]).data
    }
    static func renderRequest(work: SavedWork, context: ExactJSON, renderSeed: String?, wild: Bool?, replayOptions: ReplayOptions? = nil,
                              compositionSeed: String? = nil) throws -> ExactJSON {
        let score = try ExactJSON(data: Data(work.score.utf8))
        guard context["schema"].string == "inku.swift-saved-performance.v1",
              context["score_sha256"].string == WorkIdentity.sha256(score.data),
              context["hard_policy"].object != nil, context["operational_budget"].object != nil, context["clip"].object != nil else { throw HostError("saved_performance_context_invalid") }
        var options = try context.requiredObject("options")
        if let renderSeed {
            guard let number = UInt64(renderSeed), String(number) == renderSeed else { throw HostError("invalid_render_seed") }
            options["render_seed"] = .string(renderSeed)
        }
        if let wild { options["wild"] = .bool(wild) }
        if let compositionSeed {
            guard let number = UInt64(compositionSeed), String(number) == compositionSeed else { throw HostError("invalid_composition_seed") }
            options["composition_seed"] = .string(compositionSeed)
        }
        if let replayOptions {
            let registry = try ExactJSON(data: InkuCore.canvasRegistry)
            guard let format = registry["registry"]["formats"].array?.first(where: { $0["id"].string == replayOptions.canvasID }),
                  format["width_units"].number.flatMap(UInt32.init) == replayOptions.widthRatio,
                  format["height_units"].number.flatMap(UInt32.init) == replayOptions.heightRatio,
                  let width = options["canvas"]["width"].number.flatMap(Double.init), width > 0,
                  !replayOptions.catalogID.isEmpty else { throw HostError("replay_options_invalid") }
            let colorMap = try ExactJSON(data: replayOptions.colorMap)
            guard colorMap.object != nil else { throw HostError("replay_options_invalid") }
            options["resolved_color_map"] = colorMap
            options["catalog_id"] = .string(replayOptions.catalogID)
            options["canvas_aspect_id"] = .string(replayOptions.canvasID)
            options["canvas"] = .object(["width": .number(String(width)),
                "height": .number(String(width * Double(replayOptions.heightRatio) / Double(replayOptions.widthRatio)))])
        }
        for key in ["render_seed", "composition_seed"] {
            if let text = options[key].string {
                guard let number = UInt64(text), String(number) == text else { throw HostError("saved_performance_context_invalid") }
                // render_saved uses the older numeric i128 wire. Retain the integer lexeme exactly.
                options[key] = .number(text)
            }
        }
        return .object(["request": .object(["score": score, "options": options]), "hard_policy": context["hard_policy"],
                        "operational_budget": context["operational_budget"], "clip": context["clip"]])
    }
}
