#if os(iOS)
import SwiftUI

struct CanvasWheelSurface<Content: View>: View {
    let onScroll: (CGFloat) -> Bool
    let content: Content
    init(onScroll: @escaping (CGFloat) -> Bool, @ViewBuilder content: () -> Content) {
        self.onScroll = onScroll; self.content = content()
    }
    var body: some View { content }
}
#endif
