import XCTest
import Foundation
import InkuCore
import InkuPersistence
@testable import InkuHost

final class CompositionUpdateTests: XCTestCase, @unchecked Sendable {
    private func cases() throws -> ExactJSON {
        var path = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        while path.path != "/" {
            let file = path.appendingPathComponent("server/tests/data/composition-rules-server-cases.json")
            if FileManager.default.fileExists(atPath: file.path) { return try ExactJSON(data: Data(contentsOf: file)) }
            path.deleteLastPathComponent()
        }
        throw HostError("missing_composition_cases")
    }

    private func database() throws -> InkuDatabase {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-composition-\(UUID())")
        return try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    }

    private func saved(_ db: InkuDatabase, id: String, nodeID: String, parent: String? = nil,
                       kind: String? = nil, composition: ExactJSON, config: ExactJSON = .object([:]), ddl: String = "x") async throws -> SavedWork {
        let work = SavedWork(id: id + "_0", at: 1, input: "雪", score: "{}", svg: "<svg/>", ddl: ddl, lineageNodeID: nodeID)
        let node = LineageNode(id: nodeID, historyID: work.id, at: 1)
        let edge = parent.map { LineageEdge(id: "edge-" + id, parentNodeID: $0, childNodeID: nodeID, derivationKind: kind!, at: 1) }
        let context: ExactJSON = .object(["configuration": config, "options": .object([:]), "clip": .object([:]),
            "authority": .object(["authority": .string("description_authoritative"), "origin": .string("stage1_generated"), "revision": .string("0")]),
            "description_ddl": .object(["composition": composition])])
        let snapshot = Data("{}".utf8)
        let initial = try await db.compareAndSwapExecution(id: id, expectedRevision: nil, snapshot: snapshot)
        _ = try await db.commitEffect(id: id, expectedRevision: initial.revision, effectID: "save-render:0", snapshot: snapshot,
            acknowledgement: SavedPerformance.acknowledgement(workID: work.id, context: context), work: work, node: node, edge: edge)
        return work
    }

    func testCopiedRecordUsesWalkAndOwnFormChangeWins() async throws {
        let db = try database(), host = PipelineHost(database: db)
        let parentRecord: ExactJSON = .object(["answer": .object(["form": .string("grid"), "thesis": .string("海")])])
        _ = try await saved(db, id: "parent", nodeID: "p", composition: parentRecord)
        let copied = try await saved(db, id: "copy", nodeID: "c", parent: "p", kind: "tool_change", composition: parentRecord)
        let inherited = try await host.compositionRecord(work: copied)
        XCTAssertNil(inherited.own)
        XCTAssertEqual(inherited.inherited?["via"], .array([.string("tool_change")]))
        XCTAssertEqual(inherited.inherited?["answer"]["form"].string, "grid")
        let changed: ExactJSON = .object(["answer": .object(["form": .string("bands")])])
        let child = try await saved(db, id: "form", nodeID: "f", parent: "p", kind: "composition_form_change", composition: changed)
        let own = try await host.compositionRecord(work: child)
        XCTAssertEqual(own.own?["answer"]["form"].string, "bands")
    }

    func testSavedEdgesUseCoreMetadata() async throws {
        let db = try database(), host = PipelineHost(database: db)
        let parent: ExactJSON = .object(["answer": .object(["form": .string("grid"), "main_law": .string("B1"), "thesis": .string("前")])])
        _ = try await saved(db, id: "parent", nodeID: "node", composition: parent)
        let rows = try XCTUnwrap(cases()["metadata"].array)
        for index in [0, 2, 3, 5] {
            let input = rows[index]["input"], expected = rows[index]["expected"]["metadata"]
            let id = "candidate\(index)", work = SavedWork(id: id + "_0", at: 2, input: "雪", score: "{}", svg: "<svg/>", ddl: "x", lineageNodeID: id)
            let node = LineageNode(id: id, historyID: work.id, at: 2)
            let edge = LineageEdge(id: "edge-" + id, parentNodeID: "node", childNodeID: id, derivationKind: input["derivation_kind"].string!, at: 2)
            let context: ExactJSON = .object(["configuration": .object([:]), "options": .object([:]), "clip": .object([:]), "authority": .object(["authority": .string("description_authoritative"), "origin": .string("stage1_generated"), "revision": .string("0")])])
            let stored = StandaloneCandidate(candidate: StoredCandidate(work: work, node: node, edge: edge, context: context.data, compositionRuleSettings: input["settings"].data))
            _ = try await db.compareAndSwapExecution(id: id, expectedRevision: nil, snapshot: JSONEncoder().encode(stored))
            _ = try await host.saveCandidate(executionID: id)
            let result = try await db.edge(childNodeID: id)
            XCTAssertEqual(try ExactJSON(data: Data(XCTUnwrap(result).metadataJSON.utf8)), expected)
        }
    }

    func testThesisWireBodiesAndOneRetry() throws {
        let ask: ExactJSON = .object(["description": .string("雪"), "language": .string("ja")])
        let request = try CompositionTheses.request(ask: ask)["request"]
        let effect = try CompositionTheses.effect(request: request, actionID: "fixture")
        let provider = ProviderSettings(id: "anthropic", kind: .anthropic, baseURL: URL(string: "https://api.anthropic.com/v1")!, requiresAPIKey: false)
        let claude = try ProviderWire.prepare(action: effect.data, provider: provider, model: "claude-test", maxTokens: 4096, key: "fixture").request
        let chat = try ChatGPTWire.request(model: "gpt-test", prompt: effect["payload"]["prompt"].data, answerLimit: 16384)
        for body in [try XCTUnwrap(claude.httpBody), chat.body] {
            let text = String(decoding: body, as: UTF8.self)
            let parsed = try ExactJSON(data: body)
            XCTAssertTrue(text.contains("theses")); XCTAssertTrue(parsed.text.contains("雪"))
            XCTAssertTrue(parsed.text.contains("構図の係")); XCTAssertTrue(parsed.text.contains("additionalProperties"))
        }
        let retry = try CompositionTheses.retry(ask: ask, answer: "{}", attempt: 1)
        XCTAssertEqual(retry["next"].string, "send")
        XCTAssertEqual(retry["prompt_digest"].string, try CompositionTheses.digest(request: retry["request"]))
        let second = try CompositionTheses.retry(ask: ask, answer: #"{"theses":["雪を大きく描く。","雪を端に集める。","雪を帯に並べる。","雪を広く散らす。"]}"#, attempt: 2)
        XCTAssertEqual(second["next"].string, "accept")
    }

    func testDescriptionGroupsExcludeImagesAndKeepSelectedSingleton() throws {
        let rows = try XCTUnwrap(cases()["groups"].array)
        for row in rows {
            let actual = try ExactJSON(data: InkuCore.descriptionGroups(row["input"].data))
            XCTAssertEqual(actual["groups"], row["expected"]["groups"])
            XCTAssertEqual(actual["total"], row["expected"]["total"])
        }
    }

    func testPlaceChildIsDDLAuthoritativeAndSavedConfigProducesBoxes() async throws {
        let db = try database(), host = PipelineHost(database: db)
        let boxCase = try XCTUnwrap(cases()["boxes"].array?.first)
        let input = boxCase["input"]
        let ddl = try input.requiredString("ddl")
        let request = try fixture(.directDDL(ddl))
        var config = try ExactJSON(data: request.configuration)
        config["language"] = .string("ja")
        let options = try ExactJSON(data: request.renderOptions)
        let record: ExactJSON = .object(["answer": .object(["form": .string("grid"), "thesis": .string("海")])])
        let work = try await saved(db, id: "placeparent", nodeID: "placeparent", composition: record, config: config, ddl: ddl)
        let boxes = try await host.compositionWorkBoxes(work: work)
        XCTAssertEqual(boxes["units"], boxCase["expected"]["units"])
        let moved = try await host.compositionPlace(work: work, chunk: "大海の", at: "center")
        var child = try fixture(.directDDL(moved.requiredString("ddl")))
        child.configuration = config.data; child.renderOptions = options.data
        child.description = work.effectiveSourceText; child.parentWorkID = work.id; child.derivationKind = "layout_change"
        child.noProviderEffects = true
        let view = try await host.generate(child)
        let context = try await host.savedAuthoringContext(workID: XCTUnwrap(view.savedWorkID))
        XCTAssertEqual(context.authority, "ddl_authoritative")
    }
}
