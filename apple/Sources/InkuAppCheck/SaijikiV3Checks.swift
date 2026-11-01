import Foundation
import InkuCore
import InkuHost
import InkuUI

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

/// Compile and draw each current touch offline, then apply the shared display support check.
@MainActor
func runSaijikiV3DisplayChecks(folder: URL) async throws {
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let url = folder.appendingPathComponent("works.sqlite")
    guard !FileManager.default.fileExists(atPath: url.path) else { throw CheckFailure.message("Refusing to overwrite display fixture") }
    let app = AppModel(databaseURL: url, transport: SaijikiNoProvider())
    await app.initialize()
    app.language = "ja"; app.seedText = "42"
    let tools: [(String, String)] = [("銀筆", "silverpoint"), ("鉛筆", "pencil"), ("ペン", "pen"),
        ("チョーク", "chalk"), ("オイルパステル", "oil_pastel"), ("ガッシュ", "gouache"),
        ("水彩", "watercolor"), ("油彩", "oil_paint"), ("ペインティングナイフ", "painting_knife"),
        ("エッチング", "etching"), ("コンピュータ", "computer")]
    for (word, weight) in tools {
        guard await app.drawNewDDL("青い\(word)の線を引く。"), let work = app.selectedWork else {
            throw CheckFailure.message("\(word): draw failed: \(app.errorText ?? app.status)")
        }
        let score = try ExactJSON(data: Data(work.score.utf8))
        guard (score["instructions"].array ?? []).contains(where: { $0["weight"].string == weight }) else {
            throw CheckFailure.message("\(word): generated score did not use \(weight)")
        }
        do { _ = try InkuCore.prepareDisplay(svg: work.svg) }
        catch { throw CheckFailure.message("\(word): display support refused: \(error)") }
        print("\(word) (\(weight)): display support accepted")
    }
    print("Saijiki v3 display support: 11/11 accepted; no provider calls or GUI operation.")
}

private struct SaijikiNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data { throw HostError("provider_forbidden") }
}
