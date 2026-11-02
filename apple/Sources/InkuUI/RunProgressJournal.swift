import Foundation
import InkuHost

struct RunTokenCounts: Equatable {
    var input: UInt64?
    var output: UInt64?
    var unreported = 0

    mutating func add(_ usage: ProviderUsage?) {
        guard let usage else { unreported += 1; return }
        if let value = usage.inputTokens { input = (input ?? 0) + value }
        if let value = usage.outputTokens { output = (output ?? 0) + value }
    }
}

struct RunProgressJournal {
    var report: ExactJSON
    let beganAt: Date
    private var metrics: [ProviderActionIdentity: ProviderAttemptMetric] = [:]
    private var started: Set<ProviderActionIdentity> = []

    init(report: ExactJSON, beganAt: Date = Date()) { self.report = report; self.beganAt = beganAt }
    mutating func receive(_ metric: ProviderAttemptMetric) {
        if metric.outcome == .requestSaved { started.insert(metric.identity) }
        metrics[metric.identity] = metric
    }
    var stageTokens: [String: RunTokenCounts] {
        var result: [String: RunTokenCounts] = [:]
        for metric in metrics.values where metric.outcome != .requestSaved && (metric.sent || started.contains(metric.identity)) {
            result[metric.action, default: RunTokenCounts()].add(metric.usage)
        }
        return result
    }
    var total: RunTokenCounts {
        var result = RunTokenCounts()
        let sends = metrics.values.filter { $0.outcome != .requestSaved && ($0.sent || started.contains($0.identity)) }
        if sends.isEmpty { result.input = 0; result.output = 0 }
        for metric in sends { result.add(metric.usage) }
        return result
    }
}
