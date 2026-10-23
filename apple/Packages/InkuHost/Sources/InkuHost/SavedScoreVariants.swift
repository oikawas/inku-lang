import Foundation
import InkuPersistence

public struct GroundMaterial: Decodable, Sendable, Equatable {
    public let value: String
    public let ja: String
    public let en: String
    enum CodingKeys: String, CodingKey { case value = "score_value", ja = "surface_ja", en = "surface_en" }
    init(coreEntry: ExactJSON) throws {
        value = try coreEntry.requiredString("material")
        ja = try coreEntry.requiredString("label_ja")
        en = try coreEntry.requiredString("label_en")
    }
    public func name(language: String) -> String { language == "ja" ? ja : en }
}

/// Plans carry host-owned rendering requests; callers choose only an offered option.
public struct SavedScoreVariantPlan: Sendable {
    public let index: SavedVariantOrdinal?
    public let ground: GroundMaterial?
    let replay: SavedScoreReplayPlan
}

public struct ColorArrangementPage: Sendable {
    public let plans: [SavedScoreVariantPlan]
    public let nextCursor: SavedVariantOrdinal?
    public let total: SavedVariantOrdinal
}

extension PipelineHost {
    /// Core changes the saved Score; the host changes only the target paper in the rendering options.
    public func fitSavedWork(workID: String, paper: ReplayOptions) async throws -> SavedWork {
        guard paper.canvasWidth.isFinite, paper.canvasHeight.isFinite,
              paper.canvasWidth > 0, paper.canvasHeight > 0,
              paper.canvasWidth <= Double(UInt32.max), paper.canvasHeight <= Double(UInt32.max) else {
            throw HostError("replay_options_invalid")
        }
        let base = try await makeSavedScoreReplayPlan(workID: workID, derivationKind: "canvas_fit")
        let score = try ExactJSON(data: Data(base.work.score.utf8))
        let result = try SavedVariants.response(.object([
            "action": .string("fit_render"), "score": score,
            "drawn_on": .optional(base.work.renderCanvasAspectID ?? base.work.renderCanvasAspect),
            "paper": .string(paper.canvasID),
        ]))
        var render = try ExactJSON(data: base.renderRequest)
        render["request"]["score"] = try result.requiredObject("score")
        render["request"]["options"]["canvas_aspect_id"] = .string(paper.canvasID)
        render["request"]["options"]["canvas"] = .object([
            "width": .number(String(Int(paper.canvasWidth))), "height": .number(String(Int(paper.canvasHeight))),
        ])
        let plan = SavedScoreReplayPlan(work: base.work, parentNode: base.parentNode, context: base.context,
            renderRequest: render.data, derivationKind: "canvas_fit",
            derivationMetadata: try result.requiredObject("derivation_metadata").data,
            variationAmplitude: nil, variationSeed: nil)
        let candidate = try await previewSavedScoreReplay(plan)
        try Task.checkCancellation()
        return try await saveCandidate(executionID: candidate.executionID)
    }

    public func makeColorArrangementPage(workID: String, cursor: SavedVariantOrdinal) async throws -> ColorArrangementPage {
        let base = try await makeSavedScoreReplayPlan(workID: workID, derivationKind: "color_arrangement_change")
        guard base.work.renderSeed != nil else { throw HostError("saved_refinement_options_unavailable") }
        let request = try ExactJSON(data: base.renderRequest)
        let options = request["request"]["options"]
        let arguments: [String: ExactJSON] = ["svg": .string(base.work.svg),
            "color_map": options["resolved_color_map"], "work_id": .string(workID)]
        let page = try SavedVariants.response(.object(arguments.merging([
            "action": .string("color_plan"), "cursor": cursor.json]) { _, new in new }))
        var plans: [SavedScoreVariantPlan] = []
        for entry in page["entries"].array ?? [] {
            try Task.checkCancellation()
            let index = try SavedVariantOrdinal.read(entry["index"])
            let result = try SavedVariants.response(.object(arguments.merging([
                "action": .string("color_render"), "index": index.json,
                "catalog_id": options["catalog_id"]]) { _, new in new }))
            var render = request
            render["request"]["options"]["resolved_color_map"] = try result.requiredObject("color_map")
            let replay = SavedScoreReplayPlan(work: base.work, parentNode: base.parentNode, context: base.context,
                renderRequest: render.data, derivationKind: "color_arrangement_change",
                derivationMetadata: try result.requiredObject("derivation_metadata").data,
                variationAmplitude: nil, variationSeed: nil)
            plans.append(SavedScoreVariantPlan(index: index, ground: nil, replay: replay))
        }
        return ColorArrangementPage(plans: plans,
            nextCursor: page["next_cursor"] == .null ? nil : try SavedVariantOrdinal.read(page["next_cursor"]),
            total: try SavedVariantOrdinal.read(page["total"]))
    }

    public func makeGroundVariantPlans(workID: String) async throws -> [SavedScoreVariantPlan] {
        let base = try await makeSavedScoreReplayPlan(workID: workID, derivationKind: "ground_change")
        guard base.work.renderSeed != nil else { throw HostError("saved_refinement_options_unavailable") }
        let score = try ExactJSON(data: Data(base.work.score.utf8))
        let request = try ExactJSON(data: base.renderRequest)
        let page = try SavedVariants.response(.object(["action": .string("ground_plan"), "score": score]))
        return try (page["entries"].array ?? []).map { entry in
            let material = try GroundMaterial(coreEntry: entry)
            let result = try SavedVariants.response(.object(["action": .string("ground_render"), "score": score,
                "source": .string(base.work.ddl ?? ""), "material": .string(material.value),
                "language": .optional(base.work.instructionLangResolved)]))
            var render = request
            render["request"]["score"] = try result.requiredObject("score")
            var replay = SavedScoreReplayPlan(work: base.work, parentNode: base.parentNode, context: base.context,
                renderRequest: render.data, derivationKind: "ground_change",
                derivationMetadata: try result.requiredObject("derivation_metadata").data,
                variationAmplitude: nil, variationSeed: nil)
            replay.retouchedSource = try result.requiredString("ddl")
            return SavedScoreVariantPlan(index: nil, ground: material, replay: replay)
        }
    }

    public func previewSavedScoreVariant(_ plan: SavedScoreVariantPlan) async throws -> PreparedCandidate {
        try await previewSavedScoreReplay(plan.replay)
    }
}
