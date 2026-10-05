import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runReleaseParityChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-release-parity-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }

    // Failure: one missing or retyped field in interface.json reset every saved display choice.
    let preferencesFolder = folder.appendingPathComponent("preferences")
    try FileManager.default.createDirectory(at: preferencesFolder, withIntermediateDirectories: true)
    let olderFile: [String: Any] = ["language": "en", "theme": "dark", "textSizeStep": 3, "uiMode": "full",
                                    "captionVisible": "yes", "mascot": "none"]
    try JSONSerialization.data(withJSONObject: olderFile).write(to: preferencesFolder.appendingPathComponent("interface.json"))
    let display = DisplaySettings()
    display.connect(directory: preferencesFolder)
    let read = display.preferences
    guard display.saveError == nil, read.language == "en", read.theme == "dark", read.textSizeStep == 3, read.uiMode == "full",
          read.mascot == "none", read.captionVisible == DisplayPreferences().captionVisible else {
        throw CheckFailure.message("Older interface.json lost saved choices: \(display.saveError ?? "\(read)")")
    }
    display.preferences.batchRetries = 2
    let rewritten = try JSONSerialization.jsonObject(with: Data(contentsOf: preferencesFolder.appendingPathComponent("interface.json"))) as? [String: Any]
    guard rewritten?["language"] as? String == "en", rewritten?["batchRetries"] as? Int == 2 else {
        throw CheckFailure.message("A later change was not saved after reading an older interface.json")
    }

    // Failure: a saved demo model that is unusable at launch was overwritten in demo-settings.json.
    let demoURL = folder.appendingPathComponent("demo-settings.json")
    let demoBody = Data(#"{"seedPhrase":"春","model":"missing-provider:missing-model","interval":30,"duration":3600,"saveWorks":false,"saveFiles":false}"#.utf8)
    try demoBody.write(to: demoURL)
    let model = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: NoProviderTransport())
    await model.initialize()
    guard model.errorText == nil else { throw CheckFailure.message("Release parity initialization: \(model.errorText ?? model.status)") }
    let automation = AutomationModel()
    await automation.connect(app: model)
    guard try Data(contentsOf: demoURL) == demoBody, automation.demoModel != "missing-provider:missing-model" else {
        throw CheckFailure.message("Launch rewrote the saved demo model")
    }

    // Failure: a Japanese description defaulted to the English instruction language.
    guard model.language == "auto", model.instructionLanguage(for: "春の月") == "ja",
          model.instructionLanguage(for: "a red circle") == "en", model.instructionLanguage(for: "1 2 3") == "ja" else {
        throw CheckFailure.message("Instruction language does not follow the Server auto rule")
    }

    // Failure: a non-square paper used width 1000 and an unrounded height instead of the Server's height 1000.
    guard let wide = model.canvases.first(where: { $0.widthRatio == 16 && $0.heightRatio == 9 }) else {
        throw CheckFailure.message("16:9 paper missing from the registry")
    }
    let expectedWidth = Int((1000.0 * 16 / 9).rounded(.toNearestOrEven))
    func canvas(_ work: SavedWork) async throws -> (Int?, Int?, String?) {
        let saved = try await model.savedConfiguration(workID: work.id)
        let options = try ExactJSON(data: saved.renderOptions)
        let config = try ExactJSON(data: saved.configuration)
        return (options["canvas"]["width"].number.flatMap { Double($0) }.map { Int($0) },
                options["canvas"]["height"].number.flatMap { Double($0) }.map { Int($0) }, config["language"].string)
    }
    model.inputMode = "ddl"
    model.ddlText = "Nature.若葉 を置く"
    model.canvasID = wide.id
    model.seedText = "42"
    await model.generate()
    guard model.errorText == nil, let drawn = model.selectedWork else { throw CheckFailure.message("16:9 DDL did not draw: \(model.errorText ?? model.status)") }
    let drawnCanvas = try await canvas(drawn)
    guard drawnCanvas.0 == expectedWidth, drawnCanvas.1 == 1000, drawnCanvas.2 == "ja" else {
        throw CheckFailure.message("New 16:9 work canvas/language \(drawnCanvas), expected \(expectedWidth)x1000 ja")
    }
    model.canvasID = model.canvases.first(where: { $0.widthRatio == 9 && $0.heightRatio == 16 })?.id ?? wide.id
    await model.replayWithCurrentOptions()
    guard model.errorText == nil, let replayed = model.selectedWork, replayed.id != drawn.id else {
        throw CheckFailure.message("Replay with another paper failed: \(model.errorText ?? model.status)")
    }
    let replayedCanvas = try await canvas(replayed)
    let tall = model.canvases.first(where: { $0.id == model.canvasID })!
    let expectedReplay = Int((1000.0 * Double(tall.widthRatio) / Double(tall.heightRatio)).rounded(.toNearestOrEven))
    guard replayedCanvas.0 == expectedReplay, replayedCanvas.1 == 1000 else {
        throw CheckFailure.message("Replay canvas \(replayedCanvas), expected \(expectedReplay)x1000")
    }
    print("Release parity passed: tolerant interface.json; demo model kept; auto instruction language; 16:9 new \(expectedWidth)x1000 and replay \(expectedReplay)x1000. No external provider calls.")
}

private actor NoProviderTransport: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw CheckFailure.message("The release parity check must not call a provider")
    }
}
