import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

/// Failure: identity, language and editor labels drift when the native host copies core rules.
@MainActor
func runSharedCoreStep1Checks(casesDirectory: URL) async throws {
    func table(_ name: String) throws -> ExactJSON {
        try ExactJSON(data: Data(contentsOf: casesDirectory.appendingPathComponent(name)))
    }
    func rows(_ table: ExactJSON, _ key: String) throws -> [ExactJSON] {
        guard let values = table[key].array, !values.isEmpty else { throw CheckFailure.message("Missing shared cases: \(key)") }
        return values
    }
    func equal(_ actual: String?, _ expected: String?, _ why: String) throws {
        let matches: Bool
        if let actual, let expected { matches = actual.utf8.elementsEqual(expected.utf8) }
        else { matches = actual == nil && expected == nil }
        guard matches else { throw CheckFailure.message("Shared core mismatch: \(why)") }
    }
    let identity = try table("identity-cases.json")
    let descriptionCases = try rows(identity, "description_hash")
    for row in descriptionCases {
        try equal(WorkIdentity.description(try row.requiredString("text")), row["dh1"].string, row["why"].string ?? "dh1")
    }
    let canonicalCases = try rows(identity, "canonical_json")
    var exactCanonicalCount = 0
    for row in canonicalCases {
        let input = try row.requiredString("input")
        try equal(InkuCore.canonicalJSON(input), row["canonical"].string, row["why"].string ?? "canonical JSON")
        // ExactJSON intentionally rejects duplicate keys; the raw core entry still checks those rows above.
        if let exact = try? ExactJSON(data: Data(input.utf8)) {
            try equal(exact.canonicalText, row["canonical"].string, row["why"].string ?? "ExactJSON canonical form")
            exactCanonicalCount += 1
        }
    }
    let renderCases = try rows(identity, "render_hash")
    for row in renderCases {
        try equal(InkuCore.renderHash(itemJSON: try row.requiredString("item")), row["rh3"].string, row["why"].string ?? "rh3")
    }
    let sample = try ExactJSON(data: Data(renderCases[0].requiredString("item").utf8))
    let sampleOptions: ExactJSON = .object(["render_seed": sample["render_seed"], "wild": sample["render_wild"],
        "catalog_id": sample["render_color_catalog_id"]])
    let sampleMetadata: ExactJSON = .object(["render_engine_id": sample["render_engine_id"],
        "render_engine_version": sample["render_engine_version"]])
    try equal(try WorkIdentity.render(score: sample["score"], options: sampleOptions, metadata: sampleMetadata),
        renderCases[0]["rh3"].string, "host render fields")
    let spaces = try rows(identity, "python_space")
    let description = try descriptionCases[0].requiredString("text")
    for value in spaces {
        guard let number = value.number.flatMap(UInt32.init), let scalar = Unicode.Scalar(number) else {
            throw CheckFailure.message("Invalid shared whitespace scalar")
        }
        let pad = String(scalar)
        try equal(WorkIdentity.description(pad + description + pad), descriptionCases[0]["dh1"].string, "dh1 whitespace \(number)")
    }

    let languages = try table("instruction-language-cases.json")
    let normalizeCases = try rows(languages, "normalize"), resolveCases = try rows(languages, "resolve")
    for row in normalizeCases {
        try equal(InkuCore.normalizeInstructionLanguage(value: row["value"].string, defaultLanguage: try row.requiredString("default")),
            row["language"].string, row["why"].string ?? "normalize language")
    }
    for row in resolveCases {
        try equal(InkuCore.resolveInstructionLanguage(text: try row.requiredString("text"), requested: row["requested"].string,
            fallback: try row.requiredString("fallback")), row["language"].string, row["why"].string ?? "resolve language")
    }
    // No provider or production preferences: exercise the actual UI adapters with a temporary database path.
    let model = AppModel(databaseURL: FileManager.default.temporaryDirectory.appendingPathComponent("language-\(UUID().uuidString).sqlite"))
    for row in resolveCases where row["language"].string != nil {
        let requested = row["requested"].string ?? "auto", fallback = try row.requiredString("fallback")
        if ["auto", "ja", "en"].contains(requested), ["ja", "en"].contains(fallback) {
            model.language = requested; model.display.preferences.language = fallback
            try equal(model.instructionLanguage(for: try row.requiredString("text")), row["language"].string, "AppModel language")
        }
    }
    guard CanvasInteraction.supportsVerticalCaption("redの円"), !CanvasInteraction.supportsVerticalCaption("123"),
          !CanvasInteraction.supportsVerticalCaption("ＡＢＣ"), !CanvasInteraction.supportsVerticalCaption("ｱｲｳ") else {
        throw CheckFailure.message("Vertical-caption language adapter drifted")
    }

    let labelCases = try rows(try table("description-label-cases.json"), "cases")
    for row in labelCases {
        let text = try row.requiredString("text")
        try equal(DescriptionLabels.pipelineDescription(text), row["pipeline"].string, row["why"].string ?? "label text")
        let coreSpans = try ExactJSON(data: InkuCore.descriptionLabelSpans(text))
        guard coreSpans == row["spans"] else { throw CheckFailure.message("Shared label scalar spans differ: \(row["why"].string ?? "")") }
        let scalars = text.unicodeScalars
        let expected = try (row["spans"].array ?? []).map { value -> (NSRange, String) in
            guard let fields = value.array, let start = fields[0].number.flatMap(Int.init),
                  let end = fields[1].number.flatMap(Int.init), let kind = fields[2].string else {
                throw CheckFailure.message("Invalid shared label range")
            }
            let lower = scalars.index(scalars.startIndex, offsetBy: start), upper = scalars.index(scalars.startIndex, offsetBy: end)
            return (NSRange(lower..<upper, in: text), kind)
        }
        let actual = DescriptionLabels.excludedSpans(text)
        guard actual.count == expected.count, zip(actual, expected).allSatisfy({ $0.0.range == $0.1.0 && $0.0.kind.rawValue == $0.1.1 }) else {
            throw CheckFailure.message("Label UTF-16 projection differs: \(row["why"].string ?? "")")
        }
    }
    let unicodeText = "😀a[注]e\u{301}［x］"
    let unicodeSpans = DescriptionLabels.excludedSpans(unicodeText)
    guard unicodeSpans.map(\.range) == [NSRange(location: 3, length: 3), NSRange(location: 8, length: 3)],
          unicodeSpans.allSatisfy({ $0.kind == .comment }),
          DescriptionLabels.pipelineDescription(unicodeText).utf8.elementsEqual("😀ae\u{301}".utf8) else {
        throw CheckFailure.message("Non-BMP/combining label positions drifted")
    }
    let multiline = "1. 😀[😀]\n2. e\u{301}［x］"
    let multilineSpans = DescriptionLabels.excludedSpans(multiline)
    guard multilineSpans.map(\.range) == [NSRange(location: 0, length: 3), NSRange(location: 5, length: 4),
        NSRange(location: 10, length: 3), NSRange(location: 15, length: 3)],
          multilineSpans.map(\.kind) == [.number, .comment, .number, .comment],
          DescriptionLabels.pipelineDescription(multiline).utf8.elementsEqual("😀\ne\u{301}".utf8) else {
        throw CheckFailure.message("Multiline scalar/UTF-16 label conversion drifted")
    }
    guard InkuCore.canonicalJSON("{\"a\":}") == nil, InkuCore.renderHash(itemJSON: "[]") == nil else {
        throw CheckFailure.message("Invalid identity input was accepted")
    }
    print("Shared core step1 passed: dh1=\(descriptionCases.count), canonical=\(canonicalCases.count) (ExactJSON=\(exactCanonicalCount)), rh3=\(renderCases.count), whitespace=\(spaces.count), language normalize=\(normalizeCases.count)/resolve=\(resolveCases.count), labels=\(labelCases.count); host fields, UI language, UTF-16 non-BMP/combining ranges and invalid input checked. Provider calls=0.")
}

/// Recompute identities on a disposable SQLite Backup API copy, including trashed and lineage-only rows.
func runWorkIdentityInventory(databaseURL: URL, outputURL: URL) async throws {
    guard databaseURL.lastPathComponent == "identity-check.sqlite", FileManager.default.fileExists(atPath: databaseURL.path),
          !FileManager.default.fileExists(atPath: outputURL.path) else {
        throw CheckFailure.message("Use an existing disposable identity-check.sqlite and a fresh output path")
    }
    let database = try InkuDatabase(url: databaseURL)
    var rows: [IdentityInventoryRow] = []
    var offset = 0
    while true {
        let works = try await database.list(limit: 1000, offset: offset)
        if works.isEmpty { break }
        for work in works {
            let options: ExactJSON = .object([
                "render_seed": .optional(work.renderSeed), "wild": work.renderWild.map(ExactJSON.bool) ?? .null,
                "catalog_id": .optional(work.renderColorCatalogID ?? work.catalogID)])
            let metadata: ExactJSON = .object([
                "render_engine_id": .optional(work.renderEngineID), "render_engine_version": .optional(work.renderEngineVersion)])
            let render: String?, error: String?
            do {
                render = try WorkIdentity.render(score: ExactJSON(data: Data(work.score.utf8)), options: options, metadata: metadata)
                error = nil
            } catch let failure {
                render = nil; error = String(describing: failure)
            }
            rows.append(IdentityInventoryRow(id: work.id, storedDescription: work.descriptionHash,
                calculatedDescription: WorkIdentity.description(work.input), storedRender: work.renderHash,
                calculatedRender: render, renderError: error))
        }
        offset += works.count
    }
    let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(rows).write(to: outputURL, options: .withoutOverwriting)
    print("Identity inventory: rows=\(rows.count) storedDh1Mismatches=\(rows.filter { $0.storedDescription != nil && $0.storedDescription != $0.calculatedDescription }.count) storedRh3Mismatches=\(rows.filter { $0.storedRender != nil && $0.storedRender != $0.calculatedRender }.count) renderErrors=\(rows.filter { $0.renderError != nil }.count). No work writes or provider calls.")
}

private struct IdentityInventoryRow: Encodable {
    let id: String
    let storedDescription: String?
    let calculatedDescription: String
    let storedRender: String?
    let calculatedRender: String?
    let renderError: String?
}
