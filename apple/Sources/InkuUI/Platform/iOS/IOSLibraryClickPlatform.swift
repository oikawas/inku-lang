#if os(iOS)
import SwiftUI

/// A tap previews at once; the second tap of a double tap opens the work. The button keeps the first tap immediate:
/// the double-tap gesture runs beside it instead of making it wait. The second tap previews the same work again,
/// which changes nothing.
struct LibraryClickPlatform<Label: View>: View {
    let preview: () -> Void
    let open: () -> Void
    @ViewBuilder let label: () -> Label
    var body: some View {
        Button(action: preview) { label() }
            .simultaneousGesture(TapGesture(count: 2).onEnded { open() })
    }
}
#endif
