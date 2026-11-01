import Foundation
import Testing
@testable import InkuHost

struct DDLPackageMigrationTests {
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
