import SwiftUI

/// Web `typography.css`: `--ui-font-size-N` is N px × `--ui-text-scale`. Views use `inkuFont(N)` with the
/// Web px value instead of fixed system text styles, so the text-size setting reaches every label.
private struct InkuTextScaleKey: EnvironmentKey {
    static let defaultValue: Double = 1
}

private struct InkuMinimumFontSizeKey: EnvironmentKey {
    static let defaultValue: Double = 0
}

enum InkuTypography {
    /// The iPhone's 17-point body text matches the Web's 14-point base used by settings and front screens.
    static let phoneTextScale = 17.0 / 14.0
    static func size(_ value: Double, scale: Double, minimum: Double) -> Double {
        max(value * scale, minimum)
    }
}

extension EnvironmentValues {
    public var inkuTextScale: Double {
        get { self[InkuTextScaleKey.self] }
        set { self[InkuTextScaleKey.self] = newValue }
    }
    public var inkuMinimumFontSize: Double {
        get { self[InkuMinimumFontSizeKey.self] }
        set { self[InkuMinimumFontSizeKey.self] = newValue }
    }
}

private struct InkuFontModifier: ViewModifier {
    @Environment(\.inkuTextScale) private var scale
    @Environment(\.inkuMinimumFontSize) private var minimum
    let size: Double
    let weight: Font.Weight
    let design: Font.Design
    func body(content: Content) -> some View {
        content.font(.system(size: InkuTypography.size(size, scale: scale, minimum: minimum), weight: weight, design: design))
    }
}

extension View {
    @ViewBuilder func inkuPhoneFrontText(_ enabled: Bool, textScale: Double) -> some View {
        if enabled {
            self.font(.body)
                .environment(\.inkuTextScale, textScale * InkuTypography.phoneTextScale)
                .environment(\.inkuMinimumFontSize, 13)
                .dynamicTypeSize(.xLarge ... .accessibility5)
        } else { self }
    }
    /// The Web px size of this text, scaled by the text-size setting.
    public func inkuFont(_ size: Double, weight: Font.Weight = .regular, design: Font.Design = .default) -> some View {
        modifier(InkuFontModifier(size: size, weight: weight, design: design))
    }
}
