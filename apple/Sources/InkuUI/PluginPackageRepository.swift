import Foundation
import InkuCore
import InkuHost
import InkuPersistence

struct InstalledPluginPackage: Sendable {
    let id: String
    let package: ExactJSON?
    let problems: [ExactJSON]
    let directory: URL
    var words: [ExactJSON] { package?["words"].array ?? [] }
    var rejected: Bool { package == nil }

    func candidateWords(language: String) -> [ExactJSON] {
        words.map { word in
            let primary = word[language == "en" ? "summary_en" : "summary_ja"].string ?? ""
            let fallback = word[language == "en" ? "summary_ja" : "summary_en"].string ?? ""
            return .object(["source_id": .string("package:" + id), "definition_json": .string(word["definition"].text),
                            "summary": .string(primary.isEmpty ? fallback : primary)])
        }
    }
    func pluginWords() -> [PluginWord] {
        words.compactMap { word in
            guard let name = word["qualified_name"].string, let key = word["preview_key"].string else { return nil }
            let definition = word["definition"]
            let heading = definition["heading"].string ?? name
            let aliases = (word["visible_qualified_names"].array ?? []).dropFirst().compactMap(\.string)
            let jaAliases = (word["aliases"].array ?? []).compactMap(\.string)
            let ja = jaAliases.isEmpty ? [heading] : jaAliases
            let custom = directory.appendingPathComponent("custom/\(key)@2x.png")
            let preview = FileManager.default.fileExists(atPath: custom.path) ? custom : directory.appendingPathComponent("previews/\(key)@2x.png")
            let noteJa = word["note_ja"].string ?? "", noteEn = word["note_en"].string ?? ""
            let exampleJa = word["example_ja"].string ?? "", exampleEn = word["example_en"].string ?? ""
            return PluginWord(id: name, aliases: aliases, japanese: ja, english: [heading],
                note: noteJa.isEmpty ? noteEn : noteJa, previewURL: FileManager.default.fileExists(atPath: preview.path) ? preview : nil,
                packageID: id, sourceFile: nil, englishNote: noteEn.isEmpty ? noteJa : noteEn, firesOnJapanese: [], firesOnEnglish: [],
                exampleJapanese: exampleJa.isEmpty ? (aliases.first ?? name) + "。" : exampleJa,
                exampleEnglish: exampleEn.isEmpty ? name + "." : exampleEn)
        }
    }
}

public struct PluginPackageCheck: Sendable {
    public let report: ExactJSON
    let text: String
    let pictures: ExactJSON
    var previewKeys: [String] = []
    public var id: String? { report["id"].string }
    public var ok: Bool { report["ok"].bool == true }
    public func preview(at index: Int) -> Data? {
        guard previewKeys.indices.contains(index), let value = pictures[previewKeys[index]]["png_2x"].string else { return nil }
        return Data(base64Encoded: value)
    }
}

/// User packages live alongside the database and are parsed only by the shared core.
struct PluginPackageRepository: Sendable {
    let directory: URL
    init(dataDirectory: URL) { directory = dataDirectory.appendingPathComponent("plugin-packages", isDirectory: true) }

    static func call(_ request: ExactJSON) throws -> ExactJSON {
        let answer = try ExactJSON(data: InkuCore.pluginPackage(request.data))
        guard answer["error"] == .null else { throw HostError(answer["error"].string ?? "invalid_plugin_package_input") }
        return answer
    }
    static func safeID(_ id: String) -> Bool {
        id.range(of: #"^[A-Za-z][A-Za-z0-9_-]*\.[A-Za-z][A-Za-z0-9_-]*$"#, options: .regularExpression) != nil
    }
    func load() throws -> [InstalledPluginPackage] {
        guard FileManager.default.fileExists(atPath: directory.path) else { return [] }
        let urls = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey], options: [.skipsHiddenFiles])
        return try urls.sorted { $0.lastPathComponent < $1.lastPathComponent }.compactMap { url in
            let id = url.lastPathComponent
            let attributes = try url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard Self.safeID(id), attributes.isDirectory == true, attributes.isSymbolicLink != true else { return nil }
            let document = url.appendingPathComponent("package.json")
            guard FileManager.default.fileExists(atPath: document.path) else { return nil }
            do {
                let text = try String(contentsOf: document, encoding: .utf8)
                let result = try Self.call(.object(["action": .string("read_stored"), "document": .string(text)]))
                guard result["outcome"].string == "ok" else {
                    let problems = result["problems"].array ?? []
                    let fallback: ExactJSON = .object(["path": .string(""), "code": .string("invalid_json"), "detail": .string("")])
                    return InstalledPluginPackage(id: id, package: nil, problems: problems.isEmpty ? [fallback] : problems, directory: url)
                }
                let package = result["package"]
                let actualID = (package["namespace"].string ?? "") + "." + (package["name"].string ?? "")
                var problems = package["problems"].array ?? []
                problems += (package["words"].array ?? []).flatMap { $0["problems"].array ?? [] }
                if actualID != id { problems.append(.object(["path": .string(""), "code": .string("id_differs_from_directory"), "detail": .string("")])) }
                return InstalledPluginPackage(id: id, package: problems.isEmpty ? package : nil, problems: problems, directory: url)
            } catch {
                let problem: ExactJSON = .object(["path": .string(""), "code": .string("invalid_json"), "detail": .string(error.localizedDescription)])
                return InstalledPluginPackage(id: id, package: nil, problems: [problem], directory: url)
            }
        }
    }

    @MainActor
    func check(data: Data, isArchive: Bool, bootstrap: Bootstrap) async throws -> PluginPackageCheck {
        var taken: [String: ExactJSON] = [:]
        let installed = try load()
        let installedNames = Set(installed.flatMap { $0.words.flatMap { ($0["visible_qualified_names"].array ?? []).compactMap(\.string) } })
        for word in bootstrap.bundledPluginWords {
            for name in [word.id] + word.aliases where !installedNames.contains(name) { taken[name] = .string("plugin document") }
        }
        for package in installed {
            for word in package.words {
                for name in (word["visible_qualified_names"].array ?? []).compactMap(\.string) { taken[name] = .string(package.id) }
            }
        }
        var input: ExactJSON = .object(["action": .string("check_start"), "taken_names": .object(taken)])
        if isArchive { input["archive"] = .string(data.base64EncodedString()) }
        else if let text = String(data: data, encoding: .utf8) { input["document"] = .string(text) }
        else {
            let problem: ExactJSON = .object(["path": .string(""), "code": .string("not_utf8"), "detail": .string("")])
            return PluginPackageCheck(report: .object(["ok": .bool(false), "problems": .array([problem]), "words": .array([])]), text: "", pictures: .object([:]))
        }
        let started = try Self.call(input)
        guard started["outcome"].string == "ok" else {
            return PluginPackageCheck(report: .object(["ok": .bool(false), "problems": started["problems"], "words": .array([])]), text: "", pictures: .object([:]))
        }
        let imported = (started["imported"].array ?? []).map {
            ImportedMacroDefinition(definition: $0["definition"], summary: $0["summary"].string ?? "")
        }
        let temp = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plugin-check-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temp) }
        let database = try InkuDatabase(url: temp.appendingPathComponent("works.sqlite"))
        let host = PipelineHost(database: database, transport: PluginExampleNoProvider())
        var drawings: [ExactJSON] = []
        for example in started["draw"].array ?? [] {
            let id = example["id"].string ?? ""
            do {
                var request = try bootstrap.request(inputMode: "ddl", source: example["ddl"].string ?? "", description: "",
                    language: example["language"].string ?? "ja", catalogID: "default", canvasID: "square", seed: "1", wild: false,
                    settings: .init(), importedPlugins: imported, compositionSeed: "1")
                request.saveHistory = false; request.declareCanvas = false
                let view = try await host.generate(request)
                let delivery = try view.deliveryJSON.map { try ExactJSON(data: $0) } ?? .null
                let reasons = ["upstream_diagnostics", "downstream_diagnostics"].flatMap {
                    (delivery[$0].array ?? []).compactMap { $0["reason"].string }.filter { !$0.isEmpty }
                }
                let score = try view.scoreJSON.map { try ExactJSON(data: $0) } ?? .null
                let marks = score["instructions"].array?.count ?? 0
                let stopped = reasons.isEmpty && view.svg == nil ? ["example_not_drawn"] : reasons
                drawings.append(.object(["id": .string(id), "svg": .string(view.svg ?? ""), "marks": .integer(marks),
                                         "reasons": .array(stopped.map(ExactJSON.string))]))
            } catch {
                let reason = (error as? HostError)?.code ?? "example_not_drawn"
                drawings.append(.object(["id": .string(id), "svg": .string(""), "marks": .integer(0), "reasons": .array([.string(reason)])]))
            }
        }
        let finished = try Self.call(.object(["action": .string("check_finish"), "state": started["state"], "drawings": .array(drawings)]))
        var report = finished["report"]
        let id = report["id"].string ?? ""
        report["exists"] = .bool(installed.contains { $0.id == id })
        return PluginPackageCheck(report: report, text: finished["text"].string ?? "", pictures: finished["pictures"],
            previewKeys: (started["state"]["package"]["words"].array ?? []).map { $0["preview_key"].string ?? "" })
    }

    func install(_ check: PluginPackageCheck, replace: Bool) throws {
        guard check.ok, let id = check.id, Self.safeID(id), !check.text.isEmpty else { throw HostError("plugin_package_invalid") }
        let manager = FileManager.default
        try manager.createDirectory(at: directory, withIntermediateDirectories: true)
        let target = directory.appendingPathComponent(id, isDirectory: true)
        if manager.fileExists(atPath: target.path), !replace { throw HostError("plugin_package_exists") }
        let stage = directory.appendingPathComponent(".staging-" + UUID().uuidString, isDirectory: true)
        let backup = directory.appendingPathComponent(".backup-" + UUID().uuidString, isDirectory: true)
        try manager.createDirectory(at: stage.appendingPathComponent("previews"), withIntermediateDirectories: true)
        defer { try? manager.removeItem(at: stage) }
        try Data(check.text.utf8).write(to: stage.appendingPathComponent("package.json"), options: .atomic)
        for (key, picture) in check.pictures.object ?? [:] {
            guard key.range(of: #"^[0-9a-f]{16}$"#, options: .regularExpression) != nil,
                  let one = picture["png"].string.flatMap({ Data(base64Encoded: $0) }),
                  let two = picture["png_2x"].string.flatMap({ Data(base64Encoded: $0) }) else { throw HostError("plugin_package_picture_invalid") }
            try one.write(to: stage.appendingPathComponent("previews/\(key).png"), options: .atomic)
            try two.write(to: stage.appendingPathComponent("previews/\(key)@2x.png"), options: .atomic)
        }
        let oldCustom = target.appendingPathComponent("custom", isDirectory: true)
        if let oldFiles = try? manager.contentsOfDirectory(at: oldCustom, includingPropertiesForKeys: [.isRegularFileKey], options: [.skipsHiddenFiles]) {
            let keys = Set(check.previewKeys)
            for file in oldFiles where (try? file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true {
                let key = file.lastPathComponent.components(separatedBy: "@").first?.replacingOccurrences(of: ".png", with: "") ?? ""
                guard keys.contains(key) else { continue }
                let custom = stage.appendingPathComponent("custom", isDirectory: true)
                try manager.createDirectory(at: custom, withIntermediateDirectories: true)
                try manager.copyItem(at: file, to: custom.appendingPathComponent(file.lastPathComponent))
            }
        }
        let existed = manager.fileExists(atPath: target.path)
        if existed { try manager.moveItem(at: target, to: backup) }
        do { try manager.moveItem(at: stage, to: target) }
        catch { if existed { try? manager.moveItem(at: backup, to: target) }; throw error }
        if existed { try manager.removeItem(at: backup) }
    }
    func delete(_ id: String) throws {
        guard Self.safeID(id) else { throw HostError("invalid_package_id") }
        let target = directory.appendingPathComponent(id, isDirectory: true)
        guard FileManager.default.fileExists(atPath: target.path) else { throw HostError("plugin_package_not_found") }
        try FileManager.default.removeItem(at: target)
    }
}

private struct PluginExampleNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data { throw HostError("plugin_example_provider_forbidden") }
}
