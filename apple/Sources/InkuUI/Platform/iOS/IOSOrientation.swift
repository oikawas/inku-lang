#if os(iOS)
import SwiftUI
import UIKit

/// The orientations the app allows now. An iPad allows every one; an iPhone stays upright except while a screen that
/// shows a work is open (ios-app step 7, the author's choice 2026-11-09 "作品を見る画面だけ横も").
public final class InkuOrientationDelegate: NSObject, UIApplicationDelegate {
    public func application(_ application: UIApplication,
                            supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask {
        InkuOrientationGate.mask
    }
}

@MainActor
enum InkuOrientationGate {
    /// How many work screens are open.
    private static var holders = 0

    static var mask: UIInterfaceOrientationMask {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return .all }
        return holders > 0 ? .allButUpsideDown : .portrait
    }

    static func enter() { holders += 1; apply() }
    static func leave() { holders = max(0, holders - 1); apply() }

    private static func apply() {
        guard UIDevice.current.userInterfaceIdiom == .phone,
              let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first else { return }
        for window in scene.windows {
            var controller = window.rootViewController
            while let current = controller {
                current.setNeedsUpdateOfSupportedInterfaceOrientations()
                controller = current.presentedViewController
            }
        }
        if holders == 0 { scene.requestGeometryUpdate(.iOS(interfaceOrientations: .portrait)) { _ in } }
    }
}
#endif
