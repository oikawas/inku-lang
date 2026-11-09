import SwiftUI

/// Web `CanvasWorkSearch.svelte:38` and `HistoryManager.svelte:1090-1097`: the search box ends in its own "×" button,
/// shown even when the box is empty (then dimmed and not pressable), in place of the system's clear button. Pressing it
/// empties the box, applies the empty search at once without the typing pause, and returns the caret to the box.
@MainActor
struct InkuClearableSearchField: View {
    @Binding var value: String
    let placeholder: String
    let label: String
    let display: DisplaySettings
    var maxLength: Int? = nil
    var delay: Duration? = nil
    var onCancel: (() -> Void)? = nil
    let onSearch: (String) -> Void
    @State private var clearRequest = 0

    var body: some View {
        HStack(spacing: 0) {
            InkuSearchField(value: $value, placeholder: placeholder, label: label, maxLength: maxLength, delay: delay,
                            borderless: true, onCancel: onCancel, clearRequest: clearRequest, onSearch: onSearch)
                .inkuSearchFieldHeight()
            let clear = display.webCopy("historySearchClear", "検索をクリア")
            Button { clearRequest += 1 } label: {
                Text("×").inkuFont(12).padding(.horizontal, 6).frame(maxHeight: .infinity).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .disabled(value.isEmpty)
            .opacity(value.isEmpty ? 0.35 : 1)
            .accessibilityLabel(clear)
            .inkuTooltip(display.tooltip("検索をクリア", serverKey: "historySearchClear"))
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}
