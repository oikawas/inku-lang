import SwiftUI
import InkuUI

@main
struct InkuMacApp: App {
    @State private var model: AppModel

    init() {
        let arguments = ProcessInfo.processInfo.arguments
        let databaseURL: URL?
        if let index = arguments.firstIndex(of: "--database"), arguments.indices.contains(index + 1) {
            databaseURL = URL(fileURLWithPath: arguments[index + 1])
        } else if let path = Bundle.main.object(forInfoDictionaryKey: "InkuDatabasePath") as? String,
                  path.hasPrefix("/"), !path.contains("\0") {
            databaseURL = URL(fileURLWithPath: path)
        } else {
            databaseURL = nil
        }
        _model = State(initialValue: AppModel(databaseURL: databaseURL))
    }

    var body: some Scene {
        Window("Inku", id: "main") {
            ContentView(model: model)
                .frame(minWidth: 1000, minHeight: 680)
        }
        .defaultSize(width: 1320, height: 880)
        .commands { InkuCommands(display: model.display) }
    }
}
