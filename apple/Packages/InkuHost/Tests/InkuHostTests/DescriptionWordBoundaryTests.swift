import Foundation
import Testing
@testable import InkuHost

struct DescriptionWordBoundaryTests {
    // Concrete failure: a prepared dictionary copied under the wrong Bundle path
    // makes an accurate native counter unavailable to an otherwise built client.
    @Test func preparedBundleFeedsNativeMeterAndCancelledReadStaysCancelled() async throws {
        let meter = DescriptionMeter()
        let result = try await meter.count(text: "An old silent pond", language: "en")
        #expect(result.lines == [5] && result.syllables == 5 && result.unknown == [])
        let cancelled = Task { try await meter.count(text: "An old silent pond", language: "en") }
        cancelled.cancel()
        await #expect(throws: CancellationError.self) { try await cancelled.value }
    }

    // Concrete failure: matching "line" inside "outline" loses the unread word;
    // the same feedback must exclude emotion and recognized vocabulary segments.
    @Test func feedbackRespectsAsciiWordBoundaryAndWeakPartExtraction() {
        let vocabulary = [FeedbackLexeme(surface: "red", category: "colors"), FeedbackLexeme(surface: "line", category: "forms")]
        let text = "red outline 美しい quuxword"
        let parts = InterpretationFeedback.parts(description: text, ddl: "colors circle", vocabulary: vocabulary)
        #expect(parts.first?.text == "red" && parts.first?.tone == .strong)
        #expect(parts.contains { $0.text == "美しい" && $0.tone == .medium })
        #expect(InterpretationFeedback.unreadWords(description: text, ddl: "colors circle", vocabulary: vocabulary) == ["outline", "quuxword"])
    }
}
