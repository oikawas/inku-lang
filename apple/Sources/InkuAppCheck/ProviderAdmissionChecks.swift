import Foundation
import InkuHost
import InkuPersistence

/// Compare exact integers and numeric values while allowing the core's 62 and 62.0 spelling.
private func equalAdmissionJSON(_ a: ExactJSON, _ b: ExactJSON) -> Bool {
    switch (a, b) {
    case (.number(let x), .number(let y)):
        if x == y { return true }
        guard let left = Decimal(string: x, locale: Locale(identifier: "en_US_POSIX")),
              let right = Decimal(string: y, locale: Locale(identifier: "en_US_POSIX")) else { return false }
        return left == right
    case (.array(let x), .array(let y)):
        return x.count == y.count && zip(x, y).allSatisfy { equalAdmissionJSON($0.0, $0.1) }
    case (.object(let x), .object(let y)):
        return Set(x.keys) == Set(y.keys) && x.allSatisfy { key, value in y[key].map { equalAdmissionJSON(value, $0) } ?? false }
    default: return a == b
    }
}

func runProviderAdmissionChecks(casesURL: URL, sequenceURL: URL) throws {
    let cases = try ExactJSON(data: Data(contentsOf: casesURL))["cases"].array ?? []
    guard cases.count == 50 else { throw CheckFailure.message("Expected 50 admission cases") }
    let marker = String(repeating: "a", count: 64)
    for row in cases {
        var request = row["request"]
        var state = ProviderRateState(); state.importedLegacySources = [marker]
        if request["state"].object != nil {
            try ProviderAdmission.apply(request["state"], to: &state)
            request["state"] = ProviderAdmission.state(state)
        }
        let result = try ProviderAdmission.call(request)
        guard equalAdmissionJSON(result, row["expected"]) else { throw CheckFailure.message("Admission case \(row["name"].string ?? "?") failed: \(result.text)") }
        if result["state"].object != nil {
            try ProviderAdmission.apply(result["state"], to: &state)
            guard state.importedLegacySources == [marker], equalAdmissionJSON(ProviderAdmission.state(state), result["state"]) else {
                throw CheckFailure.message("Admission state or legacy marker changed")
            }
        }
    }
    let sequence = try ExactJSON(data: Data(contentsOf: sequenceURL))
    guard let steps = sequence["steps"].array, steps.count == 10 else { throw CheckFailure.message("Expected 10 admission steps") }
    var state = ProviderRateState(); state.importedLegacySources = [marker]
    var reservation = ""
    for (index, step) in steps.enumerated() {
        let action = step["action"].string ?? ""
        if action != "advance" {
            var request: ExactJSON = .object(["action": .string(action == "reserve" ? "admit" : action), "state": ProviderAdmission.state(state),
                "now": step["now"], "kind": .string("gemini"), "limits": sequence["limits"], "id": step["id"]])
            if action == "reserve" { request["input_tokens"] = step["value"] }
            if action == "settle" { request["id"] = .string(reservation); request["input_tokens"] = step["value"] }
            if action == "pause" { request["seconds"] = step["value"] }
            let result = try ProviderAdmission.call(request)
            if action == "reserve" {
                let expectedStatus = step["status"].string ?? ""
                if result["decision"].string == "admit" { guard expectedStatus == "ok" else { throw CheckFailure.message("Sequence decision \(index)") }; reservation = step["id"].string ?? "" }
                else if result["decision"].string == "wait" {
                    guard expectedStatus.hasPrefix("wait:"), let expected = Double(expectedStatus.dropFirst(5)),
                          result["seconds"].number.flatMap(Double.init) == expected else { throw CheckFailure.message("Sequence wait \(index)") }
                } else { throw CheckFailure.message("Sequence rejected at \(index)") }
            }
            try ProviderAdmission.apply(result["state"], to: &state)
        }
        guard let json = step["json"].string,
              equalAdmissionJSON(ProviderAdmission.state(state), try ExactJSON(data: Data(json.utf8))),
              state.importedLegacySources == [marker] else { throw CheckFailure.message("Sequence state \(index)") }
    }
    let wide = try ProviderAdmission.estimate(kind: .gemini, tpm: 1, bodyBytes: 0,
        countResponse: .object(["totalTokens": .number("18446744073709551615")]))
    guard wide["input_tokens"].number == "20291418481080506777" else { throw CheckFailure.message("Wide estimate lost precision") }
    do {
        try ProviderAdmission.preflight(wide["input_tokens"], limits: .init(requestsPerMinute: 0, tokensPerMinute: 1, requestsPerDay: 0))
        throw CheckFailure.message("Wide estimate passed the token budget")
    } catch let error as HostError where error.code == "rate_limited" { }
    let retryBody = "{\"error\":{\"details\":[{\"@type\":\"type.googleapis.com/google.rpc.RetryInfo\",\"retryDelay\":\"91s\"}]}}"
    let utf16 = Data([0xff, 0xfe]) + retryBody.data(using: .utf16LittleEndian)!
    let answer = try ProviderAdmission.call(.object(["action": .string("retry"), "now": .integer(0),
        "raw_bytes": .array(utf16.map { .integer($0) })]))
    guard answer["seconds"].number.flatMap(Double.init) == 91 else { throw CheckFailure.message("UTF-16 RetryInfo was not read") }
    print("Provider admission passed: 50 shared cases, 10 state steps, wide preflight and UTF-16 retry. No provider calls.")
}
