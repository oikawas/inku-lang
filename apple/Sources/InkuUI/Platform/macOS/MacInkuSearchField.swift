#if os(macOS)
import SwiftUI
import AppKit
/// The native search field of both history searches: the strip's (Web `CanvasWorkSearch`) and the library's, which the
/// Web draws like it since Build 1266 (`0f579f3d8`). The two share this box, its type size (Web `--btn-sm-font-size`,
/// 12 px at the text-size setting) and its clear button. A search is not applied while the input method still owns
/// marked text.
@MainActor
struct InkuSearchField: NSViewRepresentable {
    @Binding var value: String
    let placeholder: String
    let label: String
    /// Web `maxlength`: the strip's search takes 200 characters; the library's is not limited.
    var maxLength: Int? = nil
    /// The pause after typing before the search applies (the strip's 250 ms); nil applies each change at once (the
    /// library, whose model coalesces typing itself).
    var delay: Duration? = nil
    var borderless: Bool = false
    /// Escape. Without it the field clears itself, as a search field does; the library's closes the library, as Escape
    /// does there on the Web, and keeps the search.
    var onCancel: (() -> Void)? = nil
    /// Raised by `InkuClearableSearchField`'s "×" (Web `CanvasWorkSearch` `clear`): each new value empties the field.
    var clearRequest = 0
    let onSearch: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSSearchField {
        let field = NSSearchField()
        // The Web hides the browser's clear button and draws its own "×" beside the box (InkuClearableSearchField).
        (field.cell as? NSSearchFieldCell)?.cancelButtonCell = nil
        context.coordinator.clearRequest = clearRequest
        field.delegate = context.coordinator
        field.target = context.coordinator
        field.action = #selector(Coordinator.submit(_:))
        field.sendsWholeSearchString = true
        field.sendsSearchStringImmediately = false
        return field
    }
    func updateNSView(_ field: NSSearchField, context: Context) {
        context.coordinator.parent = self
        let size = CGFloat(12 * context.environment.inkuTextScale)
        if field.font?.pointSize != size { field.font = .systemFont(ofSize: size) }
        field.placeholderString = placeholder
        field.setAccessibilityLabel(label)
        field.isEnabled = context.environment.isEnabled
        field.isEditable = context.environment.isEnabled && !context.environment.inkuTooltipsCovered
        field.isBezeled = !borderless
        if clearRequest != context.coordinator.clearRequest {
            context.coordinator.clearRequest = clearRequest
            context.coordinator.clear(field)
        }
        if field.currentEditor() == nil, field.stringValue != value { field.stringValue = value }
    }
    static func dismantleNSView(_ field: NSSearchField, coordinator: Coordinator) { coordinator.pending?.cancel() }
    @MainActor final class Coordinator: NSObject, NSSearchFieldDelegate {
        var parent: InkuSearchField
        var pending: Task<Void, Never>?
        var clearRequest = 0
        init(_ parent: InkuSearchField) { self.parent = parent }
        /// Empty the field, apply the empty search without the pause, and keep the caret in the field.
        func clear(_ field: NSSearchField) {
            pending?.cancel()
            field.stringValue = ""
            parent.value = ""
            parent.onSearch("")
            field.window?.makeFirstResponder(field)
        }
        private func limitedText(of field: NSSearchField) -> String {
            guard let maxLength = parent.maxLength else { return field.stringValue }
            let text = String(field.stringValue.prefix(maxLength))
            if field.stringValue != text { field.stringValue = text }
            return text
        }
        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSSearchField else { return }
            pending?.cancel()
            guard (field.currentEditor() as? NSTextView)?.hasMarkedText() != true else { return }
            let text = limitedText(of: field)
            parent.value = text
            guard let delay = parent.delay, !text.isEmpty else { parent.onSearch(text); return }
            pending = Task { @MainActor [weak self] in
                try? await Task.sleep(for: delay)
                guard !Task.isCancelled else { return }
                self?.parent.onSearch(text)
            }
        }
        func control(_ control: NSControl, textView: NSTextView, doCommandBy selector: Selector) -> Bool {
            guard selector == #selector(NSResponder.cancelOperation(_:)), let onCancel = parent.onCancel else { return false }
            onCancel()
            return true
        }
        @objc func submit(_ field: NSSearchField) {
            pending?.cancel()
            guard (field.currentEditor() as? NSTextView)?.hasMarkedText() != true else { return }
            let text = limitedText(of: field)
            parent.value = text
            parent.onSearch(text)
            field.window?.makeFirstResponder(field)
        }
    }
}
#endif
