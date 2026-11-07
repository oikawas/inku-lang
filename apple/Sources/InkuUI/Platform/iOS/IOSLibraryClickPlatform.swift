#if os(iOS)
import SwiftUI

struct LibraryClickPlatform<Label: View>: View {
    let preview: () -> Void
    let open: () -> Void
    @ViewBuilder let label: () -> Label
    var body: some View { Button(action: preview) { label() } }
}
#endif
