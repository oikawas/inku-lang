#if os(macOS)
import AppKit
import SwiftUI

/// Builds the real DDL editor off screen and reports which characters generate no glyphs, so the folding the
/// author sees can be checked without a window on screen.
@MainActor public enum RangeFoldingProbe {
    public static func hiddenCharacters(text: String, display: DisplaySettings) -> [Int] {
        _ = NSApplication.shared
        let editor = InkuTextEditor(text: .constant(text), isEditable: false, accessibilityLabel: "probe", style: .ddlCompact,
                                    marks: { _ in [] }, rangeTable: CompositionRanges.table)
            .environment(display)
            .frame(width: 600, height: 300)
        let host = NSHostingView(rootView: editor)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 300), styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        guard let view = find(host), let layout = view.layoutManager else { return [] }
        layout.ensureLayout(for: view.textContainer!)
        let length = (view.string as NSString).length
        return (0..<length).filter { character in
            let glyph = layout.glyphIndexForCharacter(at: character)
            return glyph < layout.numberOfGlyphs && layout.propertyForGlyph(at: glyph) == .null
        }
    }

    private static func find(_ view: NSView) -> NSTextView? {
        if let text = view as? NSTextView { return text }
        for child in view.subviews { if let found = find(child) { return found } }
        return nil
    }
}
#endif
