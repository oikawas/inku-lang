import SwiftUI

/// The approved Web figures rendered in the current theme's foreground.
struct CompositionFigure: View {
    let id: String
    @Environment(\.colorScheme) private var colorScheme
    @State private var image: CGImage?
    private static let renderer = ArtworkRenderer()
    private static let figures: [String: String] = {
        guard let url = Bundle.module.url(forResource: "composition-figures", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return [:] }
        return (try? JSONDecoder().decode([String: String].self, from: data)) ?? [:]
    }()

    var body: some View {
        Group {
            if let image { Image(decorative: image, scale: 2).resizable().aspectRatio(contentMode: .fit) }
            else { Color.clear }
        }
        .task(id: "\(id)-\(colorScheme)") {
            guard let body = Self.figures[id] else { image = nil; return }
            let foreground = colorScheme == .dark ? "#ffffff" : "#000000"
            let svg = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 48 48\">\(body.replacingOccurrences(of: "currentColor", with: foreground))</svg>"
            image = try? await Self.renderer.image(svg: svg, targetWidth: 96, targetHeight: 96)
        }
    }
}
