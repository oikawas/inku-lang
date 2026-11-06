import Foundation
import InkuHost
import XCTest
@testable import InkuUI

@MainActor final class BatchRequestPreparationTests: XCTestCase {
    func testPreparedRequestsMatchIndividualRequests() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-batch-preparation-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"))
        await app.initialize()
        let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "http://localhost:1")!, requiresAPIKey: false,
            models: [.init(id: "model")])
        try await app.updateHostSettings(HostSettings(providers: [provider], models: .init(stage1Model: "fixture:model", stage2Model: "fixture:model")))
        app.activeDrawTab = "batch_text"; app.selectNextDrawingModel("fixture:model")
        app.selectDrawRoute("stages"); app.sketchMode = "off"; app.seedText = "42"; app.language = "en"
        let entries = (0..<200).map { ($0 + 1, "a red circle \($0)") }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        for mode in ["fixed", "auto", "random"] {
            app.catalogMode = mode
            let initialCatalog = app.catalogID
            var expected: [GenerationRequest] = []
            if mode != "random" {
                expected = try entries.map { try app.requestForBatchDescription($0.1, sketchMode: "off") }
            }
            let rows = try await app.makeBatchRows(entries, sketchMode: "off", batchRunID: "fixture")
            XCTAssertEqual(rows.count, entries.count)
            if mode == "random" {
                let allowed = Set(app.catalogs.map(\.id).filter { $0 != initialCatalog })
                for row in rows {
                    let options = try ExactJSON(data: row.request.renderOptions)
                    let selected = try XCTUnwrap(options["catalog_id"].string)
                    XCTAssertTrue(allowed.contains(selected))
                    app.catalogMode = "fixed"; app.catalogID = selected
                    var reference = try app.requestForBatchDescription(row.input, sketchMode: "off")
                    reference.catalogMode = "random"
                    expected.append(reference)
                }
                app.catalogID = initialCatalog
            }
            for (index, row) in rows.enumerated() {
                var reference = expected[index]
                var provenance = reference.provenance ?? GenerationProvenance()
                provenance.batchRunID = "fixture"; provenance.batchLineNumber = entries[index].0
                provenance.displayLabel = "#\(entries[index].0)"; reference.provenance = provenance
                XCTAssertEqual(try encoder.encode(row.request), try encoder.encode(reference), "\(mode) row \(index)")
            }
        }
        for mode in ["fixed", "auto", "random"] {
            app.catalogMode = mode; app.seedText = ""
            let originalCatalog = app.catalogID
            let rows = try await app.makeBatchRows(Array(entries.prefix(12)), sketchMode: "off", batchRunID: "fixture")
            for (index, row) in rows.enumerated() {
                let options = try ExactJSON(data: row.request.renderOptions)
                let selected = try XCTUnwrap(options["catalog_id"].string)
                let seed = try XCTUnwrap(options["render_seed"].string)
                app.seedText = seed
                if mode == "random" { app.catalogMode = "fixed"; app.catalogID = selected }
                var reference = try app.requestForBatchDescription(row.input, sketchMode: "off")
                if mode == "random" { reference.catalogMode = "random" }
                var provenance = reference.provenance ?? GenerationProvenance()
                provenance.batchRunID = "fixture"; provenance.batchLineNumber = entries[index].0
                provenance.displayLabel = "#\(entries[index].0)"; reference.provenance = provenance
                XCTAssertEqual(try encoder.encode(row.request), try encoder.encode(reference), "generated seed \(mode) row \(index)")
            }
            app.catalogID = originalCatalog
        }
    }
}
