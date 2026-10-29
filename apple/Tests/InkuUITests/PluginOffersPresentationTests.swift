import XCTest
import InkuHost
@testable import InkuUI

@MainActor final class PluginOffersPresentationTests: XCTestCase {
    func testSavedOffersUseWrittenNamesAndSavedDefinitions() throws {
        let catalog = try Bootstrap().macroCatalogValue(language: "ja")
        let definitions = (catalog["entries"].array ?? []).map { $0["definition"] }
        let config: ExactJSON = .object(["definitions": .array(definitions), "plugin_offers": .array([
            .object(["stage": .string("generate_normalized_ddl"), "offer": .object(["offered": .array([
                .object(["qualified_name": .string("Nature.YoungLeaves"), "reason": .string("brace"), "written_ja": .string("｛若葉｝"), "written_en": .string("{young leaves}")]),
                .object(["qualified_name": .string("Nature.YoungLeaves"), "reason": .string("ddl")]),
                .object(["qualified_name": .string("Missing.Unknown"), "reason": .string("name")])
            ])])])
        ])])
        XCTAssertEqual(SavedGenerationInformation.pluginOffers(configuration: config, japanese: true),
                       ["下絵: ｛若葉｝（括弧で書いた）、｛若葉｝（DDL にあった）、Missing.Unknown（名が記述に現れた）"])
        XCTAssertEqual(SavedGenerationInformation.pluginOffers(configuration: config, japanese: false).first,
                       "Underdrawing: {young leaves}（written in braces）, {young leaves}（in the DDL）, Missing.Unknown（name appeared in the description）")
        let empty: ExactJSON = .object(["plugin_offers": .array([.object(["stage": .string("write_description_ddl"), "offered": .array([]), "omitted": .array([.object(["qualified_name": .string("Nature.YoungLeaves"), "written_ja": .string("｛若葉｝")])])])])])
        XCTAssertEqual(SavedGenerationInformation.pluginOffers(configuration: empty, japanese: true), ["書く: 提示なし", "上限で落とした語: ｛若葉｝"])
    }
}
