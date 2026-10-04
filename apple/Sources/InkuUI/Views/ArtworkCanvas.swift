import CoreGraphics
import CoreText
import InkuPersistence
import SwiftUI
#if os(macOS)
import AppKit
#elseif os(iOS)
import UIKit
#endif

@MainActor
struct ArtworkCanvas: View {
    let svg: String
    let renderer: ArtworkRenderer
    var caption = ""
    @Environment(DisplaySettings.self) private var display
    @Environment(\.displayScale) private var displayScale
    @State private var image: CGImage?
    @State private var error: String?
    @State private var loading = false
    @State private var scale: CGFloat = 1
    @State private var gestureScale: CGFloat = 1
    @State private var offset = CGSize.zero
    @State private var dragOrigin = CGSize.zero

    var body: some View {
        VStack(spacing: 8) {
            GeometryReader { geometry in
                interactiveCanvas(size: geometry.size)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.quaternary))
                    .help(display.preferences.showTooltips ? display.localized("マウスホイールで拡大・縮小、ドラッグで移動します。") : "")
                    .task(id: requestKey(size: geometry.size)) { await render(size: geometry.size) }
            }
            .frame(minHeight: 280, maxHeight: .infinity)

            HStack(spacing: 12) {
                Spacer(minLength: 12)
                Button { setScale(scale / 1.25) } label: { Image(systemName: "minus.magnifyingglass") }
                    .accessibilityLabel(display.localized("縮小"))
                    .help(display.preferences.showTooltips ? display.localized("縮小") : "")
                    .disabled(scale <= CanvasInteraction.minimumScale)
                Text(Double(scale).formatted(.percent.precision(.fractionLength(0)))).font(.caption.monospacedDigit())
                Button { setScale(scale * 1.25) } label: { Image(systemName: "plus.magnifyingglass") }
                    .accessibilityLabel(display.localized("拡大"))
                    .help(display.preferences.showTooltips ? display.localized("拡大") : "")
                    .disabled(scale >= CanvasInteraction.maximumScale)
                Button(display.localized("用紙に合わせる")) { reset() }
                    .help(display.preferences.showTooltips ? display.localized("拡大率と位置をリセット") : "")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
            .disabled(image == nil)
        }
        .onChange(of: svg) { _, _ in image = nil; error = nil; reset() }
    }

    @ViewBuilder private func interactiveCanvas(size: CGSize) -> some View {
        #if os(macOS)
        CanvasWheelSurface(onScroll: applyWheel) { canvasContent(size: size) }
        #else
        canvasContent(size: size)
        #endif
    }

    private func canvasContent(size: CGSize) -> some View {
              ZStack {
                RoundedRectangle(cornerRadius: 14, style: .continuous).fill(.quaternary.opacity(0.3))
                if let image {
                    Image(decorative: image, scale: 1)
                        .resizable().interpolation(.high).scaledToFit()
                        .padding(18)
                        .shadow(color: .black.opacity(0.08), radius: 8, y: 3)
                        .scaleEffect(scale).offset(offset)
                        .gesture(MagnificationGesture()
                            .onChanged { value in
                                scale = bounded(gestureScale * value)
                                clearPanWhenFitted()
                            }
                            .onEnded { _ in gestureScale = scale })
                        .simultaneousGesture(DragGesture()
                            .onChanged { value in
                                guard scale > 1 else { clearPanWhenFitted(); return }
                                offset = CGSize(width: dragOrigin.width + value.translation.width,
                                                height: dragOrigin.height + value.translation.height)
                            }
                            .onEnded { _ in dragOrigin = offset })
                        .accessibilityLabel(display.localized("作品"))
                } else if loading {
                    ProgressView(display.localized("作品を表示中"))
                } else if let error {
                    ContentUnavailableView(display.localized("作品を表示できません"), systemImage: "exclamationmark.triangle", description: Text(error))
                } else {
                    ContentUnavailableView(display.localized("作品"), systemImage: "paintpalette", description: Text(display.localized("生成した作品や保存作品をここに表示します。")))
                }
                if image != nil, display.preferences.captionVisible, !caption.isEmpty {
                    captionOverlay(size: size)
                }
                if loading && image != nil { ProgressView().controlSize(.small).padding(12).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing) }
              }
    }

    private func applyWheel(_ deltaY: CGFloat) -> Bool {
        guard image != nil, deltaY != 0 else { return false }
        setScale(CanvasInteraction.wheelScale(from: scale, deltaY: deltaY))
        return true
    }

    private struct RequestKey: Hashable { let svg: String; let width: UInt32; let height: UInt32 }
    private func requestKey(size: CGSize) -> RequestKey {
        let magnification = min(3, max(1, scale))
        var width = max(128, min(4096, ceil(max(1, size.width - 36) * displayScale * magnification / 128) * 128))
        var height = max(128, min(4096, ceil(max(1, size.height - 36) * displayScale * magnification / 128) * 128))
        let factor = min(1, sqrt(8_000_000 / (width * height)))
        width *= factor; height *= factor
        return RequestKey(svg: svg, width: UInt32(width), height: UInt32(height))
    }
    private func render(size: CGSize) async {
        guard !svg.isEmpty else { image = nil; loading = false; return }
        // Coalesce resize and pinch events; the old frame stays visible until its replacement is ready.
        do {
            try await Task.sleep(for: .milliseconds(120))
            let request = requestKey(size: size)
            loading = true; error = nil
            let frame = try await renderer.image(svg: svg, targetWidth: request.width, targetHeight: request.height)
            try Task.checkCancellation()
            image = frame; loading = false
        } catch is CancellationError {} catch {
            guard !Task.isCancelled else { return }
            self.error = error.localizedDescription; loading = false
        }
    }
    private func captionOverlay(size: CGSize) -> some View {
        HStack(alignment: .bottom) {
            if display.preferences.captionPosition == "right" { Spacer(minLength: 0) }
            Group {
                if display.preferences.captionVertical {
                    VerticalCaption(text: caption)
                        .frame(width: min(170, size.width * 0.28), height: min(320, size.height * 0.8))
                } else {
                    Text(caption).font(.system(.callout, design: .serif)).lineLimit(7)
                        .textSelection(.enabled).frame(maxWidth: min(360, size.width * 0.5), alignment: .leading)
                }
            }
            .foregroundStyle(.primary).padding(12)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
            if display.preferences.captionPosition != "right" { Spacer(minLength: 0) }
        }.padding(24).frame(maxHeight: .infinity, alignment: .bottom)
    }

    private func bounded(_ value: CGFloat) -> CGFloat { CanvasInteraction.boundedScale(value) }
    private func clearPanWhenFitted() {
        offset = CanvasInteraction.offset(for: scale, current: offset)
        if scale <= 1 { dragOrigin = .zero }
    }
    private func setScale(_ value: CGFloat) { scale = bounded(value); gestureScale = scale; clearPanWhenFitted() }
    private func reset() { scale = 1; gestureScale = 1; offset = .zero; dragOrigin = .zero }
}

#if os(macOS)
@MainActor private struct CanvasWheelSurface<Content: View>: NSViewRepresentable {
    let onScroll: (CGFloat) -> Bool
    let content: Content
    init(onScroll: @escaping (CGFloat) -> Bool, @ViewBuilder content: () -> Content) {
        self.onScroll = onScroll; self.content = content()
    }
    func makeNSView(context: Context) -> CanvasWheelHostingView {
        let view = CanvasWheelHostingView(rootView: AnyView(content.environment(\.self, context.environment)))
        view.sizingOptions = []
        view.onScroll = onScroll
        return view
    }
    func updateNSView(_ view: CanvasWheelHostingView, context: Context) {
        view.rootView = AnyView(content.environment(\.self, context.environment))
        view.onScroll = onScroll
    }
    static func dismantleNSView(_ view: CanvasWheelHostingView, coordinator: ()) { view.onScroll = nil }
}

@MainActor private final class CanvasWheelHostingView: NSHostingView<AnyView> {
    var onScroll: ((CGFloat) -> Bool)?
    override func scrollWheel(with event: NSEvent) {
        if onScroll?(event.scrollingDeltaY) != true { super.scrollWheel(with: event) }
    }
}
#endif

private struct VerticalCaption: View {
    let text: String
    var body: some View {
        Canvas { context, size in
            context.withCGContext { cg in
                let font = CTFontCreateWithName("HiraginoMincho-W3" as CFString, 15, nil)
                let attributes: [NSAttributedString.Key: Any] = [
                    NSAttributedString.Key(kCTFontAttributeName as String): font,
                    NSAttributedString.Key(kCTVerticalFormsAttributeName as String): true,
                    NSAttributedString.Key(kCTForegroundColorFromContextAttributeName as String): true,
                ]
                let string = NSAttributedString(string: text, attributes: attributes)
                let setter = CTFramesetterCreateWithAttributedString(string)
                let frame = CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0),
                    CGPath(rect: CGRect(origin: .zero, size: size), transform: nil),
                    [kCTFrameProgressionAttributeName: CTFrameProgression.rightToLeft.rawValue] as CFDictionary)
                cg.saveGState()
                #if os(macOS)
                cg.setFillColor(NSColor.labelColor.cgColor)
                #elseif os(iOS)
                cg.setFillColor(UIColor.label.cgColor)
                #endif
                cg.translateBy(x: 0, y: size.height); cg.scaleBy(x: 1, y: -1)
                CTFrameDraw(frame, cg); cg.restoreGState()
            }
        }.accessibilityLabel(text)
    }
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
        .task(id: work.svg) {
            image = nil; failed = false
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
