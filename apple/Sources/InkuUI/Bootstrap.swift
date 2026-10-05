import Foundation
import CryptoKit
import InkuCore
import InkuHost

public struct ColorCatalogOption: Identifiable, Sendable {
    public let id: String
    public let name: String
    public let detail: String
    public let japaneseDetail: String?
    public let palette: [ColorCatalogSwatch]

    public func localizedDetail(language: String) -> String {
        language == "ja" ? japaneseDetail ?? detail : detail
    }
}

public struct ColorCatalogSwatch: Sendable {
    public let code: String
    public let name: String
    public let japaneseName: String?
}

public struct CanvasOption: Identifiable, Sendable {
    public let id: String
    public let name: String
    public let widthRatio: UInt32
    public let heightRatio: UInt32
    public let category: String
    public let intentJa: String
    public let intentEn: String
    public var label: String { name }

    public init(id: String, name: String, widthRatio: UInt32, heightRatio: UInt32,
                category: String = "Other", intentJa: String = "", intentEn: String = "") {
        self.id = id; self.name = name; self.widthRatio = widthRatio; self.heightRatio = heightRatio
        self.category = category; self.intentJa = intentJa; self.intentEn = intentEn
    }
}

public struct SaijikiWord: Identifiable, Sendable {
    public let id: String
    public let japanese: String
    public let english: String?
    public let detail: String
    public let isDefault: Bool
    public let englishDetail: String?
    public let preview: SaijikiPreview?
}

public struct SaijikiCategory: Identifiable, Sendable {
    public let id: String
    public let name: String
    public let words: [SaijikiWord]
    public let englishName: String?
}

public struct PluginWord: Identifiable, Sendable {
    public let id: String
    public let aliases: [String]
    public let japanese: [String]
    public let english: [String]
    public let note: String
    public let previewURL: URL?
    public let packageID: String?
    public let englishNote: String?
    public let firesOnJapanese: [String]
    public let firesOnEnglish: [String]

    public func displayName(language: String) -> String {
        (language == "ja" ? aliases.first : nil) ?? id
    }
}

struct Bootstrap {
    private let manifest: [String: Any]
    private let catalogRecords: [[String: Any]]
    private let registry: [String: Any]
    private let macroSources: [String: Any]
    let saijiki: [SaijikiCategory]
    let pluginWords: [PluginWord]
    let productReference: ProductReference
    let drawingLimitDefinition: DrawingLimitDefinition

    init() throws {
        func resource(_ name: String) throws -> Data {
            guard let url = Bundle.module.url(forResource: name, withExtension: "json") else {
                throw HostError("bundled_resources_unavailable")
            }
            return try Data(contentsOf: url)
        }
        manifest = try Self.object(resource("server-defaults"))
        let reference = try JSONDecoder().decode(ProductReference.self, from: resource("ui-reference"))
        productReference = reference
        guard reference.schema == "inku.apple-ui-reference.v1", let drawingLimits = manifest["drawing_limits"] else {
            throw HostError("installation_defaults_invalid")
        }
        drawingLimitDefinition = try JSONDecoder().decode(DrawingLimitDefinition.self, from: Self.bytes(drawingLimits))
        guard let records = try JSONSerialization.jsonObject(with: resource("color-catalogs")) as? [[String: Any]] else {
            throw HostError("color_catalogs_invalid")
        }
        catalogRecords = records
        registry = try Self.object(InkuCore.canvasRegistry)
        macroSources = try Self.object(resource("macro-sources"))
        let vocabulary = try Self.object(resource("saijiki"))
        guard vocabulary["asset_id"] as? String == "inku.saijiki.v2",
              let categories = vocabulary["categories"] as? [[String: Any]],
              let plugins = try JSONSerialization.jsonObject(with: resource("plugin-words")) as? [[String: Any]] else {
            throw HostError("bundled_vocabulary_invalid")
        }
        saijiki = try categories.map { category in
            guard let id = category["key"] as? String, let name = category["name_ja"] as? String,
                  let words = category["words"] as? [[String: Any]] else { throw HostError("bundled_vocabulary_invalid") }
            return SaijikiCategory(id: id, name: name, words: try words.filter { $0["display"] as? Bool == true }.map { word in
                guard let japanese = word["surface_ja"] as? String else { throw HostError("bundled_vocabulary_invalid") }
                let description = word["physical_description"] as? [String: String]
                return SaijikiWord(id: id + ":" + japanese, japanese: japanese,
                    english: word["surface_en"] as? String, detail: description?["ja"] ?? "",
                    isDefault: word["default"] as? Bool ?? false, englishDetail: description?["en"],
                    preview: reference.saijikiPreviews[id + ":" + japanese])
            }, englishName: category["name_en"] as? String)
        }
        pluginWords = try plugins.map { item in
            guard let id = item["id"] as? String, let surfaces = item["surfaces"] as? [String: [String]],
                  let notes = item["notes"] as? [String: String] else { throw HostError("bundled_plugins_invalid") }
            let preview = (item["preview"] as? String).flatMap {
                Bundle.module.url(forResource: $0, withExtension: nil, subdirectory: "plugin-previews")
            }
            return PluginWord(id: id, aliases: item["aliases"] as? [String] ?? [], japanese: surfaces["ja"] ?? [],
                english: surfaces["en"] ?? [], note: notes["ja"] ?? "", previewURL: preview, packageID: item["package_id"] as? String,
                englishNote: notes["en"], firesOnJapanese: (item["fires_on"] as? [String: [String]])?["ja"] ?? [],
                firesOnEnglish: (item["fires_on"] as? [String: [String]])?["en"] ?? [])
        }
    }

    var catalogs: [ColorCatalogOption] {
        catalogRecords.compactMap { item in
            guard let id = item["id"] as? String, let name = item["name"] as? String else { return nil }
            let palette = (item["palette"] as? [[String: Any]] ?? []).compactMap { color -> ColorCatalogSwatch? in
                guard let code = color["code"] as? String, let name = color["name"] as? String else { return nil }
                return ColorCatalogSwatch(code: code, name: name, japaneseName: color["name_ja"] as? String)
            }
            return ColorCatalogOption(id: id, name: name, detail: item["sub"] as? String ?? "",
                japaneseDetail: item["sub_ja"] as? String, palette: palette)
        }
    }

    var canvases: [CanvasOption] {
        guard let body = registry["registry"] as? [String: Any],
              let records = body["formats"] as? [[String: Any]] else { return [] }
        return records.compactMap { item in
            guard let id = item["id"] as? String, let width = item["width_units"] as? UInt32,
                  let height = item["height_units"] as? UInt32 else { return nil }
            let display = productReference.canvasMetadata[id]
            return CanvasOption(id: id, name: display?.label ?? id, widthRatio: width, heightRatio: height,
                                category: display?.category ?? "Other", intentJa: display?.intentJa ?? id,
                                intentEn: display?.intentEn ?? id)
        }
    }

    // Server color_catalogs.render_color_map_for_catalog uses the base map for
    // fallbacks and every named palette entry for seeded work-color assignment.
    // Keep names verbatim and later duplicate names authoritative, as on Server.
    private static func renderColorMap(for record: [String: Any]) throws -> [String: String] {
        guard var map = record["map"] as? [String: String],
              let palette = record["palette"] as? [[String: Any]] else {
            throw HostError("color_catalogs_invalid")
        }
        for color in palette {
            guard let name = color["name"] as? String, let code = color["code"] as? String else {
                throw HostError("color_catalogs_invalid")
            }
            map["palette:" + name] = code
        }
        return map
    }

    func request(inputMode: String, source: String, description: String, language: String,
                 catalogID: String, canvasID: String, seed: String, wild: Bool,
                 settings: HostSettings, parentWorkID: String? = nil, derivationKind: String = "new",
                 catalogMode: String = "fixed", sketch: SketchRequest = .off,
                 variationAmplitude: String? = nil, variationSeed: String? = nil,
                 savedConfiguration: Data? = nil, importedPlugins: [ImportedMacroDefinition] = [],
                 compositionSeed: String? = nil) throws -> GenerationRequest {
        guard derivationKind != "variation", variationAmplitude == nil, variationSeed == nil else {
            throw HostError("variation_retired")
        }
        let selectedID: String
        if catalogMode == "random" {
            guard let option = catalogs.filter({ $0.id != catalogID }).randomElement() else { throw HostError("catalog_selection_unavailable") }
            selectedID = option.id
        } else { selectedID = catalogID }
        let saved = try savedConfiguration.map(Self.object)
        guard ["en", "ja"].contains(language),
              ["fixed", "auto", "random"].contains(catalogMode),
              let record = catalogRecords.first(where: { $0["id"] as? String == selectedID }),
              let canvas = canvases.first(where: { $0.id == canvasID }),
              let originalPipeline = saved ?? manifest["pipeline"] as? [String: Any],
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
        let colorMap = try Self.renderColorMap(for: record)
        let actualSeed = seed.isEmpty ? String(UInt64.random(in: 0...((UInt64(1) << 53) - 1))) : seed
        guard let parsedSeed = UInt64(actualSeed), String(parsedSeed) == actualSeed else { throw HostError("invalid_seed") }
        if let compositionSeed {
            guard let parsed = UInt64(compositionSeed), String(parsed) == compositionSeed else { throw HostError("invalid_composition_seed") }
        }
        var config = originalPipeline
        var compiler = originalCompiler
        var host = originalHost
        host["canvas_format_id"] = canvasID
        host["canvas_format_registry_id"] = registryBody["schema"]
        host["canvas_format_registry_digest"] = registry["digest"]
        host["resolved_catalog_id"] = selectedID
        host["catalog_mode"] = selectedID == "default" ? "default" : "explicit"
        host["palette"] = try Self.object(InkuCore.resolvePalette(Self.bytes([
            "color_map": colorMap, "catalog_id": selectedID, "render_seed": actualSeed,
            "background": host["background"] ?? "white",
        ])))
        compiler["host"] = host
        compiler["composition_seed"] = compositionSeed.map { $0 as Any } ?? NSNull()
        if saved == nil, let selectedLimits = settings.operationalLimits {
            let bounds = try operationalLimitDefaults()
            guard selectedLimits.allSatisfy({ key, value in bounds[key].map { value <= $0 } ?? false }) else { throw HostError("invalid_operational_limits") }
            var budget = originalCompiler["operational_resource_budget"] as? [String: Any] ?? [:]
            var maximum = budget["maximum"] as? [String: Any] ?? [:]
            for (key, value) in selectedLimits { maximum[key] = value }
            budget["maximum"] = maximum
            compiler["operational_resource_budget"] = budget
        }
        if saved == nil {
            let limits = drawingLimitDefinition.normalized(settings.drawingLimits ?? [:])
            var hardPolicy = compiler["hard_resource_policy"] as? [String: Any] ?? [:]
            var hardBudget = hardPolicy["budget"] as? [String: Any] ?? [:]
            var hardMaximum = hardBudget["maximum"] as? [String: Any] ?? [:]
            var operational = compiler["operational_resource_budget"] as? [String: Any] ?? [:]
            var operationalMaximum = operational["maximum"] as? [String: Any] ?? [:]
            for (field, setting) in drawingLimitDefinition.budgetMapping {
                hardMaximum[field] = limits[setting]
                operationalMaximum[field] = limits[setting]
            }
            hardBudget["maximum"] = hardMaximum
            hardPolicy["budget"] = hardBudget
            let digest = SHA256.hash(data: try JSONSerialization.data(withJSONObject: hardBudget, options: [.sortedKeys, .withoutEscapingSlashes]))
            hardPolicy["identity"] = "host-settings:" + digest.map { String(format: "%02x", $0) }.joined()
            operational["maximum"] = operationalMaximum
            compiler["hard_resource_policy"] = hardPolicy
            compiler["operational_resource_budget"] = operational
        }
        compiler.removeValue(forKey: "stage15_variation")
        config["language"] = language
        config["compiler"] = compiler
        let exactCatalog = saved == nil ? try macroCatalogValue(language: language, settings: settings, importedPlugins: importedPlugins) : nil
        config["catalogs"] = [] as [Any]
        if catalogMode == "auto" {
            config["catalogs"] = try catalogRecords.map { record in
                guard let id = record["id"] as? String,
                      let name = record["name"] as? String else { throw HostError("color_catalogs_invalid") }
                let map = try Self.renderColorMap(for: record)
                var resolved = host
                resolved["resolved_catalog_id"] = id
                resolved["catalog_mode"] = id == "default" ? "default" : "explicit"
                resolved["palette"] = try Self.object(InkuCore.resolvePalette(Self.bytes([
                    "color_map": map, "catalog_id": id, "render_seed": actualSeed, "background": host["background"] ?? "white",
                ])))
                return ["prompt": ["catalog_id": id, "label": name,
                                    "description": record[language == "ja" ? "sub_ja" : "sub"] ?? ""], "resolved": resolved]
            }
        }
        let height = baseWidth * Double(canvas.heightRatio) / Double(canvas.widthRatio)
        let options: [String: Any] = [
            "resolved_color_map": colorMap, "catalog_id": selectedID,
            "canvas": ["width": baseWidth, "height": height],
            "canvas_aspect_id": canvasID, "svg_profile": "display",
            "render_seed": actualSeed, "composition_seed": compositionSeed.map { $0 as Any } ?? NSNull(),
            "wild": wild, "error_policy": compiler["error_policy"] ?? "omit_and_continue",
        ]
        let authoring: GenerationAuthoring = inputMode == "ddl"
            ? .directDDL(source) : .description(description, autoCatalog: catalogMode == "auto", sketch: sketch)
        let colorMaps = try Dictionary(uniqueKeysWithValues: catalogRecords.map { item -> (String, Data) in
            guard let id = item["id"] as? String else { throw HostError("color_catalogs_invalid") }
            let map = try Self.renderColorMap(for: item)
            return (id, try Self.bytes(map))
        })
        var exactConfiguration = try ExactJSON(data: Self.bytes(config))
        if let entries = exactCatalog?["entries"].array {
            exactConfiguration["definitions"] = .array(entries.map { $0["definition"] })
            exactConfiguration["macro_summaries"] = .array(entries.map { $0["summary"] })
        }
        return GenerationRequest(authoring: authoring, configuration: exactConfiguration.data,
            renderOptions: try Self.bytes(options), clipPolicy: try Self.bytes(clip),
            models: settings.models, providers: settings.providers, renderColorMaps: colorMaps,
            description: description, parentWorkID: parentWorkID,
            derivationKind: derivationKind,
            disabledPluginNames: pluginWords.filter {
                $0.packageID.map { settings.plugins?.disabledPackageIDs.contains($0) == true } ?? false
            }.flatMap { [$0.id] + $0.aliases },
            provenance: GenerationProvenance(ddlVersion: productReference.versions["ddlSpec"],
                ddlEngineVersion: productReference.versions["ddlEngine"],
                build: Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String,
                referenceBuild: productReference.build))
    }

    func macroCatalog(language: String, settings: HostSettings = .init(), importedPlugins: [ImportedMacroDefinition] = []) throws -> [String: Any] {
        try Self.object(macroCatalogValue(language: language, settings: settings, importedPlugins: importedPlugins).data)
    }

    func macroCatalogValue(language: String, settings: HostSettings = .init(), importedPlugins: [ImportedMacroDefinition] = []) throws -> ExactJSON {
        var request = macroSources
        request["language"] = language
        let disabled = settings.plugins?.disabledPackageIDs ?? []
        request["bundled_packages"] = (macroSources["bundled_packages"] as? [String] ?? []).filter { !disabled.contains($0) }
        request["legacy"] = (macroSources["legacy"] as? [[String: Any]] ?? []).filter {
            guard let source = $0["source_id"] as? String, source.hasPrefix("bundled:") else { return true }
            return !disabled.contains(String(source.dropFirst("bundled:".count)))
        }
        var exact = try ExactJSON(data: Self.bytes(request))
        exact["canonical"] = .array(importedPlugins.enumerated().map { $0.element.canonicalCandidate(index: $0.offset) } + (exact["canonical"].array ?? []))
        let output = try ExactJSON(data: InkuCore.resolveMacroCatalog(exact.data))
        guard output["schema"].string == "inku.macro-catalog-resolution.v1", output["error"] == .null else {
            throw HostError(output["error"].string ?? "macro_catalog_invalid")
        }
        let diagnostics = output["diagnostics"].array ?? []
        guard !diagnostics.contains(where: { $0["reason"].string == "catalog_entry_limit" || $0["source_id"].string?.hasPrefix("imported:") == true && $0["disposition"].string == "omitted" }) else {
            throw HostError("imported_macro_catalog_incomplete")
        }
        return output
    }

    func operationalLimitDefaults() throws -> [String: UInt32] {
        guard let pipeline = manifest["pipeline"] as? [String: Any], let compiler = pipeline["compiler"] as? [String: Any],
              let policy = compiler["hard_resource_policy"] as? [String: Any], let budget = policy["budget"] as? [String: Any],
              let maximum = budget["maximum"] as? [String: UInt32] else { throw HostError("installation_defaults_invalid") }
        return maximum
    }

    func replayOptions(catalogID: String, canvasID: String) throws -> ReplayOptions {
        guard let record = catalogRecords.first(where: { $0["id"] as? String == catalogID }),
              let canvas = canvases.first(where: { $0.id == canvasID }) else {
            throw HostError("replay_options_invalid")
        }
        let map = try Self.renderColorMap(for: record)
        return ReplayOptions(catalogID: catalogID, colorMap: try Self.bytes(map), canvasID: canvasID,
            widthRatio: canvas.widthRatio, heightRatio: canvas.heightRatio)
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
