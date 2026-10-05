import CoreGraphics
import Foundation
import ImageIO
import InkuHost
import InkuPersistence
import UniformTypeIdentifiers

/// One immutable saved-work snapshot, including its saved plugin definitions.
public struct ExportSource: Sendable {
    public let work: SavedWork
    public let profiles: [String: String]
    public let pluginDefinitions: [ExactJSON]
    public let pluginSummaries: [String]
    public let language: String

    public init(work: SavedWork, profiles: [String: String] = [:], pluginDefinitions: [ExactJSON] = [], pluginSummaries: [String] = [], language: String? = nil) {
        self.work = work; self.profiles = profiles
        self.pluginDefinitions = pluginDefinitions; self.pluginSummaries = pluginSummaries
        self.language = work.instructionLangResolved ?? language ?? "ja"
    }

    public func svg(profile: String) throws -> String {
        if profile == "canonical" { return work.svg }
        if profile == "display" {
            guard let opening = work.svg.range(of: "(<svg[^>]*>)", options: .regularExpression) else { return work.svg }
            let description = (work.sourceText ?? work.input)
                .replacingOccurrences(of: "&", with: "&amp;")
                .replacingOccurrences(of: "<", with: "&lt;")
                .replacingOccurrences(of: ">", with: "&gt;")
                .replacingOccurrences(of: "\"", with: "&quot;")
            var svg = work.svg
            svg.insert(contentsOf: "<desc>" + description + "</desc>", at: opening.upperBound)
            return svg
        }
        guard let svg = profiles[profile], !svg.isEmpty else { throw ExportFailure("保存時の条件から \(profile) SVG を準備できませんでした。") }
        return svg
    }
}

public enum SavedExportFormat: String, CaseIterable, Codable, Sendable {
    case svg, png, ddl, shareCard, reviewSheet, aiSheet, apng, gif
    public var title: String {
        switch self {
        case .svg: "SVG"
        case .png: "PNG"
        case .ddl: "DDL（プラグイン定義付き）"
        case .shareCard: "共有カード"
        case .reviewSheet: "コンタクトシート（閲覧用）"
        case .aiSheet: "コンタクトシート（AI用・説明付き）"
        case .apng: "APNGアニメーション"
        case .gif: "GIFアニメーション"
        }
    }
    public var fileExtension: String {
        switch self { case .svg: "svg"; case .ddl: "json"; case .gif: "gif"; default: "png" }
    }
}

public struct ExportOptions: Codable, Sendable, Equatable {
    public var format: SavedExportFormat = .png
    public var svgProfile = "display"
    public var pixelHeight = 1080
    public var pngAlphaWhite = false
    public var cardLayout = "square"
    public var cardSeal = true
    public var transition = "crossfade"
    public var holdSeconds = 1.5
    public var layerFrameCount = 12
    public var layerIntervalSeconds = 0.3
    public var layerReplay = "restart"
    public var title = "inku"
    public var subtitle = ""
    public init() {}

    enum CodingKeys: String, CodingKey {
        case format, svgProfile, pixelHeight, pngAlphaWhite, cardLayout, cardSeal, transition, holdSeconds
        case layerFrameCount, layerIntervalSeconds, layerReplay, title, subtitle
    }
    public init(from decoder: Decoder) throws {
        self.init()
        let values = try decoder.container(keyedBy: CodingKeys.self)
        format = (try values.decodeIfPresent(String.self, forKey: .format)).flatMap(SavedExportFormat.init(rawValue:)) ?? format
        svgProfile = try values.decodeIfPresent(String.self, forKey: .svgProfile) ?? svgProfile
        pixelHeight = try values.decodeIfPresent(Int.self, forKey: .pixelHeight) ?? pixelHeight
        pngAlphaWhite = try values.decodeIfPresent(Bool.self, forKey: .pngAlphaWhite) ?? pngAlphaWhite
        cardLayout = try values.decodeIfPresent(String.self, forKey: .cardLayout) ?? cardLayout
        cardSeal = try values.decodeIfPresent(Bool.self, forKey: .cardSeal) ?? cardSeal
        transition = try values.decodeIfPresent(String.self, forKey: .transition) ?? transition
        holdSeconds = try values.decodeIfPresent(Double.self, forKey: .holdSeconds) ?? holdSeconds
        layerFrameCount = try values.decodeIfPresent(Int.self, forKey: .layerFrameCount) ?? layerFrameCount
        layerIntervalSeconds = try values.decodeIfPresent(Double.self, forKey: .layerIntervalSeconds) ?? layerIntervalSeconds
        layerReplay = try values.decodeIfPresent(String.self, forKey: .layerReplay) ?? layerReplay
        title = try values.decodeIfPresent(String.self, forKey: .title) ?? title
        subtitle = try values.decodeIfPresent(String.self, forKey: .subtitle) ?? subtitle
        self = normalized()
    }

    public func normalized() -> Self {
        var value = self
        if !["display", "editable", "compat", "live"].contains(value.svgProfile) { value.svgProfile = "display" }
        value.pixelHeight = min(12000, max(64, value.pixelHeight))
        if !["square", "portrait"].contains(value.cardLayout) { value.cardLayout = "square" }
        if !["cut", "crossfade", "fade_white", "slide"].contains(value.transition) { value.transition = "crossfade" }
        if !["restart", "reverse", "once"].contains(value.layerReplay) { value.layerReplay = "restart" }
        value.holdSeconds = value.holdSeconds.isFinite ? min(30, max(0.1, value.holdSeconds)) : 1.5
        value.layerIntervalSeconds = value.layerIntervalSeconds.isFinite ? min(30, max(0.1, value.layerIntervalSeconds)) : 0.3
        value.layerFrameCount = min(120, max(2, value.layerFrameCount))
        return value
    }
}

public struct ExportArtifact: Sendable {
    public let name: String
    public let data: Data
    public init(name: String, data: Data) { self.name = name; self.data = data }
}

public struct ExportFailure: LocalizedError, Sendable {
    public let message: String
    public var errorDescription: String? { message }
    public init(_ message: String) { self.message = message }
}

public enum ExportService {
    public static let maximumImagePixels = 144_000_000
    public static let maximumAnimationPixels = 600_000_000

    /// Cancellation follows the detached worker; no database or provider is read.
    public static func prepare(sources: [ExportSource], options: ExportOptions) async throws -> [ExportArtifact] {
        try Task.checkCancellation()
        let worker = Task.detached(priority: .userInitiated) { try render(sources: sources, options: options) }
        return try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
    }

    public static func render(sources: [ExportSource], options: ExportOptions) throws -> [ExportArtifact] {
        try Task.checkCancellation()
        try validate(sources: sources, options: options)
        switch options.format {
        case .apng, .gif:
            return [ExportArtifact(name: "inku-animation.\(options.format.fileExtension)", data: try AnimationEncoder.encode(sources: sources, options: options))]
        case .reviewSheet, .aiSheet:
            return try ExportSheets.build(sources: sources, options: options)
        default:
            return try sources.map { source in
                try Task.checkCancellation()
                let prefix = "inku-" + safeName(source.work.id)
                let data: Data
                switch options.format {
                case .svg: data = Data(try source.svg(profile: options.svgProfile).utf8)
                case .png:
                    let image = try ExportRaster.image(svg: source.work.svg, height: options.pixelHeight)
                    // The work's own generation time, not the export time, as Web's downloadPNG stamps it.
                    data = PNGCaptureDate.stamp(try png(options.pngAlphaWhite ? ExportRaster.onWhite(image) : image),
                                                date: Date(timeIntervalSince1970: Double(source.work.at) / 1000))
                case .ddl: data = try ddl(source)
                case .shareCard: data = try png(ExportSheets.card(source: source, options: options))
                default: throw ExportFailure("この形式を単独の作品として書き出せません。")
                }
                return ExportArtifact(name: prefix + "." + options.format.fileExtension, data: data)
            }
        }
    }

    public static func validate(sources: [ExportSource], options: ExportOptions) throws {
        guard !sources.isEmpty, sources.count <= 1000 else { throw ExportFailure("1〜1000作品を選択してください。") }
        var ids = Set<String>()
        for source in sources {
            try Task.checkCancellation()
            guard !source.work.id.isEmpty, !source.work.trashed, ids.insert(source.work.id).inserted else { throw ExportFailure("書き出し対象に重複・削除済み・不明な作品があります。") }
            _ = try SVGDocument(source.work.svg)
            _ = try ExactJSON(data: Data(source.work.score.utf8))
        }
        guard (64...12000).contains(options.pixelHeight) else { throw ExportFailure("Y軸は64〜12000pxで指定してください。") }
        if options.format == .svg {
            guard ["canonical", "display", "editable", "compat", "live"].contains(options.svgProfile) else { throw ExportFailure("SVGプロファイルが不明です。") }
        }
        if options.format == .shareCard, !["square", "portrait"].contains(options.cardLayout) { throw ExportFailure("共有カードの用紙が不明です。") }
        if options.format == .apng || options.format == .gif {
            guard ["cut", "crossfade", "fade_white", "slide"].contains(options.transition),
                  ["restart", "reverse", "once"].contains(options.layerReplay),
                  (2...120).contains(options.layerFrameCount),
                  options.holdSeconds.isFinite, (0.1...30).contains(options.holdSeconds),
                  options.layerIntervalSeconds.isFinite, (0.1...30).contains(options.layerIntervalSeconds) else {
                throw ExportFailure("アニメーションのフレーム数・間隔・再生方式を確認してください。")
            }
        }
    }

    /// The app's CFBundleVersion, standing where Server writes its web/BUILD_NUMBER; null when the bundle has none.
    public static var applicationBuildNumber: String? {
        (Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.flatMap { $0.isEmpty ? nil : $0 }
    }

    /// Server ddl_export.build_ddl_export: a definition without a string namespace and heading is skipped.
    public static func ddl(_ source: ExportSource, buildNumber: String? = applicationBuildNumber) throws -> Data {
        guard let text = source.work.ddl, DDLSource.hasBody(text) else { throw ExportFailure("この保存作品には書き出せるDDLがありません。") }
        var plugins: [ExactJSON] = []; var seen = Set<String>()
        for (index, definition) in source.pluginDefinitions.enumerated() {
            guard let namespace = definition["namespace"].string, let heading = definition["heading"].string else { continue }
            let name = namespace + "." + heading
            let visible = [name] + (definition["aliases"].array ?? []).compactMap { $0.string.map { namespace + "." + $0 } }
            if !seen.contains(name), visible.contains(where: text.contains) {
                seen.insert(name)
                plugins.append(.object(["definition": definition, "summary": .string(index < source.pluginSummaries.count ? source.pluginSummaries[index] : "")]))
            }
        }
        return ExactJSON.object([
            "schema": .string("inku.ddl-export.v1"), "language": .string(source.language),
            "ddl": .string(text), "plugins": .array(plugins),
            "exported_from": .object(["build_number": .optional(buildNumber), "render_engine_version": .optional(source.work.renderEngineVersion)])
        ]).data
    }

    static func png(_ image: CGImage) throws -> Data {
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil) else { throw ExportFailure("PNGエンコーダーを準備できませんでした。") }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else { throw ExportFailure("PNGを書き出せませんでした。") }
        return data as Data
    }

    static func safeName(_ name: String) -> String {
        String(name.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) || "-_.".unicodeScalars.contains($0) ? Character(String($0)) : "_" }.prefix(120))
    }
}
