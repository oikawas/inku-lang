import CoreGraphics
import CryptoKit
import Foundation
import InkuCore
import InkuUI

private enum DisplayGPUCheckFailure: Error { case failed(String) }

/// `inku-display-gpu` for these checks: `--display-gpu-helper <path>`, else `INKU_DISPLAY_GPU_HELPER`, else what
/// `apple/scripts/build-core.sh` built.
func displayGPUHelper() -> URL {
    if let index = CommandLine.arguments.firstIndex(of: "--display-gpu-helper"), CommandLine.arguments.indices.contains(index + 1) {
        return URL(fileURLWithPath: CommandLine.arguments[index + 1])
    }
    if let path = ProcessInfo.processInfo.environment["INKU_DISPLAY_GPU_HELPER"], !path.isEmpty {
        return URL(fileURLWithPath: path)
    }
    return URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("scripts/.build/core/display-gpu/inku-display-gpu")
}

/// The zoomed windows Graphite draws in `inku-display-gpu` (Apple silicon), on `svg` (a supported work).
/// Failure (G5): the window is not drawn through the program, or arrives in pieces or another size.
/// Failure (pixels): the window crosses the pipe in another byte order, stride or place than the CPU draws it.
/// Failure (G4): a program that ends takes the app with it, or is started again and again for the same work,
/// or leaves no cause in the display failure log, or keeps the next work from being drawn.
/// Failure (idle end): a program the system stopped between requests marks the next work as one that ended it.
@MainActor
func runDisplayGPUChecks(svg: String, helper: URL) async throws {
    #if arch(arm64)
    func fail(_ message: String) -> DisplayGPUCheckFailure { .failed(message) }
    guard FileManager.default.isExecutableFile(atPath: helper.path) else {
        throw fail("No inku-display-gpu at \(helper.path): build it with apple/scripts/build-core.sh")
    }
    func windows(_ renderer: DisplayRenderer, _ svg: String, _ region: DisplayRegion) async throws -> [DisplayRenderer.WindowFrame] {
        var frames: [DisplayRenderer.WindowFrame] = []
        for try await frame in renderer.window(svg: svg, region: region) { frames.append(frame) }
        return frames
    }
    func pixels(_ image: CGImage) -> Data { (image.dataProvider?.data as Data?) ?? Data() }

    // G5: the work's window is drawn by the program, complete in one piece and the size asked for.
    let renderer = DisplayRenderer(windows: .gpu(helper: helper))
    let display = try InkuCore.prepareDisplay(svg: svg)
    let scale = 8000 / max(display.intrinsicWidth, display.intrinsicHeight)
    let (fullWidth, fullHeight) = (UInt32((display.intrinsicWidth * scale).rounded()), UInt32((display.intrinsicHeight * scale).rounded()))
    // The survey's 4x window: a 1000pt work at 2x density zoomed 4 times, 1800 x 1400 at its centre.
    let (width, height) = (min(1800, fullWidth), min(1400, fullHeight))
    let zoom = DisplayRegion(fullWidth: fullWidth, fullHeight: fullHeight, x: (fullWidth - width) / 2, y: (fullHeight - height) / 2,
                             width: width, height: height)
    var started = ContinuousClock.now
    let first = try await windows(renderer, svg, zoom)
    let firstTook = ContinuousClock.now - started
    started = ContinuousClock.now
    let again = try await windows(renderer, svg, zoom)
    let againTook = ContinuousClock.now - started
    guard first.count == 1, again.count == 1, first[0].complete, first[0].image.width == Int(width),
          first[0].image.height == Int(height),
          renderer.diagnostics().gpuWindows == 2, renderer.diagnostics().failures.isEmpty, renderer.gpuLaunches == 1 else {
        throw fail("The 4x window was not drawn whole by one inku-display-gpu: \(first.map(\.complete)), \(renderer.diagnostics()), "
            + "launches \(renderer.gpuLaunches ?? -1)")
    }
    let cpuWindow = try await windows(DisplayRenderer(windows: .cpu), svg, zoom).last
    let workDifference = cpuWindow.map { difference(pixels(first[0].image), pixels($0.image), width: Int(width), height: Int(height)) }

    // Pixels: a work without noise, red and green, matches the CPU's window by the author's yardstick.
    let plain = ##"<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200"><rect width="300" height="200" fill="#f4efe6"/><circle cx="90" cy="100" r="60" fill="#c0392b"/><rect x="170" y="40" width="100" height="120" fill="#2e6b3f" transform="rotate(12 220 100)"/></svg>"##
    let plainZoom = DisplayRegion(fullWidth: 1200, fullHeight: 800, x: 150, y: 120, width: 900, height: 560)
    guard let gpuPlain = try await windows(renderer, plain, plainZoom).last,
          let cpuPlain = try await windows(DisplayRenderer(windows: .cpu), plain, plainZoom).last else {
        throw fail("The plain work's window was not drawn")
    }
    let plainDifference = difference(pixels(gpuPlain.image), pixels(cpuPlain.image), width: 900, height: 560)
    guard plainDifference.worstBlock <= 16, plainDifference.farShare <= 0.005 else {
        throw fail("Graphite's window of a plain work differs from the CPU's: worst block \(plainDifference.worstBlock), "
            + "far \(plainDifference.farShare)")
    }

    // G4: a program that ends on a work's request: the app goes on, the cause is logged once, the work is not sent
    // again, and the next work starts the program again and is drawn.
    let crashing = plain.replacingOccurrences(of: "#c0392b", with: "#8e44ad")
    let crashingDigest = SHA256.hash(data: Data(crashing.utf8)).map { String(format: "%02x", $0) }.joined()
    let logFolder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-display-gpu-failures-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: logFolder) }
    let ending = DisplayRenderer(windows: .gpu(helper: helper, environment: [DisplayRenderer.gpuCheckAbortVariable: crashingDigest]))
    ending.connectFailureLog(directory: logFolder)
    var codes: [String] = []
    for _ in 0..<2 {
        do { _ = try await windows(ending, crashing, plainZoom); codes.append("drawn") }
        catch let failed as DisplayRenderer.Failed { codes.append(failed.code) }
    }
    let launchesAfterEnd = ending.gpuLaunches
    let lines = (try? String(contentsOf: logFolder.appendingPathComponent("display-failures/failures.jsonl"), encoding: .utf8))?
        .split(separator: "\n") ?? []
    let logged = lines.first.flatMap { try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any] }
    let message = logged?["message"] as? String ?? ""
    guard codes == ["gpu_process_exited", "gpu_process_exited"], launchesAfterEnd == 1, lines.count == 1,
          logged?["code"] as? String == "gpu_process_exited", logged?["stage"] as? String == "window",
          message.contains("signal 6"), message.contains(DisplayRenderer.gpuCheckAbortVariable),
          (logged?["app_executable_sha256"] as? String)?.count == 64 else {
        throw fail("An ended program was not handled: \(codes), launches \(launchesAfterEnd ?? -1), log \(lines)")
    }
    let next = try await windows(ending, plain, plainZoom)
    guard next.count == 1, next[0].complete, ending.gpuLaunches == 2 else {
        throw fail("The next work was not drawn by a new program: \(next.map(\.complete)), launches \(ending.gpuLaunches ?? -1)")
    }

    // Idle end: the program is stopped while no request is running; the same work is drawn by a new one.
    guard let idlePID = ending.gpuProcessIdentifier else { throw fail("No running inku-display-gpu after the next work") }
    kill(idlePID, SIGKILL)
    let deadline = ContinuousClock.now + .seconds(5)
    while ending.gpuProcessIdentifier != nil, ContinuousClock.now < deadline { try await Task.sleep(for: .milliseconds(20)) }
    var idleCodes: [String] = []
    for _ in 0..<2 {
        do { idleCodes.append(try await windows(ending, plain, plainZoom).last?.complete == true ? "drawn" : "partial") }
        catch let failed as DisplayRenderer.Failed { idleCodes.append(failed.code) }
    }
    let idleLines = (try? String(contentsOf: logFolder.appendingPathComponent("display-failures/failures.jsonl"), encoding: .utf8))?
        .split(separator: "\n") ?? []
    guard idleCodes == ["drawn", "drawn"], ending.gpuLaunches == 3, idleLines.count == 1 else {
        throw fail("A program stopped while idle was not started again: \(idleCodes), launches \(ending.gpuLaunches ?? -1), "
            + "log lines \(idleLines.count)")
    }

    print("Display GPU passed: 4x window \(first[0].image.width)x\(first[0].image.height) in one piece, first \(firstTook) "
        + "(start included), again \(againTook); "
        + (workDifference.map { "against the CPU: worst block \($0.worstBlock), far \($0.farShare); " } ?? "")
        + "plain work worst block \(plainDifference.worstBlock); ended program logged once (\(message.prefix(80))), "
        + "not restarted for the same work, restarted for the next; stopped while idle, started again for the same work.")
    #else
    print("Display GPU skipped: windows are drawn on the CPU on this architecture.")
    #endif
}

/// The C1/C4 measure on premultiplied RGBA composited over white: the worst 16px block's mean
/// channel difference, and the share of pixels differing by more than 32.
private func difference(_ a: Data, _ b: Data, width: Int, height: Int) -> (worstBlock: Double, farShare: Double) {
    guard a.count >= width * height * 4, b.count >= width * height * 4 else { return (.infinity, 1) }
    func white(_ value: UInt8, _ alpha: UInt8) -> Int { Int(value) + 255 - Int(alpha) }
    let blocksX = (width + 15) / 16, blocksY = (height + 15) / 16
    var sums = [Int](repeating: 0, count: blocksX * blocksY), counts = sums
    var far = 0
    a.withUnsafeBytes { a in
        b.withUnsafeBytes { b in
            for y in 0..<height {
                for x in 0..<width {
                    let i = (y * width + x) * 4
                    var worst = 0, total = 0
                    for c in 0..<3 {
                        let d = abs(white(a[i + c], a[i + 3]) - white(b[i + c], b[i + 3]))
                        worst = max(worst, d); total += d
                    }
                    if worst > 32 { far += 1 }
                    let block = (y / 16) * blocksX + x / 16
                    sums[block] += total; counts[block] += 3
                }
            }
        }
    }
    let worstBlock = zip(sums, counts).map { Double($0) / Double(max(1, $1)) }.max() ?? 0
    return (worstBlock, Double(far) / Double(width * height))
}
