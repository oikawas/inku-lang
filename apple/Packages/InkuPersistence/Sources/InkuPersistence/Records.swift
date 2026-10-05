import Foundation
import GRDB

/// Portable contract v2 facts. JSON documents and hashes remain opaque strings.
public struct SavedWork: Codable, Sendable, Equatable {
    public var id: String
    public var at: Int64
    public var input: String
    public var sourceText: String?
    public var ddl: String?
    public var ddlSourceOrigin: String?
    public var score: String
    public var svg: String
    public var elapsedMS: Int64?
    public var stage1Model: String?
    public var stage2Model: String?
    public var catalogID: String?
    public var renderEngineID: String?
    public var renderEngineVersion: String?
    public var renderColorCatalogID: String?
    public var renderColorCatalogName: String?
    public var renderColorCatalogSub: String?
    public var renderColorProfile: String?
    public var renderColorMap: String?
    public var renderCanvasAspect: String?
    public var renderCanvasAspectID: String?
    public var renderCanvasAspectRatio: Double?
    public var renderSeed: String?
    public var renderWild: Bool?
    public var compositionSeed: String?
    public var interpretationSeed: String?
    public var variationAmplitude: String?
    public var variationSeed: String?
    public var seedText: String?
    public var instructionLangRequested: String?
    public var instructionLangResolved: String?
    public var interpretFallback: String?
    public var composeFallback: String?
    public var sketchText: String?
    public var sketchGrain: String?
    public var sketchState: String?
    public var renderLimits: String?
    public var renderHash: String?
    public var descriptionHash: String?
    public var starred: Bool
    public var trashed: Bool
    public var historyVisibility: String
    public var lineageNodeID: String?

    /// The fallback is presentation-only and never changes the stored NULL.
    public var effectiveSourceText: String { sourceText ?? input }

    public init(
        id: String, at: Int64, input: String, score: String, svg: String,
        sourceText: String? = nil, ddl: String? = nil, ddlSourceOrigin: String? = nil,
        elapsedMS: Int64? = nil, stage1Model: String? = nil, stage2Model: String? = nil,
        catalogID: String? = nil, renderEngineID: String? = nil, renderEngineVersion: String? = nil,
        renderColorCatalogID: String? = nil, renderColorCatalogName: String? = nil,
        renderColorCatalogSub: String? = nil, renderColorProfile: String? = nil,
        renderColorMap: String? = nil, renderCanvasAspect: String? = nil,
        renderCanvasAspectID: String? = nil, renderCanvasAspectRatio: Double? = nil,
        renderSeed: String? = nil, renderWild: Bool? = nil, compositionSeed: String? = nil,
        interpretationSeed: String? = nil, variationAmplitude: String? = nil,
        variationSeed: String? = nil, seedText: String? = nil,
        instructionLangRequested: String? = nil, instructionLangResolved: String? = nil,
        interpretFallback: String? = nil, composeFallback: String? = nil,
        sketchText: String? = nil, sketchGrain: String? = nil, sketchState: String? = nil,
        renderLimits: String? = nil, renderHash: String? = nil, descriptionHash: String? = nil,
        starred: Bool = false, trashed: Bool = false, historyVisibility: String = "normal",
        lineageNodeID: String? = nil
    ) {
        self.id = id; self.at = at; self.input = input; self.score = score; self.svg = svg
        self.sourceText = sourceText; self.ddl = ddl; self.ddlSourceOrigin = ddlSourceOrigin
        self.elapsedMS = elapsedMS; self.stage1Model = stage1Model; self.stage2Model = stage2Model
        self.catalogID = catalogID; self.renderEngineID = renderEngineID
        self.renderEngineVersion = renderEngineVersion; self.renderColorCatalogID = renderColorCatalogID
        self.renderColorCatalogName = renderColorCatalogName; self.renderColorCatalogSub = renderColorCatalogSub
        self.renderColorProfile = renderColorProfile; self.renderColorMap = renderColorMap
        self.renderCanvasAspect = renderCanvasAspect; self.renderCanvasAspectID = renderCanvasAspectID
        self.renderCanvasAspectRatio = renderCanvasAspectRatio; self.renderSeed = renderSeed
        self.renderWild = renderWild; self.compositionSeed = compositionSeed
        self.interpretationSeed = interpretationSeed; self.variationAmplitude = variationAmplitude
        self.variationSeed = variationSeed; self.seedText = seedText
        self.instructionLangRequested = instructionLangRequested
        self.instructionLangResolved = instructionLangResolved; self.interpretFallback = interpretFallback
        self.composeFallback = composeFallback; self.sketchText = sketchText; self.sketchGrain = sketchGrain
        self.sketchState = sketchState; self.renderLimits = renderLimits; self.renderHash = renderHash
        self.descriptionHash = descriptionHash; self.starred = starred; self.trashed = trashed
        self.historyVisibility = historyVisibility; self.lineageNodeID = lineageNodeID
    }

    public enum CodingKeys: String, CodingKey {
        case id, at, input, ddl, score, svg, starred, trashed
        case sourceText = "source_text", ddlSourceOrigin = "ddl_source_origin", elapsedMS = "elapsed_ms"
        case stage1Model = "stage1_model", stage2Model = "stage2_model", catalogID = "catalog_id"
        case renderEngineID = "render_engine_id", renderEngineVersion = "render_engine_version"
        case renderColorCatalogID = "render_color_catalog_id", renderColorCatalogName = "render_color_catalog_name"
        case renderColorCatalogSub = "render_color_catalog_sub", renderColorProfile = "render_color_profile"
        case renderColorMap = "render_color_map", renderCanvasAspect = "render_canvas_aspect"
        case renderCanvasAspectID = "render_canvas_aspect_id", renderCanvasAspectRatio = "render_canvas_aspect_ratio"
        case renderSeed = "render_seed", renderWild = "render_wild", compositionSeed = "composition_seed"
        case interpretationSeed = "interpretation_seed", variationAmplitude = "variation_amplitude"
        case variationSeed = "variation_seed", seedText = "seed_text"
        case instructionLangRequested = "instruction_lang_requested", instructionLangResolved = "instruction_lang_resolved"
        case interpretFallback = "interpret_fallback", composeFallback = "compose_fallback"
        case sketchText = "sketch_text", sketchGrain = "sketch_grain", sketchState = "sketch_state"
        case renderLimits = "render_limits", renderHash = "render_hash", descriptionHash = "description_hash"
        case historyVisibility = "history_visibility", lineageNodeID = "lineage_node_id"
    }
}

extension SavedWork: FetchableRecord, PersistableRecord {
    public static let databaseTableName = "history"
}

public struct LineageNode: Codable, Sendable, Equatable {
    public var id: String
    public var historyID: String?
    public var state: String
    public var descriptionHash: String?
    public var renderHash: String?
    public var at: Int64
    public var deletedAt: Int64?
    public var rootNodeID: String?

    public init(id: String, historyID: String?, state: String = "active", at: Int64,
                descriptionHash: String? = nil, renderHash: String? = nil,
                deletedAt: Int64? = nil, rootNodeID: String? = nil) {
        self.id = id; self.historyID = historyID; self.state = state; self.at = at
        self.descriptionHash = descriptionHash; self.renderHash = renderHash
        self.deletedAt = deletedAt; self.rootNodeID = rootNodeID
    }

    public enum CodingKeys: String, CodingKey {
        case id, state, at
        case historyID = "history_id", descriptionHash = "description_hash", renderHash = "render_hash"
        case deletedAt = "deleted_at", rootNodeID = "root_node_id"
    }
}

extension LineageNode: FetchableRecord, PersistableRecord {
    public static let databaseTableName = "lineage_nodes"
}

public struct LineageEdge: Codable, Sendable, Equatable {
    public var id: String
    public var parentNodeID: String
    public var childNodeID: String
    public var derivationKind: String
    public var metadataJSON: String
    public var at: Int64

    public init(id: String, parentNodeID: String, childNodeID: String, derivationKind: String,
                metadataJSON: String = "{}", at: Int64) {
        self.id = id; self.parentNodeID = parentNodeID; self.childNodeID = childNodeID
        self.derivationKind = derivationKind; self.metadataJSON = metadataJSON; self.at = at
    }

    public enum CodingKeys: String, CodingKey {
        case id, at
        case parentNodeID = "parent_node_id", childNodeID = "child_node_id"
        case derivationKind = "derivation_kind", metadataJSON = "metadata_json"
    }
}

extension LineageEdge: FetchableRecord, PersistableRecord {
    public static let databaseTableName = "lineage_edges"
}

public struct ExecutionSnapshot: Sendable, Equatable {
    public let id: String
    public let revision: Int64
    public let snapshot: Data

    public init(id: String, revision: Int64, snapshot: Data) {
        self.id = id; self.revision = revision; self.snapshot = snapshot
    }
}

public struct EffectCommitResult: Sendable, Equatable {
    public let execution: ExecutionSnapshot
    public let acknowledgement: Data
    public let wasAlreadyCommitted: Bool
}

/// Legacy text selection uses the contract's fixed Unicode White_Space set.
public enum DDLSource {
    public static let bodyWhitespaceCodepoints: Set<UInt32> = [
        9, 10, 11, 12, 13, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196,
        8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288
    ]

    public static func hasBody(_ text: String?) -> Bool {
        text?.unicodeScalars.contains { !bodyWhitespaceCodepoints.contains($0.value) } ?? false
    }

    public static func select(ddl: String?, legacyExpanded: String?) -> (ddl: String?, origin: String?) {
        if hasBody(ddl) { return (ddl, nil) }
        if hasBody(legacyExpanded) { return (legacyExpanded, "legacy_expanded") }
        return (ddl, nil)
    }
}
