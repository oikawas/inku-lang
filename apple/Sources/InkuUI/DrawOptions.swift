import Foundation
import InkuHost
import InkuPersistence

/// Per-input choices have the same shape as the core's draw_defaults.
public struct DrawOptions: Codable, Equatable, Sendable {
    public struct Catalog: Codable, Equatable, Sendable {
        public var id: String
        public var mode: String
    }
    public struct Models: Codable, Equatable, Sendable {
        public var stage1: String?
        public var stage2: String?
        public var vision: String?
    }
    public var route: String
    public var sketch: String
    public var composition: String
    public var wild: String
    public var catalog: Catalog
    public var canvasAspect: String
    public var models: Models

    enum CodingKeys: String, CodingKey {
        case route, sketch, composition, wild, catalog, models
        case canvasAspect = "canvas_aspect"
    }
}

/// Web INPUT_PANEL_ORDER, shared by the canvas strip and its ordering check.
enum DrawOptionPresentation {
    static let inputOrder = ["models", "catalog", "route", "sketch", "composition", "wild", "canvas_aspect"]
    static func keys(isImage: Bool) -> [String] {
        inputOrder.filter { !isImage || !["route", "sketch", "composition"].contains($0) }
    }
}

enum DrawOptionsCore {
    static let keys = (try! call("release_defaults"))["draw_options"] as! [String]
    static let release: [String: DrawOptions] = {
        let response = try! call("release_defaults")
        let release = response["release"] as! [String: Any]
        return try! decode([String: DrawOptions].self, release["tabs"])
    }()
    static func call(_ action: String, _ fields: [String: Any] = [:]) throws -> [String: Any] {
        try ProviderCoreSettings.call(action, fields)
    }

    static func decode<T: Decodable>(_ type: T.Type, _ value: Any?) throws -> T {
        guard let value else { throw HostError("draw_options_invalid") }
        return try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]))
    }

    static func object<T: Encodable>(_ value: T) throws -> Any {
        try JSONSerialization.jsonObject(with: JSONEncoder().encode(value))
    }

    static func providers(_ settings: HostSettings) -> [String: Any] {
        Dictionary(uniqueKeysWithValues: settings.providers.map { provider in
            (provider.id, ["models": (provider.models ?? []).map { ["id": $0.id] }])
        })
    }

    static func legacySettings(_ settings: HostSettings, preferences: DisplayPreferences) throws -> [String: Any] {
        var legacy: [String: Any] = [:]
        func putModel(_ value: String?, provider: String, model: String) {
            guard let value, let colon = value.firstIndex(of: ":"), colon != value.startIndex else { return }
            legacy[provider] = String(value[..<colon])
            legacy[model] = String(value[value.index(after: colon)...])
        }
        putModel(settings.models.stage1Model, provider: "stage1_provider", model: "stage1_model")
        putModel(preferences.visionModelReference, provider: "vision_provider", model: "vision_model")
        if preferences.nextCatalogMode == "auto" { legacy["color_catalog_id"] = "auto" }
        else if let id = preferences.nextCatalogID { legacy["color_catalog_id"] = id }
        if let defaults = preferences.drawDefaults { legacy["draw_defaults"] = try object(defaults) }
        return legacy
    }

    static func normalized(settings: HostSettings, preferences: DisplayPreferences, colorIDs: [String]) throws -> [String: DrawOptions] {
        let legacy = try legacySettings(settings, preferences: preferences)
        let response = try call("normalize_user", ["settings": legacy, "color_ids": colorIDs,
                                                    "providers": providers(settings)])
        return try decode([String: DrawOptions].self, (response["settings"] as? [String: Any])?["draw_defaults"])
    }

    static func update(_ defaults: [String: DrawOptions], settings: HostSettings,
                       preferences: DisplayPreferences, colorIDs: [String]) throws -> [String: DrawOptions] {
        let response = try call("update_user", ["settings": legacySettings(settings, preferences: preferences),
            "patch": ["draw_defaults": object(defaults)], "color_ids": colorIDs, "providers": providers(settings)])
        return try decode([String: DrawOptions].self, (response["settings"] as? [String: Any])?["draw_defaults"])
    }

    static func recorded(_ work: InkuPersistence.SavedWork, isImage: Bool) throws -> [String: Any] {
        var record: [String: Any] = [:]
        record["draw_route"] = work.drawRoute
        record["sketch_requested"] = work.sketchRequested
        record["composition_requested"] = work.compositionRequested
        record["catalog_mode"] = work.catalogMode
        record["render_color_catalog_id"] = work.renderColorCatalogID
        record["catalog_id"] = work.catalogID
        record["render_canvas_aspect_id"] = work.renderCanvasAspectID
        record["render_canvas_aspect"] = work.renderCanvasAspect
        record["stage1_model"] = work.stage1Model
        record["stage2_model"] = work.stage2Model
        if let wild = work.renderWild { record["render_wild"] = wild ? "1" : "0" }
        if isImage { record["image_ddl"] = [:] }
        let result = try call("options_of_work", ["record": record])
        guard let options = result["options"] as? [String: Any] else { throw HostError("draw_options_invalid") }
        return options
    }

    static func forRecorded(_ options: [String: Any], tab: String, defaults: [String: DrawOptions]) throws -> DrawOptions {
        let result = try call("options_for_recorded", ["options": options, "tab": tab, "defaults": object(defaults)])
        return try decode(DrawOptions.self, result["options"])
    }
}
