import Foundation
import InkuHost
import InkuUI

/// DDL 27 title lines, as Web `a-ddl-title-line-colours-no-word.test.ts` checks them: a DDL view shows the
/// title as a heading and colours no word in it, while the sentence after it keeps its colours; a title line
/// offers no word. Bundled saijiki only, no provider call.
@MainActor func runDdlTitleChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-ddl-title-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: DdlTitleNoProvider())
    await app.initialize()
    guard !app.saijiki.isEmpty else { throw CheckFailure.message("Bundled saijiki did not load: \(app.errorText ?? app.status)") }

    let ddl = "画面比1:1。\n\n「黒い水面」\n画面の横0.5、縦0.5の位置に、青の塗りの円を1個置く。"
    let source = ddl as NSString
    let marks = DdlHighlightProbe.marks(ddl, saijiki: app.saijiki)
    let title = source.range(of: "「黒い水面」")
    let blue = source.range(of: "青")
    // Failure: the title was painted word by word (黒 as a color) or not set apart as a heading.
    guard marks.contains(where: { $0.range == title && $0.style == "title" }),
          !marks.contains(where: { $0.style != "title" && NSIntersectionRange($0.range, title).length > 0 }),
          marks.contains(where: { $0.range == blue && $0.style == "color" }) else {
        throw CheckFailure.message("DDL title highlight: \(marks.map { "\(source.substring(with: $0.range))=\($0.style)" })")
    }
    // Failure: a quoted phrase inside a sentence was taken for a title.
    let inline = "「黒い円」を中心に置く。"
    guard !DdlHighlightProbe.marks(inline, saijiki: app.saijiki).contains(where: { $0.style == "title" }) else {
        throw CheckFailure.message("A quoted phrase inside a sentence was shown as a title")
    }
    // Failure: a title line offered a word while the same word after it still is offered.
    let words = app.saijiki.flatMap(\.words).map(\.japanese)
    let typed = "「黒」\n黒"
    guard DdlCompletions.match(text: typed, caret: 3, words: words) == nil,
          DdlCompletions.match(text: typed, caret: (typed as NSString).length, words: words) != nil else {
        throw CheckFailure.message("A title line offered a word, or the sentence after it offered none")
    }
    print("DDL title passed: a title line is one heading mark with no word coloured in it; the sentence after it keeps its colours; a quoted phrase in a sentence is no title; a title line offers no word. Bundled saijiki only, no provider call.")
}

private actor DdlTitleNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("ddl_title_check_must_not_call_provider")
    }
}
