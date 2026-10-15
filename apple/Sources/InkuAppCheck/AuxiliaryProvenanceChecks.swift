import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runAuxiliaryProvenanceChecks() async throws {
    guard AuxiliaryProvider.allowedKinds == ["catalog_change", "layout_change"] else {
        throw CheckFailure.message("Vision advice still offers a retired refinement kind")
    }
    // Failure: autonomous refinements reread a description or append directions instead of drawing the saved DDL.
    // This same controller-to-SQLite check also preserves each generation's observation and excludes retired kinds.
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-auxiliary-provenance-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    let transport = AuxiliaryProvenanceProvider()
    let app = AppModel(databaseURL: databaseURL, transport: transport)
    await app.initialize()
    // Only the initial parent fixture uses Stage 1; later generations must retain its saved DDL.
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                   models: [.init(id: "generation"), .init(id: "vision", purposes: ["llm", "vision"])])
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "check:generation", stage2Model: "check:generation")))
    app.inputMode = "description"; app.descriptionText = "a red circle"; app.seedText = "42"
    guard let parent = await app.runAutomation(request: try app.requestForCurrentInput()),
          let parentNodeID = parent.lineageNodeID else {
        throw CheckFailure.message("Auxiliary provenance parent failed: \(app.errorText ?? app.status)")
    }
    let database = try InkuDatabase(url: databaseURL)
    let parentContext = try await app.savedConfiguration(workID: parent.id)
    guard parentContext.authority == "description_authoritative", await transport.generationModels == ["check:generation"] else {
        throw CheckFailure.message("Auxiliary fixture must start with one description-authoritative Stage 1 call")
    }
    let auxiliary = AuxiliaryModel(provider: AuxiliaryProvider(transport: transport, credentials: AuxiliaryProvenanceCredentials()))
    await auxiliary.initialize(app: app)
    // Obsolete stored reading and touch selections must never reach Vision or generation.
    auxiliary.enabledKinds = ["reinterpretation", "touch_change", "catalog_change"]
    auxiliary.generations = 2; auxiliary.visionMode = true
    auxiliary.modelReference = "check:vision"; auxiliary.direction = "keep the circle"
    await auxiliary.startRefinement(app: app)
    guard auxiliary.errorText == nil, auxiliary.completedGenerations == 2,
          auxiliary.generatedWorks.count == 2, auxiliary.enabledKinds == ["catalog_change"],
          !auxiliary.running, !app.isBusy else {
        throw CheckFailure.message("Vision provenance run failed: \(auxiliary.errorText ?? auxiliary.status)")
    }
    let visionChildren = auxiliary.generatedWorks
    var previousNodeID = parentNodeID
    for (index, child) in visionChildren.enumerated() {
        guard let nodeID = child.lineageNodeID, let edge = try await database.edge(childNodeID: nodeID),
              edge.parentNodeID == previousNodeID, edge.derivationKind == "catalog_change",
              let stored = try await database.work(id: child.id), stored == child,
              stored.ddl == parent.ddl, stored.effectiveSourceText == parent.effectiveSourceText,
              stored.historyVisibility == (index == 0 ? "lineage_only" : "normal") else {
            throw CheckFailure.message("Vision child did not persist its parent edge or history visibility")
        }
        let metadata = try ExactJSON(data: Data(edge.metadataJSON.utf8))
        guard metadata["autonomous_refine_mode"].string == "vision",
              metadata["vision_model"].string == "check:vision",
              metadata["vision_observation"].string == "observation \(index + 1)",
              metadata["vision_next_direction"].string == "direction \(index + 1)" else {
            throw CheckFailure.message("Saved Vision edge lost its mode or used another generation's advice")
        }
        previousNodeID = nodeID
    }

    // A later random run must not attach the advice still displayed from the previous Vision run. Like Web's
    // AIRefineModal, every run starts again from the chosen source, not from the previous run's last child.
    auxiliary.visionMode = false; auxiliary.generations = 1; auxiliary.modelReference = "check:unused"
    auxiliary.enabledKinds = ["reinterpretation", "touch_change", "layout_change"]
    await auxiliary.startRefinement(app: app)
    guard auxiliary.errorText == nil, auxiliary.completedGenerations == 1,
          auxiliary.generatedWorks.count == 1, let child = auxiliary.generatedWorks.first,
          let nodeID = child.lineageNodeID, let edge = try await database.edge(childNodeID: nodeID),
          edge.parentNodeID == parentNodeID, edge.derivationKind == "layout_change",
          child.ddl == parent.ddl, child.effectiveSourceText == parent.effectiveSourceText,
          auxiliary.enabledKinds == ["layout_change"],
          try await database.work(id: child.id)?.historyVisibility == "normal" else {
        throw CheckFailure.message("Random provenance child failed: \(auxiliary.errorText ?? auxiliary.status)")
    }
    let metadata = try ExactJSON(data: Data(edge.metadataJSON.utf8))
    guard metadata["autonomous_refine_mode"].string == "random",
          ["vision_model", "vision_observation", "vision_next_direction"].allSatisfy({ metadata.object?[$0] == nil }),
          auxiliary.advice?.observation == "observation 2",
          await transport.visionModels == ["check:vision", "check:vision"],
          await transport.generationModels == ["check:generation"],
          try await database.work(id: parent.id) == parent,
          try await app.savedConfiguration(workID: parent.id).configuration == parentContext.configuration,
          try await app.savedConfiguration(workID: parent.id).document == parentContext.document,
          !auxiliary.running, !app.isBusy else {
        throw CheckFailure.message("Random edge retained stale Vision fields, changed the parent or exceeded the provider budget")
    }
    // The displayed Vision advice suggests color, but a later adoption has only layout enabled. Its edited
    // draft is observation material and must never become drawing source text through the fallback path.
    let rowsBeforeAdoption = try await database.list().count
    auxiliary.modelReference = "check:generation"
    auxiliary.draftText = "do not append this edited advice to the drawing"
    await auxiliary.adoptAdvice(app: app)
    let adoptedWorks = try await database.list()
    guard auxiliary.errorText == nil, adoptedWorks.count == rowsBeforeAdoption + 1,
          let adopted = adoptedWorks.first(where: { work in
              work.id != parent.id && !visionChildren.contains(where: { $0.id == work.id }) && work.id != child.id
          }), let adoptedNodeID = adopted.lineageNodeID,
          let adoptedEdge = try await database.edge(childNodeID: adoptedNodeID),
          adoptedEdge.parentNodeID == parentNodeID, adoptedEdge.derivationKind == "layout_change",
          adopted.ddl == parent.ddl, adopted.effectiveSourceText == parent.effectiveSourceText,
          await transport.generationModels == ["check:generation"],
          try await database.work(id: parent.id) == parent,
          try await app.savedConfiguration(workID: parent.id).configuration == parentContext.configuration,
          try await app.savedConfiguration(workID: parent.id).document == parentContext.document else {
        throw CheckFailure.message("Adopted advice reread, appended its draft, ignored the allowed fallback or changed the parent")
    }
    // Failure: a DDL/held parent silently resets Vision to random although only catalog/layout are allowed now.
    await app.selectWork(parent)
    app.ddlText = "place one blue circle at center."
    await app.commitDDL()
    guard let held = app.selectedWork, app.sourceLocked else { throw CheckFailure.message("Held Vision fixture failed") }
    guard await app.drawNewDDL("Place 1 green circle."), let direct = app.selectedWork else { throw CheckFailure.message("Direct Vision fixture failed") }
    for source in [held, direct] {
        await transport.expectInstruction(source.effectiveSourceText.isEmpty ? (source.ddl ?? "") : source.effectiveSourceText)
        let vision = AuxiliaryModel(provider: AuxiliaryProvider(transport: transport, credentials: AuxiliaryProvenanceCredentials()))
        vision.visionMode = true
        await vision.initialize(app: app, work: source)
        guard vision.sourceIsLocked, vision.visionMode else { throw CheckFailure.message("Held/DDL initialization switched off Vision") }
        vision.generations = 1; vision.modelReference = "check:vision"
        vision.enabledKinds = ["catalog_change"]; vision.direction = "keep the circle"
        await vision.startRefinement(app: app)
        guard vision.errorText == nil, vision.completedGenerations == 1, let next = vision.generatedWorks.first,
              next.ddl == source.ddl, next.effectiveSourceText == source.effectiveSourceText,
              let nextNode = next.lineageNodeID, let nextEdge = try await database.edge(childNodeID: nextNode),
              nextEdge.parentNodeID == source.lineageNodeID,
              try ExactJSON(data: Data(nextEdge.metadataJSON.utf8))["autonomous_refine_mode"].string == "vision" else {
            throw CheckFailure.message("Vision did not draw the held/DDL parent's saved instructions: \(vision.errorText ?? vision.status); app=\(app.errorText ?? "none"); mock=\(await transport.lastMismatch)")
        }
    }
    guard await transport.visionModels.count == 4, await transport.generationModels == ["check:generation"] else {
        throw CheckFailure.message("Held/DDL Vision reread descriptions or failed to ask Vision")
    }
    print("Auxiliary provenance passed: color Vision x2 and layout random x1 + advice adoption use saved DDL; held-description and direct-DDL Vision each draw one catalog child without Stage 1; retired reading/touch excluded; directions remain observation metadata. Isolated SQLite + mock transports + real Rust only.")
}

private actor AuxiliaryProvenanceCredentials: CredentialStore {
    func key(for credentialID: String) -> String? { nil }
}

private actor AuxiliaryProvenanceProvider: ProviderTransport, AuxiliaryTransport {
    private(set) var generationModels: [String] = []
    private(set) var visionModels: [String] = []
    private var expectedInstruction = "a red circle"
    private(set) var lastMismatch = "none"
    func expectInstruction(_ text: String) { expectedInstruction = text }

    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        generationModels.append(models.stage1Model)
        let input = try ExactJSON(data: action)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": input["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }

    func performAuxiliary(prompt: AuxiliaryPrompt, modelReference: String, settings: HostSettings,
                          credentials: any CredentialStore, onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        guard prompt.images.count == 1, prompt.maximumTokens == 320 else {
            lastMismatch = "image count / advice budget"
            throw CheckFailure.message("Autonomous Vision changed its existing observation budget")
        }
        guard let start = prompt.message.firstIndex(of: "{") else { throw CheckFailure.message("Vision prompt has no context") }
        let payload = try ExactJSON(data: Data(prompt.message[start...].utf8))
        guard payload["allowed_suggested_kinds"].array?.compactMap(\.string) == ["catalog_change"],
              payload["user_direction"].string == "keep the circle",
              payload["instruction"].string == expectedInstruction else {
            lastMismatch = "kinds=\(payload["allowed_suggested_kinds"].text); direction=\(payload["user_direction"].string ?? "nil"); instruction=\(payload["instruction"].string ?? "nil"); expected=\(expectedInstruction)"
            throw CheckFailure.message("Vision received retired kinds or direction text leaked into the parent description")
        }
        visionModels.append(modelReference)
        return ExactJSON.object(["observation": .string("observation \(visionModels.count)"),
            "next_direction": .string("direction \(visionModels.count)"), "suggested_kind": .string("catalog_change")]).text
    }
}
