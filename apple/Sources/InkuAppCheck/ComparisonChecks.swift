import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runComparisonChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-comparison-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let transport = ComparisonProvider()
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let model = AppModel(databaseURL: databaseURL, transport: transport)
    await model.initialize()
    model.inputMode = "ddl"
    model.ddlText = "place one green square at center."
    model.seedText = "42"
    await model.generate()
    guard model.errorText == nil, let original = model.selectedWork else { throw CheckFailure.message("Comparison source generation failed") }
    let database = try InkuDatabase(url: databaseURL)

    // Failure: preparing comparison candidates added normal history rows before explicit selection.
    let comparison = ComparisonModel()
    await comparison.initialize(app: model)
    let catalogs = Array(model.catalogs.filter { $0.id != original.catalogID }.prefix(2))
    guard catalogs.count == 2 else { throw CheckFailure.message("Comparison needs two bundled catalogs") }
    catalogs.forEach { comparison.selectCatalog($0.id, selected: true) }
    await comparison.generate(app: model)
    guard comparison.candidates.count == 2, comparison.failures.isEmpty,
          try await database.list().count == 1, model.selectedWork == original,
          comparison.candidates.allSatisfy({ $0.work.score == original.score && $0.work.renderSeed == original.renderSeed }) else {
        throw CheckFailure.message("Comparison preparation saved or altered its pinned Score: \(comparison.errorText ?? comparison.failures.joined(separator: "; "))")
    }
    let chosen = comparison.candidates[0]
    comparison.selectCandidate(chosen.id, selected: true)
    await comparison.saveSelected(app: model)
    guard comparison.candidates[0].savedWork?.id == chosen.work.id,
          comparison.candidates[1].savedWork == nil, try await database.list().count == 2,
          try await database.work(id: original.id) == original,
          let nodeID = comparison.candidates[0].savedWork?.lineageNodeID,
          try await database.edge(childNodeID: nodeID)?.derivationKind == "catalog_change" else {
        throw CheckFailure.message("Explicit save did not preserve its one-candidate selection")
    }
    let host = PipelineHost(database: database, transport: transport)
    _ = try await host.saveCandidate(executionID: chosen.id)
    guard try await database.list().count == 2 else { throw CheckFailure.message("Explicit save repeated a committed candidate") }

    // Failure: retained-DDL derivations falsely converted an unchanged description source into a user DDL lock.
    model.newWork()
    model.inputMode = "description"
    model.descriptionText = "a red circle"
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
    try await model.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:model", stage2Model: "check:model")))
    await model.generate()
    guard model.errorText == nil, let described = model.selectedWork, !model.sourceLocked else { throw CheckFailure.message("Description source failed") }
    model.variationSeedText = "17"
    await model.varySelectedWork()
    guard model.errorText == nil, let variation = model.selectedWork,
          variation.id != described.id, variation.ddl == described.ddl, variation.variationSeed == "17", !model.sourceLocked else {
        throw CheckFailure.message("Retained source variation acquired DDL authority: \(model.errorText ?? model.status)")
    }

    // Failure: stopping an in-flight model comparison admitted late candidates or cleared busy before its request drained.
    let stoppedComparison = ComparisonModel()
    await stoppedComparison.initialize(app: model)
    stoppedComparison.kind = .model
    stoppedComparison.modelReferencesText = "check:model"
    await transport.blockNextCall()
    let rowCount = try await database.list().count
    let pending = Task { @MainActor in await stoppedComparison.generate(app: model) }
    await transport.waitForBlockedCall()
    guard model.isBusy, stoppedComparison.running else { throw CheckFailure.message("Comparison did not hold the serialized operation") }
    await stoppedComparison.stop(app: model)
    await pending.value
    guard !model.isBusy, !stoppedComparison.running, stoppedComparison.candidates.isEmpty,
          model.selectedWork == variation, try await database.list().count == rowCount else {
        throw CheckFailure.message("Stopped comparison mixed results or changed history")
    }
    // Failure: a retained variation left its standalone candidate ID attached to the editor.
    model.ddlText = "place one blue circle at center."
    await model.commitDDL()
    guard model.errorText == nil, let edited = model.selectedWork, edited.id != variation.id,
          edited.ddl == model.ddlText, model.sourceLocked,
          try await database.work(id: variation.id) == variation,
          try await database.list().count == rowCount + 1 else {
        throw CheckFailure.message("Editing a retained variation failed to create a source-authoritative child: \(model.errorText ?? model.status)")
    }
    print("Comparison passed: two previews add no history; one explicit selection creates one immutable-parent child; save retry is idempotent; unchanged-source variation retains authority and remains editable; blocked model cancellation drains with no late candidate. No external provider calls.")
}

private actor ComparisonProvider: ProviderTransport {
    private var blockNext = false
    private var blocked = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func blockNextCall() { blockNext = true; blocked = false }
    func waitForBlockedCall() async {
        if !blocked { await withCheckedContinuation { waiters.append($0) } }
    }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        if blockNext {
            blockNext = false; blocked = true
            let pending = waiters; waiters = []; pending.forEach { $0.resume() }
            try await Task.sleep(for: .seconds(10))
            throw HostError("comparison_mock_stop_not_received")
        }
        let input = try ExactJSON(data: action)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": input["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
}
