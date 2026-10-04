import Foundation
import InkuPersistence
import SwiftUI
#if os(macOS)
import AppKit
#elseif os(iOS)
import UIKit
#endif

public struct LineageScrollPosition: Sendable, Equatable {
    public var x: Double
    public var y: Double
    public init(x: Double = 0, y: Double = 0) { self.x = x; self.y = y }
}

public struct LineageBrowsingState: Sendable, Equatable {
    public private(set) var treeID: String?
    public var expandedNodeIDs: Set<String> = []
    public private(set) var overviewOpen = false
    public private(set) var overviewScale = 1.0
    public var normalScroll = LineageScrollPosition()
    public var overviewScroll = LineageScrollPosition()

    public init() {}

    public mutating func reconcile(_ graph: LineageSnapshot) {
        let tree = graph.nodes.first(where: { $0.id == graph.focusNodeID })?.node.rootNodeID
            ?? graph.nodes.first(where: { !Set(graph.edges.map(\.childNodeID)).contains($0.id) })?.id
            ?? graph.focusNodeID
        if treeID != tree {
            self = Self(); treeID = tree; expandedNodeIDs = [graph.focusNodeID]
        } else {
            expandedNodeIDs.formIntersection(graph.nodes.map(\.id))
        }
    }

    public mutating func openOverview() { overviewOpen = true }
    public mutating func closeOverview() { overviewOpen = false }
    public mutating func setOverviewScale(_ value: Double) { overviewScale = min(1.4, max(0.4, value)) }
    public var scroll: LineageScrollPosition { overviewOpen ? overviewScroll : normalScroll }
    public mutating func rememberScroll(_ value: LineageScrollPosition) {
        if overviewOpen { overviewScroll = value } else { normalScroll = value }
    }
}

/// Queries remain read-only and are injectable solely at the local database boundary.
public protocol LineageReading: Sendable {
    func read(focusNodeID: String, depth: Int, pathOnly: Bool) async throws -> LineageGraph?
    func readBranch(nodeID: String) async throws -> LineageGraph?
    func readOverview(focusNodeID: String) async throws -> LineageGraph?
}

struct DatabaseLineageReader: LineageReading {
    let database: InkuDatabase
    func read(focusNodeID: String, depth: Int, pathOnly: Bool) async throws -> LineageGraph? {
        try await database.lineage(focusNodeID: focusNodeID, descendantDepth: depth, nodeLimit: 200, pathOnly: pathOnly)
    }
    func readBranch(nodeID: String) async throws -> LineageGraph? {
        try await database.lineage(focusNodeID: nodeID, descendantDepth: 1, nodeLimit: 200)
    }
    func readOverview(focusNodeID: String) async throws -> LineageGraph? {
        try await database.lineageOverview(focusNodeID: focusNodeID)
    }
}

/// Native offsets preserve both axes when entering and leaving the map on macOS 14/iOS 17.
struct LineageViewportKey: Equatable {
    let treeID: String?
    let overview: Bool
    let vertical: Bool
}

#if os(macOS)
private final class LineageScrollObserver {
    private let token: NSObjectProtocol
    init(_ token: NSObjectProtocol) { self.token = token }
    deinit { NotificationCenter.default.removeObserver(token) }
}

struct LineageScrollBridge: NSViewRepresentable {
    let revision: LineageViewportKey
    let position: LineageScrollPosition
    let onScroll: (LineageScrollPosition) -> Void
    func makeNSView(context: Context) -> Probe { Probe() }
    func updateNSView(_ view: Probe, context: Context) {
        view.onScroll = onScroll
        view.request(revision: revision, position: position)
    }

    final class Probe: NSView {
        var onScroll: ((LineageScrollPosition) -> Void)?
        private var appliedRevision: LineageViewportKey?
        private var pendingRevision: LineageViewportKey?
        private var pendingPosition = LineageScrollPosition()
        private weak var scroll: NSScrollView?
        private var observation: LineageScrollObserver?
        private var restoring = false
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            DispatchQueue.main.async { [weak self] in self?.attach() }
        }
        func request(revision: LineageViewportKey, position: LineageScrollPosition) {
            pendingRevision = revision; pendingPosition = position
            DispatchQueue.main.async { [weak self] in self?.attach() }
        }
        private func attach() {
            guard let target = enclosingScrollView else { return }
            if scroll !== target {
                scroll = target; appliedRevision = nil; target.contentView.postsBoundsChangedNotifications = true
                observation = LineageScrollObserver(NotificationCenter.default.addObserver(forName: NSView.boundsDidChangeNotification,
                    object: target.contentView, queue: .main) { [weak self] _ in
                        MainActor.assumeIsolated { self?.changed() }
                    })
            }
            guard appliedRevision != pendingRevision else { return }
            restoring = true
            let clip = target.contentView
            let document = target.documentView?.frame.size ?? .zero
            let origin = CGPoint(x: min(max(0, pendingPosition.x), max(0, document.width - clip.bounds.width)),
                                 y: min(max(0, pendingPosition.y), max(0, document.height - clip.bounds.height)))
            clip.scroll(to: origin); target.reflectScrolledClipView(clip)
            appliedRevision = pendingRevision; restoring = false
        }
        private func changed() {
            guard !restoring, appliedRevision == pendingRevision, let origin = scroll?.contentView.bounds.origin else { return }
            onScroll?(LineageScrollPosition(x: origin.x, y: origin.y))
        }
    }
}
#elseif os(iOS)
struct LineageScrollBridge: UIViewRepresentable {
    let revision: LineageViewportKey
    let position: LineageScrollPosition
    let onScroll: (LineageScrollPosition) -> Void
    func makeUIView(context: Context) -> Probe { Probe() }
    func updateUIView(_ view: Probe, context: Context) {
        view.onScroll = onScroll; view.request(revision: revision, position: position)
    }
    final class Probe: UIView {
        var onScroll: ((LineageScrollPosition) -> Void)?
        private var appliedRevision: LineageViewportKey?
        private var pendingRevision: LineageViewportKey?
        private var pendingPosition = LineageScrollPosition()
        private weak var scroll: UIScrollView?
        private var observation: NSKeyValueObservation?
        private var restoring = false
        override func didMoveToWindow() {
            super.didMoveToWindow()
            DispatchQueue.main.async { [weak self] in self?.attach() }
        }
        func request(revision: LineageViewportKey, position: LineageScrollPosition) {
            pendingRevision = revision; pendingPosition = position
            DispatchQueue.main.async { [weak self] in self?.attach() }
        }
        private func attach() {
            var ancestor = superview
            while ancestor != nil, !(ancestor is UIScrollView) { ancestor = ancestor?.superview }
            guard let target = ancestor as? UIScrollView else { return }
            if scroll !== target {
                scroll = target; appliedRevision = nil
                observation = target.observe(\.contentOffset, options: [.new]) { [weak self] _, _ in
                    MainActor.assumeIsolated { self?.changed() }
                }
            }
            guard appliedRevision != pendingRevision else { return }
            restoring = true
            target.setContentOffset(CGPoint(x: min(max(0, pendingPosition.x), max(0, target.contentSize.width - target.bounds.width)),
                                            y: min(max(0, pendingPosition.y), max(0, target.contentSize.height - target.bounds.height))), animated: false)
            appliedRevision = pendingRevision; restoring = false
        }
        private func changed() {
            guard !restoring, appliedRevision == pendingRevision, let origin = scroll?.contentOffset else { return }
            onScroll?(LineageScrollPosition(x: origin.x, y: origin.y))
        }
    }
}
#endif
