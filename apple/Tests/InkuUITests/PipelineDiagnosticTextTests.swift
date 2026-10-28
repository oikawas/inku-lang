import XCTest
import InkuHost
@testable import InkuUI

@MainActor final class PipelineDiagnosticTextTests: XCTestCase {
    func testResourceOmissionAndPartialExecution() throws {
        let display = DisplaySettings()
        display.preferences.language = "ja"
        let value = try ExactJSON(data: Data(#"{"cause":{"reason":{"kind":"budget_exceeded","value":{"dimension":"logical_objects","required":6945,"maximum":400}}},"owner":{"kind":"source_instruction","value":{"source_instruction_index":0}}}"#.utf8))
        XCTAssertEqual(PipelineDiagnosticText.format(value, channel: "resource", display: display), "原文の指示 1 の箇所。 描画対象の数は 6945 必要でしたが、上限は 400 でした。 原文の指示 1 を省略しました。 ほかの部分の描画は続けました。")
        let missing = try ExactJSON(data: Data(#"{"reason":{"kind":"missing_entity_head"},"span":{"start_byte":0,"end_byte":9}}"#.utf8))
        let text = PipelineDiagnosticText.format(missing, channel: "upstream", display: display)
        XCTAssertTrue(text.hasPrefix("原文のバイト位置 0〜9。"))
        XCTAssertTrue(text.contains("面・道具・揺らぎの語だけでは描けません。"))
    }
}
