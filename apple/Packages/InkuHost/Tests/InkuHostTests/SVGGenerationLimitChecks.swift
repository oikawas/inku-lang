import XCTest
import Foundation
import InkuPersistence
@testable import InkuHost

final class SVGGenerationLimitChecks: XCTestCase, @unchecked Sendable {
    // Failure: a captured request keeps an old limit, invalid edits overwrite it, or character/JSON size replaces UTF-8 body bytes.
    func testLiveSavedSettingAndUTF8BodyBoundary() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-svg-limit-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = directory.appendingPathComponent("providers.json")
        let store = ProviderSettingsStore(url: url)
        let initial = try await store.svgLimitBytes()
        XCTAssertEqual(initial, 12 * 1_024 * 1_024)
        // Existing settings without the new member retain the recommended default.
        try await store.save(.init())
        var selected = try await store.load()
        selected.svgLimitMiB = 32
        try await store.save(selected)
        let reopened = ProviderSettingsStore(url: url)
        let maximum = try await reopened.svgLimitBytes()
        XCTAssertEqual(maximum, 32 * 1_024 * 1_024)
        selected.svgLimitMiB = 1
        try await store.save(selected)
        let live = try await reopened.svgLimitBytes()
        XCTAssertEqual(live, 1_024 * 1_024)
        for invalid in [0, 33] {
            selected.svgLimitMiB = invalid
            do { try await store.save(selected); XCTFail("Invalid SVG limit was saved") }
            catch let error as HostError { XCTAssertEqual(error.code, "invalid_svg_limit") }
        }
        let retained = try await reopened.svgLimitBytes()
        XCTAssertEqual(retained, live)
        for invalid in ["", "0", "33", "1.5", "12 MiB", "-1", "１２"] {
            XCTAssertThrowsError(try SVGGenerationLimit.parse(invalid))
        }
        XCTAssertEqual(try SVGGenerationLimit.parse(" 12 "), 12)
        let body = String(repeating: "あ", count: 349_525) + "x"
        XCTAssertEqual(body.utf8.count, 1_024 * 1_024)
        XCTAssertNoThrow(try SVGGenerationLimit.validate(body, maximumBytes: live))
        XCTAssertThrowsError(try SVGGenerationLimit.validate(body + "x", maximumBytes: live)) { error in
            XCTAssertEqual((error as? HostError)?.code, "svg_too_large")
        }
        // JSON escapes are a transport detail, even when they exceed the admitted body's byte count.
        let escaped = String(repeating: "\"", count: Int(live))
        XCTAssertGreaterThan(try JSONEncoder().encode(escaped).count, Int(live))
        XCTAssertNoThrow(try SVGGenerationLimit.validate(escaped, maximumBytes: live))
    }

    // Failure: restoring a host refusal exposes the old success or resumes score_ready and saves automatically.
    func testDurableRefusalNeverResumesOrSaves() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-svg-refusal-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let database = try InkuDatabase(url: directory.appendingPathComponent("works.sqlite"))
        let executionID = "svg-refusal-fixture"
        let snapshot: ExactJSON = .object([
            "execution_id": .string(executionID), "variation_id": .string("fixture"), "sequence": .string("7"),
            "authority": .object(["revision": .string("1"), "authority": .string("ddl_authoritative"), "origin": .string("user_authored_ddl")]),
            "phase": .object(["tag": .string("score_ready")]), "config": .object([:]),
            "document": .object(["source": .string("fixture source")]), "delivery": .object(["score": .object([:])]),
        ])
        let events: ExactJSON = .array([.object(["tag": .string("failed"), "sequence": .string("7"),
            "payload": .object(["stage": .string("render"), "reason": .string("svg_too_large"), "svg_limit_mib": .integer(1)])])])
        var fields: [String: Any] = [
            "schema": "inku.swift-pipeline-execution.v1", "snapshot": snapshot.data.base64EncodedString(),
            "events": events.data.base64EncodedString(), "svgFailure": "svg_too_large", "svgFailureLimitMiB": 1,
            "providers": [], "renderOptions": Data("{}".utf8).base64EncodedString(),
            "clipPolicy": Data("{}".utf8).base64EncodedString(), "renderColorMaps": [:],
            "description": "fixture", "derivationKind": "new", "startedAt": Date().timeIntervalSinceReferenceDate,
        ]
        fields["models"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(ModelSelection()))
        _ = try await database.compareAndSwapExecution(id: executionID, expectedRevision: nil,
                                                       snapshot: JSONSerialization.data(withJSONObject: fields))
        let reopened = PipelineHost(database: database)
        let restored = try await reopened.restore(executionID: executionID)
        let resumed = try await reopened.resume(executionID: executionID)
        for view in [restored, resumed] {
            XCTAssertEqual(view.phase, "failed")
            XCTAssertEqual(view.sequence, "7")
            XCTAssertNil(view.svg); XCTAssertNil(view.renderedJSON); XCTAssertNil(view.candidateWork); XCTAssertNil(view.savedWorkID)
        }
        let log = try await reopened.drawingLog(executionID: executionID)
        XCTAssertEqual(log?.failureReason, "svg_too_large")
        XCTAssertEqual(log?.failureSVGLimitMiB, 1)
        let works = try await database.list()
        XCTAssertTrue(works.isEmpty)
        // A standalone refusal has no invented core sequence and remains visible after reopening.
        let failure = StoredSVGFailure(description: "standalone", models: .init(), limitMiB: 32)
        _ = try await database.compareAndSwapExecution(id: "standalone-refusal", expectedRevision: nil,
                                                       snapshot: JSONEncoder().encode(failure))
        let logs = try await PipelineHost(database: database).drawingLogs()
        XCTAssertEqual(logs.first(where: { $0.id == "standalone-refusal" })?.failureSVGLimitMiB, 32)
    }
}
