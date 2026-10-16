import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Failures: a tall card reduces every row; unordered/missing measurements shift row boundaries;
/// duplicate batch labels acquire the wrong identity; canvas search leaks into library or treats wildcards as SQL.
@MainActor
func runLibraryParityChecks() async throws {
    let mixed = [100.25, 120.5, 80.25, 90.125, 95.5, 94.0]
    guard LibraryGridPaging.pageSize(width: 292, height: 322.125, cardHeights: mixed) == 6,
          LibraryGridPaging.pageSize(width: 292, height: 322.124, cardHeights: mixed) == 4,
          LibraryGridPaging.pageSize(width: 292, height: 225, cardHeights: [120, 100, 90, 80]) == 4,
          LibraryGridPaging.pageSize(width: 0, height: 100, cardHeights: []) == 1,
          LibraryGridPaging.pageSize(width: 292, height: 250, cardHeights: [100, .nan, 0]) == 4 else {
        throw CheckFailure.message("Library rows lost order, fractional boundary or unknown-row fallback")
    }
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-library-parity-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    let runs = [String(repeating: "a", count: 32), String(repeating: "b", count: 32), String(repeating: "c", count: 32), String(repeating: "d", count: 32)]
    for (index, run) in runs.enumerated() {
        _ = try await database.compareAndSwapExecution(id: run, expectedRevision: nil, snapshot: Data("{}".utf8))
        let provenance: [String: Any] = index < 2 ? ["batchRunID": run, "batchLineNumber": 280] : [:]
        let performance: [String: Any] = ["presentation": ["provenance": provenance],
            "authority": ["origin": index == 2 ? "direct_ddl" : "stage1_generated"]]
        let ack = try JSONSerialization.data(withJSONObject: ["work_id": index == 3 ? "wrong" : run + "_0", "performance": performance])
        _ = try await database.commitEffect(id: run, expectedRevision: 0, effectID: "save-render:0", snapshot: Data("{}".utf8), acknowledgement: ack)
    }
    let host = PipelineHost(database: database)
    let ids = runs.map { $0 + "_0" }
    let labels = try await host.savedDisplayLabels(workIDs: ids + ["missing"])
    guard labels[ids[0]] == "#280", labels[ids[1]] == "#280", labels[ids[2]] == "DDL",
          labels[ids[3]] == nil, labels["missing"] == nil, labels.count == 3 else {
        throw CheckFailure.message("Saved label projection fabricated a label or confused independent run identities")
    }
    let firstID = "12345678-abcd-4321-abcd-123456789abc"
    let works = [
        SavedWork(id: firstID, at: 3, input: "old input", score: "{}", svg: "", sourceText: "Spring 100%_literal", ddl: "DDL-ONLY", renderHash: "v82:abcdef1234", descriptionHash: "dh19:998877aacc", lineageNodeID: "node-" + firstID),
        SavedWork(id: "other", at: 2, input: "Spring 100XXliteral", score: "{}", svg: "", renderHash: "v82:ffee7788", lineageNodeID: "node-other"),
        SavedWork(id: ids[0], at: 1, input: "native", score: "{}", svg: "", lineageNodeID: "node-" + ids[0])
    ]
    for work in works { try await database.save(work, node: LineageNode(id: "node-" + work.id, historyID: work.id, at: work.at)) }
    func search(_ text: String, canvas: Bool = true) async throws -> [String] {
        try await database.libraryPage(query: LibraryQuery(text: text, canvasSearch: canvas), limit: 20).items.map(\.id)
    }
    guard try await search(firstID.uppercased()) == [firstID],
          try await search("12345678-abcd-4321-abcd-123456789ab") == [],
          try await search("100%_literal") == [firstID],
          try await search("spring").count == 2,
          try await search("abcdef") == [firstID],
          try await search("1234") == [firstID],
          try await search("dh19:9988") == [firstID],
          try await search("aacc") == [firstID],
          try await search("DDL-ONLY") == [],
          try await search("DDL-ONLY", canvas: false) == [firstID],
          try await search(ids[0].uppercased()) == [ids[0]] else {
        throw CheckFailure.message("Canvas UUID/description/hash matching or independent library contract changed")
    }
    let canvas = HistoryModel()
    let library = LibraryModel()
    canvas.library.query = "needle"
    guard canvas.library.filter.canvasSearch, !library.filter.canvasSearch, library.query.isEmpty else {
        throw CheckFailure.message("Canvas query leaked into library state")
    }
    guard try await database.list() == works else { throw CheckFailure.message("Browsing modified saved records") }
    print("Library parity passed: ordered mixed/fractional/unknown rows; saved label identity and invalid acknowledgement; independent literal canvas UUID/description/both hashes.")
}
