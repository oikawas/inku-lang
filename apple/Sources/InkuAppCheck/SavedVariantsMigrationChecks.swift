import CryptoKit
import Foundation
import InkuHost
import InkuPersistence

/// Failure: a shared-rule migration changes a saved work's deterministic variant results.
func runSavedVariantsInventory(databaseURL: URL, productURL: URL, outputURL: URL) async throws {
    guard databaseURL.lastPathComponent == "variants-check.sqlite", FileManager.default.fileExists(atPath: databaseURL.path),
          !FileManager.default.fileExists(atPath: outputURL.path) else { throw CheckFailure.message("Use a disposable variants-check.sqlite and fresh output") }
    guard FileManager.default.fileExists(atPath: productURL.appendingPathComponent("server/tests/data/saved-variant-cases.json").path) else {
        throw CheckFailure.message("Use the explicit product root containing the shared corpus")
    }
    func ask(_ request: ExactJSON) throws -> ExactJSON { try SavedVariants.response(request) }
    func digest(_ value: ExactJSON) throws -> ExactJSON {
        guard let canonical = value.canonicalText else { throw CheckFailure.message("Invalid variant audit result") }
        return .string(SHA256.hash(data: Data(canonical.utf8)).map { String(format: "%02x", $0) }.joined())
    }
    func projection(_ result: ExactJSON) throws -> ExactJSON {
        .object(["score": try digest(result["score"]), "ddl": result["ddl"], "metadata": result["derivation_metadata"]])
    }
    let database = try InkuDatabase(url: databaseURL), host = PipelineHost(database: database)
    var rows: [ExactJSON] = [], offset = 0
    while true {
        let works = try await database.list(limit: 1000, offset: offset)
        if works.isEmpty { break }
        for work in works {
            let score = try ExactJSON(data: Data(work.score.utf8))
            var record: ExactJSON = .object(["id": .string(work.id), "language": .optional(work.instructionLangResolved)])
            let groundPlan = try ask(.object(["action": .string("ground_plan"), "score": score]))
            record["grounds"] = groundPlan["entries"]
            var changedGrounds: [ExactJSON] = []
            for entry in groundPlan["entries"].array ?? [] {
                let request: ExactJSON = .object(["action": .string("ground_render"), "score": score, "source": .string(work.ddl ?? ""),
                    "material": entry["material"], "language": .optional(work.instructionLangResolved)])
                let result = try ask(request)
                var resultRow = try projection(result)
                resultRow["material"] = entry["material"]
                var english = request; english["language"] = .string("en")
                var japanese = request; japanese["language"] = .string("ja")
                resultRow["forced_en_ddl"] = try ask(english)["ddl"]
                resultRow["forced_ja_ddl"] = try ask(japanese)["ddl"]
                changedGrounds.append(resultRow)
            }
            record["ground_results"] = .array(changedGrounds)
            do {
                let context = try await host.savedAuthoringContext(workID: work.id)
                let config = try ExactJSON(data: context.configuration), options = try ExactJSON(data: context.renderOptions)
                do {
                var planRequest: ExactJSON = .object(["action": .string("tool_plan"), "config": config, "source": .string(work.ddl ?? ""),
                    "score": score, "mode": .string("uniform"), "seed": .integer(7)])
                let plan = try ask(planRequest)
                record["tool_labels"] = plan["tool_labels"]; record["drawn_tools"] = plan["sentences"]
                record["uniform_count"] = .integer(plan["entries"].array?.count ?? 0)
                planRequest["mode"] = .string("per_sentence")
                record["per_sentence_count"] = .integer(try ask(planRequest)["entries"].array?.count ?? 0)
                var tools: [ExactJSON] = []
                for label in plan["tool_labels"].array ?? [] {
                    let value = try label.requiredString("value")
                    let sentences = plan["sentences"].array ?? []
                    if sentences.isEmpty || sentences.allSatisfy({ $0["tool"].string == value }) { continue }
                    let assignments = Dictionary(uniqueKeysWithValues: try sentences.map {
                        (try $0.requiredIndexText("index"), ExactJSON.string(value))
                    })
                    let result = try ask(.object(["action": .string("tool_render"), "config": config, "source": .string(work.ddl ?? ""),
                        "score": score, "mode": .string("uniform"), "tools": .object(assignments)]))
                    var resultRow = try projection(result); resultRow["tool"] = .string(value); tools.append(resultRow)
                }
                record["tool_results"] = .array(tools)
                } catch { record["tool_refused"] = .bool(true); record["tool_error"] = .string(error.localizedDescription) }
                // Use the actual saved rendering options for color-map resolution.
                let colorMap = options["resolved_color_map"]
                do {
                    let base: [String: ExactJSON] = ["svg": .string(work.svg), "color_map": colorMap, "work_id": .string(work.id)]
                    let first = try ask(.object(base.merging(["action": .string("color_plan"), "cursor": .integer(0)]) { _, new in new }))
                    record["color_first"] = .object(["entries": first["entries"], "next_cursor": first["next_cursor"], "total": first["total"]])
                    guard let total = UInt64(first["total"].number ?? first["total"].string ?? "") else { throw CheckFailure.message("Audit sample count is not UInt64") }
                    let lastCursor = total > 8 ? total - 8 : 0
                    let last = try ask(.object(base.merging(["action": .string("color_plan"), "cursor": .integer(lastCursor)]) { _, new in new }))
                    record["color_last"] = .object(["entries": last["entries"], "next_cursor": last["next_cursor"], "total": last["total"]])
                    let indices = Array(Set(Array(UInt64(0)..<min(8, total)) + Array(lastCursor..<total))).sorted()
                    var maps: [ExactJSON] = []
                    for index in indices {
                        let result = try ask(.object(base.merging(["action": .string("color_render"), "index": .integer(index),
                            "catalog_id": options["catalog_id"]]) { _, new in new }))
                        maps.append(.object(["index": .integer(index), "map": try digest(result["color_map"]), "metadata": result["derivation_metadata"]]))
                    }
                    record["color_maps"] = .array(maps)
                } catch { record["color_refused"] = .bool(true); record["color_error"] = .string(error.localizedDescription) }
            } catch { record["context_error"] = .string(error.localizedDescription) }
            rows.append(record)
        }
        offset += works.count
    }
    try ExactJSON.array(rows).data.write(to: outputURL, options: .withoutOverwriting)
    print("Saved variants inventory: works=\(rows.count), contextFailures=\(rows.filter { $0["context_error"].string != nil }.count), colorRefusals=\(rows.filter { $0["color_refused"].bool == true }.count). Planning/rule calls only; renders, saves and providers=0.")
}

private extension ExactJSON {
    func requiredIndexText(_ key: String) throws -> String {
        guard let value = self[key].number ?? self[key].string else { throw CheckFailure.message("Missing variant ordinal") }
        return value
    }
}
