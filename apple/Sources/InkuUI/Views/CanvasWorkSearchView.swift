import SwiftUI

@MainActor
struct CanvasWorkSearchView: View {
    @Bindable var library: LibraryModel
    let display: DisplaySettings
    @State private var draft = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            InkuSearchField(value: $draft, placeholder: display.webCopy("canvasSearchPlaceholder", "記述・hash・作品ID"),
                            label: display.webCopy("canvasSearchLabel", "作品を検索"), maxLength: 200, delay: .milliseconds(250),
                            onSearch: { library.query = $0 })
                .inkuSearchFieldHeight()
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
    @ViewBuilder func body(content: Content) -> some View {
        #if os(macOS)
        content.frame(height: 26 * max(1, scale))
        #else
        content
        #endif
    }
}

extension View {
    /// One control high: 26 points, taller with a larger text size.
    func inkuSearchFieldHeight() -> some View { modifier(InkuSearchFieldHeight()) }
}
