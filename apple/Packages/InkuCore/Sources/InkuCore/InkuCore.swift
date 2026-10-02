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

/// A synchronous owned-byte facade. Hosts schedule heavy calls off MainActor.
public enum InkuCore {
    public static var versionReport: String { InkuCoreBindings.versionReport() }
    public static var rasterAPIVersion: String { InkuCoreBindings.rasterApiVersion() }
    public static var canvasRegistry: Data { Data(InkuCoreBindings.canvasRegistry().utf8) }

    public static func countDescriptionMeter(text: String, languageCode: String, dictionaryDirectory: String) -> Data {
        InkuCoreBindings.countDescriptionMeter(text: text, languageCode: languageCode, dictionaryDirectory: dictionaryDirectory)
    }

    public static func prepareSVG(svg: String) throws -> PreparedSVG {
        do { return PreparedSVG(try InkuCoreBindings.prepareRasterScene(svg: svg)) }
        catch InkuCoreBindings.RasterFailure.Refused(let code, let message) { throw CoreFailure.rasterRefused(code: code, message: message) }
        catch InkuCoreBindings.RasterFailure.InternalInvariant { throw CoreFailure.internalInvariant }
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
