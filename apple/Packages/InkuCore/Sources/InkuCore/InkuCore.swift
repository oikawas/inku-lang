import Foundation
import InkuCoreBindings

/// Immutable, host-owned presentation pixels lifted by the generated binding.
public struct RasterImage: Sendable {
    public let width: UInt32
    public let height: UInt32
    public let stride: UInt32
    public let pixelFormat: String
    public let pixels: Data

    init(_ frame: InkuCoreBindings.RasterFrame) {
        width = frame.width
        height = frame.height
        stride = frame.stride
        pixelFormat = frame.pixelFormat
        pixels = frame.pixels
    }
}

public enum CoreFailure: Error, Sendable {
    case rasterRefused(code: String, message: String)
    /// Skia display does not take this work; show it with `PreparedSVG` and count the code.
    case displayUnsupported(code: String, message: String)
    case displayRefused(code: String, message: String)
    case emptySeedText
    case internalInvariant
}

/// One immutable Rust-owned SVG scene. The last reference releases its tree.
public struct PreparedSVG: Sendable {
    private let scene: InkuCoreBindings.RasterScene
    fileprivate init(_ scene: InkuCoreBindings.RasterScene) { self.scene = scene }
    public var sourceByteCount: UInt64 { scene.sourceByteCount() }
    /// Cache admission weight, not an assertion about allocator bytes or RSS.
    public var cacheCostBytes: UInt64 { scene.cacheCostBytes() }
    public var intrinsicWidth: Double { scene.intrinsicWidth() }
    public var intrinsicHeight: Double { scene.intrinsicHeight() }

    public func rasterize(targetWidth: UInt32? = nil, targetHeight: UInt32? = nil) throws -> RasterImage {
        try lift { try scene.rasterize(targetWidth: targetWidth, targetHeight: targetHeight) }
    }
    public func region(fullWidth: UInt32, fullHeight: UInt32, x: UInt32, y: UInt32, width: UInt32, height: UInt32) throws -> RasterImage {
        try lift { try scene.region(fullWidth: fullWidth, fullHeight: fullHeight, x: x, y: y, width: width, height: height) }
    }
    private func lift(_ body: () throws -> InkuCoreBindings.RasterFrame) throws -> RasterImage {
        do { return RasterImage(try body()) }
        catch InkuCoreBindings.RasterFailure.Refused(let code, let message) { throw CoreFailure.rasterRefused(code: code, message: message) }
        catch InkuCoreBindings.RasterFailure.InternalInvariant { throw CoreFailure.internalInvariant }
    }
}

/// A window on a canvas `fullWidth` × `fullHeight` pixels.
public struct DisplayRegion: Sendable, Equatable {
    public let fullWidth: UInt32
    public let fullHeight: UInt32
    public let x: UInt32
    public let y: UInt32
    public let width: UInt32
    public let height: UInt32

    public init(fullWidth: UInt32, fullHeight: UInt32, x: UInt32, y: UInt32, width: UInt32, height: UInt32) {
        self.fullWidth = fullWidth
        self.fullHeight = fullHeight
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }

    init(_ region: InkuCoreBindings.DisplayRegion) {
        self.init(fullWidth: region.fullWidth, fullHeight: region.fullHeight, x: region.x, y: region.y,
                  width: region.width, height: region.height)
    }

    var binding: InkuCoreBindings.DisplayRegion {
        InkuCoreBindings.DisplayRegion(fullWidth: fullWidth, fullHeight: fullHeight, x: x, y: y, width: width, height: height)
    }
}

/// One work recorded by Skia for the screen. Its windows may be drawn on several threads at once.
/// The sides the display is drawn in, and the largest window and full canvas the core draws.
public struct DisplayLayout: Sendable {
    /// The coarse whole's longest side.
    public let coarseSide: UInt32
    public let tileSide: UInt32
    public let maxWindowSide: UInt32
    public let maxWindowPixels: UInt64
    /// The full canvas a window is cut from.
    public let maxCanvasSide: UInt32

    fileprivate init(_ layout: InkuCoreBindings.DisplayLayout) {
        coarseSide = layout.coarseSide
        tileSide = layout.tileSide
        maxWindowSide = layout.maxWindowSide
        maxWindowPixels = layout.maxWindowPixels
        maxCanvasSide = layout.maxCanvasSide
    }

    var binding: InkuCoreBindings.DisplayLayout {
        InkuCoreBindings.DisplayLayout(coarseSide: coarseSide, tileSide: tileSide, maxWindowSide: maxWindowSide,
                                       maxWindowPixels: maxWindowPixels, maxCanvasSide: maxCanvasSide)
    }
}

public struct PreparedDisplay: Sendable {
    private let scene: InkuCoreBindings.DisplayScene
    fileprivate init(_ scene: InkuCoreBindings.DisplayScene) { self.scene = scene }
    public var sourceByteCount: UInt64 { scene.sourceByteCount() }
    /// Skia's estimate of the recorded picture, for cache weight.
    public var pictureByteCount: UInt64 { scene.pictureByteCount() }
    public var intrinsicWidth: Double { scene.intrinsicWidth() }
    public var intrinsicHeight: Double { scene.intrinsicHeight() }
    /// How many places the display-time compatibility rewrite changed (href, ellipse, seed).
    public var rewrites: (href: UInt64, ellipse: UInt64, seed: UInt64) {
        let rewrites = scene.rewrites()
        return (rewrites.href, rewrites.ellipse, rewrites.seed)
    }

    public func rasterize(targetWidth: UInt32? = nil, targetHeight: UInt32? = nil) throws -> RasterImage {
        try lift { try scene.rasterize(targetWidth: targetWidth, targetHeight: targetHeight) }
    }
    /// The whole work fitted to the box, as a window to draw in tiles.
    public func whole(targetWidth: UInt32? = nil, targetHeight: UInt32? = nil) throws -> DisplayRegion {
        do { return DisplayRegion(try scene.whole(targetWidth: targetWidth, targetHeight: targetHeight)) }
        catch let failure as InkuCoreBindings.DisplayFailure { throw CoreFailure(failure) }
    }
    public func region(_ region: DisplayRegion) throws -> RasterImage {
        try lift { try scene.region(region: region.binding) }
    }
    /// One window joined in the core from tiles drawn on several threads.
    public func composite(window: DisplayRegion) throws -> DisplayComposite {
        do { return DisplayComposite(try scene.composite(window: window.binding)) }
        catch let failure as InkuCoreBindings.DisplayFailure { throw CoreFailure(failure) }
    }
    private func lift(_ body: () throws -> InkuCoreBindings.RasterFrame) throws -> RasterImage {
        do { return RasterImage(try body()) }
        catch let failure as InkuCoreBindings.DisplayFailure { throw CoreFailure(failure) }
    }
}

extension CoreFailure {
    init(_ failure: InkuCoreBindings.DisplayFailure) {
        switch failure {
        case .Unsupported(let code, let message): self = .displayUnsupported(code: code, message: message)
        case .Refused(let code, let message): self = .displayRefused(code: code, message: message)
        case .InternalInvariant: self = .internalInvariant
        }
    }
}

/// A synchronous owned-byte facade. Hosts schedule heavy calls off MainActor.
public enum InkuCore {
    public static let svgConsumerMaximumBytes: UInt64 = 64 * 1_024 * 1_024
    public static var versionReport: String { InkuCoreBindings.versionReport() }
    public static var rasterAPIVersion: String { InkuCoreBindings.rasterApiVersion() }
    public static var canvasRegistry: Data { Data(InkuCoreBindings.canvasRegistry().utf8) }

    public static func descriptionHash(_ text: String) -> String {
        InkuCoreBindings.descriptionHash(text: text)
    }

    public static func renderHash(itemJSON: String) -> String? {
        InkuCoreBindings.renderHash(itemJson: itemJSON)
    }

    public static func canonicalJSON(_ valueJSON: String) -> String? {
        InkuCoreBindings.canonicalJson(valueJson: valueJSON)
    }

    public static func resolveInstructionLanguage(text: String, requested: String?, fallback: String) -> String? {
        InkuCoreBindings.resolveInstructionLanguage(text: text, requested: requested, fallback: fallback)
    }

    public static func normalizeInstructionLanguage(value: String?, defaultLanguage: String) -> String? {
        InkuCoreBindings.normalizeInstructionLanguage(value: value, defaultLanguage: defaultLanguage)
    }

    public static func descriptionWithoutLabels(_ text: String) -> String {
        InkuCoreBindings.descriptionWithoutLabels(text: text)
    }

    /// `[[start, end, kind], ...]`, with Unicode scalar offsets owned by the shared core.
    public static func descriptionLabelSpans(_ text: String) -> Data {
        Data(InkuCoreBindings.descriptionLabelSpans(text: text).utf8)
    }

    public static func renderSeedWords(fromText text: String) throws -> (seed: String, text: String) {
        guard let derived = InkuCoreBindings.renderSeedFromText(seedText: text) else {
            throw CoreFailure.emptySeedText
        }
        return (derived.renderSeed, derived.seedText)
    }

    public static func renderSeed(fromText text: String) throws -> String {
        try renderSeedWords(fromText: text).seed
    }

    public static func countDescriptionMeter(text: String, languageCode: String, dictionaryDirectory: String) -> Data {
        InkuCoreBindings.countDescriptionMeter(text: text, languageCode: languageCode, dictionaryDirectory: dictionaryDirectory)
    }

    public static func prepareSVG(svg: String) throws -> PreparedSVG {
        do { return PreparedSVG(try InkuCoreBindings.prepareRasterScene(svg: svg)) }
        catch InkuCoreBindings.RasterFailure.Refused(let code, let message) { throw CoreFailure.rasterRefused(code: code, message: message) }
        catch InkuCoreBindings.RasterFailure.InternalInvariant { throw CoreFailure.internalInvariant }
    }

    public static var displayAPIVersion: String { InkuCoreBindings.displayApiVersion() }
    public static var displayLayout: DisplayLayout { DisplayLayout(InkuCoreBindings.displayLayout()) }

    public static func prepareDisplay(svg: String) throws -> PreparedDisplay {
        do { return PreparedDisplay(try InkuCoreBindings.prepareDisplayScene(svg: svg)) }
        catch let failure as InkuCoreBindings.DisplayFailure { throw CoreFailure(failure) }
    }

    /// The tiles covering a window, nearest to its centre first.
    public static func displayTiles(window: DisplayRegion, side: UInt32) -> [DisplayRegion] {
        InkuCoreBindings.displayTiles(window: window.binding, side: side).map(DisplayRegion.init)
    }

    public static func step(snapshot: Data, input: Data) -> Data {
        InkuCoreBindings.step(snapshotBytes: snapshot, inputEnvelopeBytes: input)
    }

    public static func stepSvgLimited(snapshot: Data, input: Data, maxSvgBytes: UInt64) -> (json: Data, svg: String?) {
        let output = InkuCoreBindings.stepSvgLimited(snapshotBytes: snapshot, inputEnvelopeBytes: input, maxSvgBytes: maxSvgBytes)
        return (output.jsonBytes, output.svg)
    }

    public static func providerAttempt(snapshot: Data) -> Data {
        InkuCoreBindings.providerAttempt(snapshotBytes: snapshot)
    }

    /// `inku.composition-ranges.v1`: the named composition ranges and corners the hosts fold in their display.
    public static func compositionRanges() -> Data {
        Data(InkuCoreBindings.compositionRanges().utf8)
    }

    /// `inku.composition-recompose.v1` for `{config, source, mode, seed, work_id}`: the source with its numeric ranges
    /// chosen again by principle or by chance, or why they stay.
    public static func recompose(_ input: Data) -> Data {
        InkuCoreBindings.recompose(inputBytes: input)
    }

    /// `inku.touch-change.v1` for `{config, source, tools}`. Empty tools read the changeable sentences.
    public static func retouch(_ input: Data) -> Data {
        InkuCoreBindings.retouch(inputBytes: input)
    }

    public static func savedVariants(_ input: Data) -> Data {
        InkuCoreBindings.savedVariants(inputBytes: input)
    }

    public static func providerWire(_ input: Data) -> Data {
        InkuCoreBindings.providerWire(inputBytes: input)
    }

    /// The experimental 3D viewer's input (`inku.ddl3d.v1`, Web `snapshot()`), shared with Android:
    /// `{"score": "<stored Score text>", "metadata": "<render metadata object text>"}` in, `{"json": "<input>"}` or
    /// `{"error": "<reason>"}` out.
    public static func ddl3dSnapshot(_ input: Data) -> Data {
        InkuCoreBindings.ddl3dSnapshot(inputBytes: input)
    }

    /// `inku.completion-range-states.v1` for `{config, source, completion_ranges}`: each range a completion wrote,
    /// as completed, numbers changed or words changed, with UTF-16 positions in the source.
    public static func completionRangeStates(_ input: Data) -> Data {
        InkuCoreBindings.completionRangeStates(inputBytes: input)
    }

    public static func compile(_ input: Data) -> Data {
        InkuCoreBindings.compileDocument(inputBytes: input)
    }

    public static func renderCompiled(_ input: Data) -> Data {
        InkuCoreBindings.renderCompiled(inputBytes: input)
    }

    public static func renderSaved(_ input: Data) -> Data {
        InkuCoreBindings.renderSaved(inputBytes: input)
    }

    public static func renderCompiledSvgLimited(_ input: Data, maxSvgBytes: UInt64) -> (json: Data, svg: String?) {
        let output = InkuCoreBindings.renderCompiledSvgLimited(inputBytes: input, maxSvgBytes: maxSvgBytes)
        return (output.jsonBytes, output.svg)
    }

    public static func renderSavedSvgLimited(_ input: Data, maxSvgBytes: UInt64) -> (json: Data, svg: String?) {
        let output = InkuCoreBindings.renderSavedSvgLimited(inputBytes: input, maxSvgBytes: maxSvgBytes)
        return (output.jsonBytes, output.svg)
    }

    public static func resolvePalette(_ input: Data) -> Data {
        InkuCoreBindings.resolvePalette(inputBytes: input)
    }

    public static func stage1SystemProjection(languageCode: String) -> String {
        InkuCoreBindings.stage1SystemProjection(languageCode: languageCode)
    }

    public static func resolveMacroCatalog(_ input: Data) -> Data {
        InkuCoreBindings.resolveMacroCatalog(inputBytes: input)
    }

    public static func explainPluginDiagnostics(_ input: Data) -> Data {
        InkuCoreBindings.explainPluginDiagnostics(inputBytes: input)
    }

    public static func migrateSaijikiV1(_ input: Data) -> Data {
        InkuCoreBindings.migrateSaijikiV1(inputBytes: input)
    }

    public static func rasterize(
        svg: String,
        targetWidth: UInt32? = nil,
        targetHeight: UInt32? = nil
    ) throws -> RasterImage {
        do {
            return RasterImage(try InkuCoreBindings.rasterizeSvg(
                svg: svg, targetWidth: targetWidth, targetHeight: targetHeight
            ))
        } catch InkuCoreBindings.RasterFailure.Refused(let code, let message) {
            throw CoreFailure.rasterRefused(code: code, message: message)
        } catch InkuCoreBindings.RasterFailure.InternalInvariant {
            throw CoreFailure.internalInvariant
        }
    }

    public static func rasterizeRegion(svg: String, fullWidth: UInt32, fullHeight: UInt32, x: UInt32, y: UInt32, width: UInt32, height: UInt32) throws -> RasterImage {
        do {
            return RasterImage(try InkuCoreBindings.rasterizeSvgRegion(svg: svg, fullWidth: fullWidth, fullHeight: fullHeight, x: x, y: y, width: width, height: height))
        } catch InkuCoreBindings.RasterFailure.Refused(let code, let message) {
            throw CoreFailure.rasterRefused(code: code, message: message)
        } catch InkuCoreBindings.RasterFailure.InternalInvariant {
            throw CoreFailure.internalInvariant
        }
    }
}
