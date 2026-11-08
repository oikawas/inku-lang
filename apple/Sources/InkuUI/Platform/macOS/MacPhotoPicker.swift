#if os(macOS)
import SwiftUI

/// The image tab's "choose from Photos" exists on iOS only; macOS chooses a file, as before.
struct InkuPhotoPickerButton: View {
    let title: String
    let disabled: Bool
    let onPick: (Data) -> Void

    var body: some View { EmptyView() }
}
#endif
