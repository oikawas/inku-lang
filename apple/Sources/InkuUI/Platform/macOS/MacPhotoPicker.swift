#if os(macOS)
import SwiftUI

/// The image tab's "choose from Photos" exists on iOS only; macOS chooses a file, as before.
struct InkuPhotoPickerButton: View {
    let title: String
    let disabled: Bool
    let onPick: (Data) -> Void

    var body: some View { EmptyView() }
}

/// The image tab's "Take photo" exists on iOS only.
struct InkuCameraButton: View {
    let title: String
    let disabled: Bool
    let onCapture: (Data) -> Void

    var body: some View { EmptyView() }
}
#endif
