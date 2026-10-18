import SwiftUI
#if os(macOS)
import AppKit
#endif

@MainActor
struct CanvasWorkSearchView: View {
    @Bindable var library: LibraryModel
    let display: DisplaySettings
    @State private var draft = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            #if os(macOS)
            InkuSearchField(value: $draft, placeholder: display.webCopy("canvasSearchPlaceholder", "記述・hash・作品ID"),
                            label: display.webCopy("canvasSearchLabel", "作品を検索"), maxLength: 200, delay: .milliseconds(250),
                            onSearch: { library.query = $0 })
                .inkuSearchFieldHeight()
            #else
            TextField(display.webCopy("canvasSearchPlaceholder", "記述・hash・作品ID"), text: $draft)
                .onSubmit { library.query = String(draft.prefix(200)) }
            #endif
            // None found is said by the empty tile in the history strip (Web c265e28bb); a failure is still said here.
            if !library.loading, !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
               library.query == draft, library.errorText != nil {
                Text(display.webCopy("canvasSearchFailed", "検索できませんでした")).inkuFont(10).foregroundStyle(.secondary)
            }
        }
        .onAppear { draft = library.query }
        // The strip's head is laid out two ways (one row or two), each with its own field: the one not typed in
        // follows the search that applies.
        .onChange(of: library.query) { _, query in if draft != query { draft = query } }
        .inkuTooltip(display.tooltipValue(display.webCopy("canvasSearchHint", "UUID、記述、描画・記述hashを検索します")))
    }
}

private struct InkuSearchFieldHeight: ViewModifier {
    @Environment(\.inkuTextScale) private var scale
    func body(content: Content) -> some View { content.frame(height: 26 * max(1, scale)) }
}

extension View {
    /// One control high: 26 points, taller with a larger text size.
    func inkuSearchFieldHeight() -> some View { modifier(InkuSearchFieldHeight()) }
}

#if os(macOS)
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
    /// Escape. Without it the field clears itself, as a search field does; the library's closes the library, as Escape
    /// does there on the Web, and keeps the search.
    var onCancel: (() -> Void)? = nil
    let onSearch: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSSearchField {
        let field = NSSearchField()
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
        if field.currentEditor() == nil, field.stringValue != value { field.stringValue = value }
    }
    static func dismantleNSView(_ field: NSSearchField, coordinator: Coordinator) { coordinator.pending?.cancel() }
    @MainActor final class Coordinator: NSObject, NSSearchFieldDelegate {
        var parent: InkuSearchField
        var pending: Task<Void, Never>?
        init(_ parent: InkuSearchField) { self.parent = parent }
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
