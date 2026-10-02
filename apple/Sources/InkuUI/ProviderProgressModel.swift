import Foundation
import InkuHost

/// Presentation facts from one provider stage. Usage stays absent until a host reports it.
public struct ProviderProgressSnapshot: Sendable, Equatable {
    public enum Outcome: Sendable, Equatable { case running, succeeded, failed, cancelled, awaitingReview }
    public let executionID: String
    public let action: String
    public let attempt: Int
    public let maxAttempts: Int
    public let modelReference: String?
    public let comparison: Bool
    public let stageBeganAt: Date
    public let attemptBeganAt: Date
    public let deadline: Date
    public private(set) var attemptEndedAt: Date?
    public private(set) var stageEndedAt: Date?
    public private(set) var outcome: Outcome = .running
    public private(set) var awaitingReply = true
    public private(set) var receivedBytes: Int?
    public let tokensIn: UInt64? = nil
    public let tokensOut: UInt64? = nil

    public var clockRunning: Bool { outcome == .running && stageEndedAt == nil }
    public func stageElapsed(at date: Date) -> TimeInterval {
        max(0, (stageEndedAt ?? date).timeIntervalSince(stageBeganAt))
    }
    public func attemptElapsed(at date: Date) -> TimeInterval {
        max(0, (attemptEndedAt ?? date).timeIntervalSince(attemptBeganAt))
    }

    static func start(executionID: String, report: Data, beganAt: Date, deadline: Date,
                      models: ModelSelection?, comparison: Bool, previous: Self?) -> Self? {
        guard let report = try? ExactJSON(data: report), let action = report["provider_attempt"]["action"].string,
              let attempt = report["provider_attempt"]["attempt"].number.flatMap(Int.init), attempt > 0,
              let maximum = report["provider_attempt"]["max_attempts"].number.flatMap(Int.init), maximum >= attempt else { return nil }
        let sameStage = previous?.executionID == executionID && previous?.action == action
        if sameStage, let previous,
           beganAt < previous.attemptBeganAt || (attempt == previous.attempt && previous.outcome != .running) { return nil }
        let reference = action == "complete_visible_ddl_holes" ? models?.stage2Model : models?.stage1Model
        return Self(executionID: executionID, action: action, attempt: attempt, maxAttempts: maximum,
            modelReference: reference.flatMap { $0.isEmpty ? nil : $0 }, comparison: comparison,
            stageBeganAt: sameStage ? previous!.stageBeganAt : beganAt, attemptBeganAt: beganAt, deadline: deadline)
    }

    mutating func receive(bytes: Int) {
        guard outcome == .running, awaitingReply, bytes >= 0 else { return }
        receivedBytes = bytes
    }
    mutating func changed(phase: String, at date: Date) {
        guard outcome == .running else { return }
        awaitingReply = false
        if attemptEndedAt == nil { attemptEndedAt = date }
        if phase != "awaiting_llm", stageEndedAt == nil { stageEndedAt = date }
        switch phase {
        case "completed": finish(.succeeded, at: date)
        case "failed": finish(.failed, at: date)
        case "cancelled": finish(.cancelled, at: date)
        case "needs_user_edit", "awaiting_patch_approval": finish(.awaitingReview, at: date)
        default: break
        }
    }
    mutating func finish(_ outcome: Outcome, at date: Date) {
        self.outcome = outcome; awaitingReply = false
        if attemptEndedAt == nil { attemptEndedAt = date }
        if stageEndedAt == nil { stageEndedAt = date }
    }
}
