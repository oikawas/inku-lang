#if os(iOS)
import SwiftUI

@MainActor
struct InkuSearchField: View {
    @Binding var value: String
    let placeholder: String
    let label: String
    var maxLength: Int? = nil
    var delay: Duration? = nil
    var borderless: Bool = false
    var onCancel: (() -> Void)? = nil
    let onSearch: (String) -> Void

    @ViewBuilder var body: some View {
        if borderless {
            TextField(placeholder, text: $value).accessibilityLabel(label)
        } else {
            TextField(placeholder, text: $value)
                .onSubmit { onSearch(String(value.prefix(maxLength ?? value.count))) }
        }
    }
}
#endif
