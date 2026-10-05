import Foundation
import InkuHost
import InkuPersistence
import XCTest
@testable import InkuExport

final class PackageImportChecks: XCTestCase, @unchecked Sendable {
    // Failure: reading a package changes its Unicode/source-u64 or locks, or silently accepts partial invalid definitions.
    func testPackageRoundTripKeepsExactSourceDefinitionsAndLocksAndRejectsPartialImports() throws {
        let definition: ExactJSON = .object(["schema": .string("inku.macro-definition.v1"), "namespace": .string("Trace"),
            "heading": .string("Mark"), "aliases": .array([.string("若葉")]), "version": .string("3.2.1"),
            "parameters": .object([:]), "components": .object([:]), "body": .array([])])
        let source = "Trace.若葉を置く。\n注: e\u{301}\nseed: 18446744073709551615"
        var work = SavedWork(id: "package-round-trip", at: 1, input: "保存", score: "{}", svg: "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"2\"/>")
        work.ddl = source; work.instructionLangResolved = "ja"
        let bytes = try ExportService.ddl(ExportSource(work: work, pluginDefinitions: [definition], pluginSummaries: ["Unicode e\u{301}の定義"]))
        let imported = try DDLPackageImport.parse(bytes)
        XCTAssertEqual(Array(imported.source.utf8), Array(source.utf8))
        XCTAssertEqual(imported.plugins[0].definition.data, definition.data)
        XCTAssertEqual(imported.language, "ja")
        let locks = try XCTUnwrap(try imported.resolveCatalog(language: "ja")["locks"].array)
        XCTAssertEqual(locks.count, 1); XCTAssertEqual(locks[0]["version"].string, "3.2.1")
        XCTAssertFalse(try XCTUnwrap(locks[0]["digest"].string).isEmpty)
        var next = work; next.id = "second"
        let readAgain = try DDLPackageImport.parse(ExportService.ddl(ExportSource(work: next, pluginDefinitions: imported.plugins.map(\.definition), pluginSummaries: imported.plugins.map(\.summary))))
        XCTAssertEqual(try readAgain.resolveCatalog(language: "ja")["locks"], .array(locks))
        XCTAssertEqual(try DDLPackageImport.parse(Data("{\"other\":18446744073709551615}".utf8)).source, "{\"other\":18446744073709551615}")
        var envelope = try ExactJSON(data: bytes)
        envelope["plugins"] = .array((envelope["plugins"].array ?? []) + [.object(["definition": .object(["namespace": .string("bad")])])])
        XCTAssertThrowsError(try DDLPackageImport.parse(envelope.data))
        envelope["plugins"] = .array(Array(repeating: .object(["definition": definition]), count: 65))
        XCTAssertThrowsError(try DDLPackageImport.parse(envelope.data))
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent("inku-package-check-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let file = scratch.appendingPathComponent("source.json")
        try bytes.write(to: file)
        XCTAssertEqual(try DDLPackageImport.read(url: file), imported)
        let oversized = Data(repeating: 32, count: DDLPackageImport.maximumBytes + 1)
        XCTAssertThrowsError(try DDLPackageImport.parse(oversized))
        try oversized.write(to: file)
        XCTAssertThrowsError(try DDLPackageImport.read(url: file))
    }
}
