import Foundation
import InkuCore

public struct ImportedMacroDefinition: Sendable, Equatable {
    public let definition: ExactJSON
    public let summary: String
    public init(definition: ExactJSON, summary: String) { self.definition = definition; self.summary = summary }

    public var qualifiedName: String {
        (definition["namespace"].string ?? "") + "." + (definition["heading"].string ?? "")
    }
    /// The shared catalog reads definition JSON as a string, retaining UInt64 lexemes.
    public func canonicalCandidate(index: Int) -> ExactJSON {
        .object(["source_id": .string("imported:\(index)"), "definition_json": .string(definition.text),
                 "summary": .string(summary.isEmpty ? qualifiedName : summary)])
    }
}

/// A portable package is local to the next new work, never an installation.
public struct DDLPackageImport: Sendable, Equatable {
    public static let maximumBytes = 4 * 1024 * 1024
    public static let maximumPlugins = 64
    public let source: String
    public let language: String?
    public let plugins: [ImportedMacroDefinition]
    public var names: [String] { plugins.map(\.qualifiedName) }

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
        guard let file = try? ExactJSON(data: data), file["schema"].string == "inku.ddl-export.v1" else {
            return Self(source: text, language: nil, plugins: [])
        }
        guard let source = file["ddl"].string else { throw HostError("ddl_export_without_ddl") }
        let items = file["plugins"].array ?? []
        guard items.count <= maximumPlugins else { throw HostError("ddl_export_too_many_plugins") }
        let plugins = try items.map { item in
            guard item["definition"].object != nil else { throw HostError("ddl_export_invalid_plugin") }
            return ImportedMacroDefinition(definition: item["definition"], summary: item["summary"].string ?? "")
        }
        let language = file["language"].string.flatMap { ["ja", "en"].contains($0) ? $0 : nil }
        let value = Self(source: source, language: language, plugins: plugins)
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
