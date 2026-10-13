import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Web DdlViewer and DdlEditorDialog: the box keeps a draft of the displayed work's instructions, drawn only on
/// request; another work starts from its own; the editor's discard returns to the work's saved instructions.
@MainActor func runDdlBoxChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-ddl-box-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: DdlBoxNoProvider())
    await app.initialize()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                    models: [ProviderModelSettings(id: "m")])
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:m", stage2Model: "check:m")))
    guard await app.drawNewDDL("place one red circle at center."), let parent = app.displayedWork, let saved = parent.ddl else {
        throw CheckFailure.message("Parent failed: \(app.errorText ?? app.status)")
    }
    // Failure: typing in the box changed the work, or the draft was lost before drawing.
    let edited = "place one blue square at center."
    guard app.ddlBoxText(for: parent) == saved else { throw CheckFailure.message("Box did not start from the saved instructions") }
    app.setDdlBoxText(edited, for: parent)
    guard app.ddlBoxText(for: parent) == edited, app.displayedWork?.ddl == saved, app.works.count == 1 else {
        throw CheckFailure.message("Typing in the box drew or lost the draft")
    }
    // Failure: "Draw from instructions" drew the saved text instead of the draft (ContentView draw-ddl).
    guard await app.drawEditedDDL(work: parent, source: app.ddlBoxText(for: parent)), let child = app.displayedWork,
          child.id != parent.id, child.ddl == edited else {
        throw CheckFailure.message("Drawing from the box did not draw its draft: \(app.errorText ?? app.status)")
    }
    // Failure: a draft followed the author to another work.
    guard app.ddlBoxText(for: child) == edited, app.ddlBoxText(for: parent) == saved else {
        throw CheckFailure.message("The box draft belonged to the wrong work")
    }
    // Failure: the editor's discard returned to the box draft, or a new DDL offered a discard.
    guard DdlEditingSession(work: parent, draft: "draft text").discardTarget == saved,
          DdlEditingSession(work: parent, draft: "draft text").draft == "draft text",
          DdlEditingSession(model: app).discardTarget == nil else {
        throw CheckFailure.message("Editor discard target was wrong")
    }
    // Failure: typing a word's start offered nothing, the wrong language, or a word inside a Latin word or an open range.
    let completions = app.ddlCompletions
    guard let japanese = app.saijiki.flatMap(\.words).first(where: { ($0.japanese as NSString).length >= 2 }),
          let english = app.saijiki.flatMap(\.words).compactMap(\.english).first(where: { ($0 as NSString).length >= 3 }),
          let plugin = app.pluginWords.first(where: { !$0.aliases.isEmpty }) else {
        throw CheckFailure.message("Completion: no saijiki word or aliased macro to offer")
    }
    func offered(_ before: String, _ typed: String, _ word: String) -> Bool {
        let text = before + typed
        guard let match = DdlCompletions.match(text: text, caret: (text as NSString).length, words: completions.words(for: text)) else { return false }
        return match.items.contains(word) && NSMaxRange(match.range) == (text as NSString).length && match.range.length >= (typed as NSString).length
    }
    let japanesePrefix = String(japanese.japanese.prefix(1))
    let englishPrefix = String(english.prefix(2)).uppercased()
    let alias = plugin.displayName(language: "ja")
    let qualified = plugin.displayName(language: "en")
    let midWord = "draw zq" + String(english.prefix(2))
    let inRange = DdlCompletions.match(text: "赤い円" + japanesePrefix, caret: 3 + (japanesePrefix as NSString).length,
                                       words: completions.japanese, excluded: NSRange(location: 2, length: 4))
    guard offered("赤い円を", japanesePrefix, japanese.japanese), !offered("place one ", String(english.prefix(2)), japanese.japanese),
          offered("place one ", englishPrefix, english), offered("赤い円を", String(alias.prefix(1)), alias),
          offered("place one ", String(qualified.prefix(3)), qualified),
          DdlCompletions.match(text: midWord, caret: (midWord as NSString).length, words: completions.english).map({ $0.range.location == 7 }) != true,
          DdlCompletions.match(text: "place one ", caret: 10, words: completions.english) == nil, inRange == nil else {
        throw CheckFailure.message("Completion offered the wrong words")
    }
    print("DDL box passed: the draft is kept per displayed work and never draws by itself; drawing from the box draws the draft once; another work starts from its own instructions; the editor opens on the draft and discards back to the saved instructions; a new DDL has no discard; typing offers saijiki words and macro names of the instruction language (\(completions.japanese.count) Japanese, \(completions.english.count) English), not inside a Latin word, after a space or in an open range. Real core, no provider.")
}

private actor DdlBoxNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("ddl_box_check_sends_nothing")
    }
}
