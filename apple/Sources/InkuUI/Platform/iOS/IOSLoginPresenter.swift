#if os(iOS)
import AuthenticationServices
import SwiftUI
import UIKit

/// The ChatGPT plan's sign-in on iOS (plan §3 #20): an in-app login sheet over the app. The app stays in front, so
/// its loopback listener (`ChatGPTLoopbackListener`, http://127.0.0.1:<port>/auth/callback) receives the callback as
/// on the Mac; the sheet is then closed by `close()`. The step 5 probe showed the sheet reaches the app's
/// 127.0.0.1, and that a sheet closed by `cancel()` does not call its completion.
@MainActor
final class InkuLoginPresenter: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?

    /// `onCancel`: the person closed the sheet before signing in.
    func open(_ url: URL, fallback: OpenURLAction, onCancel: @escaping @MainActor () -> Void) {
        close()
        // The scheme never comes back: the callback goes to the loopback listener, not to the sheet.
        let session = ASWebAuthenticationSession(url: url, callbackURLScheme: "inku-loopback-only") { _, error in
            guard let error = error as? ASWebAuthenticationSessionError, error.code == .canceledLogin else { return }
            Task { @MainActor in onCancel() }
        }
        session.presentationContextProvider = self
        session.prefersEphemeralWebBrowserSession = true
        self.session = session
        if !session.start() { self.session = nil; fallback(url) }
    }

    func close() {
        session?.cancel()
        session = nil
    }

    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        MainActor.assumeIsolated {
            UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows)
                .first { $0.isKeyWindow } ?? ASPresentationAnchor()
        }
    }
}
#endif
