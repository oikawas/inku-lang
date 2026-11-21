import Foundation
import InkuCore

struct WorkPackRecordIdentity: Codable, Sendable {
    let kind: String
    let key: String
    let identity: [String: String?]
}

struct WorkPackExisting: Encodable {
    var works: [String] = []
    var nodeRoots: [String: String] = [:]
    var parents: [String: String] = [:]

    enum CodingKeys: String, CodingKey {
        case works, nodeRoots = "node_roots", parents
    }
}

public struct WorkPackDecision: Decodable, Sendable, Equatable {
    public let workIDs: [String]
    public let nodeRoots: [String: String]
    public let edgeIDs: [String]
    let annotationIDs: [String]
    let colophonIDs: [String]
    public let skipped: Int

    enum CodingKeys: String, CodingKey {
        case workIDs = "works", nodeRoots = "node_roots", edgeIDs = "edges"
        case annotationIDs = "annotations", colophonIDs = "colophons", skipped
    }
}

struct WorkPackResponse: Decodable {
    let outcome: String
    let code: String?
    let reason: String?
    let line: UInt64?
    let kind: String?
    let key: String?
    let identity: [String: String?]?
    let counts: [String: Int]?

    var error: WorkPackError {
        switch code {
        case "newer_version": .newerVersion
        case "too_large": .tooLarge
        default:
            if reason == "invalid JSON object", let line { .invalid("line \(line)") }
            else { .invalid(reason ?? "record") }
        }
    }
}

enum WorkPackWire {
    static func plan(counts: [String: Int], records: [WorkPackRecordIdentity],
                     existing: WorkPackExisting) throws -> WorkPackDecision {
        struct Request: Encodable {
            let action = "plan"
            let counts: [String: Int]
            let records: [WorkPackRecordIdentity]
            let existing: WorkPackExisting
        }
        let request = try JSONEncoder().encode(Request(counts: counts, records: records, existing: existing))
        let data = InkuCore.workpackPlan(request)
        let decoder = JSONDecoder()
        let response = try decoder.decode(WorkPackResponse.self, from: data)
        guard response.outcome == "ok" else { throw response.error }
        return try decoder.decode(WorkPackDecision.self, from: data)
    }

    static func encode(_ request: [String: Any]) throws -> Data? {
        let bytes = try JSONSerialization.data(withJSONObject: request, options: [.withoutEscapingSlashes])
        let result = InkuCore.workpackEncodeLine(bytes)
        if let line = result.line { return line }
        guard let error = result.error else { throw WorkPackError.invalid("record") }
        let response = try JSONDecoder().decode(WorkPackResponse.self, from: error)
        if response.outcome == "omit" { return nil }
        throw response.error
    }
}
