import CoreGraphics
import CoreText
import InkuCore
import InkuPersistence
import SwiftUI
#if os(macOS)
import AppKit
#elseif os(iOS)
import UIKit
#endif

@MainActor
struct ArtworkCanvas: View {
    /// `.embedded` keeps the framed preview used by dialogs and the library. `.workspace` is the Web canvas area:
    /// no frame or outer margin, the Web fit (CanvasPanel.svelte:587-598) and the zoom capsule over the work.
    enum Style { case embedded, workspace }

    let svg: String
    let renderer: DisplayRenderer
    var caption = ""
    var style = Style.embedded
    var showsZoomControls = true
    /// A canvas too narrow for the zoom capsule between the corner rows carries it at the top instead.
    var zoomControlsAtTop = false
    /// The saved canvas proportion (width / height). The Web sizes the base box from it, not from the picture.
    var aspectRatio: Double? = nil
    /// The workspace keeps its zoom and pan here while the canvas view is rebuilt (tab switch, refine panel).
    var viewport: Binding<CanvasViewport>? = nil
    @Environment(DisplaySettings.self) private var display
    @Environment(\.displayScale) private var displayScale
    @State private var picture = CanvasPicture()
    @State private var localViewport = CanvasViewport()
    @State private var gestureScale: CGFloat = 1
    @State private var dragOrigin = CGSize.zero
    @State private var imageAspect: CGFloat = 1
    @State private var fitZoom: CGFloat = 1

    private var scale: CGFloat {
        get { viewport?.wrappedValue.scale ?? localViewport.scale }
        nonmutating set { if let viewport { viewport.wrappedValue.scale = newValue } else { localViewport.scale = newValue } }
    }
    private var offset: CGSize {
        get { viewport?.wrappedValue.offset ?? localViewport.offset }
        nonmutating set { if let viewport { viewport.wrappedValue.offset = newValue } else { localViewport.offset = newValue } }
    }

    var body: some View {
        switch style {
        case .embedded: embeddedBody
        case .workspace: workspaceBody
        }
    }

    /// A kept viewport belongs to one picture; the gesture origins resume from it.
    private func adoptViewport() {
        guard let viewport else { return }
        let key = svg.hashValue
        if viewport.wrappedValue.svgKey != key { viewport.wrappedValue = CanvasViewport(svgKey: key) }
        gestureScale = scale; dragOrigin = offset
    }

    private var workspaceBody: some View {
        GeometryReader { geometry in
            let fit = webFit(in: geometry.size)
            interactiveCanvas(size: geometry.size, box: fit.box)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .inkuTooltip(display.tooltip("マウスホイールで拡大・縮小、ドラッグで移動します。"))
                .task(id: requestKey(box: fit.box)) { await render(box: fit.box) }
                .onChange(of: fit.zoom, initial: true) { _, zoom in fitZoom = zoom }
        }
        .overlay(alignment: zoomControlsAtTop ? .top : .bottom) {
            if showsZoomControls { zoomCapsule.padding(zoomControlsAtTop ? .top : .bottom, 14) }
        }
        .onAppear { adoptViewport() }
        .onChange(of: svg) { _, _ in picture.clear(); reset() }
    }

    /// The Web fit for this canvas: the saved proportion, or the picture's own until a saved one is known.
    private func webFit(in size: CGSize) -> (box: CGSize, zoom: CGFloat) {
        let saved = aspectRatio.map { CGFloat($0) }.flatMap { $0.isFinite && $0 > 0 ? $0 : nil }
        return CanvasInteraction.webFit(area: size, ratio: saved ?? imageAspect)
    }

    /// Web `.zoom-controls`: one capsule with −, the percentage, ＋ and a fit button, 14pt above the bottom.
    private var zoomCapsule: some View {
        HStack(spacing: 0) {
            Button { setScale(scale / 1.25) } label: { Text("−").inkuFont(16).frame(width: 32, height: 28).contentShape(Rectangle()) }
                .accessibilityLabel(display.localized("縮小"))
                .disabled(scale <= CanvasInteraction.minimumScale)
                .inkuTooltip(display.tooltip("縮小", serverKey: "tooltipCanvasZoomOut"))
            Text("\(Int((fitZoom * scale * 100).rounded()))%").inkuFont(11, weight: .medium).monospacedDigit()
                .frame(minWidth: 38)
            Button { setScale(scale * 1.25) } label: { Text("＋").inkuFont(16).frame(width: 32, height: 28).contentShape(Rectangle()) }
                .accessibilityLabel(display.localized("拡大"))
                .disabled(scale >= CanvasInteraction.maximumScale)
                .inkuTooltip(display.tooltip("拡大", serverKey: "tooltipCanvasZoomIn"))
            Rectangle().fill(InkuColor.border).frame(width: 1, height: 28)
            Button { reset() } label: { Text("⊙").inkuFont(11).foregroundStyle(.secondary).frame(width: 32, height: 28).contentShape(Rectangle()) }
                .accessibilityLabel(display.localized("用紙に合わせる"))
                .inkuTooltip(display.tooltip("拡大率と位置をリセット", serverKey: "tooltipCanvasZoomReset"))
        }
        .buttonStyle(.plain)
        .background(Capsule().fill(InkuColor.floating))
        .overlay(Capsule().stroke(InkuColor.border2))
        .clipShape(Capsule())
        .shadow(color: .black.opacity(0.1), radius: 3, y: 1)
        .disabled(picture.image == nil)
    }

    private var embeddedBody: some View {
        VStack(spacing: 8) {
            GeometryReader { geometry in
                interactiveCanvas(size: geometry.size, box: nil)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.quaternary))
                    .inkuTooltip(display.tooltip("マウスホイールで拡大・縮小、ドラッグで移動します。"))
                    .task(id: requestKey(box: CGSize(width: geometry.size.width - 36, height: geometry.size.height - 36))) {
                        await render(box: CGSize(width: geometry.size.width - 36, height: geometry.size.height - 36))
                    }
            }
            .frame(minHeight: 280, maxHeight: .infinity)

            HStack(spacing: 12) {
                Spacer(minLength: 12)
                Button { setScale(scale / 1.25) } label: { Image(systemName: "minus.magnifyingglass") }
                    .accessibilityLabel(display.localized("縮小"))
                    .disabled(scale <= CanvasInteraction.minimumScale)
                    .inkuTooltip(display.tooltip("縮小", serverKey: "tooltipCanvasZoomOut"))
                Text(Double(scale).formatted(.percent.precision(.fractionLength(0)))).inkuFont(12).monospacedDigit()
                Button { setScale(scale * 1.25) } label: { Image(systemName: "plus.magnifyingglass") }
                    .accessibilityLabel(display.localized("拡大"))
                    .disabled(scale >= CanvasInteraction.maximumScale)
                    .inkuTooltip(display.tooltip("拡大", serverKey: "tooltipCanvasZoomIn"))
                Button(display.localized("用紙に合わせる")) { reset() }
                    .inkuTooltip(display.tooltip("拡大率と位置をリセット", serverKey: "tooltipCanvasZoomReset"))
            }
            .buttonStyle(.borderless)
            .inkuFont(12)
            .disabled(picture.image == nil)
        }
        .onChange(of: svg) { _, _ in picture.clear(); reset() }
    }

    @ViewBuilder private func interactiveCanvas(size: CGSize, box: CGSize?) -> some View {
        #if os(macOS)
        CanvasWheelSurface(onScroll: applyWheel) { canvasContent(size: size, box: box) }
        #else
        canvasContent(size: size, box: box)
        #endif
    }

    @ViewBuilder private func fitted(_ image: CGImage, box: CGSize?) -> some View {
        if let box {
            // Web `.canvas-box`: the work's own box with `0 8px 32px rgba(0,0,0,.18)`.
            Image(decorative: image, scale: 1)
                .resizable().interpolation(.high).scaledToFit()
                .frame(width: box.width, height: box.height)
                .shadow(color: .black.opacity(0.18), radius: 16, y: 8)
        } else {
            Image(decorative: image, scale: 1)
                .resizable().interpolation(.high).scaledToFit()
                .padding(18)
                .shadow(color: .black.opacity(0.08), radius: 8, y: 3)
        }
    }

    private func canvasContent(size: CGSize, box: CGSize?) -> some View {
              let plan = fittedRect(in: size, box: box).flatMap {
                  CanvasInteraction.detailPlan(picture: $0, area: size, scale: scale, offset: offset, pixelScale: displayScale,
                                               limits: InkuCore.displayLayout)
              }
              return ZStack {
                if box == nil { RoundedRectangle(cornerRadius: 14, style: .continuous).fill(.quaternary.opacity(0.3)) }
                if let image = picture.image {
                    fitted(image, box: box)
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
                    detailLayer(size: size, box: box)
                } else if picture.loading {
                    ProgressView(display.localized("作品を表示中"))
                } else if let error = picture.error {
                    ContentUnavailableView(display.localized("作品を表示できません"), systemImage: "exclamationmark.triangle", description: Text(error))
                } else {
                    ContentUnavailableView(display.localized("作品"), systemImage: "paintpalette", description: Text(display.localized("生成した作品や保存作品をここに表示します。")))
                }
                if picture.image != nil, display.preferences.captionVisible, !caption.isEmpty {
                    if box == nil { captionOverlay(size: size) } else { workspaceCaption(size: size) }
                }
                if (picture.loading || picture.windowLoading) && picture.image != nil { ProgressView().controlSize(.small).padding(12).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing) }
              }
              .frame(width: size.width, height: size.height)
              .task(id: DetailRequest(svg: svg, plan: plan)) {
                  await picture.loadWindow(svg: svg, plan: plan, renderer: renderer)
              }
    }

    /// The fitted picture at 100% in the canvas area: centered in the Web box, or inside the embedded frame's margin.
    private func fittedRect(in size: CGSize, box: CGSize?) -> CGRect? {
        guard let image = picture.image, image.width > 0, image.height > 0 else { return nil }
        let container = box.map { CGRect(x: (size.width - $0.width) / 2, y: (size.height - $0.height) / 2, width: $0.width, height: $0.height) }
            ?? CGRect(origin: .zero, size: size).insetBy(dx: 18, dy: 18)
        return CanvasInteraction.fittedPicture(aspect: CGFloat(image.width) / CGFloat(image.height), in: container)
    }

    /// The last complete window, and over it the one being drawn. Each keeps its place under later zoom and pan
    /// until its replacement is drawn.
    @ViewBuilder private func detailLayer(size: CGSize, box: CGSize?) -> some View {
        if scale > 1.001, let fitted = fittedRect(in: size, box: box) {
            let zoomed = CanvasInteraction.zoomedPicture(fitted, area: size, scale: scale, offset: offset)
            ZStack(alignment: .topLeading) {
                ForEach(Array([picture.window, picture.pendingWindow].compactMap { $0 }.enumerated()), id: \.offset) { _, window in
                    Image(decorative: window.image, scale: 1)
                        .resizable().interpolation(.high)
                        .frame(width: window.unit.width * zoomed.width, height: window.unit.height * zoomed.height)
                        .offset(x: zoomed.minX + window.unit.minX * zoomed.width, y: zoomed.minY + window.unit.minY * zoomed.height)
                }
            }
            .frame(width: size.width, height: size.height, alignment: .topLeading)
            .clipped()
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }

    private func applyWheel(_ deltaY: CGFloat) -> Bool {
        guard picture.image != nil, deltaY != 0 else { return false }
        setScale(CanvasInteraction.wheelScale(from: scale, deltaY: deltaY))
        return true
    }

    private struct RequestKey: Hashable { let svg: String; let width: UInt32; let height: UInt32 }
    private struct DetailRequest: Equatable { let svg: String; let plan: CanvasDetailPlan? }
    private func requestKey(box: CGSize) -> RequestKey {
        // The whole is drawn for 100%; a zoomed canvas adds the visible window on top (detailLayer).
        var width = max(128, min(4096, ceil(max(1, box.width) * displayScale / 128) * 128))
        var height = max(128, min(4096, ceil(max(1, box.height) * displayScale / 128) * 128))
        let factor = min(1, sqrt(8_000_000 / (width * height)))
        width *= factor; height *= factor
        return RequestKey(svg: svg, width: UInt32(width), height: UInt32(height))
    }
    private func render(box: CGSize) async {
        let request = requestKey(box: box)
        await picture.load(svg: svg, width: request.width, height: request.height, renderer: renderer)
        if let image = picture.image, image.height > 0 { imageAspect = CGFloat(image.width) / CGFloat(image.height) }
    }
    private func captionOverlay(size: CGSize) -> some View {
        HStack(alignment: .bottom) {
            if display.preferences.captionPosition == "right" { Spacer(minLength: 0) }
            Group {
                if display.preferences.captionVertical && CanvasInteraction.supportsVerticalCaption(caption) {
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

    /// Web `.instruction-caption`: a dark plate 10% in from each side, 58pt above the bottom, three lines at most.
    /// The vertical form runs from 58pt to 58pt at the chosen side.
    private func workspaceCaption(size: CGSize) -> some View {
        let right = display.preferences.captionPosition == "right"
        return Group {
            if display.preferences.captionVertical && CanvasInteraction.supportsVerticalCaption(caption) {
                VerticalCaption(text: caption, color: Color(white: 0.99))
                    .frame(width: min(size.width * 0.4, 13 * 14 * 1.55), height: max(80, size.height - 116))
                    .padding(.vertical, 9).padding(.horizontal, 14)
                    .background(Color(white: 0.07, opacity: 0.78), in: RoundedRectangle(cornerRadius: 8))
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: right ? .trailing : .leading)
                    .padding(.horizontal, 12).padding(.vertical, 58)
            } else {
                Text(caption).inkuFont(14).lineSpacing(14 * 0.55).lineLimit(3)
                    .multilineTextAlignment(right ? .trailing : .leading)
                    .foregroundStyle(Color(white: 0.99))
                    .frame(maxWidth: .infinity, alignment: right ? .trailing : .leading)
                    .padding(.vertical, 9).padding(.horizontal, 14)
                    .background(Color(white: 0.07, opacity: 0.78), in: RoundedRectangle(cornerRadius: 8))
                    .shadow(color: .black.opacity(0.22), radius: 9, y: 4)
                    .padding(.horizontal, size.width * 0.1)
                    .frame(maxHeight: .infinity, alignment: .bottom)
                    .padding(.bottom, 58)
            }
        }
        .textSelection(.enabled)
        .allowsHitTesting(true)
    }

    private func bounded(_ value: CGFloat) -> CGFloat { CanvasInteraction.boundedScale(value) }
    private func clearPanWhenFitted() {
        offset = CanvasInteraction.offset(for: scale, current: offset)
        if scale <= 1 { dragOrigin = .zero }
    }
    private func setScale(_ value: CGFloat) { scale = bounded(value); gestureScale = scale; clearPanWhenFitted() }
    private func reset() {
        scale = 1; gestureScale = 1; offset = .zero; dragOrigin = .zero
        viewport?.wrappedValue.svgKey = svg.hashValue
    }
}

/// What the canvas shows: the latest request's picture, and the progress mark only while that
/// request is drawing. Every request takes a new generation; an older one changes nothing.
@MainActor @Observable
public final class CanvasPicture {
    public private(set) var image: CGImage?
    public private(set) var loading = false
    public private(set) var error: String?
    /// The work `image` belongs to. A coarse whole replaces only another work's picture or none.
    public private(set) var imageSVG: String?
    public private(set) var painter: DisplayRenderer.Painter?
    private var generation: UInt64 = 0

    /// A window of the zoomed picture and where it lies, as a fraction of the picture.
    public struct Window: Sendable { public let image: CGImage; public let unit: CGRect }
    /// The last complete window.
    public private(set) var window: Window?
    /// The window being drawn, its undrawn tiles transparent.
    public private(set) var pendingWindow: Window?
    public private(set) var windowLoading = false
    private var windowGeneration: UInt64 = 0

    public init() {}

    public func clear() { image = nil; imageSVG = nil; painter = nil; error = nil; window = nil; pendingWindow = nil }

    /// Draw the visible window of the zoomed picture, or drop the windows at 100% or below (`plan` nil).
    /// A failed window leaves the enlarged whole in view.
    public func loadWindow(svg: String, plan: CanvasDetailPlan?, renderer: DisplayRenderer) async {
        windowGeneration &+= 1
        let mine = windowGeneration
        guard let plan, !svg.isEmpty else { window = nil; pendingWindow = nil; windowLoading = false; return }
        do {
            // Coalesce wheel and drag events; the windows already drawn stay until this one is ready.
            try await Task.sleep(for: .milliseconds(120))
            windowLoading = true
            for try await frame in renderer.window(svg: svg, region: plan.region) {
                guard windowGeneration == mine, imageSVG == svg else { return }
                let drawn = Window(image: frame.image, unit: CanvasDetailPlan.unit(of: frame.region))
                if frame.complete { window = drawn; pendingWindow = nil } else { pendingWindow = drawn }
            }
            try Task.checkCancellation()
            guard windowGeneration == mine else { return }
            windowLoading = false
        } catch {
            // A cancelled request with no request after it leaves no progress mark behind.
            guard windowGeneration == mine else { return }
            windowLoading = false
        }
    }

    public func load(svg: String, width: UInt32, height: UInt32, renderer: DisplayRenderer) async {
        generation &+= 1
        let mine = generation
        guard !svg.isEmpty else { clear(); loading = false; return }
        do {
            // Coalesce resize and pinch events; the old frame stays visible until its replacement is ready.
            try await Task.sleep(for: .milliseconds(120))
            loading = true; error = nil
            for try await frame in renderer.whole(svg: svg, width: width, height: height) {
                guard generation == mine else { return }
                if frame.coarse, image != nil, imageSVG == svg { continue }
                image = frame.image; imageSVG = svg; painter = frame.painter
            }
            try Task.checkCancellation()
            guard generation == mine else { return }
            loading = false
        } catch {
            // A cancelled request with no request after it leaves no progress mark behind.
            guard generation == mine else { return }
            loading = false
            if !(error is CancellationError), !Task.isCancelled { self.error = error.localizedDescription }
        }
    }
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
    var color: Color? = nil
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
                cg.setFillColor(color.map { NSColor($0).cgColor } ?? NSColor.labelColor.cgColor)
                #elseif os(iOS)
                cg.setFillColor(color.map { UIColor($0).cgColor } ?? UIColor.label.cgColor)
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
    @Environment(DisplaySettings.self) private var display: DisplaySettings?
    @State private var image: CGImage?
    @State private var failed = false

    /// HistoryThumbnail.svelte:51-62: one dot for both layers, its title naming the layer that fell.
    private var fallbackMarkLabel: String? {
        guard let display else { return nil }
        let labels = [work.interpretFallback.flatMap { $0.isEmpty ? nil : display.webCopy("interpretFallbackBadge", "解釈フォールバック") },
                      FallbackCopy.composeReason(work.composeFallback).map { _ in display.webCopy("composeFallbackBadge", "作曲フォールバック") }]
            .compactMap { $0 }
        return labels.isEmpty ? nil : labels.joined(separator: " / ")
    }

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
        .overlay(alignment: .topTrailing) {
            if let label = fallbackMarkLabel, let display {
                Circle().fill(Color(red: 0.878, green: 0.659, blue: 0.314))
                    .overlay(Circle().stroke(Color(red: 0.42, green: 0.267, blue: 0.063)))
                    .frame(width: 7, height: 7)
                    .padding(3)
                    .accessibilityLabel(label)
                    .inkuTooltip(display.tooltipValue(label))
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
