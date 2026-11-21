import Foundation
import XCTest
@testable import InkuPersistence

final class WorkPackTests: XCTestCase {
    private func fixture() -> URL {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        return root.appendingPathComponent("persistence/fixtures/workpack-minimal.inkupack")
    }
    func testFixtureImportDuplicateAndRoundTrip() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("workpack-tests-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let db = try InkuDatabase(url: directory.appendingPathComponent("test.sqlite"))
        let reader = try WorkPackReader(url: fixture())
        XCTAssertEqual(reader.counts["history"], 3)
        let plan = try await db.importWorkPack(reader)
        XCTAssertEqual(plan.workIDs, ["work-0", "work-1", "work-2"])
        XCTAssertEqual(plan.nodeRoots["node-2"], "node-0")
        let duplicate = try await db.importWorkPack(reader)
        XCTAssertEqual(duplicate.skipped, 3)
        let saved = try await db.work(id: "work-0")
        XCTAssertEqual(saved?.renderSeed, "18446744073709551615")
        XCTAssertEqual(saved?.score, "{\"instructions\":[]}")
        let output = directory.appendingPathComponent("out.inkupack")
        try await db.exportWorkPack(ids: ["work-0", "work-1", "work-2"], to: output, host: "test", appVersion: "1", build: 1)
        let lines = try Data(contentsOf: output).split(separator: 10)
        XCTAssertTrue(lines.contains(Data(#"{"for_revision":1,"history_id":"work-1","kind":"annotation","note":"fixture note"}"#.utf8)))
        for (index, line) in lines.enumerated() {
            var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(line)) as? [String: Any])
            let request: [String: Any]
            if index == 0 {
                request = ["kind": "header", "exported_at": try XCTUnwrap(object["exported_at"]),
                           "producer": try XCTUnwrap(object["producer"]), "counts": try XCTUnwrap(object["counts"])]
            } else {
                request = ["kind": try XCTUnwrap(object.removeValue(forKey: "kind")), "record": object]
            }
            XCTAssertEqual(try WorkPackWire.encode(request), Data(line), "Core's canonical bytes for line \(index + 1)")
        }
        let reread = try WorkPackReader(url: output)
        XCTAssertEqual(reread.counts, reader.counts)
        let other = try InkuDatabase(url: directory.appendingPathComponent("other.sqlite"))
        let roundtrip = try await other.importWorkPack(reread)
        XCTAssertEqual(roundtrip.workIDs.count, 3)
        let copied = try await other.work(id: "work-0")
        XCTAssertEqual(copied?.renderSeed, saved?.renderSeed)
        XCTAssertEqual(copied?.score, saved?.score)
        let subset = directory.appendingPathComponent("subset.inkupack")
        try await db.exportWorkPack(ids: ["work-1", "work-2"], to: subset, host: "test", appVersion: "1", build: 1)
        let subsetReader = try WorkPackReader(url: subset)
        let partial = try InkuDatabase(url: directory.appendingPathComponent("partial.sqlite"))
        let subsetResult = try await partial.importWorkPack(subsetReader)
        XCTAssertEqual(subsetResult.nodeRoots, ["node-1": "node-1", "node-2": "node-1"])
        XCTAssertEqual(subsetResult.edgeIDs, ["edge-2"])
    }
    func testPlannerMissingParentAndCollision() throws {
        let records: [WorkPackRecordIdentity] = [
            .init(kind: "history", key: "child", identity: ["id": "child", "node_id": "c"]),
            .init(kind: "history", key: "grandchild", identity: ["id": "grandchild", "node_id": "g"]),
            .init(kind: "lineage_node", key: "c", identity: ["id": "c", "history_id": "child"]),
            .init(kind: "lineage_node", key: "g", identity: ["id": "g", "history_id": "grandchild"]),
            .init(kind: "lineage_edge", key: "missing", identity: ["id": "missing", "parent": "p", "child": "c"]),
            .init(kind: "lineage_edge", key: "edge", identity: ["id": "edge", "parent": "c", "child": "g"])
        ]
        let counts = ["history": 2, "lineage_node": 2, "lineage_edge": 2, "annotation": 0, "colophon": 0]
        let plan = try WorkPackWire.plan(counts: counts, records: records, existing: .init())
        XCTAssertEqual(plan.nodeRoots, ["c": "c", "g": "c"])
        XCTAssertEqual(plan.edgeIDs, ["edge"])
        let duplicate = try WorkPackWire.plan(counts: counts, records: records,
                                              existing: .init(works: ["child"], nodeRoots: ["c": "c"]))
        XCTAssertEqual(duplicate.skipped, 1)
        XCTAssertEqual(duplicate.nodeRoots["g"], "c")
    }

    func testReadsLegacySwiftEscapesAndOmitsEmptyAnnotationOnExport() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("workpack-legacy-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let lines = try Data(contentsOf: fixture()).split(separator: 10)
        var legacy = Data()
        for line in lines {
            var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(line)) as? [String: Any])
            if object["kind"] as? String == "annotation" {
                object["note"] = ""
                object["for_revision"] = 0
            }
            if object["id"] as? String == "work-0" {
                object["draw_route"] = "must stay local"
            }
            legacy.append(try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .fragmentsAllowed]))
            legacy.append(10)
        }
        XCTAssertTrue(String(decoding: legacy, as: UTF8.self).contains(#"\/"#))
        XCTAssertTrue(String(decoding: legacy, as: UTF8.self).contains(#""note":"""#))
        let old = directory.appendingPathComponent("legacy.inkupack")
        try legacy.write(to: old)
        let reader = try WorkPackReader(url: old)
        XCTAssertEqual(reader.counts["annotation"], 1)
        let db = try InkuDatabase(url: directory.appendingPathComponent("test.sqlite"))
        let imported = try await db.importWorkPack(reader)
        XCTAssertEqual(imported.workIDs, ["work-0", "work-1", "work-2"])
        let importedWork = try await db.work(id: "work-0")
        XCTAssertNil(importedWork?.drawRoute)

        let output = directory.appendingPathComponent("out.inkupack")
        try await db.exportWorkPack(ids: imported.workIDs, to: output, host: "test", appVersion: "1", build: 1)
        let exported = try String(contentsOf: output, encoding: .utf8)
        XCTAssertFalse(exported.contains(#"\/"#))
        XCTAssertFalse(exported.contains(#""kind":"annotation""#))
        XCTAssertFalse(exported.contains(#""draw_route""#))
        XCTAssertEqual(try WorkPackReader(url: output).counts["annotation", default: 0], 0)
    }

    func testConstraintFailureRollsBackEveryWork() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("workpack-rollback-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let db = try InkuDatabase(url: directory.appendingPathComponent("test.sqlite"))
        let reader = try WorkPackReader(url: fixture())
        _ = try await db.importWorkPack(reader)
        let text = try String(contentsOf: fixture(), encoding: .utf8)
            .replacingOccurrences(of: "work-", with: "other-work-")
            .replacingOccurrences(of: "node-", with: "other-node-")
            .replacingOccurrences(of: "edge-", with: "other-edge-")
        let file = directory.appendingPathComponent("collision.inkupack")
        try text.write(to: file, atomically: true, encoding: .utf8)
        let collision = try WorkPackReader(url: file)
        do { _ = try await db.importWorkPack(collision); XCTFail("duplicate colophon must fail") }
        catch { }
        let newWork = try await db.work(id: "other-work-0")
        XCTAssertNil(newWork)
        let edgeCollision = text.replacingOccurrences(of: "other-edge-", with: "edge-")
            .replacingOccurrences(of: "colophon-1", with: "other-colophon-1")
        try edgeCollision.write(to: file, atomically: true, encoding: .utf8)
        let edgeReader = try WorkPackReader(url: file)
        do { _ = try await db.importWorkPack(edgeReader); XCTFail("duplicate edge must fail") }
        catch { }
        let rolledBack = try await db.work(id: "other-work-0")
        XCTAssertNil(rolledBack)
    }

    func testRejectsTruncationAndNewerVersion() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("workpack-invalid-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let text = try String(contentsOf: fixture(), encoding: .utf8)
        let file = directory.appendingPathComponent("bad.inkupack")
        try String(text.dropLast()).write(to: file, atomically: true, encoding: .utf8)
        XCTAssertThrowsError(try WorkPackReader(url: file))
        try text.replacingOccurrences(of: "\"format_version\":1", with: "\"format_version\":2").write(to: file, atomically: true, encoding: .utf8)
        XCTAssertThrowsError(try WorkPackReader(url: file)) { XCTAssertTrue($0 is WorkPackError) }
    }
}
