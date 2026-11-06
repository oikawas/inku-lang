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
    let imageData: Data?
    let renderer: ArtworkRenderer
    @State private var image: CGImage?
    @State private var failed = false
    #if os(macOS)
    @State private var pluginImage: NSImage?
    #else
    @State private var pluginImage: UIImage?
    #endif
    private struct ImageKey: Equatable { let svg: String?; let url: URL?; let data: Data? }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 5).fill(.quaternary.opacity(0.2))
            if imageData != nil || imageURL != nil {
                if let pluginImage {
                    #if os(macOS)
                    Image(nsImage: pluginImage).resizable().scaledToFit()
                    #else
                    Image(uiImage: pluginImage).resizable().scaledToFit()
                    #endif
                } else { Image(systemName: "leaf").foregroundStyle(.secondary) }
            } else if let image {
                Image(decorative: image, scale: 1).resizable().scaledToFit()
            } else if failed || svg?.isEmpty != false {
                Image(systemName: "leaf").foregroundStyle(.secondary)
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 5))
        .task(id: ImageKey(svg: svg, url: imageURL, data: imageData)) {
            image = nil; pluginImage = nil; failed = false
            if let data = imageData ?? imageURL.flatMap({ try? Data(contentsOf: $0) }) {
                #if os(macOS)
                pluginImage = NSImage(data: data)
                #else
                pluginImage = UIImage(data: data)
                #endif
                return
            }
            if imageData != nil || imageURL != nil { return }
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

}
