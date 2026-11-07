#if os(macOS)
import SwiftUI
import AppKit

extension LibraryPerformanceProbe {
    /// The library overlay over a hidden lineage view, as `ContentView` keeps the shell beneath the library.
    public static func hostingView(model: AppModel, preview: LibraryPreviewModel) -> NSView {
        CountingHostingView(rootView: ProbeRoot(model: model, preview: preview))
    }

    public static func historyHostingView(model: AppModel, history: HistoryModel, width: CGFloat) -> NSView {
        NSHostingView(rootView: HistoryStripView(model: model, history: history, windowWidth: width)
            .environment(model.display))
    }

    public static func lineageHostingView(model: AppModel) -> NSView {
        NSHostingView(rootView: LineageView(model: model, onWorkAction: { _, _ in }, onExport: { _ in })
            .environment(model.display))
    }

    private final class CountingHostingView: NSHostingView<ProbeRoot> {
        override func layout() {
            if LibraryPerformanceProbe.counting { LibraryPerformanceProbe.hostingLayouts += 1 }
            super.layout()
        }
    }

    private struct ProbeRoot: View {
        @Bindable var model: AppModel
        let preview: LibraryPreviewModel

        var body: some View {
            ZStack {
                LineageView(model: model, onWorkAction: { _, _ in }, onExport: { _ in })
                    .modifier(InkuCoveredView(covered: true, hidden: true))
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
}
#endif
