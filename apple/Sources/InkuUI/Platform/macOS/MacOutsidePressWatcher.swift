#if os(macOS)
import AppKit
import SwiftUI

/// A view as large as the field it sits behind. While `isActive`, a press anywhere outside it calls `end` and still
/// reaches what was pressed. In a browser any press outside a focused field blurs it; on macOS a press on a place
/// that takes no focus (the empty space, the gaps between cards) leaves the field editing (Build 81).
/// The monitor never consumes a press and is installed only while the field has the focus, so it cannot eat presses
/// under a SwiftUI cover the way the hidden lineage map's monitor did (11-06, 87ba395f3).
struct MacOutsidePressWatcher: NSViewRepresentable {
    let isActive: Bool
    let end: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSView {
        let view = PassThroughView()
        context.coordinator.view = view
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        context.coordinator.view = nsView
        context.coordinator.end = end
        context.coordinator.watch(isActive)
    }

    static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) { coordinator.watch(false) }

    @MainActor final class Coordinator {
        weak var view: NSView?
        var end: () -> Void = {}
        private var monitor: Any?

        func watch(_ active: Bool) {
            if active, monitor == nil {
                monitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown, .otherMouseDown]) { [weak self] event in
                    self?.pressed(event)
                    return event
                }
            } else if !active, let monitor {
                NSEvent.removeMonitor(monitor)
                self.monitor = nil
            }
        }

        private func pressed(_ event: NSEvent) {
            guard let view, let window = view.window else { return }
            if event.window === window, view.bounds.contains(view.convert(event.locationInWindow, from: nil)) { return }
            end()
        }
    }

    private final class PassThroughView: NSView {
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
    }
}
#endif
