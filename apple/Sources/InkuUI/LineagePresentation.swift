import Foundation
import InkuPersistence
import SwiftUI

/// A display snapshot can combine read-only branches without altering portable lineage records.
public struct LineageSnapshot: Sendable, Equatable {
    public let focusNodeID: String
    public let nodes: [LineageItem]
    public let edges: [LineageEdge]
    public let truncated: Bool
    public let pathOnly: Bool

    public init(_ graph: LineageGraph, focusNodeID: String? = nil) {
        self.focusNodeID = focusNodeID ?? graph.focusNodeID
        nodes = graph.nodes; edges = graph.edges; truncated = graph.truncated; pathOnly = graph.pathOnly
    }

    private init(focusNodeID: String, nodes: [LineageItem], edges: [LineageEdge], truncated: Bool, pathOnly: Bool) {
        self.focusNodeID = focusNodeID; self.nodes = nodes; self.edges = edges
        self.truncated = truncated; self.pathOnly = pathOnly
    }

    public func merging(_ branch: LineageGraph) -> Self {
        var nodeMap = Dictionary(uniqueKeysWithValues: nodes.map { ($0.id, $0) })
        var edgeMap = Dictionary(uniqueKeysWithValues: edges.map { ($0.id, $0) })
        for node in branch.nodes { nodeMap[node.id] = node }
        for edge in branch.edges { edgeMap[edge.id] = edge }
        let missingChildren = nodeMap.values.contains { node in
            node.childCount > edgeMap.values.filter { $0.parentNodeID == node.id }.count
        }
        let missingRoot = nodeMap.values.contains { node in
            node.node.rootNodeID.map { nodeMap[$0] == nil } ?? false
        }
        return Self(focusNodeID: focusNodeID,
                    nodes: nodeMap.values.sorted { ($0.node.at, $0.id) < ($1.node.at, $1.id) },
                    edges: edgeMap.values.sorted { ($0.at, $0.id) < ($1.at, $1.id) },
                    truncated: missingChildren || missingRoot, pathOnly: pathOnly)
    }
}

public struct LineageDisplayEdge: Sendable, Equatable, Identifiable {
    public let id: String
    public let parentID: String
    public let childID: String
    public let starredPath: Bool
    public let tombstone: Bool
}

public struct LineageConnection: Sendable, Equatable {
    public let start: CGPoint
    public let control1: CGPoint
    public let control2: CGPoint
    public let end: CGPoint
}

public enum LineagePresentation {
    public static func ancestorIDs(_ graph: LineageSnapshot) -> Set<String> {
        let parents = Dictionary(uniqueKeysWithValues: graph.edges.map { ($0.childNodeID, $0.parentNodeID) })
        var result: Set<String> = []
        var current: String? = graph.focusNodeID
        while let id = current, result.insert(id).inserted { current = parents[id] }
        return result
    }

    public static func visibleIDs(_ graph: LineageSnapshot, browsing: LineageBrowsingState) -> Set<String> {
        if browsing.overviewOpen { return Set(graph.nodes.map(\.id)) }
        var visible = ancestorIDs(graph)
        if graph.pathOnly { return visible }
        let children = Dictionary(grouping: graph.edges, by: \.parentNodeID)
        var queue = Array(visible)
        while !queue.isEmpty {
            let parent = queue.removeFirst()
            guard browsing.expandedNodeIDs.contains(parent) else { continue }
            for edge in children[parent] ?? [] where visible.insert(edge.childNodeID).inserted {
                queue.append(edge.childNodeID)
            }
        }
        return visible
    }

    public static func edges(_ graph: LineageSnapshot, visibleIDs: Set<String>) -> [LineageDisplayEdge] {
        let nodes = Dictionary(uniqueKeysWithValues: graph.nodes.map { ($0.id, $0) })
        let parents = Dictionary(uniqueKeysWithValues: graph.edges.map { ($0.childNodeID, $0) })
        var starredEdges: Set<String> = []
        for node in graph.nodes where node.work?.starred == true {
            var current = node.id
            var seen: Set<String> = []
            while seen.insert(current).inserted, let edge = parents[current] {
                starredEdges.insert(edge.id); current = edge.parentNodeID
            }
        }
        return graph.edges.compactMap { edge in
            guard visibleIDs.contains(edge.parentNodeID), visibleIDs.contains(edge.childNodeID) else { return nil }
            return LineageDisplayEdge(id: edge.id, parentID: edge.parentNodeID, childID: edge.childNodeID,
                                      starredPath: starredEdges.contains(edge.id),
                                      tombstone: nodes[edge.parentNodeID]?.node.state == "tombstone"
                                          || nodes[edge.childNodeID]?.node.state == "tombstone")
        }
    }

    public static func connection(parent: CGRect, child: CGRect, vertical: Bool) -> LineageConnection {
        if vertical {
            let start = CGPoint(x: parent.midX, y: parent.maxY + 1)
            let end = CGPoint(x: child.midX, y: child.minY - 7)
            let bend = max(18, (end.y - start.y) / 2)
            return LineageConnection(start: start, control1: CGPoint(x: start.x, y: start.y + bend),
                                     control2: CGPoint(x: end.x, y: end.y - bend), end: end)
        }
        let start = CGPoint(x: parent.maxX + 1, y: parent.midY)
        let end = CGPoint(x: child.minX - 7, y: child.midY)
        let bend = max(18, (end.x - start.x) / 2)
        return LineageConnection(start: start, control1: CGPoint(x: start.x + bend, y: start.y),
                                 control2: CGPoint(x: end.x - bend, y: end.y), end: end)
    }
}

/// A generation wraps within the viewport; card measurements also cover localized text.
struct LineageWrappingRow: Layout {
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrangement(width: proposal.width ?? 210, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrangement(width: bounds.width, subviews: subviews)
        for (index, point) in result.points.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + point.x, y: bounds.minY + point.y),
                                  anchor: .topLeading, proposal: ProposedViewSize(width: 210, height: nil))
        }
    }

    private func arrangement(width: CGFloat, subviews: Subviews) -> (points: [CGPoint], size: CGSize) {
        let width = max(210, width)
        var points: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(ProposedViewSize(width: 210, height: nil))
            if x > 0, x + 210 > width { x = 0; y += rowHeight + 14; rowHeight = 0 }
            points.append(CGPoint(x: x, y: y))
            x += 228; rowHeight = max(rowHeight, size.height)
        }
        return (points, CGSize(width: width, height: y + rowHeight))
    }
}

/// Scale the scrollable footprint as well as the pixels, so zoom never clips the last row.
struct LineageScaleLayout: Layout {
    let scale: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard let view = subviews.first else { return .zero }
        let size = view.sizeThatFits(ProposedViewSize(width: proposal.width.map { $0 / scale }, height: nil))
        return CGSize(width: size.width * scale, height: size.height * scale)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        subviews.first?.place(at: bounds.origin, anchor: .topLeading,
                              proposal: ProposedViewSize(width: bounds.width / scale, height: nil))
    }
}
