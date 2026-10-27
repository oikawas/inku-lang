import XCTest
import Foundation
import InkuCore
import InkuPersistence
@testable import InkuHost

final class HostBoundaryTests: XCTestCase, @unchecked Sendable {
    func testCancellationWhilePreparingReviewDoesNotSendReview() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-image-cancel-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let transport = ImageProvider()
        let wait = ImageReviewLimit(provider: transport)
        let host = PipelineHost(database: db, transport: transport, credentials: EmptyCredentials(), svgLimitBytes: { try await wait.limit() })
        let image = PreparedImageInput(jpeg: Data("fixture".utf8), width: 800, height: 600,
                                       originalWidth: 800, originalHeight: 600, nearestFormatID: "square")
        let request = try fixture(.image(input: image.authoringJSON, autoCatalog: false))
        let capture = ViewCapture()
        let task = Task { try await host.generate(request, image: image) { capture.receive($0) } }
        for _ in 0..<300 {
            if await wait.entered { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        guard await wait.entered else { task.cancel(); XCTFail("review did not begin"); return }
        task.cancel()
        _ = try? await task.value
        if let id = capture.executionID { _ = try? await host.cancel(executionID: id) }
        let tags = await transport.actions.compactMap { $0["tag"].string }
        XCTAssertEqual(tags, ["write_image_ddl"])
        let rows = try await db.list()
        XCTAssertTrue(rows.isEmpty)
    }
    func testImageIsWrittenAndReviewedWithTransientImages() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-image-run-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let transport = ImageProvider()
        let host = PipelineHost(database: db, transport: transport, credentials: EmptyCredentials())
        let old = try await host.generate(fixture(.directDDL("place one blue circle at center.")))
        let oldID = try XCTUnwrap(old.savedWorkID)
        let before = try await host.restoreSavedWork(workID: oldID)
        let image = PreparedImageInput(jpeg: Data("fixture".utf8), width: 800, height: 600,
                                       originalWidth: 800, originalHeight: 600, nearestFormatID: "square")
        var request = try fixture(.image(input: image.authoringJSON, autoCatalog: false))
        request.imageProvenance = "fixture provenance"
        let view = try await host.generate(request, image: image)
        XCTAssertEqual(view.phase, "completed")
        XCTAssertTrue(String(decoding: view.eventsJSON, as: UTF8.self).contains("image_ddl"))
        XCTAssertNotNil(view.savedWorkID)
        XCTAssertTrue(view.visibleDDL?.contains("Aspect ratio 4:3") == true)
        let actions = await transport.actions
        XCTAssertEqual(actions.map { $0["tag"].string }, ["write_image_ddl", "review_image_ddl"])
        XCTAssertEqual(actions[0]["_transient_images"].array?.count, 1)
        XCTAssertEqual(actions[1]["_transient_images"].array?.count, 2)
        XCTAssertTrue(actions[1]["_transient_images"].array?[1].string?.hasPrefix("data:image/png;base64,") == true)
        let provider = ProviderSettings(id: "anthropic", kind: .anthropic,
            baseURL: URL(string: "https://api.anthropic.com")!, requiresAPIKey: false)
        let wire = try ProviderWire.request(action: actions[1].data, provider: provider, model: "fixture", maxTokens: 8192, key: nil)
        let wireBody = String(decoding: try XCTUnwrap(wire.httpBody), as: UTF8.self)
        XCTAssertTrue(wireBody.contains(image.jpeg.base64EncodedString()))
        XCTAssertTrue(wireBody.contains("image/png"))
        let chatGPT = try ChatGPTPlanRuntime.request(action: actions[1].data, model: "fixture", argumentLimit: 1048576)
        let chatBody = String(decoding: chatGPT.body, as: UTF8.self)
        XCTAssertTrue(chatBody.contains("data:image/jpeg;base64,"))
        XCTAssertTrue(chatBody.contains("data:image/png;base64,"))
        let context = try await host.savedAuthoringContext(workID: XCTUnwrap(view.savedWorkID))
        XCTAssertEqual(context.authority, "ddl_authoritative")
        XCTAssertEqual(context.imageProvenance, "fixture provenance")
        let presentation = try await host.savedWorkPresentation(workID: XCTUnwrap(view.savedWorkID))
        let promptText = String(decoding: try XCTUnwrap(presentation.promptJSON), as: UTF8.self)
        XCTAssertTrue(promptText.contains("write_image_ddl")); XCTAssertTrue(promptText.contains("review_image_ddl"))
        XCTAssertFalse(promptText.contains("data:image")); XCTAssertFalse(promptText.contains("fixture provenance"))
        let summaries = try await host.savedAuthoringSummaries(workIDs: [XCTUnwrap(view.savedWorkID)])
        XCTAssertEqual(summaries[try XCTUnwrap(view.savedWorkID)]?.isImage, true)
        XCTAssertEqual(summaries[try XCTUnwrap(view.savedWorkID)]?.imageProvenance, "fixture provenance")
        let record = try ExactJSON(data: XCTUnwrap(context.imageDDL))
        XCTAssertEqual(record["image"]["sent"]["sha256"].string, image.sha256)
        XCTAssertFalse(String(decoding: try XCTUnwrap(context.imageDDL), as: UTF8.self).contains("data:image"))
        let loadedExecution = try await db.loadExecution(id: view.executionID)
        let execution = try XCTUnwrap(loadedExecution)
        let stored = try XCTUnwrap(JSONSerialization.jsonObject(with: execution.snapshot) as? [String: Any])
        for key in ["snapshot", "events", "prompts", "pendingProviderAction"] {
            guard let encoded = stored[key] as? String, let bytes = Data(base64Encoded: encoded) else { continue }
            let text = String(decoding: bytes, as: UTF8.self)
            XCTAssertFalse(text.contains("data:image"), "image URL persisted in \(key)")
            XCTAssertFalse(text.contains(image.jpeg.base64EncodedString()), "image bytes persisted in \(key)")
        }
        var childRequest = try fixture(.directDDL("place one blue circle at center."))
        childRequest.parentWorkID = view.savedWorkID
        childRequest.derivationKind = "ddl_edit"
        let child = try await host.generate(childRequest)
        let childContext = try await host.savedAuthoringContext(workID: XCTUnwrap(child.savedWorkID))
        XCTAssertEqual(childContext.imageDDL, context.imageDDL)
        XCTAssertEqual(childContext.imageProvenance, context.imageProvenance)
        var retainedRequest = try fixture(.directDDL(try XCTUnwrap(view.visibleDDL)))
        retainedRequest.parentWorkID = view.savedWorkID
        retainedRequest.derivationKind = "catalog_change"
        retainedRequest.retainedDocument = context.document
        retainedRequest.retainedAuthority = context.authorityJSON
        let retained = try await host.generate(retainedRequest)
        let retainedContext = try await host.savedAuthoringContext(workID: XCTUnwrap(retained.savedWorkID))
        XCTAssertEqual(retainedContext.imageDDL, context.imageDDL)
        XCTAssertEqual(retainedContext.imageProvenance, context.imageProvenance)
        let after = try await host.restoreSavedWork(workID: oldID)
        XCTAssertEqual(before.ddl, after.ddl)
        XCTAssertEqual(before.score, after.score)
        XCTAssertEqual(before.svg, after.svg)
        let replay = try await host.prepareReplayComparison(work: after)
        XCTAssertEqual(replay.replayedSVG, before.svg)
    }
    func testImageAutoCatalogUsesThreeProviderCalls() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-image-auto-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let transport = ImageProvider()
        let host = PipelineHost(database: db, transport: transport, credentials: EmptyCredentials())
        let image = PreparedImageInput(jpeg: Data("fixture".utf8), width: 800, height: 600,
                                       originalWidth: 800, originalHeight: 600, nearestFormatID: "square")
        var request = try fixture(.image(input: image.authoringJSON, autoCatalog: true))
        var config = try ExactJSON(data: request.configuration)
        config["catalogs"] = .array([.object(["prompt": .object(["catalog_id": .string("default"),
            "label": .string("Default"), "description": .string("")]), "resolved": config["compiler"]["host"]])])
        request.configuration = config.data
        let view = try await host.generate(request, image: image)
        XCTAssertEqual(view.phase, "completed")
        let actions = await transport.actions
        XCTAssertEqual(actions.compactMap { $0["tag"].string }, ["select_image_catalog", "write_image_ddl", "review_image_ddl"])
        let presentation = try await host.savedWorkPresentation(workID: XCTUnwrap(view.savedWorkID))
        XCTAssertTrue(String(decoding: try XCTUnwrap(presentation.promptJSON), as: UTF8.self).contains("select_image_catalog"))
    }
    func testMissingImageCancelsBeforeSending() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-image-missing-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let transport = ImmediateProvider()
        let host = PipelineHost(database: db, transport: transport, credentials: EmptyCredentials())
        let input = PreparedImageInput(jpeg: Data("fixture".utf8), width: 800, height: 600,
                                       originalWidth: 800, originalHeight: 600, nearestFormatID: "square")
        let capture = ViewCapture()
        do {
            _ = try await host.generate(fixture(.image(input: input.authoringJSON, autoCatalog: false))) { capture.receive($0) }
            XCTFail("missing image accepted")
        } catch let error as HostError { XCTAssertEqual(error.code, "image_missing") }
        let calls = await transport.calls
        XCTAssertEqual(calls, 0)
        let id = try XCTUnwrap(capture.executionID)
        let restored = try await host.restore(executionID: id)
        XCTAssertEqual(restored.phase, "cancelled")
    }
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
        XCTAssertEqual(try WorkIdentity.render(score: .object(["instructions": .array([])]), options: hashOptions, metadata: hashMetadata),
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
private actor ImageProvider: ProviderTransport {
    var actions: [ExactJSON] = []
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let effect = try ExactJSON(data: action)
        actions.append(effect)
        let tag: String, response: String
        switch effect["tag"].string {
        case "select_image_catalog": tag = "image_catalog_selected"; response = #"{"catalog_id":"default"}"#
        case "write_image_ddl": tag = "image_ddl_written"; response = #"{"ddl":"place one red circle at center."}"#
        default: tag = "image_ddl_reviewed"; response = #"{"ddl":"place one red circle at center."}"#
        }
        return ExactJSON.object(["tag": .string(tag), "identity": effect["identity"],
            "response": .string(response), "elapsed_ms": .string("1")]).data
    }
}
private actor ImageReviewLimit {
    let provider: ImageProvider
    var afterWrite = 0
    var entered = false
    init(provider: ImageProvider) { self.provider = provider }
    func limit() async throws -> UInt64 {
        if await provider.actions.count == 1 {
            afterWrite += 1
            if afterWrite == 1 { entered = true; try await Task.sleep(for: .seconds(30)) }
        }
        return 16 * 1024 * 1024
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
