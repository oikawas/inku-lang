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
    // Drawing needs the next drawing model chosen for the tab; without it `generate()` returned at its guard.
    app.selectNextDrawingModel("auto-check:one")
    app.seedText = "7"; app.descriptionText = "青い円が一つ浮かぶ"
    await app.generate()
    guard let original = app.selectedWork, let node = original.lineageNodeID else { throw CheckFailure.message("Migration replay fixture: \(app.errorText ?? app.status)") }
    await app.library.saveNote(id: original.id, note: "test data")
    let source = try app.auxiliaryDatabase()
    let copyURL = folder.appendingPathComponent("copy.sqlite"), legacyURL = folder.appendingPathComponent("legacy.sqlite")
    try await source.backup(to: copyURL)
    // A real schema-v4 database from the bundled SQL, holding the work as lineage-only. Writing `user_version = 4`
    // into today's database stopped working at v6: opening checks the tables and the migration names too.
    let resources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().appendingPathComponent("Packages/InkuPersistence/Sources/InkuPersistence/Resources")
    var build = ""
    for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4"] {
        build += try String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8) + "\n"
    }
    _ = try legacySQLite(legacyURL, build)
    let tables = try legacySQLite(legacyURL, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('schema_migrations') AND name NOT LIKE 'sqlite_%';")
        .split(separator: "\n").map(String.init)
    var copy = "ATTACH DATABASE '\(copyURL.path)' AS today; PRAGMA foreign_keys=OFF; BEGIN;"
    for table in tables {
        let columns = try legacySQLite(legacyURL, "SELECT name FROM pragma_table_info('\(table)');")
            .split(separator: "\n").map { "\"\($0)\"" }.joined(separator: ", ")
        copy += " INSERT INTO main.\"\(table)\" (\(columns)) SELECT \(columns) FROM today.\"\(table)\";"
    }
    copy += " UPDATE history SET history_visibility='lineage_only'; UPDATE lineage_nodes SET state='lineage_only'; COMMIT;"
    _ = try legacySQLite(legacyURL, copy)
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

/// One sqlite3 run on an isolated file; its standard output, one row per line.
private func legacySQLite(_ url: URL, _ sql: String) throws -> String {
    let process = Process(), output = Pipe(), errors = Pipe()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3")
    process.arguments = [url.path]
    let input = Pipe()
    process.standardInput = input; process.standardOutput = output; process.standardError = errors
    try process.run()
    input.fileHandleForWriting.write(Data(sql.utf8)); try input.fileHandleForWriting.close()
    let text = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    let failure = String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    process.waitUntilExit()
    guard process.terminationStatus == 0, failure.isEmpty else {
        throw CheckFailure.message("Could not prepare the isolated schema-v4 database: \(failure)")
    }
    return text.trimmingCharacters(in: .whitespacesAndNewlines)
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
