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
    func prepare(provider: ProviderSettings) async throws {
        let database = try accountingDatabase()
        try await importLegacy(provider: provider, database: database)
        let day = Self.day(now(), kind: provider.kind), limits = provider.effectiveRateLimits
        try await database.changeProviderRateState(providerID: provider.id) { state in
            if state.day == day && limits.requestsPerDay > 0 && state.daily >= limits.requestsPerDay { throw HostError("rate_limited") }
        }
    }

    func reserve(provider: ProviderSettings, inputTokens: Int, deadline: Date) async throws -> String {
        let limits = provider.effectiveRateLimits
        guard inputTokens >= 0, limits.minuteInputTokenBudget == 0 || inputTokens <= limits.minuteInputTokenBudget else {
            throw HostError("rate_limited")
        }
        let database = try accountingDatabase()
        try await importLegacy(provider: provider, database: database)
        let token = UUID().uuidString
        while true {
            try Task.checkCancellation()
            let now = now(), timestamp = now.timeIntervalSince1970
            let day = Self.day(now, kind: provider.kind)
            let delay = try await database.changeProviderRateState(providerID: provider.id) { state in
                state.events.removeAll { $0.at + Self.window <= timestamp }
                if state.day != day { state.day = day; state.daily = 0 }
                guard limits.requestsPerDay == 0 || state.daily < limits.requestsPerDay else { throw HostError("rate_limited") }
                var delay = max(0, state.notBefore - timestamp)
                var tokens = 0
                for event in state.events {
                    let sum = tokens.addingReportingOverflow(event.tokens)
                    guard !sum.overflow else { throw PersistenceError.corruptDatabase }
                    tokens = sum.partialValue
                }
                let total = tokens.addingReportingOverflow(inputTokens)
                guard !total.overflow else { throw PersistenceError.corruptDatabase }
                if (limits.minuteRequestBudget > 0 && state.events.count >= limits.minuteRequestBudget)
                    || (limits.minuteInputTokenBudget > 0 && total.partialValue > limits.minuteInputTokenBudget) {
                    guard let oldest = state.events.map(\.at).min() else { throw PersistenceError.corruptDatabase }
                    delay = max(delay, oldest + Self.window - timestamp)
                }
                if delay > 0 { return delay }
                guard timestamp < deadline.timeIntervalSince1970 else { throw HostError("rate_limited") }
                let daily = state.daily.addingReportingOverflow(1)
                guard !daily.overflow else { throw PersistenceError.corruptDatabase }
                state.events.append(.init(id: token, at: timestamp, tokens: inputTokens)); state.daily = daily.partialValue
                return 0.0
            }
            if delay <= 0 { return token }
            // No request can be admitted during this attempt if the wait consumes its deadline.
            guard delay < deadline.timeIntervalSince(now) else { throw HostError("rate_limited") }
            try await environment.sleep(delay)
        }
    }

    func settle(providerID: String, reservation: String, used: Int?) async throws {
        let database = try accountingDatabase(), now = now().timeIntervalSince1970
        try await database.changeProviderRateState(providerID: providerID) { state in
            if let used {
                guard used >= 0 else { throw PersistenceError.invalidRecord("negative provider usage") }
                if let index = state.events.firstIndex(where: { $0.id == reservation }) { state.events[index].tokens = used }
            } else { state.notBefore = max(state.notBefore, now + Self.window) }
        }
    }
    func coolDown(providerID: String, seconds: TimeInterval) async throws {
        let database = try accountingDatabase(), now = now().timeIntervalSince1970
        let delay = seconds.isFinite ? max(Self.window, seconds) : Self.window
        try await database.changeProviderRateState(providerID: providerID) { state in
            state.notBefore = max(state.notBefore, now + delay)
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
        let now = now(), day = Self.day(now, kind: provider.kind)
        let events = all.map { ProviderRateEvent(id: $0.id, at: $0.at.timeIntervalSince1970, tokens: $0.tokens) }
        let currentDayEvents = all.filter { Self.day($0.at, kind: provider.kind) == day }
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
    static func day(_ date: Date, kind: ProviderKind) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = kind == .gemini ? TimeZone(identifier: "America/Los_Angeles")! : TimeZone(secondsFromGMT: 0)!
        let value = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", value.year!, value.month!, value.day!)
    }

    static func retryAfter(_ header: String?, raw: Data, now: Date) -> TimeInterval {
        var values = [window]
        if let header {
            if let seconds = Double(header), seconds.isFinite { values.append(seconds) }
            else {
                let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
                formatter.timeZone = TimeZone(secondsFromGMT: 0)
                for format in ["EEE, dd MMM yyyy HH:mm:ss zzz", "EEEE, dd-MMM-yy HH:mm:ss zzz", "EEE MMM d HH:mm:ss yyyy"] {
                    formatter.dateFormat = format
                    if let date = formatter.date(from: header) { values.append(date.timeIntervalSince(now)); break }
                }
            }
        }
        if let value = try? ExactJSON(data: raw) {
            for detail in value["error"]["details"].array ?? [] {
                if detail["@type"].string == "type.googleapis.com/google.rpc.RetryInfo",
                   let text = detail["retryDelay"].string, text.hasSuffix("s"),
                   let delay = Double(text.dropLast()), delay.isFinite { values.append(delay) }
            }
        }
        return values.filter(\.isFinite).max() ?? window
    }
}
