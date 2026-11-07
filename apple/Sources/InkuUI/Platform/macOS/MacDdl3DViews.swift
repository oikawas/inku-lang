#if os(macOS)
import AppKit
import SwiftUI
import WebKit

/// The viewer's web view. Esc can be taken before the page (leaving the full-screen canvas first, as a browser does).
public final class Ddl3DWebView: WKWebView {
    /// Kept while the view is on screen; `Ddl3DWebHost.close()` lets it go.
    var bridge: Ddl3DWebHost?
    var onEscape: (() -> Bool)?
    var takesFocusInWindow = true

    public override func keyDown(with event: NSEvent) {
        if event.keyCode == 53, onEscape?() == true { return }
        super.keyDown(with: event)
    }

    public override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        // Choosing 3D gives the viewer the keyboard, so Esc and its keys work without a click first.
        guard let window, takesFocusInWindow else { return }
        takesFocusInWindow = false
        window.makeFirstResponder(self)
    }
}

/// The 3D view in the canvas area. Each appearance mounts a new viewer; leaving disposes it.
struct Ddl3DSurface: NSViewRepresentable {
    let controller: Ddl3DController
    let registration: Ddl3DInstallation.Registered
    let title: String
    let onEscape: () -> Bool

    func makeNSView(context: Context) -> Ddl3DWebView {
        let bridge = Ddl3DWebHost(registration: registration, title: title, controller: controller)
        bridge.webView.onEscape = onEscape
        controller.mount(page: bridge)
        return bridge.webView
    }

    func updateNSView(_ view: Ddl3DWebView, context: Context) { view.onEscape = onEscape }

    static func dismantleNSView(_ view: Ddl3DWebView, coordinator: ()) { view.bridge?.close() }
}
#endif
