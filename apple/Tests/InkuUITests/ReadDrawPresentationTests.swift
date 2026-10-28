import XCTest
import InkuHost
@testable import InkuUI

@MainActor final class ReadDrawPresentationTests: XCTestCase {
    func testFlowAndSketchFollowWeb() {
        let stages = DrawPresentation.flow(route: "stages", sketch: true, composition: false, japanese: true)
        XCTAssertEqual(stages.map(\.label), ["記述", "写生", "型を埋める", "構図と法則", "配色", "画"])
        XCTAssertEqual(stages.map(\.kind), ["end", "switch", "fixed", "fixed", "fixed", "end"])
        let words = DrawPresentation.flow(route: "read_and_draw", sketch: false, composition: true, japanese: false)
        XCTAssertEqual(words.map(\.label), ["Description", "Composition and laws", "Write in words", "Look and correct", "Colors", "Picture"])
        XCTAssertEqual(words.map(\.kind), ["end", "switch", "fixed", "fixed", "switch", "end"])
        XCTAssertEqual(DrawPresentation.sketchShort(nil, japanese: false), "Not recorded")
        XCTAssertEqual(DrawPresentation.sketchShort("off", japanese: true), "通さない")
    }
    func testSavedRecordsUseWebWords() throws {
        let display = DisplaySettings()
        display.preferences.language = "ja"
        let record = try ExactJSON(data: Data(#"{"reading_state":"read","dropped_items":[{"kind":"scene","quote":"雲","image":"雲の形"}],"dropped_quotes":{"eye":"月"}}"#.utf8))
        let view = ReadDrawInfoView(record: record, display: display)
        XCTAssertEqual(view.reading, "記述を読み、その読みで書いた")
        XCTAssertEqual(view.dropped, ["scene 「雲」 雲の形", "eye 「月」"])
        let round = try ExactJSON(data: Data(#"{"stage":"review_description_ddl","asked_again":true,"instructions":4,"problems":2,"figures":[{"who":"speaker_part","what":"手"}]}"#.utf8))
        XCTAssertEqual(view.round(round), "見比べ（聞き直し） · 指示 4・直す行 2 · 語り手の体の一部: 手")
        XCTAssertEqual(view.compositionState(.object(["state": .string("fallback"), "fallback": .string("refused")])), "構図と法則を決められず、構図と法則なしで書いた（答えが決まりに合わなかった）")
        XCTAssertEqual(view.counts(["ok", "off", "ok"], table: ["ok": ("合う", "fits"), "off": ("少しずれ", "a little off")]), "合う 2、少しずれ 1")
    }
    func testStageCopyAndAskedAgain() throws {
        let display = DisplaySettings()
        display.preferences.language = "en"
        for (action, again, expected) in [("read_description", true, "Reading the description…"), ("compose_description", true, "Deciding the composition and laws again…"), ("write_description_ddl", true, "Revising the instructions…"), ("review_description_ddl", false, "Correcting the instructions beside the drawing…")] {
            let report = ExactJSON.object(["provider_attempt": .object(["action": .string(action), "attempt": .number("1"), "max_attempts": .number("2"), "asked_again": .bool(again)])]).data
            let snapshot = try XCTUnwrap(ProviderProgressSnapshot.start(executionID: "x", report: report, beganAt: Date(), deadline: Date(), models: nil, comparison: false, previous: nil))
            XCTAssertEqual(snapshot.displayTitle(display), expected)
        }
        XCTAssertEqual(display.webCopy("descriptionDdlFailed", ""), "no instructions could be written from the description; change the model and draw again")
        XCTAssertEqual(display.webCopy("descriptionDdlUndrawable", ""), "the instructions written drew nothing; change the description or the model and draw again")
    }
}
