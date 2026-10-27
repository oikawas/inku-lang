import Foundation
import Testing
@testable import InkuHost

// A title line (DDL 27) names the chunk below it and draws nothing; the cases are Web
// `a-ddl-title-line-colours-no-word.test.ts`.
struct DdlTitleTests {
    static let ddl = "画面比1:1。\n\n「黒い水面」\n画面の横0.5、縦0.5の位置に、青の塗りの円を1個置く。"

    @Test func titleLineIsTheCoresOneBracketedNameOnAWholeLine() {
        #expect(DdlTitles.name("「灯台」") == "灯台")
        #expect(DdlTitles.name("　「 黒い水面 」 ") == "黒い水面")
        #expect(DdlTitles.name("\"the “low” moon\"") == "the “low” moon")
        #expect(DdlTitles.name("“lighthouse”") == "lighthouse")
        #expect(DdlTitles.name("「」") == "")
        for line in ["「赤い円」を中心に置く。", "「灯台」。", "「灯「台」", "\"", "“lighthouse\"", "画面比1:1。"] {
            #expect(DdlTitles.name(line) == nil, "\(line)")
        }
        #expect(DdlTitles.withoutTitleLines("\"灯台\"\nplace one white circle at center.\n「」") == "place one white circle at center.")
    }

    // Ranges count UTF-16 and leave out a CRLF line's carriage return.
    @Test func titleRangesAreTheWholeLineWithoutItsBreak() {
        let text = "円を置く。\r\n「灯台」\r\n線を引く。"
        #expect(DdlTitles.lineRanges(text) == [NSRange(location: 7, length: 4)])
        #expect(DdlTitles.lineRanges(Self.ddl) == [NSRange(location: 9, length: 6)])
    }

    // A work with only its DDL is named by its first drawing sentence, never by a title or an empty 「」.
    @Test func workTitleSkipsTitleLines() {
        #expect(DdlTitles.firstSentenceLine(Self.ddl) == "画面比1:1。")
        #expect(DdlTitles.firstSentenceLine("\n「黒い水面」\n「」\n青い円を置く。") == "青い円を置く。")
        #expect(DdlTitles.firstSentenceLine("「黒い水面」\n「」") == nil)
    }

    // Concrete failure: the title quotes the description's word, so without leaving it out every word reads.
    @Test func readWordsLeaveTheTitlesOut() {
        let vocabulary = [FeedbackLexeme(surface: "黒", category: "colors")]
        let black = InterpretationFeedback.parts(description: "黒い水面", ddl: Self.ddl, vocabulary: vocabulary).first { $0.text == "黒" }
        #expect(black?.tone == .medium)
        #expect(InterpretationFeedback.unreadWords(description: "黒い水面", ddl: "「黒い水面」", vocabulary: vocabulary) == [])
        #expect(InterpretationFeedback.parts(description: "黒い水面", ddl: "「黒い水面」", vocabulary: vocabulary).isEmpty)
    }
}
