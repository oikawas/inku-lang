import XCTest
import InkuHost
@testable import InkuUI

@MainActor final class PipelineDiagnosticTextTests: XCTestCase {
    func testOrderAndPluginExplanationsAndExecutionOmissions() {
        let raw = #"{"plugin_diagnostics":[{"start_byte":1,"end_byte":3}],"catalog_diagnostics":[{}],"upstream_diagnostics":[{"span":{"start_byte":1,"end_byte":3}},{"span":{"start_byte":4,"end_byte":6}}],"downstream_diagnostics":[{}],"resource_omissions":[{}],"relation_omissions":[{}],"render_diagnostics":{"diagnostics":[{}]},"resource_execution":{"omissions":[{}],"relation_omissions":[{}]},"render_warnings":[{}]}"#
        let entries = PipelineDiagnosticText.entries(raw)
        XCTAssertEqual(entries.map(\.channel), ["plugin", "catalog", "upstream", "downstream", "resource", "relation", "render", "resource", "relation", "warning"])
        XCTAssertEqual(entries[2].value["span"]["start_byte"].number, "4")
    }
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
