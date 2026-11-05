import XCTest
import InkuHost
import InkuPersistence
@testable import InkuUI

@MainActor final class BatchResumeTests: XCTestCase {
    func testResumeReconcilesSavedAndUnsavedInterruptedRows() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-batch-resume-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let transport = ResumeProvider()
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"), transport: transport)
        await app.initialize()
        let service = ProviderSettings(id: "fixture", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false,
                                       models: [ProviderModelSettings(id: "model")])
        try await app.updateHostSettings(HostSettings(providers: [service], models: .init(stage1Model: "fixture:model", stage2Model: "fixture:model")))
        app.activeDrawTab = "batch_text"
        app.selectNextDrawingModel("fixture:model")
        app.selectDrawRoute("stages")
        app.sketchMode = "off"
        let original = AutomationModel()
        await original.connect(app: app)
        original.batchSketchMode = "off"
        original.batchText = "a red circle\na blue square"
        await original.startBatch(app: app)
        XCTAssertEqual(original.rows.map(\.state), [.succeeded, .succeeded])
        let savedID = try XCTUnwrap(original.rows.first?.workID)
        let savedExecution = try XCTUnwrap(original.rows.first?.executionID)
        let before = await transport.draws

        let journalURL = root.appendingPathComponent("batch-journal.json")
        var journal = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: journalURL)) as? [String: Any])
        var rows = try XCTUnwrap(journal["rows"] as? [[String: Any]])
        rows[0]["state"] = "uncertain"; rows[0].removeValue(forKey: "workID")
        rows[1]["state"] = "uncertain"; rows[1].removeValue(forKey: "workID"); rows[1]["executionID"] = UUID().uuidString
        journal["rows"] = rows
        try JSONSerialization.data(withJSONObject: journal).write(to: journalURL, options: .atomic)

        let resumed = AutomationModel()
        await resumed.connect(app: app)
        XCTAssertEqual(resumed.uncertainCount, 2)
        await resumed.resumeBatch(app: app)
        XCTAssertEqual(resumed.rows.map(\.state), [.succeeded, .succeeded])
        XCTAssertEqual(resumed.rows[0].workID, savedID)
        XCTAssertEqual(resumed.rows[0].executionID, savedExecution)
        XCTAssertNotNil(resumed.rows[1].workID)
        XCTAssertNotEqual(resumed.rows[1].executionID, rows[1]["executionID"] as? String)
        let after = await transport.draws
        XCTAssertEqual(after, before + 1)
        let database = try InkuDatabase(url: root.appendingPathComponent("works.sqlite"))
        let saved = try await database.work(id: savedID)
        XCTAssertNotNil(saved)
    }
}

private actor ResumeProvider: ProviderTransport {
    private(set) var draws = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let value = try ExactJSON(data: action)
        guard value["tag"].string == "generate_normalized_ddl" else {
            return ExactJSON.object(["tag": .string("provider_failed"), "identity": value["identity"],
                                     "failure": .string("provider_rejected"), "elapsed_ms": .string("1")]).data
        }
        draws += 1
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": value["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
}
