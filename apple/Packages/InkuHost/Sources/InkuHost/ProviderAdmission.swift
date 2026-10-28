import Foundation
import InkuCore
import InkuPersistence

/// Shared admission calculations. Persistence, waiting and the clock stay in the host.
public enum ProviderAdmission {
    public static func call(_ request: ExactJSON) throws -> ExactJSON {
        let answer = try ExactJSON(data: InkuCore.providerAdmission(request.data))
        if answer["error"].string == "corrupt_state" { throw PersistenceError.corruptDatabase }
        guard answer["error"] == .null else { throw HostError("pipeline_schema_violation") }
        return answer
    }

    public static func state(_ value: ProviderRateState) -> ExactJSON {
        .object(["events": .array(value.events.map { .object(["id": .string($0.id), "at": .number(String($0.at)), "tokens": .integer($0.tokens)]) }),
                 "day": .string(value.day), "daily": .integer(value.daily), "not_before": .number(String(value.notBefore))])
    }

    /// Convert only the core-owned fields, preserving the host's legacy-import markers.
    public static func apply(_ value: ExactJSON, to state: inout ProviderRateState) throws {
        guard let events = value["events"].array, let day = value["day"].string,
              let daily = value["daily"].number.flatMap(Int.init), daily >= 0,
              let notBefore = value["not_before"].number.flatMap(Double.init), notBefore.isFinite, notBefore >= 0 else {
            throw PersistenceError.corruptDatabase
        }
        let converted: [ProviderRateEvent] = try events.map { event in
            guard let id = event["id"].string, !id.isEmpty, let at = event["at"].number.flatMap(Double.init), at.isFinite, at >= 0,
                  let tokens = event["tokens"].number.flatMap(Int.init), tokens >= 0 else { throw PersistenceError.corruptDatabase }
            return ProviderRateEvent(id: id, at: at, tokens: tokens)
        }
        state.events = converted; state.day = day; state.daily = daily; state.notBefore = notBefore
    }

    public static func limits(_ limits: EffectiveProviderRateLimits) -> ExactJSON {
        .object(["rpm": .integer(limits.requestsPerMinute), "tpm": .integer(limits.tokensPerMinute), "rpd": .integer(limits.requestsPerDay)])
    }

    public static func estimate(kind: ProviderKind, tpm: Int, bodyBytes: Int, countResponse: ExactJSON? = nil) throws -> ExactJSON {
        var input: ExactJSON = .object(["action": .string("estimate"), "kind": .string(kind.rawValue),
                                        "tpm": .integer(tpm), "body_bytes": .integer(bodyBytes)])
        if let countResponse { input["count_response"] = countResponse }
        return try call(input)
    }
    public static func preflight(_ tokens: ExactJSON, limits: EffectiveProviderRateLimits) throws {
        let result = try call(.object(["action": .string("preflight"), "limits": self.limits(limits), "input_tokens": tokens]))
        guard result["decision"].string == "continue" else { throw HostError("rate_limited") }
    }
}
