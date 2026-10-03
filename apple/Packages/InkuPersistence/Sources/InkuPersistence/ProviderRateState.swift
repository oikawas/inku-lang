import Foundation
import GRDB

public struct ProviderRateEvent: Codable, Sendable, Equatable {
    public let id: String
    public let at: TimeInterval
    public var tokens: Int
    public init(id: String, at: TimeInterval, tokens: Int) { self.id = id; self.at = at; self.tokens = tokens }
}

/// Private accounting only; it carries no provider address, credentials or artwork.
public struct ProviderRateState: Codable, Sendable, Equatable {
    public var events: [ProviderRateEvent] = []
    public var day: String = ""
    public var daily: Int = 0
    public var notBefore: TimeInterval = 0
    public var importedLegacySources: [String] = []
    public init() {}
    static func decode(_ data: Data) throws -> ProviderRateState {
        do { return try JSONDecoder().decode(Self.self, from: data) }
        catch { throw PersistenceError.corruptDatabase }
    }
    func validate() throws {
        guard daily >= 0, notBefore.isFinite, notBefore >= 0,
              (day.isEmpty ? (daily == 0 && events.isEmpty) : Self.validDay(day)),
              events.allSatisfy({ !$0.id.isEmpty && $0.at.isFinite && $0.at >= 0 && $0.tokens >= 0 }),
              Set(events.map(\.id)).count == events.count,
              Set(importedLegacySources).count == importedLegacySources.count,
              importedLegacySources.allSatisfy({ $0.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }) else {
            throw PersistenceError.corruptDatabase
        }
    }
    private static func validDay(_ value: String) -> Bool {
        guard value.range(of: "^[0-9]{4}-[0-9]{2}-[0-9]{2}$", options: .regularExpression) != nil else { return false }
        let parts = value.split(separator: "-").compactMap { Int($0) }
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        guard let date = calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2])) else { return false }
        let day = calendar.dateComponents([.year, .month, .day], from: date)
        return day.year == parts[0] && day.month == parts[1] && day.day == parts[2]
    }
}

extension InkuDatabase {
    /// GRDB's write transaction starts IMMEDIATE, including across separate connections.
    /// Admission decisions and the durable reservation are committed together.
    public func changeProviderRateState<Result: Sendable>(providerID: String,
        _ operation: @Sendable (inout ProviderRateState) throws -> Result) throws -> Result {
        guard !providerID.isEmpty else { throw PersistenceError.invalidRecord("empty provider ID") }
        return try queue.write { db in
            let data = try Data.fetchOne(db, sql: "SELECT state_json FROM provider_rate_state WHERE provider_id = ?", arguments: [providerID])
            var state = try data.map(ProviderRateState.decode) ?? ProviderRateState()
            try state.validate()
            let result = try operation(&state)
            try state.validate()
            try db.execute(sql: """
                INSERT INTO provider_rate_state (provider_id, state_json) VALUES (?, ?)
                ON CONFLICT (provider_id) DO UPDATE SET state_json = excluded.state_json
                """, arguments: [providerID, try JSONEncoder().encode(state)])
            return result
        }
    }
    public func providerRateState(providerID: String) throws -> ProviderRateState? {
        try queue.read { db in
            let data = try Data.fetchOne(db, sql: "SELECT state_json FROM provider_rate_state WHERE provider_id = ?", arguments: [providerID])
            guard let data else { return nil }
            let state = try ProviderRateState.decode(data); try state.validate(); return state
        }
    }

    /// Restore requires stopped host activity. Merge the latest committed live
    /// accounting into the isolated backup before SQLite replaces artwork atomically.
    func retainLiveProviderRates(in restored: DatabaseQueue) throws {
        let live = try queue.read { db in
            try Row.fetchAll(db, sql: "SELECT provider_id, state_json FROM provider_rate_state").map { row in
                let provider: String = row["provider_id"], data: Data = row["state_json"]
                guard !provider.isEmpty else { throw PersistenceError.corruptDatabase }
                let state = try ProviderRateState.decode(data); try state.validate(); return (provider, state)
            }
        }
        try restored.write { db in
            for (provider, current) in live {
                let data = try Data.fetchOne(db, sql: "SELECT state_json FROM provider_rate_state WHERE provider_id = ?", arguments: [provider])
                var state = try data.map(ProviderRateState.decode) ?? ProviderRateState()
                try state.validate()
                if !current.day.isEmpty {
                    state.daily = state.day == current.day ? max(state.daily, current.daily) : current.daily
                    state.day = current.day
                }
                var events = Dictionary(uniqueKeysWithValues: state.events.map { ($0.id, $0) })
                for event in current.events {
                    if let prior = events[event.id] {
                        events[event.id] = ProviderRateEvent(id: event.id, at: max(prior.at, event.at), tokens: max(prior.tokens, event.tokens))
                    } else { events[event.id] = event }
                }
                state.events = events.values.sorted { $0.id < $1.id }
                state.notBefore = max(state.notBefore, current.notBefore)
                state.importedLegacySources = Array(Set(state.importedLegacySources + current.importedLegacySources)).sorted()
                try state.validate()
                try db.execute(sql: """
                    INSERT INTO provider_rate_state (provider_id, state_json) VALUES (?, ?)
                    ON CONFLICT (provider_id) DO UPDATE SET state_json = excluded.state_json
                    """, arguments: [provider, try JSONEncoder().encode(state)])
            }
        }
    }
}
