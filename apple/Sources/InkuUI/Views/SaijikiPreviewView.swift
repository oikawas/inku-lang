import CoreGraphics
import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

@MainActor
struct SaijikiPreviewView: View {
    let svg: String?
    let imageURL: URL?
    let renderer: ArtworkRenderer
    @State private var image: CGImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 5).fill(.quaternary.opacity(0.2))
            if let imageURL {
                pluginImage(imageURL)
            } else if let image {
                Image(decorative: image, scale: 1).resizable().scaledToFit()
            } else if failed || svg?.isEmpty != false {
                Image(systemName: "leaf").foregroundStyle(.secondary)
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 5))
        .task(id: svg) {
            image = nil; failed = false
            guard let svg, !svg.isEmpty else { return }
            do {
                let rendered = try await renderer.image(svg: svg, targetWidth: 432, targetHeight: 184)
                try Task.checkCancellation()
                image = rendered
            } catch {
                guard !Task.isCancelled else { return }
                failed = true
            }
        }
    }

    @ViewBuilder private func pluginImage(_ url: URL) -> some View {
        #if os(macOS)
        if let image = NSImage(contentsOf: url) {
            Image(nsImage: image).resizable().scaledToFit()
        } else { Image(systemName: "leaf").foregroundStyle(.secondary) }
        #else
        if let image = UIImage(contentsOfFile: url.path) {
            Image(uiImage: image).resizable().scaledToFit()
        } else { Image(systemName: "leaf").foregroundStyle(.secondary) }
        #endif
    }
}
