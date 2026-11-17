import XCTest
@testable import InkuUI

final class SaijikiBundleTests: XCTestCase {
    func testWebGroupsIncludeRelationsAndAspectRatioInTheirPlaces() throws {
        let bootstrap = try Bootstrap()
        let appleRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let asset = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: appleRoot.appendingPathComponent("Sources/InkuUI/Resources/saijiki.json"))) as? [String: Any])
        let assetBundles = try XCTUnwrap(asset["bundles"] as? [[String: String]])
        let assetCategories = try XCTUnwrap(asset["categories"] as? [[String: Any]])
        let bundles = bootstrap.saijikiBundles
        XCTAssertEqual(bundles.map(\.key), assetBundles.compactMap { $0["key"] })
        XCTAssertEqual(bundles.map(\.labelJa), assetBundles.compactMap { $0["name_ja"] })
        XCTAssertEqual(bundles.map(\.labelEn), assetBundles.compactMap { $0["name_en"] })
        for bundle in bundles {
            var expected = assetCategories.filter { $0["bundle"] as? String == bundle.key }.compactMap { $0["key"] as? String }
            if bundle.key == "where" { expected.append("aida") }
            XCTAssertEqual(bundle.categories(in: bootstrap.saijiki).map(\.id), expected)
        }
        XCTAssertEqual(Set(bundles.flatMap { $0.categories(in: bootstrap.saijiki).map(\.id) }), Set(bootstrap.saijiki.map(\.id)))
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
