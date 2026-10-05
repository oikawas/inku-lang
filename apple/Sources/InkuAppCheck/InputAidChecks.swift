import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Saved choices, the description label rule, the meter, the batch count, the comment limit, the edited sketch
/// and the fork, each against the failure it prevents. Expected meter labels and the batch count were produced by
/// the Build1162 Web functions (`verseForm.ts` `describeLength` with the ja/en templates, `numberedBatchLines`).
@MainActor
func runInputAidChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-input-aids-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }

    // Failure: a choice made on one launch was gone on the next, or an older file lost its other values.
    let fresh = DisplaySettings()
    fresh.connect(directory: folder)
    guard fresh.preferences.theme == "dark", fresh.preferences.sketchExpanded == nil else {
        throw CheckFailure.message("A new install must start dark with the sketch section default (open)")
    }
    fresh.preferences.nextCatalogID = "kept-catalog"
    fresh.preferences.nextCatalogMode = "auto"
    fresh.preferences.nextCanvasID = "kept-canvas"
    fresh.preferences.nextWild = true
    fresh.preferences.settingsTab = "export"
    fresh.preferences.workspaceTab = "lineage"
    fresh.preferences.inputTab = "batch"
    fresh.preferences.libraryLayout = "list"
    fresh.preferences.libraryGrouped = true
    fresh.preferences.refineKind = "layout_change"
    fresh.preferences.comparisonModels = ["a:one", "b:two"]
    fresh.preferences.aiRefine = AIRefineChoices(visionMode: true, generations: 7, kinds: ["layout_change"], direction: "夜へ")
    let reread = DisplaySettings()
    reread.connect(directory: folder)
    guard reread.preferences == fresh.preferences else {
        throw CheckFailure.message("Saved choices did not come back from interface.json")
    }
    let older = folder.appendingPathComponent("older", isDirectory: true)
    try FileManager.default.createDirectory(at: older, withIntermediateDirectories: true)
    try Data(#"{"theme":"system","language":"en","historyFields":["size","generation","engine","model"]}"#.utf8)
        .write(to: older.appendingPathComponent("interface.json"))
    let existing = DisplaySettings()
    existing.connect(directory: older)
    guard existing.preferences.theme == "system", existing.preferences.language == "en",
          existing.preferences.nextCatalogID == nil, existing.preferences.aiRefine == nil,
          existing.preferences.historyStripFields == ["generation", "model", "engine"] else {
        throw CheckFailure.message("An older interface.json must keep its values, add no choices, and print fields in the Web order")
    }

    // Failure: a catalog or paper that no longer exists was restored as the next condition.
    let database = folder.appendingPathComponent("inku.sqlite")
    let provider = InputAidProvider()
    try JSONEncoder().encode({ () -> DisplayPreferences in
        var saved = DisplayPreferences()
        saved.nextCatalogID = "removed-catalog"; saved.nextCanvasID = "removed-paper"
        saved.nextCatalogMode = "auto"; saved.nextWild = true
        return saved
    }()).write(to: folder.appendingPathComponent("interface.json"))
    let gone = AppModel(databaseURL: database, transport: provider)
    await gone.initialize()
    guard gone.catalogID == "default", gone.canvasID == "square", gone.catalogMode == "auto", gone.wild else {
        throw CheckFailure.message("Vanished catalog/paper must fall back to the defaults while mode and wild are kept: \(gone.catalogID) \(gone.canvasID)")
    }
    let otherCatalog = try required(gone.catalogs.first { $0.id != "default" }?.id, "a second catalog")
    let otherPaper = try required(gone.canvases.first { $0.id != "square" }?.id, "a second paper")
    gone.catalogID = otherCatalog; gone.canvasID = otherPaper; gone.wild = false; gone.catalogMode = "fixed"
    let relaunched = AppModel(databaseURL: database, transport: provider)
    await relaunched.initialize()
    guard relaunched.catalogID == otherCatalog, relaunched.canvasID == otherPaper, !relaunched.wild, relaunched.catalogMode == "fixed" else {
        throw CheckFailure.message("Next-work conditions did not come back after a relaunch")
    }

    // Failure: the Swift label rule drifted from the Server/Web corpus.
    let corpusURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("server/tests/data/description-label-cases.json")
    let corpus = try ExactJSON(data: Data(contentsOf: corpusURL))
    let cases = corpus["cases"].array ?? []
    guard !cases.isEmpty else { throw CheckFailure.message("The description label corpus is empty") }
    for item in cases {
        let text = try required(item["text"].string, "corpus text")
        let spans = DescriptionLabels.excludedSpans(text).map { "\($0.range.location),\(NSMaxRange($0.range)),\($0.kind == .number ? "number" : "comment")" }
        let expected = (item["spans"].array ?? []).map { span in
            (span.array ?? []).map { $0.string ?? $0.text }.joined(separator: ",")
        }
        guard DescriptionLabels.pipelineDescription(text) == item["pipeline"].string, spans == expected else {
            throw CheckFailure.message("Label rule differs from the corpus for \(item["why"].string ?? text): \(spans) vs \(expected)")
        }
    }

    // Failure: a description made only of numbers and comments could be drawn.
    try await relaunched.updateHostSettings(HostSettings(
        providers: [ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                     label: "Offline input-aid fixture", models: [ProviderModelSettings(id: "aid", label: "LLM", purposes: ["llm"])])],
        models: ModelSelection(stage1Model: "check:aid", stage2Model: "check:aid")))
    relaunched.inputMode = "description"
    relaunched.descriptionText = "1. [メモだけ]\n［下書き］"
    guard !relaunched.canGenerateDescription else { throw CheckFailure.message("A comment-only description was drawable") }
    relaunched.descriptionText = "1. 月が昇る [メモ]"
    guard relaunched.canGenerateDescription else { throw CheckFailure.message("A numbered description with text was not drawable") }

    // Failure: the meter's estimate, wording or English syllables differed from the Web.
    let meterCases: [(String, String, Bool, Bool, DescriptionMoraAnswer?, [Int]?, String, String)] = [
        ("ふるいけやかわずとびこむみずのおと", "ja", true, true, nil, nil, "文字数 17/17（俳句/川柳）", "Characters 17/17 (haiku or senryū)"),
        ("古池や 蛙飛び込む 水の音", "ja", true, true, DescriptionMoraAnswer(total: 17, phrases: [5, 7, 5], unread: ["蛙"]), nil,
         "音数 約17/17（俳句/川柳）", "Sounds about 17/17 (haiku or senryū)"),
        ("古池や 蛙飛び込む 水の音", "en", true, true, DescriptionMoraAnswer(total: 18, phrases: [5, 8, 5], unread: []), nil,
         "音数 18/17（俳句/川柳）", "Sounds 18/17 (haiku or senryū)"),
        ("1. 月が昇る [メモ]", "ja", false, true, nil, nil, "文字数 4", "Characters 4"),
        ("An old silent pond\nA frog jumps into the pond\nSplash! Silence again", "en", true, true, nil, nil, "行数 3/3（ハイク）", "Lines 3/3 (haiku)"),
        ("An old silent pond\nA frog jumps into the pond\nSplash! Silence again", "ja", true, true, nil, [5, 8, 7], "行数 3/3（ターセット）", "Lines 3/3 (tercet)"),
        ("Snow\nquiet falling\nover sleeping village roofs\nlanterns glowing in the dusk\nhush", "en", true, true, nil, nil,
         "行数 5/5（シンクェイン）", "Lines 5/5 (cinquain)"),
        ("A moon rises beyond the mountains", "en", true, false, nil, nil, "行数 1", "Lines 1"),
        ("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわを", "ja", true, true, nil, nil,
         "文字数 45/43（長歌）", "Characters 45/43 (chōka)"),
    ]
    for (text, ui, japanese, english, mora, syllables, expectedJA, expectedEN) in meterCases {
        let reading = DescriptionMeterModel.describe(text, uiLanguage: ui, japaneseEnabled: japanese, englishEnabled: english,
                                                     mora: mora, syllableLines: syllables)
        guard reading.label(language: "ja") == expectedJA, reading.label(language: "en") == expectedEN else {
            throw CheckFailure.message("Meter for \(text.prefix(12)) said \(reading.label(language: "ja")) / \(reading.label(language: "en"))")
        }
    }
    let syllables = ["little", "make", "the", "silence", "don't", "queue", "fire", "table", "beautiful"].map(DescriptionMeterModel.englishSyllables)
    guard syllables == [2, 1, 1, 2, 1, 1, 1, 2, 3] else { throw CheckFailure.message("English syllable estimate differs: \(syllables)") }

    // Failure: the batch count included comment-only and number-only lines (Web counts 3 here; the run keeps 6 entries).
    let batch = "1. 月\n\n[メモ]\n２．霧 [x]\n   \n#3 線\n［コメント］ \n3) "
    guard BatchInputLines.paintableCount(in: batch) == 3, BatchInputLines.entries(in: batch).count == 6 else {
        throw CheckFailure.message("Batch count \(BatchInputLines.paintableCount(in: batch)) differs from the Web's 3")
    }

    // Failure: lengths were counted in scalars where the Web counts UTF-16 code units.
    let emoji = String(repeating: "😀", count: 121)
    let kana = String(repeating: "あ", count: 241)
    guard LibraryNoteEditorModel.limited(emoji).utf16.count == 240, LibraryNoteEditorModel.limited(emoji).count == 120,
          LibraryNoteEditorModel.limited(kana).count == 240, String(repeating: "😀", count: 2001).utf16.count > DescriptionMeterModel.dictionaryTextLimit else {
        throw CheckFailure.message("The 240 comment limit or the 4000 meter limit is not counted in UTF-16")
    }

    // Failure: an edited sketch was not what Stage 1 read.
    relaunched.descriptionText = "a red circle in an open field"
    relaunched.sketchMode = "on"
    relaunched.seedText = "42"
    await relaunched.generate()
    guard relaunched.errorText == nil, let parent = relaunched.selectedWork, let prose = parent.sketchText, !prose.isEmpty else {
        throw CheckFailure.message("Sketch parent did not draw: \(relaunched.errorText ?? relaunched.status)")
    }
    let sketchesBefore = await provider.sketchCalls
    var draft = SketchDraft(workID: parent.id, source: parent.effectiveSourceText, original: prose)
    draft.text = "A narrow field under a low winter sun, edited by the author."
    relaunched.sketchDraft = draft
    await relaunched.generate()
    let sketchesAfter = await provider.sketchCalls
    guard relaunched.errorText == nil, let child = relaunched.selectedWork, child.id != parent.id,
          child.sketchText == draft.text, sketchesAfter == sketchesBefore else {
        throw CheckFailure.message("Edited sketch did not reach the pipeline: \(relaunched.selectedWork?.sketchText ?? "-"), sketch calls \(sketchesBefore)->\(sketchesAfter)")
    }

    // Failure: a held work could not start a new work from its description.
    guard await relaunched.drawEditedDDL(work: child, source: "place one blue circle at center."),
          let held = relaunched.selectedWork, held.id != child.id else {
        throw CheckFailure.message("DDL-edited fixture did not draw: \(relaunched.errorText ?? relaunched.status)")
    }
    await relaunched.selectWork(held)
    guard relaunched.sourceLocked, !relaunched.canGenerateDescription, relaunched.canForkDescription else {
        throw CheckFailure.message("A DDL-edited work must offer the fork instead of drawing from its description")
    }
    await relaunched.forkDescription()
    guard relaunched.errorText == nil, let forked = relaunched.selectedWork, forked.id != held.id,
          !relaunched.sourceLocked, forked.effectiveSourceText == held.effectiveSourceText else {
        throw CheckFailure.message("Fork did not start an unlocked work from the description: \(relaunched.errorText ?? relaunched.status)")
    }

    print("Input aids passed: interface.json kept 12 new choices and an older file's values; vanished catalog/paper fell back to default/square; "
          + "label rule matched \(cases.count) corpus cases; comment-only description not drawable; \(meterCases.count) meter labels and 9 syllable estimates "
          + "matched the Web; batch count 3 (entries 6); comment 240 and meter 4000 counted in UTF-16; edited sketch drawn without a sketch call; "
          + "held work forked into an unlocked work. Temporary SQLite and an offline provider mock only.")
}

private func required<T>(_ value: T?, _ name: String) throws -> T {
    guard let value else { throw CheckFailure.message("Missing \(name)") }
    return value
}

private actor InputAidProvider: ProviderTransport {
    private(set) var sketchCalls = 0

    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        let isSketch = input["tag"].string == "generate_sketch"
        if isSketch { sketchCalls += 1 }
        let body = isSketch ? ExactJSON.object(["sketch": .string("An open field extends into distant light \(sketchCalls).")]).text
            : #"{"normalized_ddl":"place one red circle at center."}"#
        return ExactJSON.object(["tag": .string(isSketch ? "sketch_generated" : "normalized_ddl_generated"),
            "identity": input["identity"], "response": .string(body), "elapsed_ms": .string("1")]).data
    }
}
