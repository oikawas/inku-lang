#if os(macOS)
import AppKit
import InkuPersistence
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

    func drawsNoBackground() { setValue(false, forKey: "drawsBackground") }
}

/// Where the viewer's PNG or GLB goes: the save panel, on the web view's window when it has one.
@MainActor
enum InkuSaveDestination {
    static func choose(suggestedName: String, attachedTo view: NSView, completion: @escaping @MainActor (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedName
        panel.canCreateDirectories = true
        let finish: (NSApplication.ModalResponse) -> Void = { result in
            completion(result == .OK ? panel.url : nil)
        }
        if let window = view.window { panel.beginSheetModal(for: window, completionHandler: finish) } else { panel.begin(completionHandler: finish) }
    }
}

/// The 3D view in the canvas area. Each appearance mounts a new viewer; leaving disposes it.
struct Ddl3DSurface: NSViewRepresentable {
    let controller: Ddl3DController
    let registration: Ddl3DInstallation.Registered
    let title: String
    let onEscape: () -> Bool
    @Environment(InkuFileDialogs.self) private var fileDialogs: InkuFileDialogs?

    func makeNSView(context: Context) -> Ddl3DWebView {
        let bridge = Ddl3DWebHost(registration: registration, title: title, controller: controller)
        bridge.webView.onEscape = onEscape
        bridge.fileDialogs = fileDialogs
        controller.mount(page: bridge)
        return bridge.webView
    }

    func updateNSView(_ view: Ddl3DWebView, context: Context) {
        view.onEscape = onEscape
        view.bridge?.fileDialogs = fileDialogs
    }

    static func dismantleNSView(_ view: Ddl3DWebView, coordinator: ()) { view.bridge?.close() }
}

/// InkuAppCheck `--ddl3d-only`: the work tab's 3D view alone in a hosting view, built as CreationView builds it, over
/// the copy of the viewer the check names (the build's copy in the source tree).
@MainActor
public enum Ddl3DProbe {
    public static func hostingView(registration: Ddl3DInstallation.Registered, work: SavedWork, controller: Ddl3DController,
                                   display: DisplaySettings, initialView: Ddl3DInitialView, onReturn: @escaping () -> Void) -> NSView {
        NSHostingView(rootView: Ddl3DCanvas(controller: controller, registration: registration, work: work,
                                            initialView: initialView, onReturn: onReturn, onEscape: { false })
            .environment(display))
    }
}
#endif
