#if os(iOS)
import SwiftUI

/// The picture in a library table row: a tap previews at once and a double tap opens the work, as on the cards.
struct LibraryTableThumbnail<Label: View>: View {
    let locked: Bool
    let preview: () -> Void
    let open: () -> Void
    @ViewBuilder let label: () -> Label
    var body: some View {
        LibraryClickPlatform(preview: preview, open: open, label: label)
            .buttonStyle(.plain).disabled(locked)
    }
}

extension View {
    /// The table's row menu only. An iOS table runs a primary action on a single tap, which would open the work
    /// instead of previewing it; the picture's double tap opens it.
    func inkuTableMenu<I: Hashable, M: View>(forSelectionType type: I.Type, @ViewBuilder menu: @escaping (Set<I>) -> M,
                                              primaryAction: @escaping (Set<I>) -> Void) -> some View {
        contextMenu(forSelectionType: type, menu: menu)
    }
}
#endif
