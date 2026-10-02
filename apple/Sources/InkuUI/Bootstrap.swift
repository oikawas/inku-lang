import Foundation
import InkuCore
import InkuHost

public struct ColorCatalogOption: Identifiable, Sendable {
    public let id: String
    public let name: String
}

public struct CanvasOption: Identifiable, Sendable {
    public let id: String
    public let name: String
    public let widthRatio: UInt32
    public let heightRatio: UInt32
}

struct Bootstrap {
    private let manifest: [String: Any]
    private let catalogRecords: [[String: Any]]
    private let registry: [String: Any]

    init() throws {
        func resource(_ name: String) throws -> Data {
            guard let url = Bundle.module.url(forResource: name, withExtension: "json") else {
                throw HostError("bundled_resources_unavailable")
            }
            return try Data(contentsOf: url)
        }
        manifest = try Self.object(resource("server-defaults"))
        guard let records = try JSONSerialization.jsonObject(with: resource("color-catalogs")) as? [[String: Any]] else {
            throw HostError("color_catalogs_invalid")
        }
        catalogRecords = records
        registry = try Self.object(InkuCore.canvasRegistry)
    }

    var catalogs: [ColorCatalogOption] {
        catalogRecords.compactMap { item in
            guard let id = item["id"] as? String, let name = item["name"] as? String else { return nil }
            return ColorCatalogOption(id: id, name: name)
        }
    }

    var canvases: [CanvasOption] {
        guard let body = registry["registry"] as? [String: Any],
              let records = body["formats"] as? [[String: Any]] else { return [] }
        return records.compactMap { item in
            guard let id = item["id"] as? String, let width = item["width_units"] as? UInt32,
                  let height = item["height_units"] as? UInt32 else { return nil }
            return CanvasOption(id: id, name: id, widthRatio: width, heightRatio: height)
        }
    }

    func request(inputMode: String, source: String, description: String, language: String,
                 catalogID: String, canvasID: String, seed: String, wild: Bool,
                 settings: HostSettings, parentWorkID: String? = nil) throws -> GenerationRequest {
        guard ["en", "ja"].contains(language),
              let record = catalogRecords.first(where: { $0["id"] as? String == catalogID }),
              let colorMap = record["map"] as? [String: String],
              let canvas = canvases.first(where: { $0.id == canvasID }),
              let originalPipeline = manifest["pipeline"] as? [String: Any],
              let originalCompiler = originalPipeline["compiler"] as? [String: Any],
              let originalHost = originalCompiler["host"] as? [String: Any],
              let render = manifest["render"] as? [String: Any],
              let defaults = render["options"] as? [String: Any],
              let base = defaults["canvas"] as? [String: Any],
              let baseWidth = base["width"] as? Double,
              let clip = render["clip"] as? [String: Any],
              let registryBody = registry["registry"] as? [String: Any] else {
            throw HostError("installation_defaults_invalid")
        }
        let actualSeed = seed.isEmpty ? String(UInt64.random(in: 0...((UInt64(1) << 53) - 1))) : seed
        guard let parsedSeed = UInt64(actualSeed), String(parsedSeed) == actualSeed else { throw HostError("invalid_seed") }
        var config = originalPipeline
        var compiler = originalCompiler
        var host = originalHost
        host["canvas_format_id"] = canvasID
        host["canvas_format_registry_id"] = registryBody["schema"]
        host["canvas_format_registry_digest"] = registry["digest"]
        host["resolved_catalog_id"] = catalogID
        host["catalog_mode"] = catalogID == "default" ? "default" : "explicit"
        host["palette"] = try Self.object(InkuCore.resolvePalette(Self.bytes([
            "color_map": colorMap, "catalog_id": catalogID, "render_seed": actualSeed,
            "background": host["background"] ?? "white",
        ])))
        compiler["host"] = host
        compiler["composition_seed"] = actualSeed
        config["language"] = language
        config["compiler"] = compiler
        let height = baseWidth * Double(canvas.heightRatio) / Double(canvas.widthRatio)
        let options: [String: Any] = [
            "resolved_color_map": colorMap, "catalog_id": catalogID,
            "canvas": ["width": baseWidth, "height": height],
            "canvas_aspect_id": canvasID, "svg_profile": "display",
            "render_seed": actualSeed, "composition_seed": actualSeed,
            "wild": wild, "error_policy": compiler["error_policy"] ?? "omit_and_continue",
        ]
        let authoring: GenerationAuthoring = inputMode == "ddl"
            ? .directDDL(source) : .description(description, autoCatalog: false)
        let colorMaps = try Dictionary(uniqueKeysWithValues: catalogRecords.compactMap { item -> (String, Data)? in
            guard let id = item["id"] as? String, let map = item["map"] as? [String: String] else { return nil }
            return (id, try Self.bytes(map))
        })
        return GenerationRequest(authoring: authoring, configuration: try Self.bytes(config),
            renderOptions: try Self.bytes(options), clipPolicy: try Self.bytes(clip),
            models: settings.models, providers: settings.providers, renderColorMaps: colorMaps,
            description: description, parentWorkID: parentWorkID,
            derivationKind: parentWorkID == nil ? "new" : "ddl_edit")
    }

    static func object(_ data: Data) throws -> [String: Any] {
        guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw HostError("expected_json_object")
        }
        return value
    }
    static func bytes(_ value: Any) throws -> Data {
        guard JSONSerialization.isValidJSONObject(value) else { throw HostError("invalid_json_value") }
        return try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }
}
