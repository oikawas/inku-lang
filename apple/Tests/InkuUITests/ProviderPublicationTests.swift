import XCTest
import InkuHost
@testable import InkuUI

final class ProviderPublicationTests: XCTestCase {
    func testModelPublication() {
        let models = (0..<50).map { ProviderModelSettings(id: "measure-\($0)", purposes: ["llm"]) }
        let enabled = Dictionary(uniqueKeysWithValues: models.enumerated().map { ($0.element.id, $0.offset % 2 != 0) })
        let draft = ProviderModelsDraft(models: models, enabled: enabled)
        let ids = draft.filteredModels(search: "", filter: .enabled).map(\.id)
        let count = draft.enabledCount
        XCTAssertEqual(count, 25)
        XCTAssertEqual(Set(ids), Set(models.enumerated().filter { $0.offset % 2 != 0 }.map { $0.element.id }))
    }
}
