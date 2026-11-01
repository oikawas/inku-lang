import Foundation
import InkuCore

public struct ImportedMacroDefinition: Sendable, Equatable {
    public let definition: ExactJSON
    public let note: String
    public init(definition: ExactJSON, note: String) { self.definition = definition; self.note = note }

    /// The shared catalog reads definition JSON as a string, retaining UInt64 lexemes.
    public func canonicalCandidate(index: Int) -> ExactJSON {
        .object(["source_id": .string("imported:\(index)"), "definition_json": .string(definition.text),
                 "summary": .string(note)])
    }
}

/// A portable package is local to the next new work, never an installation.
public struct DDLPackageImport: Sendable, Equatable {
    public static let maximumBytes = 4 * 1024 * 1024
    public static let maximumPlugins = 64
    public let source: String
    public let language: String?
    public let plugins: [ImportedMacroDefinition]
    public let migratedEdits: Int?
    public var names: [String] {
        let resolvedLanguage = language ?? InkuCore.resolveInstructionLanguage(text: source, requested: "auto", fallback: "ja") ?? "ja"
        guard let catalog = try? resolveCatalog(language: resolvedLanguage) else { return [] }
        let locks = (catalog["locks"].array ?? []).map { value -> ExactJSON in
            var value = value
            if let digest = value["digest"].string, !digest.hasPrefix("sha256:") { value["digest"] = .string("sha256:" + digest) }
            return value
        }
        let request: ExactJSON = .object([
            "source": .string(source), "language": .string(resolvedLanguage),
            "definitions": .array(plugins.map(\.definition)),
            "summaries": .array(plugins.map { .string($0.note) }),
            "locks": .array(locks), "compiler": .null
        ])
        guard let answer = try? ExactJSON(data: InkuCore.pluginCalls(request.data)) else { return [] }
        return (answer["entries"].array ?? []).compactMap { $0[resolvedLanguage == "en" ? "written_en" : "written_ja"].string }
    }

    public static func read(url: URL) throws -> Self {
        try Task.checkCancellation()
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        // One extra byte detects oversize files without loading an unbounded document.
        var bytes = Data()
        while bytes.count <= maximumBytes {
            try Task.checkCancellation()
            let count = min(65_536, maximumBytes + 1 - bytes.count)
            guard let chunk = try file.read(upToCount: count), !chunk.isEmpty else { break }
            bytes.append(chunk)
        }
        return try parse(bytes)
    }

    public static func parse(_ data: Data) throws -> Self {
        try Task.checkCancellation()
        guard data.count <= maximumBytes else { throw HostError("ddl_import_too_large") }
        guard let text = String(data: data, encoding: .utf8) else { throw HostError("ddl_import_invalid_utf8") }
        guard let file = try? ExactJSON(data: data) else {
            return Self(source: text, language: nil, plugins: [], migratedEdits: nil)
        }
        if file["schema"].string == "inku.ddl-export.v1" { throw HostError("ddl_export_requires_v2") }
        guard file["schema"].string == "inku.ddl-export.v2" else {
            return Self(source: text, language: nil, plugins: [], migratedEdits: nil)
        }
        guard let source = file["ddl"].string else { throw HostError("ddl_export_without_ddl") }
        let items = file["plugins"].array ?? []
        guard items.count <= maximumPlugins else { throw HostError("ddl_export_too_many_plugins") }
        var plugins = try items.map { item in
            guard item["definition"].object != nil else { throw HostError("ddl_export_invalid_plugin") }
            return ImportedMacroDefinition(definition: item["definition"], note: item["note"].string ?? "")
        }
        let language = file["language"].string.flatMap { ["ja", "en"].contains($0) ? $0 : nil }
        var outputSource = source
        var migratedEdits: Int?
        if file.object?["saijiki"] == nil {
            let definitions = plugins.map(\.definition)
            let first = try ExactJSON(data: InkuCore.migrateSaijikiV2(ExactJSON.object(["definitions": .array(definitions)]).data))
            guard first["error"] == .null, let entries = first["definitions"].array,
                  entries.count == definitions.count else { throw HostError("ddl_export_invalid") }
            let locks: [ExactJSON] = try entries.map { entry in
                guard entry["error"] == .null, let name = entry["qualified_name"].string,
                      let version = entry["version"].string, let digest = entry["old_digest"].string else {
                    throw HostError("ddl_export_invalid")
                }
                return .object(["qualified_name": .string(name), "version": .string(version), "digest": .string(digest)])
            }
            let resolvedLanguage = language ?? InkuCore.resolveInstructionLanguage(text: source, requested: "auto", fallback: "ja") ?? "ja"
            let request: ExactJSON = .object(["definitions": .array(definitions), "document": .object([
                "source": .string(source), "language": .string(resolvedLanguage), "macro_locks": .array(locks),
                "saijiki": .string("inku.saijiki.v2")])])
            let result = try ExactJSON(data: InkuCore.migrateSaijikiV2(request.data))
            guard result["error"] == .null, result["document"]["error"] == .null,
                  let migratedSource = result["document"]["document"]["source"].string,
                  let edits = result["document"]["edits"].array, let entries = result["definitions"].array,
                  entries.count == plugins.count, entries.allSatisfy({ $0["error"] == .null && $0["definition"].object != nil }) else {
                throw HostError("ddl_export_invalid")
            }
            outputSource = migratedSource
            migratedEdits = edits.count
            plugins = zip(entries, plugins).map { ImportedMacroDefinition(definition: $0.0["definition"], note: $0.1.note) }
        } else if file["saijiki"].string != "inku.saijiki.v3" {
            throw HostError("ddl_export_invalid")
        }
        let value = Self(source: outputSource, language: language, plugins: plugins, migratedEdits: migratedEdits)
        // Reject the whole carried catalog on any omitted/invalid definition or duplicate name.
        let resolved = try value.resolveCatalog(language: language ?? "ja")
        try Task.checkCancellation()
        guard resolved["entries"].array?.count == plugins.count,
              (resolved["diagnostics"].array ?? []).allSatisfy({ $0["disposition"].string != "omitted" }) else {
            throw HostError("ddl_export_invalid_plugin")
        }
        return value
    }

    public var canonicalCandidates: [ExactJSON] { plugins.enumerated().map { $0.element.canonicalCandidate(index: $0.offset) } }
    public func resolveCatalog(language: String) throws -> ExactJSON {
        let request: ExactJSON = .object(["maximum_entries": .integer(Self.maximumPlugins), "language": .string(language),
            "canonical": .array(canonicalCandidates), "legacy": .array([]), "bundled_packages": .array([])])
        let result = try ExactJSON(data: InkuCore.resolveMacroCatalog(request.data))
        guard result["schema"].string == "inku.macro-catalog-resolution.v1", result["error"] == .null else {
            throw HostError(result["error"].string ?? "macro_catalog_invalid")
        }
        return result
    }
}
