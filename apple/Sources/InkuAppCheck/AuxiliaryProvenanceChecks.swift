import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

// The AI refinement process and the juxtaposition are gone (author 2026-11-13): their checks (shared moves, saved
// laws stages, the provenance of the laws, juxtaposition and chunk moves) went with them. The lineage migration replay
// stays; it still draws through the fake provider below.

@MainActor func runLineageMigrationReplayChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-migrate-replay-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let transport = AutonomousCheckProvider()
    let app = AppModel(databaseURL: folder.appendingPathComponent("source.sqlite"), transport: transport)
    await app.initialize(); app.selectDrawRoute("stages"); app.sketchMode = "off"
    let service = ProviderSettings(id: "auto-check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false,
        models: [.init(id: "one", purposes: ["llm", "vision"])])
    try await app.updateHostSettings(HostSettings(providers: [service], models: .init(stage1Model: "auto-check:one", stage2Model: "auto-check:one")))
    app.seedText = "7"; app.descriptionText = "青い円が一つ浮かぶ"
    await app.generate()
    guard let original = app.selectedWork, let node = original.lineageNodeID else { throw CheckFailure.message("Migration replay fixture: \(app.errorText ?? app.status)") }
    await app.library.saveNote(id: original.id, note: "test data")
    let source = try app.auxiliaryDatabase(), legacyURL = folder.appendingPathComponent("legacy.sqlite")
    try await source.backup(to: legacyURL)
    let sql = "UPDATE history SET history_visibility='lineage_only'; UPDATE lineage_nodes SET state='lineage_only'; DELETE FROM schema_migrations WHERE identifier='swift-v5-show-lineage-works'; PRAGMA user_version=4;"
    let sqlite = Process(); sqlite.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3"); sqlite.arguments = [legacyURL.path, sql]
    try sqlite.run(); sqlite.waitUntilExit()
    guard sqlite.terminationStatus == 0 else { throw CheckFailure.message("Could not prepare isolated legacy database") }
    let migrated = try InkuDatabase(url: legacyURL)
    guard let work = try await migrated.work(id: original.id), work.historyVisibility == "normal",
          try await migrated.node(id: node)?.state == "active", try await migrated.libraryPage().total == 1,
          work.ddl == original.ddl, work.score == original.score, work.svg == original.svg else {
        throw CheckFailure.message("Migration changed artwork or failed to expose the work")
    }
    let host = PipelineHost(database: migrated, transport: transport, credentials: AutonomousCheckCredentials())
    let replay = try await host.replay(workID: work.id)
    guard replay.ddl == original.ddl, replay.score == original.score, replay.svg == original.svg else {
        throw CheckFailure.message("Migrated work replay changed DDL, Score or SVG")
    }
    print("Migrated 1 lineage-only work and node to normal history; DDL, Score, SVG and replay are unchanged.")
}

private actor AutonomousCheckCredentials: CredentialStore {
    func key(for credentialID: String) -> String? { nil }
}

/// The laws-and-colors fake provider with every drawing asked for large shapes.
private actor AutonomousCheckProvider: ProviderTransport {
    let base = LawsColorsCheckProvider(refuseColors: true)

    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        var answer = try ExactJSON(data: await base.perform(action: action, models: models, providers: providers, credentials: credentials, onBytes: onBytes))
        if input["tag"].string == "generate_normalized_ddl", let response = answer["response"].string {
            answer["response"] = .string(response.replacingOccurrences(of: "\"size\":\"small\"", with: "\"size\":\"large\""))
        }
        return answer.data
    }
}
