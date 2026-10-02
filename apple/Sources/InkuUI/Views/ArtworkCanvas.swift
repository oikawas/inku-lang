import CoreGraphics
import InkuPersistence
import SwiftUI

@MainActor
struct ArtworkCanvas: View {
    let svg: String
    let renderer: ArtworkRenderer
    var caption = ""
    @State private var image: CGImage?
    @State private var error: String?
    @State private var loading = false
    @State private var scale: CGFloat = 1
    @State private var gestureScale: CGFloat = 1
    @State private var offset = CGSize.zero
    @State private var dragOrigin = CGSize.zero

    var body: some View {
        VStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 10).fill(.quaternary.opacity(0.3))
                if let image {
                    Image(decorative: image, scale: 1)
                        .resizable().interpolation(.high).scaledToFit()
                        .padding(18)
                        .scaleEffect(scale).offset(offset)
                        .gesture(MagnificationGesture()
                            .onChanged { value in scale = bounded(gestureScale * value) }
                            .onEnded { _ in gestureScale = scale })
                        .simultaneousGesture(DragGesture()
                            .onChanged { value in
                                offset = CGSize(width: dragOrigin.width + value.translation.width,
                                                height: dragOrigin.height + value.translation.height)
                            }
                            .onEnded { _ in dragOrigin = offset })
                        .accessibilityLabel("作品")
                } else if loading {
                    ProgressView("作品を表示中")
                } else if let error {
                    ContentUnavailableView("作品を表示できません", systemImage: "exclamationmark.triangle", description: Text(error))
                } else {
                    ContentUnavailableView("作品", systemImage: "paintpalette", description: Text("生成した作品や保存作品をここに表示します。"))
                }
            }
            .frame(minHeight: 280, maxHeight: .infinity)
            .clipped()

            HStack(spacing: 12) {
                if !caption.isEmpty { Text(caption).font(.callout).lineLimit(2).textSelection(.enabled) }
                Spacer(minLength: 12)
                Button { setScale(scale / 1.25) } label: { Image(systemName: "minus.magnifyingglass") }
                    .accessibilityLabel("縮小")
                Text(Double(scale).formatted(.percent.precision(.fractionLength(0)))).font(.caption.monospacedDigit())
                Button { setScale(scale * 1.25) } label: { Image(systemName: "plus.magnifyingglass") }
                    .accessibilityLabel("拡大")
                Button("全体") { reset() }
            }
            .buttonStyle(.borderless)
            .disabled(image == nil)
        }
        .task(id: svg) {
            image = nil
            error = nil
            reset()
            guard !svg.isEmpty else { loading = false; return }
            loading = true
            do {
                let rendered = try await renderer.image(svg: svg, targetWidth: 1600, targetHeight: 1600)
                guard !Task.isCancelled else { return }
                image = rendered
            } catch {
                guard !Task.isCancelled else { return }
                self.error = error.localizedDescription
            }
            loading = false
        }
    }

    private func bounded(_ value: CGFloat) -> CGFloat { min(8, max(0.25, value)) }
    private func setScale(_ value: CGFloat) { scale = bounded(value); gestureScale = scale }
    private func reset() { scale = 1; gestureScale = 1; offset = .zero; dragOrigin = .zero }
}

@MainActor
struct ArtworkThumbnail: View {
    let work: SavedWork
    let renderer: ArtworkRenderer
    @State private var image: CGImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 6).fill(.quaternary.opacity(0.3))
            if let image {
                Image(decorative: image, scale: 1).resizable().scaledToFit().padding(4)
            } else if failed {
                Image(systemName: "exclamationmark.triangle").foregroundStyle(.secondary)
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .task(id: work.id) {
            do {
                let rendered = try await renderer.image(svg: work.svg, targetWidth: 160, targetHeight: 160)
                guard !Task.isCancelled else { return }
                image = rendered
            } catch {
                guard !Task.isCancelled else { return }
                failed = true
            }
        }
    }
}
