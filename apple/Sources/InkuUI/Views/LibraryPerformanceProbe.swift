import SwiftUI
#if os(macOS)
import AppKit
#endif

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

    public static func reset() {
        refreshesStarted = 0; refreshesFinished = 0; lineageReads = 0; cardBodies = 0; lineageNodeBodies = 0
    }

    static func refreshStarted() { if counting { refreshesStarted += 1 } }
    static func refreshFinished() { if counting { refreshesFinished += 1 } }
    static func lineageRead() { if counting { lineageReads += 1 } }
    static func cardBody() { if counting { cardBodies += 1 } }
    static func lineageNodeBody() { if counting { lineageNodeBodies += 1 } }

    #if os(macOS)
    /// The library overlay over a hidden lineage view, as `ContentView` keeps the shell beneath the library.
    public static func hostingView(model: AppModel, preview: LibraryPreviewModel) -> NSView {
        NSHostingView(rootView: ProbeRoot(model: model, preview: preview))
    }

    private struct ProbeRoot: View {
        @Bindable var model: AppModel
        let preview: LibraryPreviewModel

        var body: some View {
            ZStack {
                LineageView(model: model, onWorkAction: { _, _ in }, onExport: { _ in })
                    .opacity(0)
                    .accessibilityHidden(true)
                    .allowsHitTesting(false)
                    .disabled(true)
                    .environment(\.inkuTooltipsCovered, true)
                LibraryView(model: model, preview: preview, onEditWork: { _, _ in }, onAdjustWork: { _ in },
                            onReplayWork: { _ in }, onWorkAction: { _, _ in }, onClose: {})
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(InkuColor.bg)
            }
            .environment(model.display)
            .environment(\.locale, Locale(identifier: model.display.preferences.language))
            .font(.system(size: 13 * model.display.preferences.textScale))
            .environment(\.inkuTextScale, model.display.preferences.textScale)
        }
    }
    #endif
}
