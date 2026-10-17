import Foundation
import InkuHost
import InkuUI

/// Failure: the Swift wire boundary disagrees with a shared saved-variant fixture,
/// truncates a core ordinal, or changes a refusal's user-visible detail.
@MainActor
func runSharedSavedVariantChecks(casesURL: URL, folder: URL) async throws {
    let cases = try ExactJSON(data: Data(contentsOf: casesURL))
    let url = folder.appendingPathComponent("works.sqlite")
    guard !FileManager.default.fileExists(atPath: url.path) else { throw CheckFailure.message("Use a fresh saved-variant fixture") }
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let app = AppModel(databaseURL: url, transport: SharedVariantsNoProvider())
    await app.initialize()
    app.language = "en"; app.seedText = "42"
    let source = "Place 1 red circle.\nPlace 1 blue circle.\nPlace 1 green circle.\nPlace 1 black circle."
    guard await app.drawNewDDL(source), let work = app.selectedWork else {
        throw CheckFailure.message("Shared variants configuration fixture failed: \(app.errorText ?? app.status)")
    }
    let config = try ExactJSON(data: await app.savedConfiguration(workID: work.id).configuration)
    func require(_ condition: Bool, _ detail: String) throws {
        if !condition { throw CheckFailure.message("Shared saved variants: " + detail) }
    }
    func ask(_ action: String, _ fields: [String: ExactJSON]) throws -> ExactJSON {
        try SavedVariants.response(.object(fields.merging(["action": .string(action)]) { _, new in new }))
    }
    let conditions = cases["conditions"]
    try require(try SavedVariants.groundMaterials().map(\.value) == conditions["ground_materials"].array?.compactMap(\.string), "ground vocabulary/order")
    var counts: [String: Int] = [:]
    for row in cases["tools"].array ?? [] {
        let args: [String: ExactJSON] = ["config": config, "source": .string(source), "score": row["score"], "seed": .integer(7)]
        for mode in ["uniform", "per_sentence"] {
            let request = args.merging(["mode": .string(mode)]) { _, new in new }
            let result = try ask("tool_plan", request)
            try require(try result == ask("tool_plan", request), "fixed-seed tool plan is unstable")
            try require(result["tool_labels"].array?.compactMap { $0["value"].string } == conditions["tools"].array?.compactMap(\.string), "tool vocabulary")
            let sentences = result["sentences"].array ?? []
            try require(.array(sentences.map { $0["index"] }) == row["sentences"], "changeable sentence indices")
            var drawn: [String: ExactJSON] = [:]
            for sentence in sentences { drawn[sentence["index"].number!] = sentence["tool"] }
            try require(.object(drawn) == row["drawn"], "drawn tool readback")
            let entries = result["entries"].array ?? []
            try require(entries.count == 4 && Set(entries.map { $0["tools"].text }).count == 4, "four distinct tool options")
            for entry in entries {
                let tools = entry["tools"].object ?? [:]
                try require(!tools.isEmpty, "empty tool assignment")
                if mode == "uniform" { try require(Set(tools.values.compactMap(\.string)).count == 1, "nonuniform assignment") }
                else { try require(tools.allSatisfy { row["drawn"][$0.key] != $0.value }, "unchanged per-sentence tool") }
            }
        }
        let rendered = try ask("tool_render", ["config": config, "source": .string(source), "score": row["score"],
            "mode": .string("uniform"), "tools": row["asked"]])
        try require(rendered["score"] == row["score_with_tools"], "tool substitution")
        try require(rendered["derivation_metadata"]["tools"] == row["asked"], "tool metadata")
        counts["tools", default: 0] += 1
    }
    for row in cases["grounds"].array ?? [] {
        let plan = try ask("ground_plan", ["score": row["score"]])
        try require(plan["current"] == row["current"] && .array((plan["entries"].array ?? []).map { $0["material"] }) == row["entries"], "ground candidates/current")
        for (material, expected) in row["score_with_ground"].object ?? [:] {
            let result = try ask("ground_render", ["score": row["score"], "source": .string(""), "material": .string(material), "language": .string("en")])
            try require(result["score"] == expected, "ground Score replacement")
            try require(result["derivation_metadata"] == .object(["ground_material": .string(material), "parent_ground_material": row["current"]]), "ground metadata")
        }
        counts["grounds", default: 0] += 1
    }
    let groundScore: ExactJSON = .object(["canvas": .object(["ground": .object(["material": .string("washi")])])])
    for row in cases["ground_sentences"].array ?? [] {
        for (material, expected) in row["results"].object ?? [:] {
            let result = try ask("ground_render", ["score": groundScore, "source": row["ddl"], "material": .string(material), "language": row["language"]])
            try require(result["ddl"] == expected, "ground sentence/language: " + (row["why"].string ?? ""))
        }
        counts["ground_sentences", default: 0] += 1
    }
    for row in cases["colors"].array ?? [] {
        let args: [String: ExactJSON] = ["svg": row["svg"], "color_map": row["color_map"], "work_id": row["work_id"]]
        for (cursor, expected) in row["pages"].object ?? [:] {
            let result = try ask("color_plan", args.merging(["cursor": .string(cursor)]) { _, new in new })
            try require(result["total"] == row["total"] && result["entries"] == expected["entries"] && result["next_cursor"] == expected["next_cursor"], "color page/total")
        }
        for (index, expected) in row["color_maps"].object ?? [:] {
            let result = try ask("color_render", args.merging(["index": .string(index), "catalog_id": .string("fixture")]) { _, new in new })
            try require(result["color_map"] == expected, "color replacement/composition")
            try require(result["derivation_metadata"] == .object(["color_arrangement_index": .number(index), "catalog_id": .string("fixture")]), "exact color metadata")
        }
        counts["colors", default: 0] += 1
    }
    for row in cases["color_refusals"].array ?? [] {
        do {
            _ = try ask("color_render", ["svg": row["svg"], "color_map": row["color_map"], "work_id": row["work_id"], "index": row["index"], "catalog_id": .string("fixture")])
            throw CheckFailure.message("Expected color refusal")
        } catch let refusal as SavedVariantRefusal {
            try require(refusal.detail == row["detail"].string && refusal.localizedDescription == refusal.detail, "refusal detail")
        }
        counts["color_refusals", default: 0] += 1
    }

    // Failure: a valid core page above UInt64 gets truncated by the Swift host/UI.
    let colors = (1...21).map { String(format: "#%06x", $0) }
    let svg = "<svg>" + colors.map { "<rect fill=\"\($0)\"/>" }.joined() + "</svg>"
    let map = ExactJSON.object(Dictionary(uniqueKeysWithValues: colors.enumerated().map { ("palette:\($0.offset)", ExactJSON.string($0.element)) }))
    let last = "51090942171709439998"
    let page = try ask("color_plan", ["svg": .string(svg), "color_map": map, "work_id": .string("wide-ordinal"), "cursor": .string(last)])
    try require(page["total"].string == "51090942171709439999" && page["entries"] == .array([.object(["index": .string(last)])]) && page["next_cursor"] == .null, "wide ordinal transport")
    try require(SavedVariantOrdinal(rawValue: last)?.displayNumber == "51090942171709439999" && SavedVariantOrdinal(rawValue: "999")?.displayNumber == "1000", "one-based wide label")
    _ = try ask("color_render", ["svg": .string(svg), "color_map": map, "work_id": .string("wide-ordinal"), "index": .string(last), "catalog_id": .string("wide")])
    print("Shared saved variants PASS: \(counts.sorted { $0.key < $1.key }); includes all 13 colors/6,227,020,799 arrangements and >UInt64 transport/labels. Provider=0.")
}

private actor SharedVariantsNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw CheckFailure.message("Shared variants checks must not call a provider")
    }
}
