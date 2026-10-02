import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor func runCompositionHostChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-composition-host-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let app = AppModel(databaseURL: folder.appendingPathComponent("bootstrap.sqlite"), transport: CompositionCheckProvider())
    await app.initialize()
    guard app.errorText == nil, !app.catalogs.isEmpty, !app.canvases.isEmpty else {
        throw CheckFailure.message("Composition host fixture could not load bundled defaults: \(app.errorText ?? app.status)")
    }
    let service = ProviderSettings(id: "composition-check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false)
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "composition-check:pinned", stage2Model: "composition-check:pinned")))
    app.inputMode = "description"; app.descriptionText = compositionCheckDescription
    app.language = "en"; app.seedText = "42"
    var request = try app.requestForCurrentInput()
    request.models = ModelSelection(stage1Model: "composition-check:pinned", stage2Model: "composition-check:unused-stage2",
                                    stage1MaxTokens: 3072, holeMaxTokens: 512)
    var config = try ExactJSON(data: request.configuration)
    guard config["composition"]["read"].bool == true else {
        throw CheckFailure.message("The generated Server manifest omitted the new composition read=true default")
    }
    let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    let credentials = CompositionEmptyCredentials()
    let provider = CompositionCheckProvider()
    let host = PipelineHost(database: database, transport: provider, credentials: credentials)

    // Failure: read_composition was rejected after a real structured Stage 1
    // result, so native creation could not reach a committed/saved composition.
    let composed = try await host.generate(request)
    guard composed.phase == "completed", let composedID = composed.savedWorkID,
          composed.svg?.contains("<svg") == true, composed.visibleDDL?.contains("[composition]") == true,
          compositionEventTags(composed).contains("composition_read"),
          await provider.actions.map({ $0["tag"].string ?? "" }) == ["generate_normalized_ddl", "read_composition"],
          await provider.selectedModels == ["composition-check:pinned", "composition-check:pinned"] else {
        throw CheckFailure.message("Structured Stage1 -> composition -> commit/save did not complete with the pinned Stage1 model")
    }
    let prompts = try composed.promptJSON.map { try ExactJSON(data: $0).array ?? [] } ?? []
    guard prompts.map({ $0["action"].string ?? "" }) == ["generate_normalized_ddl"] else {
        throw CheckFailure.message("Composition reading leaked into the author-facing prompt journal")
    }
    let saved = try await host.restoreSavedWork(workID: composedID)
    let context = try await host.savedAuthoringContext(workID: composedID)
    guard try ExactJSON(data: context.configuration)["composition"]["read"].bool == true,
          saved.ddl == composed.visibleDDL else {
        throw CheckFailure.message("Saved authoring context lost the run's composition setting or committed DDL")
    }
    guard let reading = await provider.actions.first(where: { $0["tag"].string == "read_composition" }) else {
        throw CheckFailure.message("Composition action was not captured at the host boundary")
    }
    try compositionWireCheck(reading, service: service, models: request.models)

    // Failure: host routing bypassed the shared composition retry/fallback path.
    // A two-attempt policy and zero delay keep this check bounded and offline.
    config["composition_retry"] = .object(["max_attempts": .integer(2), "attempt_timeout_ms": .string("1000"),
        "total_timeout_ms": .string("2000"), "retry_delay_ms": .string("0")])
    var fallbackRequest = request; fallbackRequest.configuration = config.data
    let failing = CompositionCheckProvider(failReading: true)
    let fallbackHost = PipelineHost(database: database, transport: failing, credentials: credentials)
    let fallback = try await fallbackHost.generate(fallbackRequest)
    let retries = await failing.actions.filter { $0["tag"].string == "read_composition" }
    guard fallback.phase == "completed", fallback.savedWorkID != nil,
          compositionEventTags(fallback).contains("composition_fallback"), retries.count == 2,
          retries[0]["identity"]["action_id"] == retries[1]["identity"]["action_id"],
          retries.map({ $0["identity"]["attempt"].number ?? "" }) == ["1", "2"] else {
        throw CheckFailure.message("Composition failure did not use the Rust-owned finite retry budget and save its fallback result")
    }

    // Failure: fresh installation defaults were retrofitted onto saved configs
    // that deliberately have no composition step, or use its default reading.
    var oldFields = try ExactJSON(data: request.configuration).object!
    oldFields.removeValue(forKey: "composition")
    var oldRequest = request; oldRequest.configuration = ExactJSON.object(oldFields).data
    let compatibility = CompositionCheckProvider()
    let compatibilityHost = PipelineHost(database: database, transport: compatibility, credentials: credentials)
    let oldRun = try await compatibilityHost.generate(oldRequest)
    var noReadRequest = request
    var noReadConfig = try ExactJSON(data: request.configuration)
    noReadConfig["composition"] = .object(["read": .bool(false)])
    noReadRequest.configuration = noReadConfig.data
    let noReadRun = try await compatibilityHost.generate(noReadRequest)
    guard oldRun.phase == "completed", let oldID = oldRun.savedWorkID,
          noReadRun.phase == "completed", let noReadID = noReadRun.savedWorkID,
          oldRun.visibleDDL?.contains("[composition]") == false,
          noReadRun.visibleDDL?.contains("[composition]") == true,
          await compatibility.actions.map({ $0["tag"].string ?? "" }) == ["generate_normalized_ddl", "generate_normalized_ddl"] else {
        throw CheckFailure.message("Absent/read:false composition configs acquired a reading request or changed their composition semantics")
    }
    let oldContext = try await compatibilityHost.savedAuthoringContext(workID: oldID)
    let noReadContext = try await compatibilityHost.savedAuthoringContext(workID: noReadID)
    guard try ExactJSON(data: oldContext.configuration)["composition"] == .null,
          try ExactJSON(data: noReadContext.configuration)["composition"]["read"].bool == false else {
        throw CheckFailure.message("Saved old/read:false composition settings were replaced by installation defaults")
    }
    let oldWork = try await compatibilityHost.restoreSavedWork(workID: oldID)
    let replayed = try await compatibilityHost.replay(workID: oldID)
    let oldAfterReplay = try await compatibilityHost.restoreSavedWork(workID: oldID)
    let composedAfter = try await host.restoreSavedWork(workID: composedID)
    guard oldAfterReplay == oldWork, composedAfter == saved,
          replayed.score == oldWork.score, replayed.ddl == oldWork.ddl,
          await compatibility.actions.count == 2 else {
        throw CheckFailure.message("Composition integration retroactively changed saved SVG/Score/DDL or sent a reading during saved-Score replay")
    }
    try await compositionTransportGates(reading, models: request.models, folder: folder, credentials: credentials)
    print("Composition host passed: real Rust Stage1 -> read -> commit/save; Stage1 model/cap and sampling; schema propertyOrdering preserved; prompt journal excludes composition; finite shared retry/fallback; saved absent/read:false settings retained; saved Score replay unchanged; ordinary/personal gates accept the action without network/OAuth/Keychain. Temporary DB only.")
}

private func compositionEventTags(_ view: PipelineView) -> [String] {
    (try? ExactJSON(data: view.eventsJSON).array?.compactMap { $0["tag"].string }) ?? []
}

private func compositionWireCheck(_ action: ExactJSON, service: ProviderSettings, models: ModelSelection) throws {
    let prompt = action["payload"]["prompt"]
    let schema = prompt["response_schema"]
    let request = try ProviderWire.request(action: action.data, provider: service, model: "pinned", maxTokens: models.stage1MaxTokens, key: nil)
    let body = try ExactJSON(data: request.httpBody ?? Data())
    let transported = body["tools"].array?.first?["function"]["parameters"] ?? .null
    let ordering = ExactJSON.array(["thesis", "roles", "relations", "tension", "stated_places"].map(ExactJSON.string))
    guard body["model"].string == "pinned", body["max_tokens"].number == "3072", body["temperature"].number == "0.3",
          transported == schema, transported["propertyOrdering"] == ordering,
          body["messages"].array?.first?["content"] == prompt["system"],
          prompt["system"].string?.contains("propertyOrdering") == false else {
        throw CheckFailure.message("Composition wire changed Stage1 sampling/cap, lost schema ordering or appended the schema to the system prompt")
    }
    let gemini = ProviderSettings(id: "composition-gemini", kind: .gemini, baseURL: URL(string: "https://example.invalid")!, requiresAPIKey: false)
    let geminiRequest = try ProviderWire.request(action: action.data, provider: gemini, model: "pinned", maxTokens: models.stage1MaxTokens, key: nil)
    let geminiBody = try ExactJSON(data: geminiRequest.httpBody ?? Data())
    let geminiSchema = geminiBody["tools"].array?.first?["functionDeclarations"].array?.first?["parametersJsonSchema"] ?? .null
    for path in [schema, schema["properties"]["relations"]["items"], schema["properties"]["tension"], schema["properties"]["stated_places"]["items"]] {
        guard path["propertyOrdering"].array?.isEmpty == false else { throw CheckFailure.message("Core composition schema is missing an object property order") }
    }
    guard geminiSchema == schema, geminiBody["generationConfig"]["maxOutputTokens"].number == "3072" else {
        throw CheckFailure.message("Gemini projection dropped composition propertyOrdering or used the Stage2 cap")
    }
}

private func compositionTransportGates(_ action: ExactJSON, models: ModelSelection, folder: URL,
                                       credentials: CompositionEmptyCredentials) async throws {
    // An empty selection fails before credential lookup or URLSession I/O, but
    // only after the ordinary transport recognizes the new composition action.
    let ordinary = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("unused-budget.json"))
    let rejected = try ExactJSON(data: await ordinary.perform(action: action.data, models: ModelSelection(), providers: [],
                                                            credentials: credentials, onBytes: { _ in }))
    guard rejected["tag"].string == "provider_failed", rejected["identity"] == action["identity"] else {
        throw CheckFailure.message("Ordinary transport rejected the composition action instead of returning the common provider failure result")
    }
    try await compositionPersonalPlanGate(action, models: models, folder: folder, credentials: credentials)
}

// Recheck only the failed final gate; do not repeat successful core/save/replay
// or ordinary transport boundaries when correcting the disconnected pin fixture.
func runCompositionPersonalPlanGateChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-composition-personal-gate-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let action: ExactJSON = .object(["tag": .string("read_composition"), "version": .integer(1),
        "identity": .object(["action_id": .string("composition-gate"), "attempt": .integer(1), "request_digest": .string("fixture")]),
        "timeout_ms": .string("1000"), "delay_ms": .string("0"), "payload": .object([:])])
    try await compositionPersonalPlanGate(action,
        models: ModelSelection(stage1Model: "chatgpt:pinned", stage2Model: "composition-check:unused-stage2"),
        folder: folder, credentials: CompositionEmptyCredentials())
}

private func compositionPersonalPlanGate(_ action: ExactJSON, models: ModelSelection, folder: URL,
                                         credentials: CompositionEmptyCredentials) async throws {
    let ordinary = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("unused-personal-budget.json"))
    let http = CompositionNoHTTP()
    let runtime = ChatGPTPlanRuntime(directory: folder.appendingPathComponent("empty-personal-vault"), http: http)
    let route = PersonalPlanRoutingTransport(ordinary: ordinary, runtime: runtime)
    let diagnostics = CompositionDiagnosticCapture()
    let personal = try ExactJSON(data: await route.performPersonalPlan(action: action.data,
        models: ModelSelection(stage1Model: "chatgpt:pinned", stage2Model: models.stage2Model), providers: [.personalPlan],
        // The pin must be structurally valid before the empty vault can reject
        // it as disabled. A non-UUID fails earlier as chatgpt_session_changed.
        session: ChatGPTPlanSession(profileID: "00000000-0000-4000-8000-000000000001", generation: 1), argumentLimit: 4096,
        credentials: credentials, onBytes: { _ in }, onDiagnostic: { diagnostics.record($0) }))
    let httpCalls = await http.calls
    let credentialCalls = await credentials.calls
    let actual = "tag=\(personal["tag"].string ?? "nil"), failure=\(personal["failure"].string ?? "nil"), identityMatches=\(personal["identity"] == action["identity"]), diagnostics=\(diagnostics.codes), HTTP=\(httpCalls), credentials=\(credentialCalls)"
    guard personal["tag"].string == "provider_failed", personal["identity"] == action["identity"],
          diagnostics.codes == ["chatgpt_disabled"], httpCalls == 0, credentialCalls == 0 else {
        throw CheckFailure.message("PersonalPlan composition gate failed: \(actual)")
    }
    print("Composition PersonalPlan gate passed: \(actual). Empty temporary vault; no OAuth/Keychain.")
}

private let compositionCheckDescription = "A red circle above black dots scattered at the bottom"

private actor CompositionCheckProvider: ProviderTransport {
    let failReading: Bool
    private(set) var actions: [ExactJSON] = []
    private(set) var selectedModels: [String] = []
    init(failReading: Bool = false) { self.failReading = failReading }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let action = try ExactJSON(data: action)
        actions.append(action); selectedModels.append(models.stage1Model)
        let tag = try action.requiredString("tag")
        let response: ExactJSON
        let resultTag: String
        if tag == "generate_normalized_ddl" {
            resultTag = "normalized_ddl_generated"; response = Self.plan
        } else if tag == "read_composition" {
            if failReading {
                return ExactJSON.object(["tag": .string("provider_failed"), "identity": action["identity"],
                    "failure": .string("rate_limited"), "elapsed_ms": .string("10")]).data
            }
            resultTag = "composition_read"; response = Self.reading
        } else { throw HostError("unexpected_composition_check_effect") }
        return ExactJSON.object(["tag": .string(resultTag), "identity": action["identity"],
            "response": .string(response.text), "elapsed_ms": .string("10")]).data
    }
    private static func layer(_ action: String, _ shape: String, _ count: Int, _ position: String, _ size: String, _ color: String) -> ExactJSON {
        var fields = Dictionary(uniqueKeysWithValues: ["angle", "bleeding", "continuity", "line_up_direction", "motion_amplitude", "motion_quality", "proportion", "thinness"].map { ($0, ExactJSON.string("unspecified")) })
        fields.merge(["action": .string(action), "shape": .string(shape), "count": .integer(count), "position": .string(position),
            "size": .string(size), "color": .string(color), "handling": .string("dense"), "tool": .string("pen"),
            "surface": .string(shape == "point" ? "empty" : "flat")]) { _, value in value }
        return .object(fields)
    }
    private static let plan: ExactJSON = .object(["ground": .string("paper"), "background": .string("white"), "plugins": .array([]),
        "layers": .array([layer("fill", "square", 1, "unspecified", "large", "gray"), layer("place", "circle", 1, "center", "small", "red"),
                          layer("scatter", "point", 12, "bottom", "very_small", "black")])])
    private static let reading: ExactJSON = .object(["thesis": .string("a lone circle above a floor of dots"),
        "roles": .array(["field", "focal", "scattered"].map(ExactJSON.string)),
        "relations": .array([.object(["type": .string("above"), "layers": .array([.integer(1), .integer(2)]),
            "side": .string("unspecified"), "toward": .string("unspecified")])]),
        "tension": .object(["motion": .string("still"), "focus": .string("unspecified"), "vertical": .string("unspecified"),
            "balance": .string("unspecified"), "symmetry": .string("unspecified"), "void": .string("unspecified")]),
        "stated_places": .array([.object(["layer": .integer(2), "words": .string("at the bottom"), "place": .string("bottom")])])])
}

private actor CompositionEmptyCredentials: CredentialStore {
    private(set) var calls = 0
    func key(for credentialID: String) async throws -> String? { calls += 1; return nil }
}

private actor CompositionNoHTTP: ChatGPTHTTPClient {
    private(set) var calls = 0
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void) async throws -> ChatGPTHTTPResponse {
        calls += 1; throw HostError("composition_check_must_not_contact_http")
    }
}

private final class CompositionDiagnosticCapture: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: [String] = []
    var codes: [String] { lock.withLock { stored } }
    func record(_ value: ChatGPTPlanDiagnostic) { lock.withLock { stored.append(value.code) } }
}
