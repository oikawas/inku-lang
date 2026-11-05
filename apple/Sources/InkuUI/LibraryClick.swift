import Foundation
import SwiftUI
#if os(macOS)
import AppKit
#endif

/// Web `click` and `dblclick` (HistoryManager.svelte:1202) on a library or lineage picture: the first click previews at
/// once and the second click of a double click opens the work. The count comes from the mouse-down that pressed this
/// very picture, recorded as it happens, not from whatever event is current when SwiftUI runs the button's action:
/// that event can be a later one (a move, or the press on another card), which would miscount the clicks.
enum LibraryClick {
    /// A left mouse-down: its click count, window, place in the window's base coordinates and time.
    struct Press: Equatable, Sendable {
        let clickCount: Int
        let windowNumber: Int
        let locationInWindow: CGPoint
        let time: TimeInterval
    }

    /// Opens only when the latest press was in the picture's window, inside the picture, recent enough to be the press
    /// that ran the action, and the second (or later) click. Anything else, a key or accessibility press among them,
    /// previews.
    static func opensWork(press: Press?, windowNumber: Int?, contains: (CGPoint) -> Bool, now: TimeInterval,
                          interval: TimeInterval) -> Bool {
        guard let press, let windowNumber, press.windowNumber == windowNumber,
              now - press.time >= 0, now - press.time <= interval, contains(press.locationInWindow) else { return false }
        return press.clickCount >= 2
    }

    #if os(macOS)
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
    #endif
}

#if os(macOS)
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
#endif

/// The picture button of a library or lineage card: one button, and the press that ran it.
/// `.buttonStyle` and `.disabled` set outside reach the button through the environment.
struct LibraryClickButton<Label: View>: View {
    let preview: () -> Void
    let open: () -> Void
    @ViewBuilder let label: () -> Label
    #if os(macOS)
    @State private var anchor = LibraryClickAnchor()
    #endif

    var body: some View {
        #if os(macOS)
        Button { LibraryClick.press(anchor: anchor.view, preview: preview, open: open) } label: { label() }
            .background(LibraryClickAnchorView(anchor: anchor))
            .onAppear { LibraryClick.installMonitor() }
        #else
        Button(action: preview) { label() }
        #endif
    }
}
