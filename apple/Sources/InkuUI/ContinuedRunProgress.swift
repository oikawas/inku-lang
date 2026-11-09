import Foundation

/// The completed units an iOS continued-processing task reports for a run (IOSBackgroundRuns.swift): 1000 a row (a
/// single drawing is one row), and within a row one unit every 5 s, up to 990 (about 82 minutes).
///
/// The system ends a task that reports no progress for about a minute. Counting whole rows only, the iPad 9 ended a
/// batch 59 s after its second row ("Task has not reported progress within expected cadence", ios-app step 6 check,
/// 2026-11-09). A row's length is not known ahead, so a steady step is the honest report; the status line is not
/// counted, because an answer's bytes change it many times a second.
struct ContinuedRunProgress {
    static let unitsPerRow = 1000
    static let secondsPerUnit: TimeInterval = 5

    private var rowsDone = -1
    private var withinRow = 0
    private var lastMove: Date?

    mutating func advance(rowsDone done: Int, now: Date) -> Int64 {
        if done != rowsDone { rowsDone = done; withinRow = 0; lastMove = now }
        if let last = lastMove, now.timeIntervalSince(last) >= Self.secondsPerUnit {
            lastMove = now
            withinRow = min(withinRow + 1, Self.unitsPerRow - 10)
        }
        return Int64(done * Self.unitsPerRow + withinRow)
    }
}
