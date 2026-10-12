import CoreGraphics
import Darwin
import Foundation
import InkuCore
import os

/// The zoomed windows' own process on Apple silicon (author's decisions, 2026-10-11): `inku-display-gpu`
/// (Rust, `core/crates/inku-display-gpu`) draws each window with Skia Graphite on Metal, so a GPU driver
/// that ends that process does not end the app. The pipe format is that crate's `protocol.rs`.
///
/// One request at a time; a request whose canvas moved on while it waited is not sent. When the
/// process ends during a request, the request fails with the way it ended and the end of its standard
/// error, and that work is not sent again in this run. The next work starts the process again.
final class DisplayGPUProcess: @unchecked Sendable {
    struct Failure: Error, Sendable {
        let code: String
        let message: String
    }

    /// Set only by checks to an SVG's SHA-256 (hex): a request for that SVG stops the program.
    static let checkAbortVariable = "INKU_DISPLAY_GPU_CHECK_ABORT"
    /// A request for one window; a GPU that has not answered by then is taken as stuck.
    static let timeout: DispatchTimeInterval = .seconds(60)
    private static let magic: [UInt8] = Array("IKG1".utf8)
    private static let maxPixelBytes = 16_777_216 * 4
    private static let logger = Logger(subsystem: "app.inku", category: "display")

    private let helper: URL?
    private let environment: [String: String]
    /// One request at a time. The fields after it are touched only while it is held.
    private let gate = DispatchSemaphore(value: 1)
    private var process: Process?
    private var input: Pipe?
    private var output: Pipe?
    private var errors: Pipe?
    /// The works the running process has read, by SHA-256.
    private var sent: Set<String> = []
    /// The works whose request ended the process, and how it ended.
    private var ended: [String: String] = [:]
    private let errorTail = OSAllocatedUnfairLock(initialState: Data())
    /// The request the watchdog may stop, and whether it did.
    private let watch = OSAllocatedUnfairLock(initialState: (request: UInt64(0), stopped: false))
    private let launchCount = OSAllocatedUnfairLock(initialState: 0)

    init(helper: URL?, environment: [String: String] = [:]) {
        self.helper = helper
        self.environment = environment
    }

    deinit {
        // Closing its input ends the program after the request it is drawing.
        try? input?.fileHandleForWriting.close()
    }

    /// How many times the program was started.
    var launches: Int { launchCount.withLock { $0 } }

    /// The window `region` of `svg` (SHA-256 `digest`), unless `cancelled` says the canvas moved on.
    func window(svg: String, digest: [UInt8], region: DisplayRegion, cancelled: () -> Bool) throws -> CGImage {
        gate.wait()
        defer { gate.signal() }
        if cancelled() { throw CancellationError() }
        let key = digest.map { String(format: "%02x", $0) }.joined()
        if let how = ended[key] {
            throw Failure(code: "gpu_process_exited", message: "not sent again in this run; it ended inku-display-gpu: \(how)")
        }
        if process == nil { try launch() }
        var includeSVG = !sent.contains(key)
        for _ in 0..<2 {
            let answer: Answer
            do { answer = try exchange(svg: includeSVG ? svg : nil, digest: digest, region: region) }
            catch is PipeEnded { throw stopped(key) }
            switch answer {
            case .image(let image):
                sent.insert(key)
                return image
            case .failure(let code, let message):
                throw Failure(code: code, message: message)
            case .sceneMissing:
                includeSVG = true
            }
        }
        throw Failure(code: "internal_invariant", message: "inku-display-gpu did not keep the work it was just sent")
    }

    private enum Answer {
        case image(CGImage)
        case failure(String, String)
        case sceneMissing
    }

    /// The pipe ended in the middle of a request: the process is gone or going.
    private struct PipeEnded: Error {}

    private func launch() throws {
        guard let helper else {
            throw Failure(code: "gpu_helper_missing", message: "inku-display-gpu is not next to the app")
        }
        let process = Process()
        process.executableURL = helper
        process.environment = ProcessInfo.processInfo.environment.merging(environment) { $1 }
        let input = Pipe(), output = Pipe(), errors = Pipe()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = errors
        let tail = errorTail
        tail.withLock { $0.removeAll() }
        errors.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty else { handle.readabilityHandler = nil; return }
            Self.logger.notice("inku-display-gpu: \(String(decoding: data, as: UTF8.self), privacy: .public)")
            tail.withLock { tail in
                tail.append(data)
                if tail.count > 4096 { tail.removeFirst(tail.count - 4096) }
            }
        }
        do { try process.run() }
        catch { throw Failure(code: "gpu_process_start", message: "inku-display-gpu did not start: \(error.localizedDescription)") }
        // A write after the program ended reports EPIPE here instead of a signal that ends the app.
        _ = fcntl(input.fileHandleForWriting.fileDescriptor, F_SETNOSIGPIPE, 1)
        launchCount.withLock { $0 += 1 }
        (self.process, self.input, self.output, self.errors) = (process, input, output, errors)
        sent.removeAll()
    }

    private func exchange(svg: String?, digest: [UInt8], region: DisplayRegion) throws -> Answer {
        guard let process, let write = input?.fileHandleForWriting.fileDescriptor,
              let read = output?.fileHandleForReading.fileDescriptor else { throw PipeEnded() }
        let request = watch.withLock { watch -> UInt64 in
            watch.request &+= 1
            return watch.request
        }
        let pid = process.processIdentifier
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + Self.timeout) { [watch = self.watch] in
            let stop = watch.withLock { watch -> Bool in
                guard watch.request == request else { return false }
                watch.stopped = true
                return true
            }
            if stop { kill(pid, SIGKILL) }
        }
        defer { watch.withLock { $0.request &+= 1 } }

        var head = Self.magic + digest
        for value in [region.fullWidth, region.fullHeight, region.x, region.y, region.width, region.height] {
            head += withUnsafeBytes(of: value.littleEndian, Array.init)
        }
        var text = svg ?? ""
        head += withUnsafeBytes(of: UInt64(text.utf8.count).littleEndian, Array.init)
        try head.withUnsafeBytes { try Self.write(write, $0) }
        try text.withUTF8 { try Self.write(write, UnsafeRawBufferPointer($0)) }

        let status = try Self.read(read, count: 5)
        guard Array(status[0..<4]) == Self.magic else { throw PipeEnded() }
        switch status[4] {
        case 0:
            let shape = try Self.read(read, count: 20)
            let width = Self.u32(shape, 0), height = Self.u32(shape, 4), stride = Self.u32(shape, 8)
            let count = Self.u64(shape, 12)
            guard width == region.width, height == region.height, stride >= width * 4,
                  count == UInt64(stride) * UInt64(height), count <= UInt64(Self.maxPixelBytes) else {
                // The unread pixels would be taken for the next answer: start the program afresh.
                discard()
                throw Failure(code: "gpu_answer", message: "a \(width)x\(height) window (stride \(stride), \(count) bytes) "
                    + "for a \(region.width)x\(region.height) request")
            }
            let pixels = UnsafeMutableRawPointer.allocate(byteCount: Int(count), alignment: 16)
            do { try Self.read(read, into: UnsafeMutableRawBufferPointer(start: pixels, count: Int(count))) }
            catch { pixels.deallocate(); throw error }
            guard let image = Self.image(pixels, width: Int(width), height: Int(height), stride: Int(stride), count: Int(count)) else {
                throw Failure(code: "image_unavailable", message: "CoreGraphics could not make the window's image")
            }
            return .image(image)
        case 1:
            let code = try Self.text(read), message = try Self.text(read)
            return .failure(code, message)
        case 2:
            return .sceneMissing
        default:
            throw PipeEnded()
        }
    }

    /// Stop a program whose answer cannot be read on; the next request starts it again.
    private func discard() {
        process?.terminate()
        errors?.fileHandleForReading.readabilityHandler = nil
        (process, input, output, errors) = (nil, nil, nil, nil)
        sent.removeAll()
    }

    /// The process ended during the request for `key`: wait for it, say how it ended, and start afresh next time.
    private func stopped(_ key: String) -> Failure {
        let timedOut = watch.withLock { watch -> Bool in
            defer { watch.stopped = false }
            return watch.stopped
        }
        var how = "ended"
        if let process {
            if process.isRunning { process.terminate() }
            process.waitUntilExit()
            how = switch process.terminationReason {
            case .uncaughtSignal: "ended by signal \(process.terminationStatus)"
            case .exit: "exited with status \(process.terminationStatus)"
            @unknown default: "ended (\(process.terminationStatus))"
            }
        }
        if let handle = errors?.fileHandleForReading {
            handle.readabilityHandler = nil
            if let rest = try? handle.readToEnd() { errorTail.withLock { $0.append(rest) } }
        }
        let tail = errorTail.withLock { String(decoding: $0.suffix(4096), as: UTF8.self) }
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if timedOut { how = "did not answer in \(Self.timeout) and was stopped (\(how))" }
        let message = "inku-display-gpu \(how)" + (tail.isEmpty ? "" : ": \(tail)")
        ended[key] = message
        (process, input, output, errors) = (nil, nil, nil, nil)
        sent.removeAll()
        return Failure(code: timedOut ? "gpu_process_timeout" : "gpu_process_exited", message: message)
    }

    private static func image(_ pixels: UnsafeMutableRawPointer, width: Int, height: Int, stride: Int, count: Int) -> CGImage? {
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
              let provider = CGDataProvider(dataInfo: nil, data: pixels, size: count, releaseData: { _, data, _ in
                  UnsafeMutableRawPointer(mutating: data).deallocate()
              }) else {
            pixels.deallocate()
            return nil
        }
        // A failed CGImage releases the provider, and the provider frees the pixels.
        return CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: stride,
                       space: colorSpace,
                       bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue).union(.byteOrder32Big),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }

    private static func write(_ descriptor: Int32, _ bytes: UnsafeRawBufferPointer) throws {
        var offset = 0
        while offset < bytes.count {
            let written = Darwin.write(descriptor, bytes.baseAddress! + offset, bytes.count - offset)
            if written < 0 {
                if errno == EINTR { continue }
                throw PipeEnded()
            }
            offset += written
        }
    }

    private static func read(_ descriptor: Int32, into bytes: UnsafeMutableRawBufferPointer) throws {
        var offset = 0
        while offset < bytes.count {
            let count = Darwin.read(descriptor, bytes.baseAddress! + offset, bytes.count - offset)
            if count < 0 && errno == EINTR { continue }
            guard count > 0 else { throw PipeEnded() }
            offset += count
        }
    }

    private static func read(_ descriptor: Int32, count: Int) throws -> [UInt8] {
        var bytes = [UInt8](repeating: 0, count: count)
        try bytes.withUnsafeMutableBytes { try read(descriptor, into: $0) }
        return bytes
    }

    private static func text(_ descriptor: Int32) throws -> String {
        let length = Int(u32(try read(descriptor, count: 4), 0))
        guard length <= 64 * 1024 else { throw PipeEnded() }
        return String(decoding: try read(descriptor, count: length), as: UTF8.self)
    }

    private static func u32(_ bytes: [UInt8], _ at: Int) -> UInt32 {
        (0..<4).reduce(UInt32(0)) { $0 | UInt32(bytes[at + $1]) << (8 * UInt32($1)) }
    }

    private static func u64(_ bytes: [UInt8], _ at: Int) -> UInt64 {
        (0..<8).reduce(UInt64(0)) { $0 | UInt64(bytes[at + $1]) << (8 * UInt64($1)) }
    }
}
