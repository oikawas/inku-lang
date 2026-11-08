#if os(iOS)
import PhotosUI
import SwiftUI

/// The image tab's "choose from Photos" (iOS plan §3 #7). The system picker runs outside the app, so it needs no
/// photo-library permission; `.compatible` hands a HEIC photo over as JPEG, which the image input accepts.
struct InkuPhotoPickerButton: View {
    let title: String
    let disabled: Bool
    let onPick: (Data) -> Void
    @State private var item: PhotosPickerItem?

    var body: some View {
        PhotosPicker(selection: $item, matching: .images, preferredItemEncoding: .compatible) { Text(title) }
            .buttonStyle(InkuGhostButtonStyle())
            .disabled(disabled)
            .onChange(of: item) { _, picked in
                guard let picked else { return }
                item = nil
                Task {
                    guard let data = try? await picked.loadTransferable(type: Data.self) else { InkuFeedback.beep(); return }
                    onPick(data)
                }
            }
    }
}
#endif
