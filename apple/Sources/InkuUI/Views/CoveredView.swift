import SwiftUI

struct InkuCoveredView: ViewModifier {
    let covered: Bool
    var hidden = false
    func body(content: Content) -> some View {
        content.opacity(hidden ? 0 : 1)
            .allowsHitTesting(!covered)
            .accessibilityHidden(covered)
            .environment(\.inkuTooltipsCovered, covered)
    }
}
