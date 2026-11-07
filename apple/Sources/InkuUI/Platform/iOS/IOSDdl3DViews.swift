#if os(iOS)
import SwiftUI
import UIKit
import WebKit

/// The viewer's web view. iOS has no 3D switch yet (`Ddl3DInstallation.available`); this keeps the shared host compiling.
public final class Ddl3DWebView: WKWebView {
    /// Kept while the view is on screen; `Ddl3DWebHost.close()` lets it go.
    var bridge: Ddl3DWebHost?
    var onEscape: (() -> Bool)?
    var takesFocusInWindow = true

    func drawsNoBackground() {
        isOpaque = false
        backgroundColor = .clear
        scrollView.backgroundColor = .clear
    }
}

/// Where the viewer's PNG or GLB goes. The iOS way (share or save to Files) is decided with the iOS app; until then
/// nothing is saved.
@MainActor
enum InkuSaveDestination {
    static func choose(suggestedName: String, attachedTo view: UIView, completion: @escaping @MainActor (URL?) -> Void) {
        completion(nil)
    }
}

/// The 3D view in the canvas area. Each appearance mounts a new viewer; leaving disposes it.
struct Ddl3DSurface: UIViewRepresentable {
    let controller: Ddl3DController
    let registration: Ddl3DInstallation.Registered
    let title: String
    let onEscape: () -> Bool

    func makeUIView(context: Context) -> Ddl3DWebView {
        let bridge = Ddl3DWebHost(registration: registration, title: title, controller: controller)
        bridge.webView.onEscape = onEscape
        controller.mount(page: bridge)
        return bridge.webView
    }

    func updateUIView(_ view: Ddl3DWebView, context: Context) { view.onEscape = onEscape }

    static func dismantleUIView(_ view: Ddl3DWebView, coordinator: ()) { view.bridge?.close() }
}
#endif
