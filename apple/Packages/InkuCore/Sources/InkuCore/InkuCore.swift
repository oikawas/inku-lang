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

/// A synchronous owned-byte facade. Hosts schedule heavy calls off MainActor.
public enum InkuCore {
    public static var versionReport: String { InkuCoreBindings.versionReport() }
    public static var rasterAPIVersion: String { InkuCoreBindings.rasterApiVersion() }
    public static var canvasRegistry: Data { Data(InkuCoreBindings.canvasRegistry().utf8) }

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
}
