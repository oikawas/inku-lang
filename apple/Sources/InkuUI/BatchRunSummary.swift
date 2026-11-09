import Foundation

/// What the batch tiles show (Web `BatchRunSummary.svelte`, `features/batch/state.svelte.ts`, `image-folder.svelte.ts`):
/// the line among the whole plan, the time since the batch started and the average time of a saved work.
struct BatchRunSummary: Equatable, Sendable {
    /// The plan's size: every line (or picture) of the batch, finished ones included.
    var planTotal = 0
    /// The lines this round draws (a retry round or a resume draws fewer than the plan).
    var roundTotal = 0
    /// 1-based position inside the round; 0 before its first line.
    var roundPosition = 0
    var startedAt: Date?
    var workStartedAt: Date?
    private var workDurationTotal: TimeInterval = 0
    private var workDurationCount = 0

    /// Web `summaryCurrent`: the round's position read as a position among the whole plan.
    var current: Int { roundPosition > 0 ? planTotal - roundTotal + roundPosition : 0 }
    /// Web `averageWorkMs`: nil until the first work is saved.
    var averageWork: TimeInterval? { workDurationCount > 0 ? workDurationTotal / Double(workDurationCount) : nil }

    mutating func start(planTotal: Int, at date: Date) {
        self = BatchRunSummary(planTotal: planTotal, startedAt: date)
    }

    mutating func beginRound(_ count: Int) { roundTotal = count; roundPosition = 0 }

    mutating func beginWork(position: Int, at date: Date = Date()) { roundPosition = position; workStartedAt = date }

    /// Only a saved work counts (Web `recordWorkDuration`): failed and stopped lines are left out.
    mutating func finishWork(saved: Bool, at date: Date = Date()) {
        defer { workStartedAt = nil }
        guard saved, let workStartedAt else { return }
        workDurationTotal += max(0, date.timeIntervalSince(workStartedAt))
        workDurationCount += 1
    }
}
