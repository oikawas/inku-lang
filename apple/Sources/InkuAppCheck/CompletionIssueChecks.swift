import Foundation
import InkuHost
import InkuUI

/// Web `pipelineCompletionReason` and `providerAttemptText`: the reason a hole was not completed, and the
/// attempt that asks again after a refused proposal.
@MainActor func runCompletionIssueChecks() throws {
    let display = DisplaySettings()
    display.preferences.language = "ja"
    // Failure: a known reason, the context limit or an unknown code read as another reason.
    for (code, expected) in [("numeric_range_outside_words", "数の範囲が、括弧の前の位置の語の範囲から外れた"),
                             ("context_limit", "文脈が長すぎて補えなかった"), ("new_check_code", "検査で断られた（new_check_code）")] {
        let text = HoleCompletionReasons.text(code, display: display)
        guard text == expected else { throw CheckFailure.message("Completion reason \(code) read as \(text)") }
    }
    display.preferences.language = "en"
    guard HoleCompletionReasons.text("context_limit", display: display) == "The context was too long to complete." else {
        throw CheckFailure.message("English completion reason did not follow the Web")
    }
    // Failure: a proposal asked for again after the check refused it read as a resend.
    func report(_ askedAgain: Bool?) -> Data {
        var attempt: ExactJSON = .object(["action": .string("complete_visible_ddl_holes"), "attempt": .integer(2), "max_attempts": .integer(4)])
        if let askedAgain { attempt["asked_again"] = .bool(askedAgain) }
        return ExactJSON.object(["provider_attempt": attempt]).data
    }
    let now = Date()
    guard let asked = ProviderProgressSnapshot.start(executionID: "e", report: report(true), beganAt: now, deadline: now.addingTimeInterval(60),
                                                     models: nil, comparison: false, previous: nil), asked.askedAgain,
          let resent = ProviderProgressSnapshot.start(executionID: "e", report: report(nil), beganAt: now, deadline: now.addingTimeInterval(60),
                                                      models: nil, comparison: false, previous: nil), !resent.askedAgain else {
        throw CheckFailure.message("The attempt report's asked_again was not read")
    }
    print("Completion issues passed: 3 Japanese and 1 English reasons follow the Web (known, context limit, unknown code); asked_again tells a second request from a resend.")
}
