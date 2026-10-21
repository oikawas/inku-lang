import Foundation
import XCTest
@testable import InkuHost

final class SavedPromptStagesTests: XCTestCase {
    private static func entry(_ action: String, _ system: String, message: String = "message") -> ExactJSON {
        .object(["action": .string(action), "identity": .object(["attempt": .integer(1)]),
                 "prompt": .object(["system": .string(system), "message": .string(message)])])
    }

    // Failure: a saved work dropped the sketch, the composition reading, the laws or the colors, kept the
    // catalog choice, kept an earlier attempt, or lost the order the prompt tab shows.
    func testSavedWorkKeepsTheLastPromptOfEachShownStageInCallOrder() throws {
        let journal: ExactJSON = .array([
            Self.entry("generate_sketch", "sketch system", message: "sketch message"),
            Self.entry("select_description_catalog", "catalog system"),
            Self.entry("generate_normalized_ddl", "stage1 first"),
            Self.entry("generate_normalized_ddl", "stage1 retry"),
            Self.entry("read_composition", "composition system", message: "composition message"),
            Self.entry("choose_laws", "laws first", message: "laws message"),
            Self.entry("choose_laws", "laws again", message: "laws message again"),
            Self.entry("choose_colors", "colors system", message: "colors message"),
            Self.entry("complete_visible_ddl_holes", "stage2 system"),
        ])
        let record = try SavedPresentation.capture(delivery: .object([:]), rendered: .object(["metadata": .object([:])]),
            prompts: journal.data, events: Data("[]".utf8), configuration: .object([:]), document: .object(["source": .string("")]))
        let saved = try SavedWorkPresentation(context: .object(["presentation": record]))
        let prompts = try XCTUnwrap(saved.promptJSON.map { try ExactJSON(data: $0).array })
        XCTAssertEqual(prompts?.map { $0["action"].string ?? "" },
                       ["generate_sketch", "generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors",
                        "complete_visible_ddl_holes"])
        XCTAssertEqual(prompts?.map { $0["prompt"]["system"].string ?? "" },
                       ["sketch system", "stage1 retry", "composition system", "laws again", "colors system", "stage2 system"])
        XCTAssertEqual(prompts?.first?["prompt"]["message"].string, "sketch message")
        XCTAssertEqual(prompts?[3]["prompt"]["message"].string, "laws message again")
        XCTAssertEqual(saved.promptStages, ["sketch", "stage1", "composition", "laws", "colors", "stage2"])
    }

    // Failure: a work saved before the record named its stages read its sketch and reading as "not sent".
    func testEarlierSavedWorkKeptStageOneAndTwoOnly() throws {
        var record = try SavedPresentation.capture(delivery: .object([:]), rendered: .object(["metadata": .object([:])]),
            prompts: nil, events: Data("[]".utf8), configuration: .object([:]), document: .object(["source": .string("")]))
        record["prompt_stages"] = .null
        XCTAssertEqual(try SavedWorkPresentation(context: .object(["presentation": record])).promptStages, ["stage1", "stage2"])
    }
}
