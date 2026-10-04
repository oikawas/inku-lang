import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runDrawingLimitsEditingChecks() async throws {
    // Failure: the settings field forced edits back below shipping defaults.
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-drawing-limits-edit-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let url = directory.appendingPathComponent("works.sqlite")
    let transport = DrawingLimitsNoProvider()
    let app = AppModel(databaseURL: url, transport: transport)
    await app.initialize()
    app.seedText = "42"
    await app.generate()
    guard app.errorText == nil, let work = app.selectedWork, let definition = app.drawingLimitDefinition else {
        throw CheckFailure.message("Drawing limits editing fixture did not save: \(app.errorText ?? app.status)")
    }
    let savedContext = try await app.savedConfiguration(workID: work.id)
    var draft = definition.defaults.mapValues(String.init)
    draft["max_expanded_primitives"] = "800"
    draft["max_expanded_per_instruction"] = "1000"
    let selected = try definition.parsedDraft(draft)
    try await app.updateDrawingLimits(selected)
    let next = try app.requestForCurrentInput()
    let inherited = try app.requestForCurrentInput(parentWorkID: work.id, derivationKind: "user_edit")
    let nextBudgets = try limitsBudgets(next.configuration)
    let inheritedBudgets = try limitsBudgets(inherited.configuration)
    let originalBudgets = try limitsBudgets(savedContext.configuration)
    guard nextBudgets.hard["primitive_marks"] == 800, nextBudgets.operational["primitive_marks"] == 800,
          nextBudgets.hard["maximum_per_template_primitive_marks"] == 800,
          nextBudgets.operational["maximum_per_template_primitive_marks"] == 800,
          inheritedBudgets.hard == originalBudgets.hard,
          inheritedBudgets.operational == originalBudgets.operational,
          inheritedBudgets.identity == originalBudgets.identity,
          try await app.savedConfiguration(workID: work.id).configuration == savedContext.configuration else {
        throw CheckFailure.message("Edited limits did not reach both new-work budgets or replaced saved-work budgets")
    }
    let reopened = AppModel(databaseURL: url, transport: transport)
    await reopened.initialize()
    let settings = try await ProviderSettingsStore(url: directory.appendingPathComponent("providers.json")).load()
    let database = try InkuDatabase(url: url)
    guard settings.drawingLimits?["max_expanded_primitives"] == 800,
          try reopened.drawingLimits()["max_expanded_primitives"] == 800,
          try await database.list() == [work], await transport.calls == 0 else {
        throw CheckFailure.message("Drawing limit edits did not persist independently of the saved work")
    }
    draft["max_expanded_primitives"] = ""
    do {
        _ = try definition.parsedDraft(draft)
        throw CheckFailure.message("An empty drawing limit was accepted for saving")
    } catch let error as HostError where error.code == "invalid_drawing_limit_value" {}
    guard try reopened.drawingLimits()["max_expanded_primitives"] == 800 else {
        throw CheckFailure.message("An invalid draft replaced the saved drawing limit")
    }
    print("Drawing limits editing passed: 400→800 persists; normalization reaches both new-work budgets; one saved core work retains its original policy and history; empty draft rejected. Provider0.")
}

private func limitsBudgets(_ data: Data) throws -> (hard: [String: UInt32], operational: [String: UInt32], identity: String) {
    guard let config = try JSONSerialization.jsonObject(with: data) as? [String: Any],
          let compiler = config["compiler"] as? [String: Any],
          let policy = compiler["hard_resource_policy"] as? [String: Any],
          let budget = policy["budget"] as? [String: Any],
          let hard = budget["maximum"] as? [String: UInt32],
          let operational = compiler["operational_resource_budget"] as? [String: Any],
          let maximum = operational["maximum"] as? [String: UInt32],
          let identity = policy["identity"] as? String else { throw CheckFailure.message("Drawing limits fixture has no compiler budgets") }
    return (hard, maximum, identity)
}

private actor DrawingLimitsNoProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw CheckFailure.message("Drawing limits editing must not call a provider")
    }
}
