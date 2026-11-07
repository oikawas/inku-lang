#if os(iOS)
import CoreGraphics
import Foundation
import InkuCore

/// iOS has no `inku-display-gpu` program next to the app. Every window request fails as a Mac without the
/// program does (`gpu_helper_missing`); how iOS draws the zoomed windows is decided with the iOS app.
final class DisplayGPUProcess: @unchecked Sendable {
    struct Failure: Error, Sendable {
        let code: String
        let message: String
    }

    static let checkAbortVariable = "INKU_DISPLAY_GPU_CHECK_ABORT"

    init(helper: URL?, environment: [String: String] = [:]) {}

    var launches: Int { 0 }

    var runningProcessIdentifier: Int32? { nil }

    func window(svg: String, digest: [UInt8], region: DisplayRegion, cancelled: () -> Bool) throws -> CGImage {
        if cancelled() { throw CancellationError() }
        throw Failure(code: "gpu_helper_missing", message: "inku-display-gpu is not next to the app")
    }
}
#endif
