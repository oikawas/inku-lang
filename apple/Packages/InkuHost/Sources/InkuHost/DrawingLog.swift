import Foundation
import InkuPersistence

/// Ordinary execution facts. Private provider bodies, credentials and frozen settings are excluded.
public struct DrawingLogRecord: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let databaseRevision: Int64
    public let startedAt: Date
    public let description: String
    public let phase: String
    public let failureReason: String?
    public let failureStage: String?
    public let stage1Model: String
    public let stage2Model: String
    public let savedWorkID: String?
    public let providerMetrics: [ProviderAttemptMetric]
    public let events: [DrawingLogEvent]

    public var isTerminal: Bool { ["completed", "failed", "cancelled"].contains(phase) }
}

public struct DrawingLogEvent: Codable, Sendable, Equatable, Identifiable {
    public let sequence: String
    public let tag: String
    public let action: String?
    public let state: String?
    public let stage: String?
    public let reason: String?
    public let attempt: UInt32?
    public var id: String { sequence + ":" + tag }
}

extension PipelineHost {
    public func drawingLogs(limit: Int = 100) async throws -> [DrawingLogRecord] {
        let ids = try await database.listExecutionIDs(limit: limit)
        var result: [DrawingLogRecord] = []
        // Hold at most one private snapshot; developer captures can be much larger than public log facts.
        for id in ids {
            try Task.checkCancellation()
            if let record = try await database.loadExecution(id: id), let log = try Self.drawingLog(record) {
                result.append(log)
            }
        }
        return result.sorted { $0.startedAt > $1.startedAt }
    }

    public func drawingLog(executionID: String) async throws -> DrawingLogRecord? {
        guard let record = try await database.loadExecution(id: executionID) else { return nil }
        return try Self.drawingLog(record)
    }

    private static func drawingLog(_ record: ExecutionSnapshot) throws -> DrawingLogRecord? {
        let decoder = JSONDecoder()
        guard try decoder.decode(StoredDrawingLogSchema.self, from: record.snapshot).schema == "inku.swift-pipeline-execution.v1" else {
            return nil
        }
        // Decode only public fields; even developer-captured raw bodies are never decoded here.
        let stored = try decoder.decode(StoredDrawingLog.self, from: record.snapshot)
        let core = try ExactJSON(data: stored.snapshot)
        let events = try ExactJSON(data: stored.events).array ?? []
        let phase = core["phase"]["tag"].string ?? core["phase"].string ?? "unknown"
        let failure = phase == "failed" ? events.last { $0["tag"].string == "failed" }?["payload"] ?? .null : .null
        return DrawingLogRecord(id: record.id, databaseRevision: record.revision,
            startedAt: stored.startedAt, description: stored.description,
            phase: phase,
            failureReason: failure["reason"].string, failureStage: failure["stage"].string,
            stage1Model: stored.models.stage1Model, stage2Model: stored.models.stage2Model,
            savedWorkID: stored.savedWorkID, providerMetrics: stored.providerObservations?.map(\.metric) ?? [],
            events: events.map { event in
                let payload = event["payload"]
                return DrawingLogEvent(sequence: event["sequence"].string ?? "", tag: event["tag"].string ?? "unknown",
                    action: payload["tag"].string, state: payload["state"].string,
                    stage: payload["stage"].string,
                    reason: payload["reason"].string ?? payload["failure"].string ?? payload["detail"]["failure"].string,
                    attempt: payload["identity"]["attempt"].number.flatMap(UInt32.init))
            })
    }
}

private struct StoredDrawingLogSchema: Decodable { let schema: String }
private struct StoredDrawingLog: Decodable {
    struct Observation: Decodable { let metric: ProviderAttemptMetric }
    let snapshot: Data
    let events: Data
    let description: String
    let models: ModelSelection
    let startedAt: Date
    let savedWorkID: String?
    let providerObservations: [Observation]?
}
