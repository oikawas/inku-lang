import XCTest
@testable import InkuUI

final class SaijikiBundleTests: XCTestCase {
    func testWebGroupsIncludeRelationsAndAspectRatioInTheirPlaces() throws {
        let bootstrap = try Bootstrap()
        let bundles = bootstrap.productReference.saijikiBundles
        XCTAssertEqual(bundles.map(\.key), ["what", "where", "with", "face", "ground", "color", "sway"])
        XCTAssertEqual(bundles.map(\.labelJa), ["かたち", "場所と動き", "道具", "面", "地", "色", "揺れ"])
        XCTAssertEqual(bundles.map(\.labelEn), ["What", "Where", "With", "Face", "Ground", "Color", "Sway"])
        XCTAssertEqual(bundles.map { $0.categories(in: bootstrap.saijiki).map(\.id) }, [
            ["katachi", "wariai", "ookisa"], ["katamuki", "basho", "ugoki", "jun", "aida"],
            ["tezawari", "tsuranari", "futosa"], ["omote", "sabaki", "kime"], ["ji"], ["iro"], ["yuragi"]
        ])
        let ground = try XCTUnwrap(bootstrap.saijiki.first { $0.id == "ji" })
        XCTAssertEqual(ground.bundle, "ground")
        XCTAssertEqual(ground.words.last?.id, "ji:画面比")
        XCTAssertEqual(bootstrap.saijiki.first { $0.id == "aida" }?.bundle, "where")
        let places = try XCTUnwrap(bootstrap.saijiki.first { $0.id == "basho" })
        XCTAssertTrue(Set(places.words.map(\.japanese)).isDisjoint(with: ["始点", "終点", "途中"]))
        XCTAssertEqual(bootstrap.saijiki.flatMap(\.words).filter { !$0.referenceOnly && !$0.id.hasPrefix("aida:") }.count,
                       bootstrap.productReference.saijikiPreviews.count)
    }

    func testDescriptionOverridesPreviewOnlyWhenNonemptyForDisplayLanguage() {
        let preview = SaijikiPreview(svg: "", effectJa: "見本", effectEn: "Preview", exampleJa: "", exampleEn: "")
        let word = SaijikiWord(id: "test", japanese: "語", english: "word", detail: "physical", isDefault: false,
                               englishDetail: "physical", preview: preview, descriptionJa: "説明", descriptionEn: "")
        XCTAssertEqual(word.effect(language: "ja"), "説明")
        XCTAssertEqual(word.effect(language: "en"), "Preview")
    }
}
