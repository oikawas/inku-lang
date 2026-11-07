#if os(macOS)
import AppKit
import SwiftUI

extension LibraryClick {

    @MainActor private static var latest: Press?
    @MainActor private static var monitor: Any?

    /// Watches left mouse-downs without consuming them. Installed once, when the first picture button appears.
    @MainActor static func installMonitor() {
        guard monitor == nil else { return }
        monitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { event in
            if let window = event.window {
                latest = Press(clickCount: event.clickCount, windowNumber: window.windowNumber,
                               locationInWindow: event.locationInWindow, time: event.timestamp)
            }
            return event
        }
    }

    /// `anchor` is a view laid out exactly over the picture; it answers whether the press fell on it.
    @MainActor static func press(anchor: NSView?, preview: () -> Void, open: () -> Void) {
        let opens = opensWork(press: latest, windowNumber: anchor?.window?.windowNumber, contains: { point in
            guard let anchor else { return false }
            return anchor.bounds.contains(anchor.convert(point, from: nil))
        }, now: ProcessInfo.processInfo.systemUptime, interval: NSEvent.doubleClickInterval + 0.5)
        if opens { open() } else { preview() }
    }
}

/// Holds the view behind a picture button, read when the button is pressed.
@MainActor final class LibraryClickAnchor {
    weak var view: NSView?
}

/// A view as large as the picture button, behind it; it never takes the mouse.
private struct LibraryClickAnchorView: NSViewRepresentable {
    let anchor: LibraryClickAnchor

    func makeNSView(context: Context) -> NSView {
        let view = PassThroughView()
        anchor.view = view
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) { anchor.view = nsView }

    private final class PassThroughView: NSView {
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
    }
}

struct LibraryClickPlatform<Label: View>: View {
    let preview: () -> Void
    let open: () -> Void
    @ViewBuilder let label: () -> Label
    @State private var anchor = LibraryClickAnchor()
    init(preview: @escaping () -> Void, open: @escaping () -> Void, @ViewBuilder label: @escaping () -> Label) {
        self.preview = preview; self.open = open; self.label = label
    }
    var body: some View {
        Button { LibraryClick.press(anchor: anchor.view, preview: preview, open: open) } label: { label() }
            .background(LibraryClickAnchorView(anchor: anchor))
            .onAppear { LibraryClick.installMonitor() }
    }
}
#endif
