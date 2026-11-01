import Foundation
import InkuCore
import Testing
@testable import InkuHost

struct DDLPackageMigrationTests {
    @Test func importAdoptsRecoveredDefinitionsFromCoreAnswer() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let table = try ExactJSON(data: Data(contentsOf: root.appendingPathComponent("core/crates/inku-pipeline-uniffi/assets/nature-historical-definitions.json")))
        let definitions = try #require(table["definitions"].array)
        let initial = try ExactJSON(data: InkuCore.migrateSaijikiV2(ExactJSON.object(["definitions": .array([definitions[14]])]).data))
        let identity = try #require(initial["definitions"].array?.first)
        let lock: ExactJSON = .object(["qualified_name": identity["qualified_name"], "version": identity["version"], "digest": identity["old_digest"]])
        let request: ExactJSON = .object(["definitions": .array([]), "document": .object(["source": .string("｛若葉｝。"), "language": .string("ja"), "macro_locks": .array([lock]), "saijiki": .string("inku.saijiki.v2")])])
        let response = InkuCore.migrateSaijikiV2(request.data)
        let recovered = try ExactJSON(data: response)["document"]["recovered_definitions"].array
        #expect(recovered?.count == 1)
        let file: ExactJSON = .object(["schema": .string("inku.ddl-export.v2"), "language": .string("ja"), "ddl": .string("｛若葉｝。"), "plugins": .array([])])
        var call = 0
        let result = try DDLPackageImport.parse(file.data) { input in
            call += 1
            return call == 1 ? InkuCore.migrateSaijikiV2(input) : response
        }
        #expect(call == 2)
        #expect(result.plugins.count == 1)
        #expect(result.plugins.first?.definition == recovered?.first?["definition"])
        #expect(result.plugins.first?.note == "")
    }

    @Test func legacyPackageMigratesBundledDefinitionBeforeResolvingCatalog() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let fixture = root.appendingPathComponent("core/crates/inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json")
        let package = try ExactJSON(data: Data(contentsOf: fixture))
        let definition = try #require(package["entries"].array?.first?["definition"])
        let input: ExactJSON = .object(["schema": .string("inku.ddl-export.v2"), "language": .string("ja"),
            "ddl": .string("｛若葉｝。青い細筆の線を引く。"),
            "plugins": .array([.object(["definition": definition, "note": .string("keep")])])])
        let output = try DDLPackageImport.parse(input.data)
        #expect(output.source.contains("ガッシュ"))
        #expect((output.migratedEdits ?? 0) > 0)
        #expect(output.plugins.count == 1)
        #expect(output.plugins[0].note == "keep")
        #expect(try output.resolveCatalog(language: "ja")["entries"].array?.count == 1)
    }

    @Test func legacyPackageMigratesButPlainTextAndV3DoNot() throws {
        let old = Data(#"{"schema":"inku.ddl-export.v2","language":"ja","ddl":"青い細筆の線を引く。","plugins":[]}"#.utf8)
        let migrated = try DDLPackageImport.parse(old)
        #expect(migrated.source.contains("ガッシュ"))
        #expect((migrated.migratedEdits ?? 0) > 0)
        let current = Data(#"{"schema":"inku.ddl-export.v2","saijiki":"inku.saijiki.v3","language":"ja","ddl":"青い水彩の線を引く。","plugins":[]}"#.utf8)
        let unchanged = try DDLPackageImport.parse(current)
        #expect(unchanged.source == "青い水彩の線を引く。")
        #expect(unchanged.migratedEdits == nil)
        let plain = try DDLPackageImport.parse(Data("青い細筆の線を引く。".utf8))
        #expect(plain.source == "青い細筆の線を引く。")
        #expect(plain.migratedEdits == nil)
        let invalid = Data(#"{"schema":"inku.ddl-export.v2","saijiki":null,"ddl":"x","plugins":[]}"#.utf8)
        #expect(throws: HostError.self) { try DDLPackageImport.parse(invalid) }
    }
}
