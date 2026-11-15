import XCTest
import InkuPersistence
@testable import InkuUI

final class CompositionDerivationTests: XCTestCase {
    @MainActor func testThesisHeadMatchesWebFourteenUnicodeScalars() {
        let display = DisplaySettings()
        let edge = LineageEdge(id: "e", parentNodeID: "p", childNodeID: "c", derivationKind: "composition_form_change",
            metadataJSON: #"{"thesis_from":"短い","thesis_to":"あいうえおかきくけこさしすせそた"}"#, at: 1)
        let detail = compositionDerivationDetail(edge, display: display)
        XCTAssertEqual(detail, "命題: 短い → あいうえおかきくけこさしすせ…")
    }
}
