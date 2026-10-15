import InkuPersistence

public struct LineageExportRequest: Sendable, Equatable {
    public let workIDs: [String]
    public let preserveOrder: Bool
    public init(workIDs: [String], preserveOrder: Bool) {
        self.workIDs = workIDs; self.preserveOrder = preserveOrder
    }
}

public enum LineageWorkScope {
    public static func focused(_ graph: LineageSnapshot) -> LineageExportRequest {
        request(graph.nodes.filter { $0.id == graph.focusNodeID }.compactMap(\.work), ordered: false)
    }

    public static func path(_ graph: LineageSnapshot) -> LineageExportRequest {
        let nodes = Dictionary(uniqueKeysWithValues: graph.nodes.map { ($0.id, $0) })
        let parents = Dictionary(uniqueKeysWithValues: graph.edges.map { ($0.childNodeID, $0.parentNodeID) })
        var current: String? = graph.focusNodeID
        var seen: Set<String> = [], works: [SavedWork] = []
        while let id = current, seen.insert(id).inserted {
            if let work = nodes[id]?.work { works.insert(work, at: 0) }
            current = parents[id]
        }
        return request(works, ordered: true)
    }

    public static func checked(_ graph: LineageSnapshot, ids: Set<String>) -> LineageExportRequest {
        request(graph.nodes.compactMap(\.work).filter { ids.contains($0.id) }, ordered: false)
    }

    private static func request(_ works: [SavedWork], ordered: Bool) -> LineageExportRequest {
        LineageExportRequest(workIDs: works.filter { !$0.trashed }.map(\.id), preserveOrder: ordered)
    }

    public static func sameText(_ item: LineageItem, focus: LineageItem?) -> Bool {
        guard let hash = item.node.descriptionHash, !hash.isEmpty else { return false }
        return item.id != focus?.id && hash == focus?.node.descriptionHash
    }

    public static func sameEdition(_ item: LineageItem, focus: LineageItem?) -> Bool {
        guard let hash = item.node.renderHash, !hash.isEmpty else { return false }
        return item.id != focus?.id && hash == focus?.node.renderHash
    }
}
