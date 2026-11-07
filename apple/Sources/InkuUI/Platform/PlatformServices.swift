import Combine
import Foundation
import InkuHost
import SwiftUI
#if os(macOS)
import AppKit
#elseif os(iOS)
import UIKit
#endif

@MainActor
enum InkuPasteboard {
    @discardableResult
    static func copy(text: String, includingIOS: Bool = true) -> Bool {
        #if os(macOS)
        NSPasteboard.general.clearContents()
        return NSPasteboard.general.setString(text, forType: .string)
        #elseif os(iOS)
        guard includingIOS else { return false }
        UIPasteboard.general.string = text
        return true
        #else
        return false
        #endif
    }

    static var supportsImages: Bool {
        #if os(macOS)
        true
        #else
        false
        #endif
    }

    static func copy(image data: Data) throws {
        #if os(macOS)
        guard let image = NSImage(data: data) else { throw HostError("clipboard_image_unavailable") }
        NSPasteboard.general.clearContents()
        guard NSPasteboard.general.writeObjects([image]) else { throw HostError("clipboard_write_failed") }
        #endif
    }
}

/// Finder's "show in folder"; iOS has no file viewer to open.
@MainActor
enum InkuFileViewer {
    static var available: Bool {
        #if os(macOS)
        true
        #else
        false
        #endif
    }

    static func reveal(_ urls: [URL]) {
        #if os(macOS)
        NSWorkspace.shared.activateFileViewerSelecting(urls)
        #endif
    }
}

/// The system alert sound where a save or a viewer file fails.
@MainActor
enum InkuFeedback {
    static func beep() {
        #if os(macOS)
        NSSound.beep()
        #endif
    }
}

/// Web color tokens mapped onto each system palette with the existing native colors.
enum InkuColor {
    #if os(macOS)
    static let bg = Color(nsColor: .windowBackgroundColor)
    static let panel = Color(nsColor: .controlBackgroundColor)
    static let libraryBackground = Color(nsColor: .windowBackgroundColor)
    #else
    static let bg = Color(uiColor: .systemGroupedBackground)
    static let panel = Color(uiColor: .secondarySystemGroupedBackground)
    static let libraryBackground = Color(uiColor: .secondarySystemBackground)
    #endif
    static let bg2 = Color.primary.opacity(0.045)
    static let border = Color.primary.opacity(0.12)
    static let border2 = Color.primary.opacity(0.2)
    static let floating = panel.opacity(0.92)
}

/// A weak reference keeps full-screen ownership tied to the same window as before.
@MainActor
final class InkuWindow {
    #if os(macOS)
    private weak var window: NSWindow?
    private init(_ window: NSWindow) { self.window = window }
    #endif

    static var key: InkuWindow? {
        #if os(macOS)
        NSApp.keyWindow.map(InkuWindow.init)
        #else
        nil
        #endif
    }

    var isFullScreen: Bool {
        #if os(macOS)
        window?.styleMask.contains(.fullScreen) == true
        #else
        false
        #endif
    }

    func toggleFullScreen() {
        #if os(macOS)
        window?.toggleFullScreen(nil)
        #endif
    }

    func matches(_ notification: Notification) -> Bool {
        #if os(macOS)
        (notification.object as? NSWindow) === window
        #else
        false
        #endif
    }

    static var didExitFullScreen: AnyPublisher<Notification, Never> {
        #if os(macOS)
        NotificationCenter.default.publisher(for: NSWindow.didExitFullScreenNotification).eraseToAnyPublisher()
        #else
        Empty().eraseToAnyPublisher()
        #endif
    }

    static func removeFocus() {
        #if os(macOS)
        NSApp.keyWindow?.makeFirstResponder(nil)
        #endif
    }
}
