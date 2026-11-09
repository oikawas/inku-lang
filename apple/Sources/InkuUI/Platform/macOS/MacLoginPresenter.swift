#if os(macOS)
import SwiftUI

/// The ChatGPT plan's sign-in on the Mac: the default browser, as before (iOS: `IOSLoginPresenter.swift`).
@MainActor
final class InkuLoginPresenter {
    func open(_ url: URL, fallback: OpenURLAction, onCancel: @escaping @MainActor () -> Void) { fallback(url) }
    func close() {}
}
#endif
