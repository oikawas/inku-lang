import Foundation
import InkuHost
import InkuUI

// Concrete failure: default limits and explicitly saved default limits named
// the same effective budget differently, causing Server replay to reject it.
@MainActor
func runResourcePolicyParityChecks(fixtureDirectory: URL? = nil) async throws {
    let folder = fixtureDirectory ?? FileManager.default.temporaryDirectory.appendingPathComponent("inku-resource-policy-\(UUID().uuidString)")
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    guard !FileManager.default.fileExists(atPath: databaseURL.path) else {
        throw CheckFailure.message("Resource policy fixture already exists")
    }
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { if fixtureDirectory == nil { try? FileManager.default.removeItem(at: folder) } }
    let app = AppModel(databaseURL: databaseURL, transport: ResourcePolicyNoProvider())
    await app.initialize()
    guard app.errorText == nil, let definition = app.drawingLimitDefinition else {
        throw CheckFailure.message("Resource policy fixture did not initialize")
    }
    let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "http://localhost:1/v1")!,
        requiresAPIKey: false, label: "Offline resource policy fixture",
        models: [ProviderModelSettings(id: "alpha", label: "LLM A", purposes: ["llm"])])
    var settings = HostSettings(providers: [provider], models: .init(stage1Model: "fixture:alpha", stage2Model: "fixture:alpha"))
    try await app.updateHostSettings(settings)
    app.seedText = "42"
    app.catalogMode = "fixed"
    app.inputMode = "ddl"
    app.ddlText = "place one green square at center."
    let implicit = try app.requestForCurrentInput()
    guard await app.drawNewDDL(app.ddlText), let first = app.selectedWork else {
        throw CheckFailure.message("Implicit default policy did not produce a work: \(app.errorText ?? app.status)")
    }
    let firstContext = try await app.savedConfiguration(workID: first.id)
    settings.drawingLimits = definition.defaults
    try await app.updateHostSettings(settings)
    let explicit = try app.requestForCurrentInput()
    let left = try policyParts(implicit.configuration), right = try policyParts(explicit.configuration)
    guard left == right, left.0["identity"].string?.hasPrefix("host-settings:") == true else {
        throw CheckFailure.message("Implicit and explicit default limits have different resource authority")
    }
    guard await app.drawNewDDL(app.ddlText), let second = app.selectedWork,
          first.score == second.score, first.svg == second.svg, first.renderHash == second.renderHash else {
        throw CheckFailure.message("Saving the default limits changed the deterministic drawing")
    }
    let secondContext = try await app.savedConfiguration(workID: second.id)
    var changed = definition.defaults
    changed["max_expanded_primitives"] = (changed["max_expanded_primitives"] ?? 400) + 1
    settings.drawingLimits = changed
    try await app.updateHostSettings(settings)
    let next = try app.requestForCurrentInput()
    guard try policyParts(next.configuration) != left,
          try await app.savedConfiguration(workID: first.id).configuration == firstContext.configuration,
          try await app.savedConfiguration(workID: second.id).configuration == secondContext.configuration else {
        throw CheckFailure.message("A new limit did not affect new requests or replaced a saved policy")
    }
    if fixtureDirectory != nil {
        try Data(second.score.utf8).write(to: folder.appendingPathComponent("native-score.json"), options: .atomic)
        try Data(second.svg.utf8).write(to: folder.appendingPathComponent("native.svg"), options: .atomic)
        try secondContext.renderOptions.write(to: folder.appendingPathComponent("native-render-options.json"), options: .atomic)
        try JSONEncoder().encode(definition.defaults).write(to: folder.appendingPathComponent("drawing-limits.json"), options: .atomic)
    }
    print("Resource policy parity passed: implicit/explicit defaults share authority, Score, SVG and hash; changed limits affect new requests and preserve both saved policies. Two deterministic works, provider0.")
}

private func policyParts(_ data: Data) throws -> (ExactJSON, ExactJSON) {
    let value = try ExactJSON(data: data)
    return (value["compiler"]["hard_resource_policy"], value["compiler"]["operational_resource_budget"])
}

private struct ResourcePolicyNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("unexpected_provider_call_in_resource_policy_check")
    }
}
