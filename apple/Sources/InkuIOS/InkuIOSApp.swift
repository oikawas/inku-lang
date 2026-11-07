import SwiftUI
import InkuUI

/// The iPad application. One window over one app model, as on the Mac: a second window would show the same
/// model twice (Info-iOS.plist does not support multiple scenes). "About inku" opens in Settings on iOS.
@main
struct InkuIOSApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView(model: model)
        }
        .commands { InkuCommands(display: model.display) }
    }
}
