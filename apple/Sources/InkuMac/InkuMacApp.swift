import SwiftUI
import InkuUI

@main
struct InkuMacApp: App {
    @State private var model = AppModel()

    init() {
        let arguments = ProcessInfo.processInfo.arguments
        if let index = arguments.firstIndex(of: "--database"), arguments.indices.contains(index + 1) {
            _model = State(initialValue: AppModel(databaseURL: URL(fileURLWithPath: arguments[index + 1])))
        }
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
