#if os(macOS)
import AppKit
#endif

/// A first click previews immediately; the second click opens the work.
enum LibraryClick {
    static func opensWork(clickCount: Int) -> Bool { clickCount >= 2 }

    @MainActor static var currentClickCount: Int {
        #if os(macOS)
        guard let event = NSApp.currentEvent,
              [.leftMouseDown, .leftMouseUp, .otherMouseDown, .otherMouseUp].contains(event.type) else { return 1 }
        return event.clickCount
        #else
        return 1
        #endif
    }

    @MainActor static func press(preview: () -> Void, open: () -> Void) {
        if opensWork(clickCount: currentClickCount) { open() } else { preview() }
    }
}
