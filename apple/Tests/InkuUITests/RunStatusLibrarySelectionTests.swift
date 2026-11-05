import XCTest
import SwiftUI
import AppKit
@testable import InkuUI

@MainActor
final class RunStatusLibrarySelectionTests: XCTestCase {
    func testLongProgressKeepsStopInsideMeasuredWidth() throws {
        for variant in [RunStatusVariant.bar, .inline] {
            let button = NSButton(title: "停止", target: nil, action: nil)
            let view = RunStatusRow(variant: variant) {
                Color.clear.frame(width: 32, height: 32)
            } content: {
                VStack {
                    RunMetadataFlow {
                        Text(String(repeating: "断られた案を理由を添えて問い直し中（2/4回目）", count: 4))
                        Text("経過 169.5秒")
                        Text("受信 308 KB")
                    }.lineLimit(1).truncationMode(.tail)
                    Text("合計（一部不明）入力 123,456,789・出力 123,456,789").lineLimit(1).truncationMode(.tail)
                }
            } stop: {
                MeasuredButton(button: button).frame(width: 64, height: 28)
            }
            let host = NSHostingView(rootView: view)
            host.frame = NSRect(x: 0, y: 0, width: 280, height: 100)
            let window = NSWindow(contentRect: host.frame, styleMask: [], backing: .buffered, defer: false)
            window.contentView = host
            host.layoutSubtreeIfNeeded()
            XCTAssertNotNil(button.superview)
            let bounds = host.convert(button.bounds, from: button)
            XCTAssertGreaterThanOrEqual(bounds.minX, -0.5)
            XCTAssertLessThanOrEqual(bounds.maxX, host.bounds.maxX + 0.5)
            XCTAssertEqual(bounds.width, 64, accuracy: 0.5)
        }
    }

    func testSelectionPresentationKeepsSelectTitleAndDisablesEmptyClear() {
        let display = DisplaySettings()
        for language in ["ja", "en"] {
            display.preferences.language = language
            let empty = LibrarySelectionPresentation(display: display, selectedIDs: [])
            let selected = LibrarySelectionPresentation(display: display, selectedIDs: ["one", "two"])
            XCTAssertEqual(empty.selectTitle, selected.selectTitle)
            XCTAssertEqual(empty.selectTitle, display.webCopy("historySelectAll", fallback: "すべて選択"))
            XCTAssertTrue(empty.clearDisabled)
            XCTAssertFalse(selected.clearDisabled)
        }
    }
}

private struct MeasuredButton: NSViewRepresentable {
    let button: NSButton
    func makeNSView(context: Context) -> NSButton { button }
    func updateNSView(_ nsView: NSButton, context: Context) {}
}
