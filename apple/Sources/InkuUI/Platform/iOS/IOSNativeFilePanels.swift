#if os(iOS)
import Foundation
import UniformTypeIdentifiers

/// The save destinations the app's own code writes to (Platform/macOS has the panels). How iOS hands an export on
/// (share, or save to Files after making it) is decided with the iOS app; until then nothing is chosen.
@MainActor
enum NativeFilePanels {
    static func exportFile(title: String, type: UTType, name: String) -> URL? { nil }
}
#endif
