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
            CanvasSearchField(value: $draft, placeholder: display.webCopy("canvasSearchPlaceholder", "記述・hash・作品ID"),
                              label: display.webCopy("canvasSearchLabel", "作品を検索"),
                              onSearch: { library.query = $0 })
                .frame(height: 26)
            #else
            TextField(display.webCopy("canvasSearchPlaceholder", "記述・hash・作品ID"), text: $draft)
                .onSubmit { library.query = String(draft.prefix(200)) }
            #endif
            if !library.loading, !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
               library.query == draft {
                if library.errorText != nil {
                    Text(display.webCopy("canvasSearchFailed", "検索できませんでした")).inkuFont(10).foregroundStyle(.secondary)
                } else if library.total == 0 {
                    Text(display.webCopy("canvasSearchEmpty", "一致する作品はありません")).inkuFont(10).foregroundStyle(.secondary)
                }
            }
        }
        .onAppear { draft = library.query }
        .inkuTooltip(display.tooltipValue(display.webCopy("canvasSearchHint", "UUID、記述、描画・記述hashを検索します")))
    }
}

#if os(macOS)
/// Do not apply a search while the input method still owns marked text.
@MainActor
private struct CanvasSearchField: NSViewRepresentable {
    @Binding var value: String
    let placeholder: String
    let label: String
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
        field.placeholderString = placeholder
        field.setAccessibilityLabel(label)
        if field.currentEditor() == nil, field.stringValue != value { field.stringValue = value }
    }
    static func dismantleNSView(_ field: NSSearchField, coordinator: Coordinator) { coordinator.pending?.cancel() }
    @MainActor final class Coordinator: NSObject, NSSearchFieldDelegate {
        var parent: CanvasSearchField
        var pending: Task<Void, Never>?
        init(_ parent: CanvasSearchField) { self.parent = parent }
        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSSearchField else { return }
            pending?.cancel()
            guard (field.currentEditor() as? NSTextView)?.hasMarkedText() != true else { return }
            let text = String(field.stringValue.prefix(200))
            if field.stringValue != text { field.stringValue = text }
            parent.value = text
            if text.isEmpty { parent.onSearch(text); return }
            pending = Task { @MainActor [weak self] in
                try? await Task.sleep(for: .milliseconds(250))
                guard !Task.isCancelled else { return }
                self?.parent.onSearch(text)
            }
        }
        @objc func submit(_ field: NSSearchField) {
            pending?.cancel()
            guard (field.currentEditor() as? NSTextView)?.hasMarkedText() != true else { return }
            let text = String(field.stringValue.prefix(200))
            parent.value = text
            parent.onSearch(text)
            field.window?.makeFirstResponder(field)
        }
    }
}
#endif
