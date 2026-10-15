import Foundation

public struct GroundMaterial: Decodable, Sendable, Equatable {
    public let value: String
    public let ja: String
    public let en: String
    enum CodingKeys: String, CodingKey { case value = "score_value", ja = "surface_ja", en = "surface_en" }
    public func name(language: String) -> String { language == "ja" ? ja : en }
}

/// Plans carry host-owned rendering requests; callers can only choose a saved work and an offered option.
public struct SavedScoreVariantPlan: Sendable {
    public let index: UInt64?
    public let ground: GroundMaterial?
    let replay: SavedScoreReplayPlan
}

public struct ColorArrangementPage: Sendable {
    public let plans: [SavedScoreVariantPlan]
    public let nextCursor: UInt64?
    public let total: UInt64
}

enum GroundVariants {
    static func current(_ score: ExactJSON) -> String { score["canvas"]["ground"]["material"].string ?? "plain" }

    static func score(_ score: ExactJSON, material: String) -> ExactJSON {
        var changed = score
        if changed["canvas"].object == nil {
            changed["canvas"] = .object(["aspect": score["canvas"].string.map(ExactJSON.string) ?? .string("square")])
        }
        if changed["canvas"]["ground"].object == nil { changed["canvas"]["ground"] = .object([:]) }
        changed["canvas"]["ground"]["material"] = .string(material)
        return changed
    }

    static func source(_ source: String, material: GroundMaterial, language: String?, vocabulary: [GroundMaterial]) -> String {
        func sentence(_ item: GroundMaterial, _ language: String) -> String {
            language == "ja" ? item.ja + "。" : item.en.prefix(1).uppercased() + item.en.dropFirst() + "."
        }
        var lines = source.components(separatedBy: "\n")
        for (index, line) in lines.enumerated() {
            let line = line.trimmingCharacters(in: .whitespacesAndNewlines)
            for item in vocabulary {
                if line == sentence(item, "ja") { lines[index] = sentence(material, "ja"); return lines.joined(separator: "\n") }
                if line.lowercased() == sentence(item, "en").lowercased() { lines[index] = sentence(material, "en"); return lines.joined(separator: "\n") }
            }
        }
        let language = ["ja", "en"].contains(language ?? "") ? language! :
            (source.unicodeScalars.contains { (0x3040...0x9fff).contains($0.value) } ? "ja" : "en")
        return sentence(material, language) + (source.isEmpty ? "" : "\n" + source)
    }
}

extension PipelineHost {
    public func makeColorArrangementPage(workID: String, cursor: UInt64) async throws -> ColorArrangementPage {
        let base = try await makeSavedScoreReplayPlan(workID: workID, derivationKind: "color_arrangement_change")
        guard base.work.renderSeed != nil else { throw HostError("saved_refinement_options_unavailable") }
        let request = try ExactJSON(data: base.renderRequest)
        let map = request["request"]["options"]["resolved_color_map"].data
        let sequence = try ColorArrangementIndex(svg: base.work.svg, colorMap: map, workID: workID)
        let end = cursor >= sequence.total ? sequence.total : min(cursor + 8, sequence.total)
        var plans: [SavedScoreVariantPlan] = []
        if cursor < end {
            for index in cursor..<end {
                var render = request
                let colors = try sequence.colorMap(map, at: index)
                render["request"]["options"]["resolved_color_map"] = try ExactJSON(data: colors)
                let metadata: ExactJSON = .object(["color_arrangement_index": .number(String(index)),
                    "catalog_id": request["request"]["options"]["catalog_id"],
                    "color_arrangement": .object(try sequence.substitution(at: index).mapValues(ExactJSON.string))])
                let replay = SavedScoreReplayPlan(work: base.work, parentNode: base.parentNode, context: base.context,
                    renderRequest: render.data, derivationKind: "color_arrangement_change", derivationMetadata: metadata.data,
                    variationAmplitude: nil, variationSeed: nil)
                plans.append(SavedScoreVariantPlan(index: index, ground: nil, replay: replay))
            }
        }
        return ColorArrangementPage(plans: plans, nextCursor: end < sequence.total ? end : nil, total: sequence.total)
    }

    public func makeGroundVariantPlans(workID: String, vocabulary: [GroundMaterial]) async throws -> [SavedScoreVariantPlan] {
        let base = try await makeSavedScoreReplayPlan(workID: workID, derivationKind: "ground_change")
        guard base.work.renderSeed != nil, !vocabulary.isEmpty, Set(vocabulary.map(\.value)).count == vocabulary.count else {
            throw HostError("saved_refinement_options_unavailable")
        }
        let score = try ExactJSON(data: Data(base.work.score.utf8))
        let request = try ExactJSON(data: base.renderRequest)
        let current = GroundVariants.current(score)
        return vocabulary.filter { $0.value != current }.map { material in
            var render = request
            render["request"]["score"] = GroundVariants.score(score, material: material.value)
            let metadata: ExactJSON = .object(["ground_material": .string(material.value), "parent_ground_material": .string(current)])
            var replay = SavedScoreReplayPlan(work: base.work, parentNode: base.parentNode, context: base.context,
                renderRequest: render.data, derivationKind: "ground_change", derivationMetadata: metadata.data,
                variationAmplitude: nil, variationSeed: nil)
            replay.retouchedSource = GroundVariants.source(base.work.ddl ?? "", material: material,
                language: base.work.instructionLangResolved, vocabulary: vocabulary)
            return SavedScoreVariantPlan(index: nil, ground: material, replay: replay)
        }
    }

    public func previewSavedScoreVariant(_ plan: SavedScoreVariantPlan) async throws -> PreparedCandidate {
        try await previewSavedScoreReplay(plan.replay)
    }
}
