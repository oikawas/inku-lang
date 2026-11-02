import XCTest
import InkuHost
import Observation
@testable import InkuUI

final class RunProgressJournalTests: XCTestCase {
    @MainActor func testJournalObservationFollowsExecutionAndProgress() {
        let app = AppModel()
        let executionChanged = expectation(description: "journal execution became available")
        withObservationTracking {
            XCTAssertNil(app.runJournal)
        } onChange: { executionChanged.fulfill() }
        let attempt = ExactJSON.object(["provider_attempt": .object(["action": .string("read_description"),
            "attempt": .number("1"), "max_attempts": .number("4")])]).data
        app.receiveProviderProgress(.providerAttempt(executionID: "run", report: attempt, beganAt: Date(), deadline: Date()), models: nil, comparison: false)
        XCTAssertEqual(app.runJournalExecutionID, "run")
        XCTAssertNil(app.runJournal)

        let journalChanged = expectation(description: "journal report became available")
        withObservationTracking {
            XCTAssertNil(app.runJournal)
        } onChange: { journalChanged.fulfill() }
        let report = ExactJSON.object(["run_progress": .object(["current": .object(["kind": .string("provider"),
            "action": .string("read_description")]), "finished": .array([])])]).data
        app.receiveProviderProgress(.runProgress(executionID: "run", report: report), models: nil, comparison: false)
        XCTAssertEqual(app.runJournal?.report["current"]["action"].string, "read_description")
        wait(for: [executionChanged, journalChanged], timeout: 1)
    }
    func testRetryAndMissingUsageAreCountedOncePerSend() {
        var journal = RunProgressJournal(report: .object([:]))
        func metric(_ id: String, _ attempt: UInt32, _ action: String, _ usage: ProviderUsage?) -> ProviderAttemptMetric {
            ProviderAttemptMetric(identity: .init(actionID: id, attempt: attempt, requestDigest: "digest"), action: action,
                                  stage: .read_and_draw, requestedModelReference: "check:model", timeoutMS: 1000,
                                  usage: usage, outcome: .completed, sent: true)
        }
        let first = metric("read", 1, "read_description", .init(inputTokens: 1000, outputTokens: 2))
        journal.receive(first)
        journal.receive(first)
        journal.receive(metric("read", 2, "read_description", nil))
        journal.receive(metric("write", 1, "write_description_ddl", .init(inputTokens: 20, outputTokens: 3)))
        var timeout = metric("read", 3, "read_description", nil)
        timeout.sent = false; timeout.outcome = .requestSaved
        journal.receive(timeout)
        timeout.outcome = .failed; timeout.failure = "transport_timeout"
        journal.receive(timeout)
        XCTAssertEqual(journal.stageTokens["read_description"], RunTokenCounts(input: 1000, output: 2, unreported: 2))
        XCTAssertEqual(journal.total, RunTokenCounts(input: 1020, output: 5, unreported: 2))
    }
}
