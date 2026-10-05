import Foundation

/// These local annotations never alter portable source, Score, SVG or identities.
public struct LibraryAnnotation: Sendable, Equatable {
    public var note: String?
    public var forRevision: Bool
    public var forShare: Bool

    public init(note: String? = nil, forRevision: Bool = false, forShare: Bool = false) {
        self.note = note; self.forRevision = forRevision; self.forShare = forShare
    }
}

public enum LibraryOrder: String, CaseIterable, Sendable {
    case newest, oldest
}

public struct LibraryQuery: Sendable, Equatable {
    public var text: String
    public var trashed: Bool
    public var starred: Bool
    public var forRevision: Bool
    public var forShare: Bool
    public var order: LibraryOrder

    public init(text: String = "", trashed: Bool = false, starred: Bool = false,
                forRevision: Bool = false, forShare: Bool = false, order: LibraryOrder = .newest) {
        self.text = text; self.trashed = trashed; self.starred = starred
        self.forRevision = forRevision; self.forShare = forShare; self.order = order
    }
}

public struct LibraryItem: Sendable, Equatable, Identifiable {
    public let work: SavedWork
    public let annotation: LibraryAnnotation
    public var id: String { work.id }
}

public struct LibraryPage: Sendable, Equatable {
    public let items: [LibraryItem]
    public let total: Int
}

public struct LibraryGroup: Sendable, Equatable, Identifiable {
    public let rootNodeID: String
    public let representative: LibraryItem
    public let itemCount: Int
    public let starredCount: Int
    public let revisionCount: Int
    public let latestAt: Int64
    public var id: String { rootNodeID }
}

public struct LibraryGroupPage: Sendable, Equatable {
    public let groups: [LibraryGroup]
    public let total: Int
}

public struct LineageItem: Sendable, Equatable, Identifiable {
    public let node: LineageNode
    public let work: SavedWork?
    public let annotation: LibraryAnnotation
    public let generation: Int
    public let childCount: Int
    public var id: String { node.id }
}

public struct LineageGraph: Sendable, Equatable {
    public let focusNodeID: String
    public let nodes: [LineageItem]
    public let edges: [LineageEdge]
    public let truncated: Bool
    public let pathOnly: Bool
}

public struct ColophonRecord: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let targetNodeID: String
    public let branchSnapshot: [String]
    public let model: String
    public let at: Int64
    public let language: String
    public let generatedBody: String
    public var adoptedBody: String?
    public let signature: String
    public let warnings: [String]
    public let factSheetJSON: String

    public init(id: String, targetNodeID: String, branchSnapshot: [String], model: String,
                at: Int64, language: String, generatedBody: String, adoptedBody: String? = nil,
                signature: String, warnings: [String], factSheetJSON: String) {
        self.id = id; self.targetNodeID = targetNodeID; self.branchSnapshot = branchSnapshot
        self.model = model; self.at = at; self.language = language
        self.generatedBody = generatedBody; self.adoptedBody = adoptedBody
        self.signature = signature; self.warnings = warnings; self.factSheetJSON = factSheetJSON
    }
}
