import SwiftUI

/// Counts read by InkuAppCheck's library paging measurement (`--library-paging-perf-only`). Nothing is counted
/// until that check sets `counting`; the app never does, so each call site costs one untaken branch.
@MainActor
public enum LibraryPerformanceProbe {
    public static var counting = false
    public private(set) static var refreshesStarted = 0
    public private(set) static var refreshesFinished = 0
    public private(set) static var lineageReads = 0
    /// Times a library grid card built its view tree.
    public private(set) static var cardBodies = 0
    /// Times a lineage node card built its view tree (the lineage view stays beneath the library).
    public private(set) static var lineageNodeBodies = 0
    /// Layout passes of the probe's hosting view, each a SwiftUI update of the whole window.
    public internal(set) static var hostingLayouts = 0
    /// Times a library work menu (context menu or ⋯) built its items.
    public private(set) static var menuBodies = 0
    public private(set) static var actionSummaryReads = 0
    public private(set) static var previewReads = 0

    public static func reset() {
        refreshesStarted = 0; refreshesFinished = 0; lineageReads = 0; cardBodies = 0; lineageNodeBodies = 0
        hostingLayouts = 0; menuBodies = 0; actionSummaryReads = 0; previewReads = 0
    }

    static func refreshStarted() { if counting { refreshesStarted += 1 } }
    static func refreshFinished() { if counting { refreshesFinished += 1 } }
    static func lineageRead() { if counting { lineageReads += 1 } }
    static func cardBody() { if counting { cardBodies += 1 } }
    static func lineageNodeBody() { if counting { lineageNodeBodies += 1 } }
    static func menuBody() { if counting { menuBodies += 1 } }
    static func actionSummaryRead() { if counting { actionSummaryReads += 1 } }
    static func previewRead() { if counting { previewReads += 1 } }

}
