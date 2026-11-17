import XCTest
import InkuPersistence
@testable import InkuUI

@MainActor final class SaijikiInsertionLanguageTests: XCTestCase {
    func testDrawerInsertionUsesDisplayedInstructionLanguageAndEmptyFallsBackToUI() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-saijiki-language-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let model = AppModel(databaseURL: folder.appendingPathComponent("test.sqlite"))
        await model.initialize()
        model.display.preferences.language = "en"
        let work = SavedWork(id: "language-fixture", at: 1, input: "", score: "{}", svg: "<svg/>",
                             ddl: "青い線を引く。", instructionLangResolved: "ja")
        await model.selectWork(work)
        XCTAssertEqual(model.shownDDLLanguage, "ja")
        var inserted: [String] = []
        let japaneseDrawer = SaijikiView(model: model, onInsertWord: { inserted.append($0) }, wordLanguage: model.shownDDLLanguage)
        japaneseDrawer.insertSelection(.builtin("ji:紙"))
        XCTAssertEqual(inserted, ["紙"])
        let paper = try XCTUnwrap(model.saijiki.first { $0.id == "ji" }?.words.first { $0.japanese == "紙" })
        XCTAssertEqual(paper.effect(language: model.display.preferences.language), "Makes the ground plain paper, with faint specks of fiber.")

        model.ddlText = ""
        XCTAssertNil(model.shownDDLLanguage)
        let emptyDrawer = SaijikiView(model: model, onInsertWord: { inserted.append($0) }, wordLanguage: model.shownDDLLanguage)
        emptyDrawer.insertSelection(.builtin("ji:紙"))
        XCTAssertEqual(inserted, ["紙", "paper"])

        var recordedEnglish = work
        recordedEnglish.instructionLangResolved = "en"
        await model.selectWork(recordedEnglish)
        XCTAssertEqual(model.shownDDLLanguage, "en")
        var noRecordedLanguage = work
        noRecordedLanguage.instructionLangResolved = nil
        await model.selectWork(noRecordedLanguage)
        XCTAssertEqual(model.shownDDLLanguage, "ja")
        noRecordedLanguage.instructionLangResolved = "unknown"
        await model.selectWork(noRecordedLanguage)
        XCTAssertEqual(model.shownDDLLanguage, "ja")
    }
}
