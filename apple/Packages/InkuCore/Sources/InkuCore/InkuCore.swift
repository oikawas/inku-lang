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

    /// Pixels a host joined from display tiles, laid out as the core returns them.
    public init(premultipliedRGBA pixels: Data, width: UInt32, height: UInt32) {
        self.width = width
        self.height = height
        stride = width * 4
        pixelFormat = "rgba8-premultiplied"
        self.pixels = pixels
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

    fileprivate init(_ region: InkuCoreBindings.DisplayRegion) {
        self.init(fullWidth: region.fullWidth, fullHeight: region.fullHeight, x: region.x, y: region.y,
                  width: region.width, height: region.height)
    }

    fileprivate var binding: InkuCoreBindings.DisplayRegion {
        InkuCoreBindings.DisplayRegion(fullWidth: fullWidth, fullHeight: fullHeight, x: x, y: y, width: width, height: height)
    }
}

/// One work recorded by Skia for the screen. Its windows may be drawn on several threads at once.
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
    private func lift(_ body: () throws -> InkuCoreBindings.RasterFrame) throws -> RasterImage {
        do { return RasterImage(try body()) }
        catch let failure as InkuCoreBindings.DisplayFailure { throw CoreFailure(failure) }
    }
}

private extension CoreFailure {
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
    public static var versionReport: String { InkuCoreBindings.versionReport() }
    public static var rasterAPIVersion: String { InkuCoreBindings.rasterApiVersion() }
    public static var canvasRegistry: Data { Data(InkuCoreBindings.canvasRegistry().utf8) }

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
    /// The coarse whole's longest side and the tile side the display is drawn in.
    public static var displayLayout: (coarseSide: UInt32, tileSide: UInt32) {
        let layout = InkuCoreBindings.displayLayout()
        return (layout.coarseSide, layout.tileSide)
    }

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

    public static func providerAttempt(snapshot: Data) -> Data {
        InkuCoreBindings.providerAttempt(snapshotBytes: snapshot)
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
