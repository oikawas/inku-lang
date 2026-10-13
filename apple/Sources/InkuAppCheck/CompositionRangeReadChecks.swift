import Foundation
import InkuUI

/// Web `composition-ranges.test.ts`, copied example by example.
@MainActor func runCompositionRangeReadChecks() throws {
    typealias R = CompositionRanges
    var compared = 0
    func expect(_ condition: Bool, _ name: String) throws {
        compared += 1
        guard condition else { throw CheckFailure.message("Composition ranges: \(name)") }
    }
    let table = R.read(Data(#"{"schema":"inku.composition-ranges.v1","ranges":[{"key":"left","words":{"ja":"左上","en":"top left"},"bounds":[[0,1],[0,1],[1,3],[1,3]],"corner":false},{"key":"right","words":{"ja":"右下","en":"bottom right"},"bounds":[[2,3],[2,3],[1,1],[1,1]],"corner":false}]}"#.utf8))
    try expect(table.count == 2, "table")
    func key(_ text: String) -> String? { R.scan(text).first.flatMap { R.matching($0, table)?.key } }
    // only equal words and exact rationals fold; language-specific syntax stays bounded
    try expect(key("［構図］右下（横４／６～１，縦２／３~１）に、円。") == "right", "fullwidth")
    try expect(key("左上（横2/3〜1、縦2/3〜1）に、円。") == nil, "other bounds")
    try expect(key("左上（横0〜0.333333、縦0〜1/3）に、円。") == nil, "decimal is not 1/3")
    try expect(key("A circle at [composition] the top left (horizontal 0 to 2/6, vertical 0 to 1/3).") == "left", "english mark")
    try expect(key("A circle ON the top left (HORIZONTAL 0 TO 1/3, VERTICAL 0 TO 1/3).") == "left", "english case")
    try expect(key("A circle ON the Top Left (HORIZONTAL 0 TO 1/3, VERTICAL 0 TO 1/3).") == nil, "name case")
    try expect(R.parseBody("horizontal ０ to 1/3, vertical 0 to 1/3", lang: "en") == nil, "en fullwidth")
    try expect(R.parseBody("horizontal 0 ~ 1/3, vertical 0 to 1/3", lang: "en") == nil, "en tilde")
    try expect(R.parseBody("横0〜1/1000001、縦0〜1", lang: "ja") == nil, "denominator limit")
    for digit in ["⓪", "⁰"] { try expect(R.parseBody("横\(digit)〜1/3、縦0〜1/3", lang: "ja") == nil, "digit \(digit)") }
    try expect(R.parseBody("横0〜1 / 3、縦0〜1/3", lang: "ja") == nil, "spaced fraction")
    try expect(R.scan("画面の横0.2〜0.5、縦0〜0.3の範囲に、円。").isEmpty, "unnamed range")
    // editing only the range follows matching names and preserves surrounding source bytes
    let source = "  紙。\n［構図］右下（横2/3〜1、縦2/3〜1）に、赤い円。\n青い線。  "
    let range = try XCTUnwrapRange(R.scan(source).first)
    let left = R.edit(source, range: range, body: "横０〜１／３、縦０〜１／３", table: table)
    try expect(left.source == "  紙。\n［構図］左上（横０〜１／３、縦０〜１／３）に、赤い円。\n青い線。  ", "follow left")
    let custom = R.edit(left.source, range: left.range, body: "横0.1〜0.4、縦0.2〜0.5", table: table)
    try expect(custom.range.name == "指定の範囲" && R.matching(custom.range, table) == nil, "chosen place")
    for body in ["横1〜0、縦0〜1", "横0〜1.1、縦0〜1", "横0〜0、縦0〜1", "typing"] {
        let invalid = R.edit(source, range: range, body: body, table: table)
        try expect(invalid.range.bounds == nil && invalid.source.contains("（\(body)）"), "invalid \(body)")
    }
    try expect(R.read(Data(#"{"schema":"wrong","ranges":[]}"#.utf8)).isEmpty, "wrong schema")
    try expect(R.read(Data(#"{"schema":"inku.composition-ranges.v1","ranges":[{"bounds":"invalid"}]}"#.utf8)).isEmpty, "invalid row")
    // Japanese hyphens accept the reported edit and follow the matching range name
    try expect(R.parseBody("横1/3-2/3、縦2/3〜1", lang: "ja") == [.init(1, 3), .init(2, 3), .init(2, 3), .init(1, 1)], "ja hyphen bounds")
    let ja = "右下（横2/3〜1、縦2/3〜1）に、赤い円。"
    for body in ["横0-1/3、縦0－1/3", "横０ － １／３、縦０ - １／３"] {
        let edited = R.edit(ja, range: try XCTUnwrapRange(R.scan(ja).first), body: body, table: table)
        try expect(edited.source == "左上（\(body)）に、赤い円。" && key(edited.source) == "left", "ja hyphen \(body)")
    }
    // English hyphens and en dashes follow matching range names with optional spaces
    let en = "A circle at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1)."
    for body in ["horizontal 0-1/3, vertical 0–1/3", "horizontal 0 – 1/3, vertical 0 - 1/3"] {
        try expect(R.parseBody(body, lang: "en") == table[0].bounds, "en parse \(body)")
        let edited = R.edit(en, range: try XCTUnwrapRange(R.scan(en).first), body: body, table: table)
        try expect(edited.source == "A circle at the top left (\(body))." && key(edited.source) == "left", "en hyphen \(body)")
    }
    try expect(!R.table.isEmpty, "core table")
    // Web codemirror-ranges.ts: fold, open, frame, follow.
    let folded = "右下（横2/3〜1、縦2/3〜1）に、赤い円。"
    let rest = NSRange(location: 2, length: 15)
    let closed = RangeEditorState.derive(text: folded, selection: NSRange(location: 0, length: 0), focused: false, hover: nil, previous: nil, table: table)
    try expect(closed.hidden == [rest] && closed.names == [NSRange(location: 0, length: 2)] && closed.active == nil && closed.preview == nil, "folded unfocused")
    let open = RangeEditorState.derive(text: folded, selection: NSRange(location: 1, length: 0), focused: true, hover: nil, previous: closed, table: table)
    try expect(open.hidden.isEmpty && open.active?.start == 0 && open.preview?.bounds == [2.0 / 3, 2.0 / 3, 1, 1] && open.preview?.invalid == false, "caret opens")
    let hovered = RangeEditorState.derive(text: folded, selection: NSRange(location: 0, length: 0), focused: false, hover: 0, previous: closed, table: table)
    try expect(hovered.hidden == [rest] && hovered.preview?.bounds == [2.0 / 3, 2.0 / 3, 1, 1], "hover frames")
    let marked = RangeEditorState.derive(text: "［構図］" + folded, selection: NSRange(location: 0, length: 0), focused: false, hover: nil, previous: nil, table: table)
    try expect(marked.hidden.contains(NSRange(location: 0, length: 4)), "old mark folds")
    try expect(open.pendingName(afterEditing: NSRange(location: 5, length: 1)) && !open.pendingName(afterEditing: NSRange(location: 0, length: 1)), "numbers ask, words cancel")
    var pending = open; pending.pendingName = true
    let renumbered = "右下（横0〜1/3、縦0〜1/3）に、赤い円。"
    let follow = pending.followedName(text: renumbered, selection: NSRange(location: 20, length: 0), focused: true, table: table)
    try expect(follow?.range == NSRange(location: 0, length: 2) && follow?.name == "左上", "name follows on leaving")
    try expect(pending.followedName(text: renumbered, selection: NSRange(location: 6, length: 0), focused: true, table: table) == nil, "no follow while inside")
    let broken = RangeEditorState.derive(text: "右下（横2/3〜、縦2/3〜1）に、赤い円。", selection: NSRange(location: 6, length: 0), focused: true, hover: nil, previous: open, table: table)
    try expect(broken.invalid && broken.preview?.invalid == true && broken.preview?.bounds == open.preview?.bounds, "invalid keeps the last frame")
    // The real editor, off screen: a core-table range folds its numbers; text without one folds nothing.
    let probeDisplay = DisplaySettings()
    let ranged = "Fill one gray pen dense flat large square at the left half (horizontal 0 to 1/2, vertical 0 to 1)."
    let hidden = RangeFoldingProbe.hiddenCharacters(text: ranged, display: probeDisplay)
    let numbers = (ranged as NSString).range(of: " (horizontal 0 to 1/2, vertical 0 to 1)")
    try expect(Set(hidden) == Set(numbers.location..<NSMaxRange(numbers)), "editor folds \(hidden.count) of \(numbers.length) characters")
    try expect(RangeFoldingProbe.hiddenCharacters(text: "place one red circle at center.", display: probeDisplay).isEmpty, "editor folds nothing without ranges")
    print("Composition ranges passed: \(compared) checks (Web examples for folding, syntax bounds, editing, name following, hyphens; editor folding, opening, hover frame, old mark, name following and the last valid frame); the core table has \(R.table.count) ranges.")
}

private func XCTUnwrapRange(_ value: CompositionRanges.NumericRange?) throws -> CompositionRanges.NumericRange {
    guard let value else { throw CheckFailure.message("Composition ranges: no range scanned") }
    return value
}
