#if os(macOS)
import SwiftUI
import AppKit
@MainActor struct CanvasWheelSurface<Content: View>: NSViewRepresentable {
    let onScroll: (CGFloat) -> Bool
    let content: Content
    init(onScroll: @escaping (CGFloat) -> Bool, @ViewBuilder content: () -> Content) {
        self.onScroll = onScroll; self.content = content()
    }
    func makeNSView(context: Context) -> CanvasWheelHostingView {
        let view = CanvasWheelHostingView(rootView: AnyView(content.environment(\.self, context.environment)))
        view.sizingOptions = []
        view.onScroll = onScroll
        return view
    }
    func updateNSView(_ view: CanvasWheelHostingView, context: Context) {
        view.rootView = AnyView(content.environment(\.self, context.environment))
        view.onScroll = onScroll
    }
    static func dismantleNSView(_ view: CanvasWheelHostingView, coordinator: ()) { view.onScroll = nil }
}

@MainActor final class CanvasWheelHostingView: NSHostingView<AnyView> {
    var onScroll: ((CGFloat) -> Bool)?
    override func scrollWheel(with event: NSEvent) {
        if onScroll?(event.scrollingDeltaY) != true { super.scrollWheel(with: event) }
    }
}
#endif
