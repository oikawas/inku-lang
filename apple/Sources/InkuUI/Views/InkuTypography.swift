import SwiftUI

/// Web `typography.css`: `--ui-font-size-N` is N px × `--ui-text-scale`. Views use `inkuFont(N)` with the
/// Web px value instead of fixed system text styles, so the text-size setting reaches every label.
private struct InkuTextScaleKey: EnvironmentKey {
    static let defaultValue: Double = 1
}

extension EnvironmentValues {
    public var inkuTextScale: Double {
        get { self[InkuTextScaleKey.self] }
        set { self[InkuTextScaleKey.self] = newValue }
    }
}

private struct InkuFontModifier: ViewModifier {
    @Environment(\.inkuTextScale) private var scale
    let size: Double
    let weight: Font.Weight
    let design: Font.Design
    func body(content: Content) -> some View {
        content.font(.system(size: size * scale, weight: weight, design: design))
    }
}

extension View {
    /// The Web px size of this text, scaled by the text-size setting.
    public func inkuFont(_ size: Double, weight: Font.Weight = .regular, design: Font.Design = .default) -> some View {
        modifier(InkuFontModifier(size: size, weight: weight, design: design))
    }
}
