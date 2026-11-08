#if os(iOS)
import UIKit

extension InkuEditorMark.Style {
    /// The same colours as the Mac (MacDdlHighlightAttributes.swift): Web `.label-muted`, the `.ddl-token-*` palette in
    /// both themes, the amber unknown name, the completion underline and the heading. iOS paints them as character
    /// attributes, so only colours and underlines are set; the font and paragraph stay the editor's.
    var attributes: [NSAttributedString.Key: Any] {
        switch self {
        case .muted:
            return [.backgroundColor: UIColor.systemGray.withAlphaComponent(0.22)]
        case .completion(let state):
            let color: UIColor = switch state { case .completed: .systemBlue; case .numbersChanged: .systemGreen; case .wordsChanged: .systemOrange }
            return [.underlineStyle: NSUnderlineStyle.thick.rawValue | NSUnderlineStyle.patternDot.rawValue, .underlineColor: color]
        case .unknownName:
            return [.foregroundColor: Self.dynamic(0x8a5a12, 0xf0c368),
                    .backgroundColor: Self.dynamic(0xbf8820, 0xbf8820, lightAlpha: 0.12, darkAlpha: 0.26),
                    .underlineStyle: NSUnderlineStyle.single.rawValue | NSUnderlineStyle.patternDot.rawValue,
                    .underlineColor: Self.dynamic(0xbf8820, 0xf0c368, lightAlpha: 0.42, darkAlpha: 0.48)]
        case .title:
            return [.foregroundColor: Self.dynamic(0x3d4650, 0xd6dde4),
                    .underlineStyle: NSUnderlineStyle.single.rawValue,
                    .underlineColor: Self.dynamic(0x3d4650, 0xd6dde4, lightAlpha: 0.45, darkAlpha: 0.45)]
        case .token(let token):
            let palette = Self.palette[token] ?? Self.palette[.word]!
            var attributes: [NSAttributedString.Key: Any] = [.foregroundColor: Self.dynamic(palette.light, palette.dark)]
            if let background = palette.background {
                attributes[.backgroundColor] = Self.dynamic(background.light, background.dark,
                                                            lightAlpha: background.lightAlpha, darkAlpha: background.darkAlpha)
            }
            return attributes
        }
    }

    private static func dynamic(_ light: Int, _ dark: Int, lightAlpha: CGFloat = 1, darkAlpha: CGFloat = 1) -> UIColor {
        UIColor { traits in
            let isDark = traits.userInterfaceStyle == .dark
            let value = isDark ? dark : light
            return UIColor(red: CGFloat((value >> 16) & 0xff) / 255, green: CGFloat((value >> 8) & 0xff) / 255,
                           blue: CGFloat(value & 0xff) / 255, alpha: isDark ? darkAlpha : lightAlpha)
        }
    }
}
#endif
