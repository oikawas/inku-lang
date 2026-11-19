import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runRefinementChecks() async throws {
    let began = Date()
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-refinement-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    let provider = RefinementProvider()
    let app = AppModel(databaseURL: databaseURL, transport: provider)
    await app.initialize()
    app.selectDrawRoute("stages"); app.sketchMode = "off"
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                   models: ["original", "layout"].map { ProviderModelSettings(id: $0) })
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "check:original", stage2Model: "check:original")))
    app.selectNextDrawingModel("check:original")
    app.inputMode = "description"; app.descriptionText = "a red circle"; app.seedText = "0"; app.wild = true
    var parentRequest = try app.requestForCurrentInput()
    var parentConfiguration = try ExactJSON(data: parentRequest.configuration)
    var parentOptions = try ExactJSON(data: parentRequest.renderOptions)
    parentConfiguration["compiler"]["composition_seed"] = .null
    parentOptions["composition_seed"] = .null
    parentRequest.configuration = parentConfiguration.data; parentRequest.renderOptions = parentOptions.data
    _ = await app.runAutomation(request: parentRequest)
    guard app.errorText == nil, let parent = app.selectedWork, parent.compositionSeed == nil, parent.renderSeed == "0" else {
        throw CheckFailure.message("Refinement parent failed: \(app.errorText ?? app.status)")
    }
    let database = try InkuDatabase(url: databaseURL)
    let context = try await app.savedConfiguration(workID: parent.id)
    let document = try ExactJSON(data: context.document!)
    let initialRows = try await database.list().count
    let initialCalls = await provider.calls

    // Failure: retired reading/touch still reaches either the plan or the saved-work request path (the refinement
    // dialogs' `makeRefinementRequest`; the AI refinement process that also used it is gone, 2026-11-13).
    guard RefinementKind.availableKinds == [.layout] else { throw CheckFailure.message("Retired parameters are still offered") }
    for kind in ["touch_change", "reinterpretation"] {
        do {
            _ = try await app.makeDrawingAdjustmentPlans(work: parent, kind: kind, count: 1)
            throw CheckFailure.message("Retired manual \(kind) accepted a plan")
        } catch let error as HostError where error.code == "unknown_refinement_kind" { }
        do {
            _ = try await app.makeRefinementRequest(work: parent, kind: kind)
            throw CheckFailure.message("Retired saved-work \(kind) accepted a request")
        } catch let error as HostError where error.code == "unknown_refinement_kind" { }
    }
    guard await provider.calls == initialCalls, try await database.list().count == initialRows,
          app.selectedWork == parent else { throw CheckFailure.message("Retired refinement called a provider, saved or moved selection") }

    // Failure: removing the parameters dialog also removes layout or makes it reread a description.
    let layout = RefinementModel(work: parent)
    await layout.initialize(app: app)
    app.selectNextDrawingModel("check:layout")
    app.catalogID = app.catalogs.first(where: { $0.id != parent.catalogID })!.id
    app.seedText = "999"; app.wild = false
    await layout.generate(app: app, count: 4)
    guard layout.errorText == nil, layout.candidates.count == 4, layout.candidates.map(\.number) == [1, 2, 3, 4],
          layout.slots.allSatisfy({ $0.state == .ready }),
          layout.capturedStage1Model == "check:layout", layout.capturedStage2Model == "check:layout",
          Set(layout.candidates.compactMap { $0.work.compositionSeed }).count == 4,
          // Each option's instructions are the ranges it chose again from the saved DDL (the parent's when unchanged).
          layout.candidates.contains(where: { $0.recomposition?.source != nil }),
          layout.candidates.allSatisfy({ $0.work.renderSeed == "0" && $0.work.ddl == ($0.recomposition?.source ?? parent.ddl)
              && $0.work.renderColorCatalogID == app.catalogID && $0.work.renderWild == true
              && $0.work.stage1Model == "check:layout" && $0.work.stage2Model == "check:layout"
              && $0.work.interpretationSeed == nil }),
          await provider.calls == initialCalls, try await database.list().count == initialRows,
          app.selectedWork == parent else {
        throw CheckFailure.message("Layout dialog lost saved conditions, reread or saved a preview: \(layout.errorText ?? layout.status)")
    }
    layout.preview(layout.candidates[0].id)
    guard layout.selectedCount == 0, layout.canGenerate(count: 1) else { throw CheckFailure.message("Layout enlargement adopted an option or blocked redrawing") }
    layout.preview(nil)
    layout.selectCandidate(layout.candidates[0].id, selected: true)
    guard await layout.saveSelected(app: app), let saved = layout.committedWorks.first,
          try await database.list().count == initialRows + 1,
          let edge = try await database.edge(childNodeID: saved.lineageNodeID!),
          edge.derivationKind == "layout_change", edge.parentNodeID == parent.lineageNodeID,
          try ExactJSON(data: Data(edge.metadataJSON.utf8))["composition_seed"] == .number(saved.compositionSeed!),
          try ExactJSON(data: Data(edge.metadataJSON.utf8))["interpretation_seed"] == .null,
          try ExactJSON(data: await app.savedConfiguration(workID: saved.id).document!)["macro_locks"] == document["macro_locks"],
          try await database.work(id: parent.id) == parent,
          try await app.savedConfiguration(workID: parent.id).configuration == context.configuration,
          try await app.savedConfiguration(workID: parent.id).document == context.document else {
        throw CheckFailure.message("Layout adoption lost parent/locks/provenance: \(layout.errorText ?? layout.status)")
    }
    print(String(format: "Refinement passed in %.3fs: retired reading and touch refused on the plan and saved-work request paths without provider or save; layout-only dialog draws four saved-DDL previews with zero additional Stage 1 calls and adopts one layout edge; parent remains unchanged. Mock transport + isolated SQLite + real Rust only.", Date().timeIntervalSince(began)))
}

/// Answers each stage as the laws-and-colors fake does, counting every send. The older answer here,
/// `{"normalized_ddl": "place one red circle at center."}` for every action, no longer reads as a plan: the parent kept
/// only its paper, so every layout option kept the parent's instructions unchanged and recorded its instruction model.
private actor RefinementProvider: ProviderTransport {
    private(set) var calls = 0
    private let base = LawsColorsCheckProvider(refuseColors: true)
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        return try await base.perform(action: action, models: models, providers: providers, credentials: credentials, onBytes: onBytes)
    }
}
