import Foundation
import InkuPersistence
import SwiftUI

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
        let tree = graph.rootNodeID
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

/// The scroll position is kept per tree, map and layout; a change of any of them puts its own position back.
struct LineageViewportKey: Equatable {
    let treeID: String?
    let overview: Bool
    let vertical: Bool
}

/// The cards' frames in the lineage's scroll content, where a drag does not pan.
struct LineageCardRects: PreferenceKey {
    static let defaultValue: [CGRect] = []
    static func reduce(value: inout [CGRect], nextValue: () -> [CGRect]) { value += nextValue() }
}

/// The lineage's scroll view: both axes of its position are kept and put back (`position` for `revision`), and a
/// drag that starts on the empty canvas pans it (PLAN §7). The drag is measured in the scroll view's own space, which
/// the drag does not move; and the offsets the scroll view reports before the put-back position arrives are not
/// kept, or the first report (the top left) would replace the kept position.
struct LineageScrolling: ViewModifier {
    let revision: LineageViewportKey
    let position: LineageScrollPosition
    let onScroll: (LineageScrollPosition) -> Void
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.inkuTooltipsCovered) private var covered
    @State private var scroll = ScrollPosition()
    @State private var geometry: ScrollGeometry?
    @State private var cards: [CGRect] = []
    @State private var applied: LineageViewportKey?
    /// The put-back offset, until the scroll view reports it.
    @State private var expected: CGPoint?
    /// The offset when a pan began; nil while no pan runs (no drag, or one that began on a card).
    @State private var panStart: CGPoint?
    @State private var panDecided = false
    private static let space = "inku.lineage.viewport"

    /// The library, settings and a presentation cover the shell without disabling it; a covered lineage does not pan,
    /// as a disabled one does not (2026-11-06).
    static func pans(isEnabled: Bool, covered: Bool) -> Bool { isEnabled && !covered }

    func body(content: Content) -> some View {
        content
            .scrollPosition($scroll)
            .coordinateSpace(.named(Self.space))
            .onPreferenceChange(LineageCardRects.self) { cards = $0 }
            .onScrollGeometryChange(for: ScrollGeometry.self) { $0 } action: { _, now in reported(now) }
            .onChange(of: revision, initial: true) { _, _ in putBack() }
            .simultaneousGesture(pan, including: Self.pans(isEnabled: isEnabled, covered: covered) ? .all : .subviews)
    }

    private var pan: some Gesture {
        DragGesture(minimumDistance: 4, coordinateSpace: .named(Self.space))
            .onChanged { value in
                if !panDecided {
                    panDecided = true
                    let origin = geometry?.contentOffset ?? .zero
                    let start = CGPoint(x: value.startLocation.x + origin.x, y: value.startLocation.y + origin.y)
                    panStart = cards.contains(where: { $0.contains(start) }) ? nil : origin
                }
                guard let start = panStart else { return }
                scroll.scrollTo(point: clamped(CGPoint(x: start.x - value.translation.width, y: start.y - value.translation.height)))
            }
            .onEnded { _ in panStart = nil; panDecided = false }
    }

    private func reported(_ now: ScrollGeometry) {
        geometry = now
        if applied != revision { return putBack() }
        if let target = expected {
            guard abs(now.contentOffset.x - target.x) < 1, abs(now.contentOffset.y - target.y) < 1 else { return }
            expected = nil
        }
        onScroll(LineageScrollPosition(x: now.contentOffset.x, y: now.contentOffset.y))
    }

    /// Puts this revision's kept position back once the content's size is known.
    private func putBack() {
        guard applied != revision, geometry != nil else { return }
        let target = clamped(CGPoint(x: position.x, y: position.y))
        applied = revision
        expected = target
        scroll.scrollTo(point: target)
        // A position the scroll view cannot reach exactly (the content changed meanwhile) stops waiting.
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(500))
            if expected == target { expected = nil }
        }
    }

    private func clamped(_ point: CGPoint) -> CGPoint {
        guard let geometry else { return point }
        let limit = CGSize(width: max(0, geometry.contentSize.width - geometry.containerSize.width),
                           height: max(0, geometry.contentSize.height - geometry.containerSize.height))
        return CGPoint(x: min(max(0, point.x), limit.width), y: min(max(0, point.y), limit.height))
    }
}

extension View {
    func lineageScrolling(revision: LineageViewportKey, position: LineageScrollPosition,
                          onScroll: @escaping (LineageScrollPosition) -> Void) -> some View {
        modifier(LineageScrolling(revision: revision, position: position, onScroll: onScroll))
    }
}
