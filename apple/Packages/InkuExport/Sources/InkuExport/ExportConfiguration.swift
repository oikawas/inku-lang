import Foundation

/// Local UI defaults are separate from saved artwork and captured export options.
public struct ExportConfiguration: Codable, Sendable, Equatable {
    public var options: ExportOptions
    public var resolution: Int
    public var customHeight: Int
    public var destinationBookmark: Data?
    public var destinationName: String?
    public init(options: ExportOptions = .init(), resolution: Int = 1080, customHeight: Int = 720) {
        self.options = options; self.resolution = resolution; self.customHeight = customHeight
    }
    enum CodingKeys: String, CodingKey { case options, resolution, customHeight, destinationBookmark, destinationName }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        self.init(options: try values.decodeIfPresent(ExportOptions.self, forKey: .options) ?? .init(),
                  resolution: try values.decodeIfPresent(Int.self, forKey: .resolution) ?? 1080,
                  customHeight: try values.decodeIfPresent(Int.self, forKey: .customHeight) ?? 720)
        destinationBookmark = try values.decodeIfPresent(Data.self, forKey: .destinationBookmark)
        destinationName = try values.decodeIfPresent(String.self, forKey: .destinationName)
        self = normalized()
    }
    public func normalized() -> Self {
        var value = self
        value.options = value.options.normalized()
        if value.resolution != 0, !(64...12000).contains(value.resolution) { value.resolution = 1080 }
        value.customHeight = min(12000, max(64, value.customHeight))
        value.options.pixelHeight = value.resolution == 0 ? value.customHeight : value.resolution
        if (value.destinationBookmark?.count ?? 0) > 65_536 { value.destinationBookmark = nil; value.destinationName = nil }
        return value
    }
}

public struct ExportTemplate: Codable, Sendable, Equatable, Identifiable {
    public var id: String
    public var name: String
    public var description: String
    public var pixelHeight: Int
    public init(id: String = UUID().uuidString, name: String = "PNG", description: String = "", pixelHeight: Int = 1080) {
        self.id = id; self.name = name; self.description = description; self.pixelHeight = pixelHeight
    }
    enum CodingKeys: String, CodingKey { case id, name, description; case pixelHeight = "y_px" }
    public static var defaults: [Self] {
        [1080, 2160, 4320].map { Self(id: "png-\($0)", name: "PNG \($0)px", description: "PNG / Y軸 \($0)px", pixelHeight: $0) }
    }
    public static func normalized(_ templates: [Self]?) -> [Self] {
        guard let templates else { return defaults }
        if templates.count == 2, templates[0].id == "png-1024", templates[0].pixelHeight == 1024,
           templates[1].id == "png-2048", templates[1].pixelHeight == 2048 { return defaults }
        var result: [Self] = []; var seen = Set<String>()
        for var template in templates {
            guard (64...12000).contains(template.pixelHeight) else { continue }
            template.id = String(template.id.trimmingCharacters(in: .whitespacesAndNewlines).prefix(80))
            if template.id.isEmpty { template.id = UUID().uuidString }
            guard seen.insert(template.id).inserted else { continue }
            template.name = String(template.name.trimmingCharacters(in: .whitespacesAndNewlines).prefix(80))
            if template.name.isEmpty { template.name = "PNG" }
            template.description = String(template.description.trimmingCharacters(in: .whitespacesAndNewlines).prefix(240))
            result.append(template)
            if result.count == 20 { break }
        }
        return result.isEmpty ? defaults : result
    }
}
