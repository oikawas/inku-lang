import Foundation

enum PhoneDrawState: Equatable {
    case noConnection, keyMissing, signIn, modelUnavailable, empty, editing
    case drawing, otherRun, needsReview, candidate, completedHere, completedElsewhere
    case stopped, stoppedInBackground, failed
    struct Facts {
        var hasConnection = true, keyMissing = false, chatGPTSelected = false, signedIn = true, modelAvailable = true
        var editing = false, activeRun = false, drawing = false, needsReview = false, candidate = false
        var completedHere = false, completedElsewhere = false, stopped = false, stoppedInBackground = false, failed = false
    }
    static func resolve(_ f: Facts) -> Self {
        if f.activeRun { return f.drawing ? .drawing : .otherRun }
        if f.needsReview { return .needsReview }
        if f.candidate { return .candidate }
        if f.completedHere { return .completedHere }
        if f.completedElsewhere { return .completedElsewhere }
        if f.stoppedInBackground { return .stoppedInBackground }
        if f.failed { return .failed }
        if f.stopped { return .stopped }
        if !f.hasConnection { return .noConnection }
        if f.chatGPTSelected && !f.signedIn { return .signIn }
        if f.keyMissing { return .keyMissing }
        if !f.modelAvailable { return .modelUnavailable }
        return f.editing ? .editing : .empty
    }
}
