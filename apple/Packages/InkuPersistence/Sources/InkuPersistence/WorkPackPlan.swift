import Foundation

/// The small identity graph used to plan an import; artwork bytes never enter this value.
public struct WorkPackIdentity: Sendable, Equatable {
    public struct Work: Sendable, Equatable {
        public let id: String
        public let nodeID: String?
        public init(id: String, nodeID: String?) { self.id = id; self.nodeID = nodeID }
    }
    public struct Node: Sendable, Equatable {
        public let id: String
        public let historyID: String?
        public init(id: String, historyID: String?) { self.id = id; self.historyID = historyID }
    }
    public struct Edge: Sendable, Equatable {
        public let id: String
        public let parent: String
        public let child: String
        public init(id: String, parent: String, child: String) { self.id = id; self.parent = parent; self.child = child }
    }
    public var works: [Work]
    public var nodes: [Node]
    public var edges: [Edge]
    public init(works: [Work], nodes: [Node], edges: [Edge]) {
        self.works = works; self.nodes = nodes; self.edges = edges
    }
}

public struct WorkPackDecision: Sendable, Equatable {
    public let workIDs: Set<String>
    public let nodeRoots: [String: String]
    public let edgeIDs: Set<String>
    public let skipped: Int
}

/// Makes the same decisions regardless of SQLite or the order of nodes in the source file.
public enum WorkPackPlanner {
    public static func decide(_ pack: WorkPackIdentity, existingWorks: Set<String>,
                              existingRoots: [String: String], existingParents: [String: String]) throws -> WorkPackDecision {
        func unique(_ ids: [String]) throws {
            guard ids.allSatisfy({ !$0.isEmpty }), Set(ids).count == ids.count else {
                throw PersistenceError.invalidRecord("duplicate or empty work pack identity")
            }
        }
        try unique(pack.works.map(\.id)); try unique(pack.nodes.map(\.id)); try unique(pack.edges.map(\.id))
        let nodeByID = Dictionary(uniqueKeysWithValues: pack.nodes.map { ($0.id, $0) })
        var accepted = Set<String>()
        for work in pack.works {
            guard !existingWorks.contains(work.id) else { continue }
            if let nodeID = work.nodeID {
                guard let node = nodeByID[nodeID], node.historyID == work.id else {
                    throw PersistenceError.invalidRecord("work and node do not match")
                }
                guard existingRoots[nodeID] == nil else { continue }
            }
            accepted.insert(work.id)
        }
        let importedNodes = Set(pack.nodes.compactMap { node -> String? in
            guard let workID = node.historyID, accepted.contains(workID),
                  pack.works.contains(where: { $0.id == workID && $0.nodeID == node.id }) else { return nil }
            return node.id
        })
        var parents = existingParents
        var acceptedEdges = Set<String>()
        let available = importedNodes.union(existingRoots.keys)
        for edge in pack.edges {
            guard edge.parent != edge.child else { throw PersistenceError.invalidRecord("self edge") }
            guard available.contains(edge.parent), available.contains(edge.child), importedNodes.contains(edge.child),
                  parents[edge.child] == nil else { continue }
            parents[edge.child] = edge.parent
            acceptedEdges.insert(edge.id)
        }
        var roots: [String: String] = [:]
        for id in importedNodes {
            var seen = Set<String>(), current = id
            while let parent = parents[current] {
                guard seen.insert(current).inserted else { throw PersistenceError.invalidRecord("lineage cycle") }
                current = parent
            }
            roots[id] = existingRoots[current] ?? current
        }
        return WorkPackDecision(workIDs: accepted, nodeRoots: roots, edgeIDs: acceptedEdges,
                                skipped: pack.works.count - accepted.count)
    }
}
