import Foundation
import InkuCore
import InkuHost

/// An old export must migrate before it reaches the v3 authoring catalog.
func runSaijikiV3Checks() throws {
    let legacy: ExactJSON = .object(["schema": .string("inku.ddl-export.v2"), "language": .string("ja"),
        "ddl": .string("青い細筆の線を引く。"), "plugins": .array([])])
    let migrated = try DDLPackageImport.parse(legacy.data)
    guard migrated.source.contains("ガッシュ"), (migrated.migratedEdits ?? 0) > 0 else {
        throw CheckFailure.message("Old export was not migrated")
    }
    let request: ExactJSON = .object(["definitions": .array([]), "document": .object([
        "source": .string("青い細筆の線を引く。"), "language": .string("ja"),
        "macro_locks": .array([]), "saijiki": .string("inku.saijiki.v2")])])
    let answer = try ExactJSON(data: InkuCore.migrateSaijikiV2(request.data))
    guard answer["document"]["document"]["saijiki"].string == "inku.saijiki.v3",
          answer["document"]["document"]["source"].string == migrated.source,
          answer["document"]["edits"].array?.count == migrated.migratedEdits else {
        throw CheckFailure.message("Import and core migration disagree")
    }
    print("Saijiki v3 checks passed: old export and saved document agree; no provider calls.")
}
