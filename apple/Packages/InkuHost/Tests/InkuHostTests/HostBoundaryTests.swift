import XCTest
import Foundation
import InkuCore
import InkuPersistence
@testable import InkuHost

final class HostBoundaryTests: XCTestCase, @unchecked Sendable {
    // Failure: converting a transport JSON number through Double silently rounds a saved seed.
    func testExactSeedAndMLXWire() throws {
        let value = try ExactJSON(data: Data(#"{"seed":18446744073709551615}"#.utf8))
        XCTAssertEqual(value["seed"].number, "18446744073709551615")
        XCTAssertEqual(try ExactJSON(data: value.data), value)
        // Failure: forcing a tool on Gemma 4 MLX repeats thought-channel markers.
        let action = ExactJSON.object(["payload": .object(["prompt": .object([
            "system": .string("core system"), "message": .string("core message"), "action_name": .string("generate_normalized_ddl"),
            "response_schema": .object(["type": .string("object"), "properties": .object([:])]),
        ])])])
        let provider = ProviderSettings(id: "local", baseURL: URL(string: "http://127.0.0.1:8080/v1")!, apiProfile: "mlx", requiresAPIKey: false)
        let request = try ProviderWire.request(action: action.data, provider: provider, model: "gemma-4-31b-it", maxTokens: 2048, key: nil)
        let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
        XCTAssertEqual(body["response_format"]["type"].string, "json_schema")
        XCTAssertEqual(body["response_format"]["json_schema"]["schema"], action["payload"]["prompt"]["response_schema"])
        XCTAssertEqual(body["tools"], .null)
        XCTAssertEqual(body["enable_thinking"].bool, false)
        XCTAssertEqual(body["temperature"].number, "1.0")
        XCTAssertEqual(body["top_p"].number, "0.95")
        XCTAssertEqual(body["top_k"].number, "64")
        // Failure: a platform-specific hash replaces the Server contract's dh1/rh3 identity.
        XCTAssertEqual(WorkIdentity.description(" \r\nA\u{030A}\r "), "dh1:0a94dc9d420d1142d6b71de60f9bf7e2f345a4d62c9f141b091539769ddf3075")
        let hashOptions: ExactJSON = .object(["render_seed": .string("18446744073709551615"), "wild": .bool(false), "catalog_id": .string("default")])
        let hashMetadata: ExactJSON = .object(["render_engine_id": .string("rust"), "render_engine_version": .string("1")])
        XCTAssertEqual(WorkIdentity.render(score: .object(["instructions": .array([])]), options: hashOptions, metadata: hashMetadata),
                       "rh3:07e6e7bd570887e4b40fc6197e9f8f32ccb0230ca734f5190767fdc70e3e330a")
    }

    // Failure: a save becomes visible without its ACK/snapshot, or replay recompiles stored source.
    func testDirectDDLAndDescriptionSaveThenRestore() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-host-check-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let transport = ImmediateProvider()
        let host = PipelineHost(database: db, transport: transport, credentials: EmptyCredentials())
        let direct = try await host.generate(fixture(.directDDL("place one red circle at center.")))
        XCTAssertEqual(direct.phase, "completed")
        XCTAssertTrue(direct.svg?.contains("<svg") == true)
        let id = try XCTUnwrap(direct.savedWorkID)
        let saved = try await host.restoreSavedWork(workID: id)
        XCTAssertEqual(saved.ddl, "place one red circle at center.")
        XCTAssertEqual(saved.svg, direct.svg)
        XCTAssertEqual(saved.compositionSeed, "18446744073709551615")
        let reopened = PipelineHost(database: db, transport: transport, credentials: EmptyCredentials())
        let restored = try await reopened.restore(executionID: direct.executionID)
        XCTAssertEqual(restored.svg, saved.svg)
        XCTAssertEqual(restored.savedWorkID, id)
        let description = try await host.generate(fixture(.description("a red circle", autoCatalog: false)))
        XCTAssertEqual(description.phase, "completed")
        XCTAssertNotNil(description.savedWorkID)
        let rows = try await db.list()
        XCTAssertEqual(rows.count, 2)
        let calls = await transport.calls
        XCTAssertEqual(calls, 1)
        // A stale author revision cannot mutate or insert a history row.
        do {
            _ = try await host.perform(executionID: description.executionID, command: .commitUserDDL(expectedRevision: "0", source: "place one blue circle at center."))
            XCTFail("stale revision accepted")
        } catch let error as HostError { XCTAssertEqual(error.code, "authority_conflict") }
        let after = try await db.list()
        XCTAssertEqual(after.count, 2)
    }

    // Failure: reading work A shows diagnostics or prompts from its execution's newer work B.
    func testSavedPresentationStaysWithEachWork() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-host-presentation-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let host = PipelineHost(database: db, transport: ImmediateProvider(), credentials: EmptyCredentials())
        var request = try fixture(.description("a red circle", autoCatalog: false))
        request.provenance = GenerationProvenance(ddlVersion: "16", ddlEngineVersion: "57", build: "42", uiLanguage: "ja",
                                                batchRunID: "fixture-batch", batchLineNumber: 3)
        let first = try await host.generate(request)
        let firstID = try XCTUnwrap(first.savedWorkID)
        let before = try await host.savedWorkPresentation(workID: firstID)
        let firstDelivery = try ExactJSON(data: XCTUnwrap(before.deliveryJSON))
        let firstPrompts = try ExactJSON(data: XCTUnwrap(before.promptJSON))
        XCTAssertEqual(firstPrompts.array?.count, 1)
        let second = try await host.perform(executionID: first.executionID,
            command: .commitUserDDL(expectedRevision: first.revision, source: "place one blue circle at center."))
        let secondID = try XCTUnwrap(second.savedWorkID)
        XCTAssertNotEqual(firstID, secondID)
        let newer = try await host.savedWorkPresentation(workID: secondID)
        XCTAssertNotEqual(firstDelivery, try ExactJSON(data: XCTUnwrap(newer.deliveryJSON)))
        let reopened = PipelineHost(database: db, credentials: EmptyCredentials())
        let after = try await reopened.savedWorkPresentation(workID: firstID)
        XCTAssertEqual(before.deliveryJSON, after.deliveryJSON)
        XCTAssertEqual(before.promptJSON, after.promptJSON)
        XCTAssertEqual(before.diagnosticsJSON, after.diagnosticsJSON)
        XCTAssertEqual(before.renderedJSON, after.renderedJSON)
        XCTAssertEqual(before.eventsJSON, after.eventsJSON)
        XCTAssertEqual(after.provenance?.ddlVersion, "16")
        XCTAssertEqual(after.provenance?.ddlEngineVersion, "57")
        XCTAssertEqual(after.provenance?.build, "42")
        XCTAssertEqual(after.provenance?.uiLanguage, "ja")
        XCTAssertEqual(after.provenance?.batchRunID, "fixture-batch")
        XCTAssertEqual(after.provenance?.batchLineNumber, 3)
        let firstOrigin = try await reopened.savedAuthoringContext(workID: firstID).originKind
        let secondOrigin = try await reopened.savedAuthoringContext(workID: secondID).originKind
        XCTAssertEqual(firstOrigin, .stage1Generated)
        // Editing changes authority. Its original Stage 1 provenance remains a recorded fact.
        XCTAssertEqual(secondOrigin, .stage1Generated)
        let secondAuthority = try await reopened.savedAuthoringContext(workID: secondID).authority
        XCTAssertEqual(secondAuthority, "ddl_authoritative")
        // A cancel after the durable save does not lose or repeat either save.
        _ = try await host.cancel(executionID: second.executionID)
        let rows = try await db.list()
        XCTAssertEqual(rows.count, 2)
        let afterCancel = try await reopened.savedWorkPresentation(workID: firstID)
        XCTAssertEqual(afterCancel.deliveryJSON, before.deliveryJSON)
    }

    // Failure: replay copies the old SVG or overwrites its parent instead of rendering the saved Score.
    func testSavedScoreReplayCreatesChildWithoutMutatingOriginal() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-host-replay-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let host = PipelineHost(database: db, transport: ImmediateProvider(), credentials: EmptyCredentials())
        let generated = try await host.generate(fixture(.directDDL("place one red circle at center.")))
        let id = try XCTUnwrap(generated.savedWorkID)
        let original = try await host.restoreSavedWork(workID: id)
        // A fresh host recovers the immutable render options and policies from the durable save ACK.
        let reopened = PipelineHost(database: db, credentials: EmptyCredentials())
        let replayed = try await reopened.replay(workID: id)
        XCTAssertNotEqual(replayed.id, original.id)
        XCTAssertEqual(replayed.score, original.score)
        XCTAssertEqual(replayed.ddl, original.ddl)
        XCTAssertEqual(replayed.renderSeed, "18446744073709551615")
        XCTAssertEqual(replayed.svg, original.svg)
        let unchanged = try await reopened.restoreSavedWork(workID: id)
        XCTAssertEqual(unchanged, original)
        let edge = try await db.edge(childNodeID: XCTUnwrap(replayed.lineageNodeID))
        XCTAssertEqual(edge?.parentNodeID, original.lineageNodeID)
        let rows = try await db.list()
        XCTAssertEqual(rows.count, 2)
    }

    // Failure: a restored paid request is resent, or its late answer revives a cancelled execution.
    func testInterruptedCallAndLateResponseAreNotApplied() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-host-cancel-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let transport = SuspendedProvider()
        let host = PipelineHost(database: db, transport: transport, credentials: EmptyCredentials())
        let progress = ViewCapture()
        let generation = Task { try await host.generate(fixture(.description("a red circle", autoCatalog: false)), progress: { progress.receive($0) }) }
        await transport.waitUntilStarted()
        let id = try XCTUnwrap(progress.executionID)
        let reopened = PipelineHost(database: db, transport: transport, credentials: EmptyCredentials())
        let interrupted = try await reopened.restore(executionID: id)
        XCTAssertTrue(interrupted.interruptedProvider)
        do {
            _ = try await reopened.resume(executionID: id)
            XCTFail("interrupted paid request resumed")
        } catch let error as HostError { XCTAssertEqual(error.code, "interrupted_execution_requires_cancel") }
        let callsBefore = await transport.calls
        XCTAssertEqual(callsBefore, 1)
        let cancelled = try await host.cancel(executionID: id)
        XCTAssertEqual(cancelled.phase, "cancelled")
        try await transport.releaseLateAnswer()
        let result = try await generation.value
        XCTAssertEqual(result.phase, "cancelled")
        XCTAssertNil(result.savedWorkID)
        let rows = try await db.list()
        XCTAssertTrue(rows.isEmpty)
        let callsAfter = await transport.calls
        XCTAssertEqual(callsAfter, 1)
    }
}

private struct EmptyCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}
private actor ImmediateProvider: ProviderTransport {
    var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        return try response(action)
    }
}
private actor SuspendedProvider: ProviderTransport {
    var calls = 0
    var continuation: CheckedContinuation<Data, Never>?
    var startedWaiter: CheckedContinuation<Void, Never>?
    var action: Data?
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1; self.action = action
        return await withCheckedContinuation { continuation in
            self.continuation = continuation; startedWaiter?.resume(); startedWaiter = nil
        }
    }
    func waitUntilStarted() async {
        if continuation != nil { return }
        await withCheckedContinuation { startedWaiter = $0 }
    }
    func releaseLateAnswer() throws {
        guard let continuation, let action else { return }
        self.continuation = nil; continuation.resume(returning: try response(action))
    }
}
private final class ViewCapture: @unchecked Sendable {
    private let lock = NSLock()
    private var id: String?
    var executionID: String? { lock.withLock { id } }
    func receive(_ progress: PipelineProgress) {
        if case .changed(let view) = progress { lock.withLock { id = view.executionID } }
    }
}
private func response(_ action: Data) throws -> Data {
    let effect = try ExactJSON(data: action)
    return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": effect["identity"],
                             "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
}

private func fixture(_ authoring: GenerationAuthoring) throws -> GenerationRequest {
    let seed = "18446744073709551615"
    let registry = try ExactJSON(data: InkuCore.canvasRegistry)
    let palette = try ExactJSON(data: InkuCore.resolvePalette(ExactJSON.object(["color_map": .object([:]), "catalog_id": .string("default"), "render_seed": .string(seed), "background": .string("white")]).data))
    let budget: ExactJSON = .object(["maximum": .object([
        "logical_objects": .integer(4096), "primitive_marks": .integer(400), "object_templates": .integer(64),
        "maximum_per_template_primitive_marks": .integer(240), "maximum_resolved_count": .integer(2000),
        "template_nodes": .integer(128), "anchor_instances": .integer(4096), "transform_instances": .integer(4096),
        "placement_instances": .integer(64), "fill_instances": .integer(64),
    ])])
    let compiler: ExactJSON = .object([
        "host": .object(["canvas_format_id": .string("square"), "canvas_format_registry_id": registry["registry"]["schema"], "canvas_format_registry_digest": registry["digest"],
                          "resolved_catalog_id": .string("default"), "catalog_mode": .string("default"), "background": .string("white"), "palette": palette]),
        "composition_seed": .string(seed), "macro_expansion_limits": .object(["max_invocations": .string("64"), "max_depth": .string("16"), "max_evaluation_steps": .string("8192"), "max_nodes_per_invocation": .string("128"), "max_total_nodes": .string("128")]),
        "stage15_variation": .null, "error_policy": .string("omit_and_continue"),
        "hard_resource_policy": .object(["identity": .string("apple.host-check.v1"), "budget": budget]), "operational_resource_budget": budget,
    ])
    let retry: ExactJSON = .object(["max_attempts": .integer(1), "attempt_timeout_ms": .string("120000"), "total_timeout_ms": .string("120000"), "retry_delay_ms": .string("0")])
    let config: ExactJSON = .object([
        "envelope_limits": .object(["max_input_bytes": .integer(16 * 1024 * 1024), "max_snapshot_bytes": .integer(32 * 1024 * 1024), "max_output_bytes": .integer(64 * 1024 * 1024)]),
        "language": .string("en"), "compiler": compiler, "definitions": .array([]), "macro_summaries": .array([]), "catalogs": .array([]),
        "prompt_limits": .object(["max_catalog_entries": .integer(64), "max_summary_bytes": .integer(8192), "max_catalog_serialized_bytes": .integer(1048576), "max_source_bytes": .integer(400000), "max_response_bytes": .integer(1048576)]),
        "catalog_retry": retry, "stage1_retry": retry, "hole_retry": retry,
    ])
    let options: ExactJSON = .object(["resolved_color_map": .object([:]), "catalog_id": .string("default"), "canvas": .object(["width": .integer(128), "height": .integer(128)]), "canvas_aspect_id": .string("square"), "svg_profile": .string("display"), "render_seed": .string(seed), "composition_seed": .string(seed), "wild": .bool(false), "error_policy": .string("omit_and_continue")])
    let clip: ExactJSON = .object(["tolerance_pixels": .number("0.1"), "max_nodes": .string("50000"), "max_path_elements": .string("200000"), "max_flattened_points": .string("200000"), "max_work": .string("10000000"), "max_output_vertices": .string("200000")])
    return GenerationRequest(authoring: authoring, configuration: config.data, renderOptions: options.data, clipPolicy: clip.data)
}
