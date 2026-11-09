import SwiftUI
import InkuUI

/// The iPad and iPhone application. One window over one app model, as on the Mac: a second window would show the same
/// model twice (Info-iOS.plist does not support multiple scenes). "About inku" opens in Settings on iOS.
@main
struct InkuIOSApp: App {
    /// An iPhone stays upright except on the screens that show a work (ios-app step 7).
    @UIApplicationDelegateAdaptor(InkuOrientationDelegate.self) private var orientation
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView(model: model)
        }
        .commands { InkuCommands(display: model.display) }
    }
}
