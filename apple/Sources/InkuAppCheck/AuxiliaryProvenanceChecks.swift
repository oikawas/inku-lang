import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runAuxiliaryProvenanceChecks() async throws {
    // Failure: autonomous children persisted empty edges, losing the mode and each generation's Vision advice.
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-auxiliary-provenance-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    let transport = AuxiliaryProvenanceProvider()
    let app = AppModel(databaseURL: databaseURL, transport: transport)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "check:generation", stage2Model: "check:generation")))
    app.inputMode = "description"; app.descriptionText = "a red circle"; app.seedText = "42"
    guard let parent = await app.runAutomation(request: try app.requestForCurrentInput()),
          let parentNodeID = parent.lineageNodeID else {
        throw CheckFailure.message("Auxiliary provenance parent failed: \(app.errorText ?? app.status)")
    }
    let database = try InkuDatabase(url: databaseURL)
    let parentContext = try await app.savedConfiguration(workID: parent.id)
    let auxiliary = AuxiliaryModel(provider: AuxiliaryProvider(transport: transport, credentials: AuxiliaryProvenanceCredentials()))
    await auxiliary.initialize(app: app)
    auxiliary.enabledKinds = ["reinterpretation"]
    auxiliary.generations = 2; auxiliary.visionMode = true
    auxiliary.modelReference = "check:vision"; auxiliary.direction = "keep the circle"
    await auxiliary.startRefinement(app: app)
    guard auxiliary.errorText == nil, auxiliary.completedGenerations == 2,
          auxiliary.generatedWorks.count == 2, !auxiliary.running, !app.isBusy else {
        throw CheckFailure.message("Vision provenance run failed: \(auxiliary.errorText ?? auxiliary.status)")
    }
    let visionChildren = auxiliary.generatedWorks
    var previousNodeID = parentNodeID
    for (index, child) in visionChildren.enumerated() {
        guard let nodeID = child.lineageNodeID, let edge = try await database.edge(childNodeID: nodeID),
              edge.parentNodeID == previousNodeID, edge.derivationKind == "reinterpretation",
              let stored = try await database.work(id: child.id), stored == child,
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

    // A later random run must not attach the advice still displayed from the previous Vision run.
    auxiliary.visionMode = false; auxiliary.generations = 1; auxiliary.modelReference = "check:unused"
    await auxiliary.startRefinement(app: app)
    guard auxiliary.errorText == nil, auxiliary.completedGenerations == 1,
          auxiliary.generatedWorks.count == 1, let child = auxiliary.generatedWorks.first,
          let nodeID = child.lineageNodeID, let edge = try await database.edge(childNodeID: nodeID),
          edge.parentNodeID == previousNodeID, edge.derivationKind == "reinterpretation",
          try await database.work(id: child.id)?.historyVisibility == "normal" else {
        throw CheckFailure.message("Random provenance child failed: \(auxiliary.errorText ?? auxiliary.status)")
    }
    let metadata = try ExactJSON(data: Data(edge.metadataJSON.utf8))
    guard metadata["autonomous_refine_mode"].string == "random",
          ["vision_model", "vision_observation", "vision_next_direction"].allSatisfy({ metadata.object?[$0] == nil }),
          auxiliary.advice?.observation == "observation 2",
          await transport.visionModels == ["check:vision", "check:vision"],
          await transport.generationModels == ["check:generation", "check:vision", "check:vision", "check:generation"],
          try await database.work(id: parent.id) == parent,
          try await app.savedConfiguration(workID: parent.id).configuration == parentContext.configuration,
          !auxiliary.running, !app.isBusy else {
        throw CheckFailure.message("Random edge retained stale Vision fields, changed the parent or exceeded the provider budget")
    }
    print("Auxiliary provenance passed: persisted Vision advice per generation; random mode excludes stale advice; parent chain/visibility/snapshots and 4 generation + 2 observation calls retained. Isolated SQLite + mock transports + real Rust only.")
}

private actor AuxiliaryProvenanceCredentials: CredentialStore {
    func key(for credentialID: String) -> String? { nil }
}

private actor AuxiliaryProvenanceProvider: ProviderTransport, AuxiliaryTransport {
    private(set) var generationModels: [String] = []
    private(set) var visionModels: [String] = []

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
            throw CheckFailure.message("Autonomous Vision changed its existing observation budget")
        }
        visionModels.append(modelReference)
        return ExactJSON.object(["observation": .string("observation \(visionModels.count)"),
            "next_direction": .string("direction \(visionModels.count)"), "suggested_kind": .string("reinterpretation")]).text
    }
}
