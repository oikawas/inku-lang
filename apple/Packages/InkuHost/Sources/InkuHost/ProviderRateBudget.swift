import CryptoKit
import Foundation
import InkuPersistence

struct ProviderRateEnvironment: Sendable {
    let clock: @Sendable () -> Date
    let sleep: @Sendable (TimeInterval) async throws -> Void
    static let live = Self(clock: { Date() }, sleep: { try await Task.sleep(for: .seconds($0)) })
}

/// The DB transaction, rather than this actor's memory, owns shared admission state.
actor ProviderRateBudget {
    static let window: TimeInterval = 62
    nonisolated let environment: ProviderRateEnvironment
    private var database: InkuDatabase?
    private let legacyURL: URL
    init(database: InkuDatabase?, legacyURL: URL, environment: ProviderRateEnvironment = .live) {
        self.database = database; self.legacyURL = legacyURL; self.environment = environment
    }
    nonisolated func now() -> Date { environment.clock() }

    /// CountTokens is not a generation reservation. Still verify durable accounting
    /// before its HTTP call, so a broken ledger cannot cause any provider send.
    /// The daily limit is judged at reservation, after the count, as Server does.
    func prepare(provider: ProviderSettings) async throws {
        let database = try accountingDatabase()
        try await importLegacy(provider: provider, database: database)
    }

    func reserve(provider: ProviderSettings, inputTokens: Int, deadline: Date) async throws -> String {
        let limits = provider.effectiveRateLimits
        guard inputTokens >= 0 else { throw HostError("rate_limited") }
        try ProviderAdmission.preflight(.integer(inputTokens), limits: limits)
        let database = try accountingDatabase()
        try await importLegacy(provider: provider, database: database)
        let token = UUID().uuidString
        while true {
            try Task.checkCancellation()
            let now = now(), timestamp = now.timeIntervalSince1970
            let delay = try await database.changeProviderRateState(providerID: provider.id) { state in
                let result = try ProviderAdmission.call(.object(["action": .string("admit"), "state": ProviderAdmission.state(state),
                    "now": .number(String(timestamp)), "kind": .string(provider.kind.rawValue), "limits": ProviderAdmission.limits(limits),
                    "input_tokens": .integer(inputTokens), "id": .string(token)]))
                switch result["decision"].string {
                case "reject": throw HostError("rate_limited")
                case "admit":
                    guard timestamp < deadline.timeIntervalSince1970 else { throw HostError("rate_limited") }
                    try ProviderAdmission.apply(result["state"], to: &state)
                    return 0.0
                case "wait":
                    guard let delay = result["seconds"].number.flatMap(Double.init), delay.isFinite, delay > 0 else { throw PersistenceError.corruptDatabase }
                    try ProviderAdmission.apply(result["state"], to: &state)
                    return delay
                default: throw PersistenceError.corruptDatabase
                }
            }
            if delay <= 0 { return token }
            // Server waits without its own deadline; the attempt deadline ends the wait as rate_limited.
            try await environment.sleep(delay)
        }
    }

    func settle(providerID: String, reservation: String, used: Int?) async throws {
        let database = try accountingDatabase(), now = now().timeIntervalSince1970
        try await database.changeProviderRateState(providerID: providerID) { state in
            if let used, used < 0 { throw PersistenceError.invalidRecord("negative provider usage") }
            let result = try ProviderAdmission.call(.object(["action": .string("settle"), "state": ProviderAdmission.state(state),
                "now": .number(String(now)), "id": .string(reservation), "input_tokens": used.map { .integer($0) } ?? .null]))
            try ProviderAdmission.apply(result["state"], to: &state)
        }
    }
    func coolDown(providerID: String, seconds: TimeInterval) async throws {
        let database = try accountingDatabase(), now = now().timeIntervalSince1970
        let delay = seconds.isFinite ? max(Self.window, seconds) : Self.window
        try await database.changeProviderRateState(providerID: providerID) { state in
            let result = try ProviderAdmission.call(.object(["action": .string("pause"), "state": ProviderAdmission.state(state),
                "now": .number(String(now)), "seconds": .number(String(delay))]))
            try ProviderAdmission.apply(result["state"], to: &state)
        }
    }
    private func accountingDatabase() throws -> InkuDatabase {
        if let database { return database }
        let database = try InkuDatabase(url: legacyURL.appendingPathExtension("sqlite"))
        self.database = database
        return database
    }

    private struct LegacyReservation: Codable, Sendable { let id: String; let at: Date; let tokens: Int }
    private struct LegacyState: Codable, Sendable { let reservations: [String: [LegacyReservation]]; let cooldowns: [String: Date] }
    private func importLegacy(provider: ProviderSettings, database: InkuDatabase) async throws {
        let source = SHA256.hash(data: Data(legacyURL.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
        if try await database.providerRateState(providerID: provider.id)?.importedLegacySources.contains(source) == true { return }
        let legacy: LegacyState?
        if FileManager.default.fileExists(atPath: legacyURL.path) {
            legacy = try JSONDecoder().decode(LegacyState.self, from: Data(contentsOf: legacyURL))
        } else { legacy = nil }
        let all = legacy?.reservations[provider.id] ?? []
        guard legacy?.reservations.values.allSatisfy({ events in
                  events.allSatisfy { !$0.id.isEmpty && $0.at.timeIntervalSince1970.isFinite && $0.at.timeIntervalSince1970 >= 0 && $0.tokens >= 0 }
                    && Set(events.map(\.id)).count == events.count
              }) ?? true,
              legacy?.cooldowns.values.allSatisfy({ $0.timeIntervalSince1970.isFinite && $0.timeIntervalSince1970 >= 0 }) ?? true else {
            throw PersistenceError.corruptDatabase
        }
        let now = now(), day = try Self.day(now, kind: provider.kind)
        let events = all.map { ProviderRateEvent(id: $0.id, at: $0.at.timeIntervalSince1970, tokens: $0.tokens) }
        let currentDayEvents = try all.filter { try Self.day($0.at, kind: provider.kind) == day }
        let legacyEntry = legacy?.reservations[provider.id] != nil || legacy?.cooldowns[provider.id] != nil
        let dailyHold = provider.kind == .gemini && legacyEntry ? provider.effectiveRateLimits.requestsPerDay : 0
        let cooldown = legacy?.cooldowns[provider.id]?.timeIntervalSince1970 ?? 0
        try await database.changeProviderRateState(providerID: provider.id) { state in
            guard !state.importedLegacySources.contains(source) else { return }
            if state.day != day { state.day = day; state.daily = 0 }
            let ids = Set(state.events.map(\.id))
            let newDaily = currentDayEvents.filter { !ids.contains($0.id) }.count
            let total = state.daily.addingReportingOverflow(newDaily)
            guard !total.overflow else { throw PersistenceError.corruptDatabase }
            state.daily = max(total.partialValue, dailyHold)
            var merged = Dictionary(uniqueKeysWithValues: state.events.map { ($0.id, $0) })
            for event in events {
                if let prior = merged[event.id] {
                    merged[event.id] = .init(id: event.id, at: max(prior.at, event.at), tokens: max(prior.tokens, event.tokens))
                } else { merged[event.id] = event }
            }
            state.events = merged.values.sorted { $0.id < $1.id }
            state.notBefore = max(state.notBefore, cooldown)
            state.importedLegacySources.append(source)
        }
    }
    static func day(_ date: Date, kind: ProviderKind) throws -> String {
        let result = try ProviderAdmission.call(.object(["action": .string("day"), "now": .number(String(date.timeIntervalSince1970)), "kind": .string(kind.rawValue)]))
        guard let day = result["day"].string else { throw PersistenceError.corruptDatabase }
        return day
    }

    static func retryAfter(_ header: String?, raw: Data, now: Date) -> TimeInterval {
        let input: ExactJSON = .object(["action": .string("retry"), "now": .number(String(now.timeIntervalSince1970)),
            "retry_after": .optional(header), "raw_bytes": .array(raw.map { .integer($0) })])
        return (try? ProviderAdmission.call(input)["seconds"].number.flatMap(Double.init)) ?? window
    }
}
