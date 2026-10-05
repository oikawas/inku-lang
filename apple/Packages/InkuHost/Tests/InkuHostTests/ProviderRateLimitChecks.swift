import Foundation
import InkuPersistence
import SQLite3
import XCTest
@testable import InkuHost

final class ProviderRateLimitChecks: XCTestCase, @unchecked Sendable {
    // Failure: independent cached ledgers admit the same last slot, lose usage on
    // restart/restore, or send despite the Server's input/day/deadline policy.
    func testDurableAdmissionDeadlineAndRetryAccounting() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-rate-budget-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let absent = folder.appendingPathComponent("absent-legacy.json")
        let clock = RateCheckClock(date: ISO8601DateFormatter().date(from: "2026-10-03T06:59:59Z")!)
        let databaseURL = folder.appendingPathComponent("works.sqlite")
        try Self.makeV2(databaseURL)
        let firstDB = try InkuDatabase(url: databaseURL)
        XCTAssertEqual(try Self.integerSQL(databaseURL, "PRAGMA user_version"), 3)
        let retained = try await firstDB.work(id: "fixture-work")
        XCTAssertEqual(retained?.svg, "<svg/>")
        let secondDB = try InkuDatabase(url: databaseURL)

        let gemini = ProviderSettings(id: "gemini", kind: .gemini, baseURL: URL(string: "https://fixture.invalid")!, requiresAPIKey: false)
        XCTAssertEqual(gemini.effectiveRateLimits, .init(requestsPerMinute: 30, tokensPerMinute: 16_000, requestsPerDay: 14_400))
        var old = gemini; old.rateLimits = ProviderRateLimits()
        XCTAssertEqual(old.effectiveRateLimits, .init(requestsPerMinute: 0, tokensPerMinute: 0, requestsPerDay: 0))
        old.rateLimits = .init(requestsPerMinute: 0, tokensPerMinute: 0, requestsPerDay: 0); try old.validate()
        XCTAssertEqual(ProviderRateLimits.defaults(providerID: "custom").effective(providerID: "custom"), old.effectiveRateLimits)
        XCTAssertEqual(EffectiveProviderRateLimits(requestsPerMinute: 1, tokensPerMinute: 1, requestsPerDay: 0).minuteRequestBudget, 1)

        // One slot at 90% of RPM2, acquired concurrently through separate connections.
        // One transport uses the normal API and one the durable observation API.
        let race = Self.provider("race", limits: .init(requestsPerMinute: 2, requestsPerDay: 10))
        let raceHTTP = RateCheckHTTP(database: firstDB, providerID: race.id, mode: .ordinary)
        let a = URLSessionProviderTransport(usageURL: absent, http: raceHTTP, database: firstDB, environment: clock.environment)
        let b = URLSessionProviderTransport(usageURL: absent, http: raceHTTP, database: secondDB, environment: clock.environment)
        let sink = RateCheckSink(url: folder.appendingPathComponent("observation.json"))
        async let normal = a.perform(action: Self.action("normal"), models: Self.models(race.id), providers: [race], credentials: RateCheckCredentials(), onBytes: { _ in })
        async let observed = b.performObserved(action: Self.action("observed"), models: Self.models(race.id), providers: [race], credentials: RateCheckCredentials(),
            observation: .init(captureRaw: true), willSend: { try await sink.save($0) }, didFinish: { try await sink.save($0) }, onBytes: { _ in })
        let results = try await [normal, observed].map { try ExactJSON(data: $0) }
        XCTAssertEqual(results.map { $0["tag"].string ?? "" }.sorted(), ["composition_read", "provider_failed"])
        XCTAssertEqual(results.first { $0["tag"].string == "provider_failed" }?["failure"].string, "rate_limited")
        let raceCount = await raceHTTP.generations
        XCTAssertEqual(raceCount, 1)
        let raceState = try await state(secondDB, race.id)
        XCTAssertEqual(raceState.events.count, 1); XCTAssertEqual(raceState.daily, 1)
        XCTAssertEqual(raceState.notBefore, 0) // Missing usage does not pause a disabled TPM limit.
        let observedRecords = await sink.records
        XCTAssertEqual(observedRecords.count, 2)
        XCTAssertEqual(observedRecords.last?.metric.stage, .composition)

        let limiter = ProviderRateBudget(database: firstDB, legacyURL: absent, environment: clock.environment)
        let window = Self.provider("window", limits: .init(requestsPerMinute: 10, tokensPerMinute: 1_000))
        for _ in 0..<9 { _ = try await limiter.reserve(provider: window, inputTokens: 10, deadline: clock.now.addingTimeInterval(1_000)) }
        await expectLimited { _ = try await limiter.reserve(provider: window, inputTokens: 10, deadline: clock.now.addingTimeInterval(1)) }
        _ = try await limiter.reserve(provider: window, inputTokens: 10, deadline: clock.now.addingTimeInterval(1_000))
        // Fixed sleep advances the clock; no real wait. The refused reservation waits as Server does and
        // is refused at its deadline, then the next one waits out the window.
        XCTAssertEqual(clock.sleeps, [62, 62])
        let settled = try await limiter.reserve(provider: Self.provider("usage", limits: .init(tokensPerMinute: 1_000)), inputTokens: 100, deadline: clock.now.addingTimeInterval(2))
        try await limiter.settle(providerID: "usage", reservation: settled, used: nil)
        let unknown = try await state(firstDB, "usage")
        XCTAssertEqual(unknown.events.first?.tokens, 100)
        XCTAssertEqual(unknown.notBefore, clock.now.timeIntervalSince1970 + 62)
        try await limiter.coolDown(providerID: "usage", seconds: 100)
        try await limiter.coolDown(providerID: "usage", seconds: 1)
        let held = try await state(firstDB, "usage")
        XCTAssertEqual(held.notBefore, clock.now.timeIntervalSince1970 + 100)
        try await limiter.settle(providerID: "usage", reservation: settled, used: 0)
        let zero = try await state(firstDB, "usage")
        XCTAssertEqual(zero.events.first?.tokens, 0); XCTAssertEqual(zero.notBefore, held.notBefore)

        // Real transport admission rejects a one-request TPM oversize before HTTP.
        let tiny = Self.provider("tiny", limits: .init(tokensPerMinute: 1))
        let tinyHTTP = RateCheckHTTP(database: firstDB, providerID: tiny.id, mode: .ordinary)
        let tinyTransport = URLSessionProviderTransport(usageURL: absent, http: tinyHTTP, database: firstDB, environment: clock.environment)
        let oversized = try ExactJSON(data: await tinyTransport.perform(action: Self.action("tiny"), models: Self.models(tiny.id), providers: [tiny], credentials: RateCheckCredentials(), onBytes: { _ in }))
        XCTAssertEqual(oversized["failure"].string, "rate_limited")
        let tinyCount = await tinyHTTP.generations; XCTAssertEqual(tinyCount, 0)

        let countedProvider = Self.provider("gemini-count", kind: .gemini, limits: .init(tokensPerMinute: 1_000))
        let countedHTTP = RateCheckHTTP(database: firstDB, providerID: countedProvider.id, mode: .gemini)
        let countedTransport = URLSessionProviderTransport(usageURL: absent, http: countedHTTP, database: firstDB, environment: clock.environment)
        let counted = try ExactJSON(data: await countedTransport.perform(action: Self.action("counted"), models: Self.models(countedProvider.id), providers: [countedProvider], credentials: RateCheckCredentials(), onBytes: { _ in }))
        XCTAssertEqual(counted["tag"].string, "composition_read")
        let countedState = try await state(firstDB, countedProvider.id)
        XCTAssertEqual(countedState.events.first?.tokens, 85)
        let counts = await countedHTTP.counts; XCTAssertEqual(counts, 1)
        let missingProvider = Self.provider("gemini-missing", kind: .gemini, limits: .init(tokensPerMinute: 1_000))
        let missingHTTP = RateCheckHTTP(database: firstDB, providerID: missingProvider.id, mode: .missingCount)
        let missingTransport = URLSessionProviderTransport(usageURL: absent, http: missingHTTP, database: firstDB, environment: clock.environment)
        let missing = try ExactJSON(data: await missingTransport.perform(action: Self.action("missing"), models: Self.models(missingProvider.id), providers: [missingProvider], credentials: RateCheckCredentials(), onBytes: { _ in }))
        XCTAssertEqual(missing["failure"].string, "rate_limited")
        let missingGenerations = await missingHTTP.generations; XCTAssertEqual(missingGenerations, 0)

        let retryInfo = Data(#"{"error":{"details":[{"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"125s"}]}}"#.utf8)
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
        XCTAssertEqual(ProviderRateBudget.retryAfter(formatter.string(from: clock.now.addingTimeInterval(90)), raw: retryInfo, now: clock.now), 125)
        let retryProvider = Self.provider("retry", limits: .init(requestsPerDay: 2))
        let retryHTTP = RateCheckHTTP(database: firstDB, providerID: retryProvider.id, mode: .retry429)
        let retryTransport = URLSessionProviderTransport(usageURL: absent, http: retryHTTP, database: firstDB, environment: clock.environment)
        for index in 0..<2 {
            let refusal = try ExactJSON(data: await retryTransport.perform(action: Self.action("retry-\(index)"), models: Self.models(retryProvider.id), providers: [retryProvider], credentials: RateCheckCredentials(), onBytes: { _ in }))
            XCTAssertEqual(refusal["failure"].string, "rate_limited")
            if index == 0 { clock.advance(99) }
        }
        let daily = try ExactJSON(data: await retryTransport.perform(action: Self.action("daily"), models: Self.models(retryProvider.id), providers: [retryProvider], credentials: RateCheckCredentials(), onBytes: { _ in }))
        XCTAssertEqual(daily["failure"].string, "rate_limited")
        let retryCount = await retryHTTP.generations; XCTAssertEqual(retryCount, 2)
        let retryState = try await state(firstDB, retryProvider.id)
        XCTAssertEqual(retryState.daily, 2)
        XCTAssertEqual(retryState.notBefore, clock.now.timeIntervalSince1970 + 99)

        // Legacy JSON is preserved; UTC-pruned Gemini day counts are never guessed as zero.
        let legacyURL = folder.appendingPathComponent("legacy.json")
        let legacyClock = RateCheckClock(date: ISO8601DateFormatter().date(from: "2026-10-03T06:59:59Z")!)
        let legacy: ExactJSON = .object(["reservations": .object(["gemini": .array([.object(["id": .string("legacy-unsent"),
            "at": .number(String(legacyClock.now.timeIntervalSinceReferenceDate - 1)), "tokens": .integer(100)])])]),
            "cooldowns": .object(["gemini": .number(String(legacyClock.now.timeIntervalSinceReferenceDate))])])
        try legacy.data.write(to: legacyURL)
        var legacyGemini = gemini; legacyGemini.rateLimits = .init(requestsPerDay: 2)
        let heldGemini = legacyGemini
        let legacyBudget = ProviderRateBudget(database: firstDB, legacyURL: legacyURL, environment: legacyClock.environment)
        await expectLimited { _ = try await legacyBudget.reserve(provider: heldGemini, inputTokens: 0, deadline: legacyClock.now.addingTimeInterval(2)) }
        let imported = try await state(secondDB, "gemini")
        XCTAssertEqual(imported.day, "2026-10-02"); XCTAssertEqual(imported.daily, 2)
        XCTAssertEqual(imported.events.first?.id, "legacy-unsent")
        XCTAssertEqual(try Data(contentsOf: legacyURL), legacy.data)
        legacyClock.advance(1)
        _ = try await legacyBudget.reserve(provider: legacyGemini, inputTokens: 0, deadline: legacyClock.now.addingTimeInterval(2))
        let midnight = try await state(secondDB, "gemini")
        XCTAssertEqual(midnight.day, "2026-10-03"); XCTAssertEqual(midnight.daily, 1)
        XCTAssertEqual(ProviderRateBudget.day(legacyClock.now.addingTimeInterval(-1), kind: .openAICompatible), "2026-10-03")

        let brokenJSON = folder.appendingPathComponent("broken.json"); try Data("{".utf8).write(to: brokenJSON)
        let brokenProvider = Self.provider("broken")
        let brokenHTTP = RateCheckHTTP(database: firstDB, providerID: brokenProvider.id, mode: .ordinary)
        let broken = URLSessionProviderTransport(usageURL: brokenJSON, http: brokenHTTP, database: firstDB, environment: clock.environment)
        let invalid = try ExactJSON(data: await broken.perform(action: Self.action("broken"), models: Self.models(brokenProvider.id), providers: [brokenProvider], credentials: RateCheckCredentials(), onBytes: { _ in }))
        XCTAssertEqual(invalid["failure"].string, "transport_unavailable")
        let brokenCount = await brokenHTTP.generations; XCTAssertEqual(brokenCount, 0)
        let blockedURL = folder.appendingPathComponent("write-failure.sqlite"), blockedDB = try InkuDatabase(url: blockedURL)
        try Self.executeSQL(blockedURL, "CREATE TRIGGER fixture_write_failure BEFORE INSERT ON provider_rate_state BEGIN SELECT RAISE(ABORT, 'fixture'); END;")
        let blockedHTTP = RateCheckHTTP(database: blockedDB, providerID: brokenProvider.id, mode: .ordinary)
        let blocked = URLSessionProviderTransport(usageURL: absent, http: blockedHTTP, database: blockedDB, environment: clock.environment)
        let notSaved = try ExactJSON(data: await blocked.perform(action: Self.action("write-failed"), models: Self.models(brokenProvider.id), providers: [brokenProvider], credentials: RateCheckCredentials(), onBytes: { _ in }))
        XCTAssertEqual(notSaved["failure"].string, "transport_unavailable")
        let blockedCount = await blockedHTTP.generations; XCTAssertEqual(blockedCount, 0)

        let backup = folder.appendingPathComponent("budget-backup.sqlite")
        try await firstDB.backup(to: backup)
        let restored = try InkuDatabase(url: folder.appendingPathComponent("restored.sqlite"))
        try await restored.restore(from: backup)
        let restoredRetry = try await restored.providerRateState(providerID: retryProvider.id)
        XCTAssertEqual(restoredRetry, retryState)
        let oldBackup = folder.appendingPathComponent("old-v2-backup.sqlite"); try Self.makeV2(oldBackup)
        try await firstDB.restore(from: oldBackup)
        let protected = try await secondDB.providerRateState(providerID: retryProvider.id)
        XCTAssertEqual(protected, retryState)
        let oldArtwork = try await firstDB.work(id: "fixture-work")
        XCTAssertEqual(oldArtwork?.svg, "<svg/>")
    }

    private func expectLimited(_ operation: @Sendable () async throws -> Void) async {
        do { try await operation(); XCTFail("A bounded rate refusal admitted a send") }
        catch { XCTAssertEqual((error as? HostError)?.code, "rate_limited") }
    }
    private func state(_ database: InkuDatabase, _ provider: String) async throws -> ProviderRateState {
        let result = try await database.providerRateState(providerID: provider)
        return try XCTUnwrap(result)
    }
    private static func provider(_ id: String, kind: ProviderKind = .openAICompatible, limits: ProviderRateLimits = .init()) -> ProviderSettings {
        .init(id: id, kind: kind, baseURL: URL(string: "https://fixture.invalid/v1")!, requiresAPIKey: false, rateLimits: limits)
    }
    private static func models(_ provider: String) -> ModelSelection { .init(stage1Model: provider + ":offered", stage2Model: provider + ":unused") }
    private static func action(_ id: String) -> Data {
        ExactJSON.object(["tag": .string("read_composition"), "identity": .object(["action_id": .string(id), "attempt": .integer(1), "request_digest": .string("digest-" + id)]),
            "timeout_ms": .string("2000"), "payload": .object(["prompt": .object(["system": .string("system"), "message": .string("message"),
                "action_name": .string("read_composition"), "response_schema": .object(["type": .string("object")])])])]).data
    }
    private static func makeV2(_ url: URL) throws {
        let packages = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let resources = packages.appendingPathComponent("InkuPersistence/Sources/InkuPersistence/Resources")
        let sql = try String(contentsOf: resources.appendingPathComponent("schema-v1.sql"), encoding: .utf8)
            + String(contentsOf: resources.appendingPathComponent("migration-v2.sql"), encoding: .utf8)
        try executeSQL(url, sql + """
            INSERT INTO lineage_nodes (id, state, at) VALUES ('fixture-node', 'visible', 1);
            INSERT INTO history (id, at, input, score, svg, lineage_node_id) VALUES ('fixture-work', 1, 'kept', '{}', '<svg/>', 'fixture-node');
            UPDATE lineage_nodes SET history_id = 'fixture-work' WHERE id = 'fixture-node';
            """)
    }
    private static func executeSQL(_ url: URL, _ sql: String) throws {
        var db: OpaquePointer?
        guard sqlite3_open(url.path, &db) == SQLITE_OK else { throw HostError("fixture_sql_open_failed") }
        defer { sqlite3_close(db) }
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else { throw HostError("fixture_sql_failed") }
    }
    private static func integerSQL(_ url: URL, _ sql: String) throws -> Int {
        var db: OpaquePointer?, statement: OpaquePointer?
        guard sqlite3_open(url.path, &db) == SQLITE_OK else { throw HostError("fixture_sql_open_failed") }
        defer { sqlite3_finalize(statement); sqlite3_close(db) }
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK, sqlite3_step(statement) == SQLITE_ROW else { throw HostError("fixture_sql_failed") }
        return Int(sqlite3_column_int64(statement, 0))
    }
}

private final class RateCheckClock: @unchecked Sendable {
    private let lock = NSLock()
    private var date: Date
    private var waits: [TimeInterval] = []
    init(date: Date) { self.date = date }
    var now: Date { lock.withLock { date } }
    var sleeps: [TimeInterval] { lock.withLock { waits } }
    func advance(_ seconds: TimeInterval) { lock.withLock { date.addTimeInterval(seconds) } }
    var environment: ProviderRateEnvironment {
        .init(clock: { self.now }, sleep: { seconds in
            try Task.checkCancellation()
            self.lock.withLock { self.waits.append(seconds); self.date.addTimeInterval(seconds) }
        })
    }
}
private struct RateCheckCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}
private actor RateCheckSink {
    let url: URL
    private(set) var records: [ProviderAttemptObservation] = []
    init(url: URL) { self.url = url }
    func save(_ value: ProviderAttemptObservation) throws { try JSONEncoder().encode(value).write(to: url, options: .atomic); records.append(value) }
}
private actor RateCheckHTTP: ProviderHTTPClient {
    enum Mode: Sendable, Equatable { case ordinary, gemini, missingCount, retry429 }
    let database: InkuDatabase
    let providerID: String
    let mode: Mode
    private(set) var generations = 0
    private(set) var counts = 0
    private var countBody: ExactJSON?
    init(database: InkuDatabase, providerID: String, mode: Mode) { self.database = database; self.providerID = providerID; self.mode = mode }
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        let body = try ExactJSON(data: request.httpBody!)
        if request.url!.path.hasSuffix(":countTokens") {
            counts += 1; countBody = body["generateContentRequest"]
            let data = (mode == .missingCount ? ExactJSON.object([:]) : .object(["totalTokens": .integer(100)])).data
            onResponse(.init(status: 200, data: data, sent: true, complete: true, truncated: false))
            return .init(status: 200, data: data)
        }
        generations += 1
        let state = try await database.providerRateState(providerID: providerID)
        guard let state, state.daily > 0, !state.events.isEmpty else { throw HostError("fixture_send_before_durable_reservation") }
        var status = 200, value: ExactJSON
        switch mode {
        case .ordinary:
            value = .object(["choices": .array([.object(["message": .object(["content": .string("{\"composition\":\"fixture\"}")])])])])
        case .gemini:
            var counted = countBody!; counted["model"] = .null
            var fields = counted.object!; fields.removeValue(forKey: "model")
            guard .object(fields) == body, state.events.first?.tokens == 110 else { throw HostError("fixture_count_estimate_or_schema_changed") }
            value = .object(["usageMetadata": .object(["promptTokenCount": .integer(85)]), "candidates": .array([.object(["content": .object(["parts": .array([
                .object(["functionCall": .object(["name": .string(ProviderWire.responseName), "args": .object(["composition": .string("fixture")])])])])])])])])
        case .missingCount: throw HostError("fixture_missing_count_sent_generation")
        case .retry429:
            status = 429; value = .object(["error": .object(["details": .array([.object(["@type": .string("type.googleapis.com/google.rpc.RetryInfo"), "retryDelay": .string("99s")])])])])
        }
        onBytes(value.data.count); onResponse(.init(status: status, data: value.data, sent: true, complete: true, truncated: false))
        return .init(status: status, data: value.data, retryAfter: 1)
    }
}
