import Foundation
import Testing
@testable import InkuHost

struct DdlTitleTests {
    @Test func sharedTitleCases() throws {
        var directory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        while directory.path != "/" {
            let file = directory.appendingPathComponent("server/tests/data/ddl-title-cases.json")
            if FileManager.default.fileExists(atPath: file.path) {
                let fixture = try ExactJSON(data: Data(contentsOf: file))
                let cases = try #require(fixture["cases"].array)
                for row in cases {
                    let text = try #require(row["text"].string)
                    let offsets = text.unicodeScalars.reduce(into: [0]) { $0.append($0.last! + ($1.value > 0xFFFF ? 2 : 1)) }
                    let expected = try #require(row["lines"].array).map { line -> NSRange in
                        let values = try #require(line.array)
                        let start = try #require(values[0].number.flatMap(Int.init))
                        let end = try #require(values[1].number.flatMap(Int.init))
                        return NSRange(location: offsets[start], length: offsets[end] - offsets[start])
                    }
                    #expect(DdlTitles.lineRanges(text) == expected, "\(row["why"].string ?? "")")
                    #expect(DdlTitles.withoutTitleLines(text) == row["without"].string)
                }
                return
            }
            directory.deleteLastPathComponent()
        }
        Issue.record("Shared title cases not found")
    }

    @Test func readWordsLeaveTitlesOut() throws {
        let vocabulary = [FeedbackLexeme(surface: "黒", category: "colors")]
        #expect(try InterpretationFeedback.unreadWords(description: "黒い水面", ddl: "「黒い水面」", vocabulary: vocabulary) == [])
        #expect(try InterpretationFeedback.parts(description: "黒い水面", ddl: "「黒い水面」", vocabulary: vocabulary).isEmpty)
        #expect(DdlTitles.firstSentenceLine("\n「題」\n青い円。") == "青い円。")
    }
}
