#if os(macOS)
import SwiftUI

/// The picture in a library table row. On the Mac the row itself previews on a click and opens on a double click
/// (the table's selection and primary action), so the picture is only drawn.
struct LibraryTableThumbnail<Label: View>: View {
    let locked: Bool
    let preview: () -> Void
    let open: () -> Void
    @ViewBuilder let label: () -> Label
    var body: some View { label() }
}

extension View {
    /// The table's row menu and its primary action (a double click or Return opens the work).
    func inkuTableMenu<I: Hashable, M: View>(forSelectionType type: I.Type, @ViewBuilder menu: @escaping (Set<I>) -> M,
                                              primaryAction: @escaping (Set<I>) -> Void) -> some View {
        contextMenu(forSelectionType: type, menu: menu, primaryAction: primaryAction)
    }
}
#endif
