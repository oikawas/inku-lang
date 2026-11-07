#if os(iOS)
import SwiftUI
struct InkuTooltipModifier: ViewModifier {
    let text: String
    let placement: InkuTooltipPlacement
    let wide: Bool
    let focus: InkuTooltipFocus
    // inkuTooltip applies this modifier, so calling it here would recurse; iOS has no hover bubble.
    func body(content: Content) -> some View { content.help(text) }
}
#endif
