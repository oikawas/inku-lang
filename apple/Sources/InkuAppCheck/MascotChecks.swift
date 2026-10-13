import CoreGraphics
import Foundation
import ImageIO
import InkuUI
import UniformTypeIdentifiers

/// Web IncuMascot.svelte / YuragiMascot.svelte keyframes, read by hand at their stops.
@MainActor
func runMascotChecks() throws {
    var compared = 0
    func expect(_ name: String, _ actual: [Double], _ expected: [Double], tolerance: Double = 0.02) throws {
        compared += 1
        guard actual.count == expected.count, zip(actual, expected).allSatisfy({ abs($0 - $1) <= tolerance }) else {
            throw CheckFailure.message("Mascot \(name): \(actual) != \(expected)")
        }
    }
    func rgb(_ hex: Int) -> [Double] { [Double(hex >> 16 & 255), Double(hex >> 8 & 255), Double(hex & 255)].map { $0 / 255 } }
    func breathing(_ time: Double, _ delay: Double) -> [Double] {
        let value = IncuMascotFrames.breathing(at: time, delay: delay); return [value.rotation, value.scale, value.radius]
    }
    // Incu: a pixel delayed by -0.4 s is 10% into vortex-breathe at the start, 40% after 1.2 s, 50% after 1.6 s.
    try expect("incu breathe 10%", breathing(0, -0.4), [0, 1, 0])
    try expect("incu breathe 40%", breathing(1.2, -0.4), [180, 0.33, 0.5])
    try expect("incu breathe 50%", breathing(1.6, -0.4), [180, 0.33, 0.5])
    try expect("incu breathe 95%", breathing(3.4, -0.4), [360, 1, 0])
    try expect("incu spin 7.5 s", [IncuMascotFrames.spinDegrees(at: 7.5)], [180])
    try expect("incu left incubator before half", IncuMascotFrames.incubatorColor(face: "left", at: 2.4), rgb(0x111111), tolerance: 0.001)
    try expect("incu left incubator after half", IncuMascotFrames.incubatorColor(face: "left", at: 2.6), rgb(0xa2342a), tolerance: 0.001)
    try expect("incu right incubator after half", IncuMascotFrames.incubatorColor(face: "right", at: 3.6), rgb(0x2f6b3a), tolerance: 0.001)
    try expect("incu top incubator after half", IncuMascotFrames.incubatorColor(face: "top", at: 3.1), rgb(0x555555), tolerance: 0.001)
    // Yuragi: 87% of the left claw's 11 s, 82% of the right claw's 8 s, half of the 1.5 s step.
    func claw(_ left: Bool, _ time: Double) -> [Double] {
        let value = YuragiMascotFrames.claw(left: left, at: time); return [value.scale, value.rotation, value.y, value.radius]
    }
    try expect("yuragi left claw 87%", claw(true, 0.87 * 11), [1.3, -45, -4, 0.5])
    try expect("yuragi left claw 89%", claw(true, 0.89 * 11), [1.3, 15, -4, 0.5])
    try expect("yuragi left claw at rest", claw(true, 5), [1, 0, 0, 0])
    try expect("yuragi right claw 82%", claw(false, 0.82 * 8), [1.3, 45, -4, 0.5])
    let step = YuragiMascotFrames.stepping(at: 0.75)
    try expect("yuragi step half", [step.x, step.rotation], [4, 3])
    let start = YuragiMascotFrames.stepping(at: 0)
    try expect("yuragi step start", [start.x, start.rotation], [-4, -3])
    func bubble(_ index: Int, _ time: Double) -> [Double] {
        let value = YuragiMascotFrames.bubble(index: index, at: time); return [value.x, value.y, value.scale, value.radius, value.opacity]
    }
    try expect("yuragi bubble 0 at 92%", bubble(0, 0.92 * 12), [-17.5, -30, 1.2, 0.5, 0.6])
    try expect("yuragi bubble 1 at 92% after its 0.2 s delay", bubble(1, 0.92 * 12 + 0.2), [10.5, -30, 0.8, 0.5, 0.6])
    try expect("yuragi bubble 1 before its delay", [bubble(1, 0.1)[4]], [0])
    try expect("yuragi right eye winks at 67%", YuragiMascotFrames.eyeColor(left: false, at: 0.67 * 7), rgb(0x111111), tolerance: 0.001)
    try expect("yuragi left eye open at 67%", YuragiMascotFrames.eyeColor(left: true, at: 0.67 * 7), rgb(0xffffff), tolerance: 0.001)
    try expect("yuragi left eye blinks at 97%", YuragiMascotFrames.eyeColor(left: true, at: 0.97 * 7), rgb(0x111111), tolerance: 0.001)

    // StopButton.svelte stopPulse, 2.2 s ease-in-out: background, outer ring, its spread, saturation.
    func pulse(_ time: Double, dark: Bool) -> [Double] {
        let frame = StopPulse.frame(at: time, dark: dark); return frame.background + frame.ring + [frame.spread, frame.saturation]
    }
    try expect("stop pulse light 0%", pulse(0, dark: false), [154, 61, 61, 0.16, 154, 61, 61, 0.088, 0, 1], tolerance: 0.001)
    try expect("stop pulse light 25%", pulse(0.55, dark: false), [154, 61, 61, 0.23, 154, 61, 61, 0.154, 2.5, 1.14], tolerance: 0.001)
    try expect("stop pulse light 50%", pulse(1.1, dark: false), [154, 61, 61, 0.30, 154, 61, 61, 0.22, 5, 1.28], tolerance: 0.001)
    try expect("stop pulse light 100%", pulse(2.2, dark: false), [154, 61, 61, 0.16, 154, 61, 61, 0.088, 0, 1], tolerance: 0.001)
    try expect("stop pulse dark 25% premultiplied", pulse(0.55, dark: true), [255, 121.48, 98.84, 0.31, 255, 126, 104, 0.196, 2.5, 1.14], tolerance: 0.01)
    try expect("stop pulse dark 50%", pulse(1.1, dark: true), [255, 126, 104, 0.42, 255, 126, 104, 0.28, 5, 1.28], tolerance: 0.001)

    var sheet = "not written"
    if let path = ProcessInfo.processInfo.environment["INKU_MASCOT_SHEET"] { sheet = try writeMascotSheet(to: URL(fileURLWithPath: path)) }
    var stopSheet = "not written"
    if let path = ProcessInfo.processInfo.environment["INKU_STOP_SHEET"] { stopSheet = try writeStopSheet(to: URL(fileURLWithPath: path)) }
    print("Mascot frames passed: \(compared) keyframe values compared with the Web CSS (Incu breathe/spin/incubators, Yuragi claws/step/bubbles/eyes, stop button pulse). Sheet: \(sheet). Stop sheet: \(stopSheet).")
}

/// A row per mascot of stills at chosen times, so the pixels' overlap, overflow and size can be looked at.
@MainActor
private func writeMascotSheet(to url: URL) throws -> String {
    let times: [(String, [Double])] = [
        ("incu", [0, 0.6, 1.0, 1.6, 2.4, 3.0, 3.6, 7.5]),
        ("yuragi", [0, 0.75, 4.69, 6.56, 9.57, 10.4, 11.04, 11.5]),
    ]
    let cell = 448
    guard let context = CGContext(data: nil, width: cell * 8, height: cell * times.count, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        throw CheckFailure.message("Mascot sheet context failed")
    }
    for (row, entry) in times.enumerated() {
        for (column, time) in entry.1.enumerated() {
            guard let image = MascotSnapshot.image(kind: entry.0, at: time) else { throw CheckFailure.message("Mascot snapshot failed") }
            context.draw(image, in: CGRect(x: column * cell, y: (times.count - 1 - row) * cell, width: cell, height: cell))
            // The 32-point layout box (128 pixels at this scale) the Web keeps the grid inside.
            context.setStrokeColor(CGColor(red: 0.2, green: 0.6, blue: 1, alpha: 1)); context.setLineWidth(2)
            context.stroke(CGRect(x: column * cell + (cell - 128) / 2, y: (times.count - 1 - row) * cell + (cell - 128) / 2, width: 128, height: 128))
        }
    }
    guard let image = context.makeImage(),
          let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw CheckFailure.message("Mascot sheet image failed")
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else { throw CheckFailure.message("Mascot sheet write failed") }
    return url.path + " (rows incu, yuragi; times " + times.map { $0.0 + " " + $0.1.map { String($0) }.joined(separator: "/") }.joined(separator: "; ") + " s)"
}

/// Light and dark rows of the stop button at 0 %, 25 % and 50 % of its pulse.
@MainActor
private func writeStopSheet(to url: URL) throws -> String {
    let times = [0, 0.55, 1.1]
    let width = 480, height = 192
    guard let context = CGContext(data: nil, width: width * times.count, height: height * 2, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        throw CheckFailure.message("Stop sheet context failed")
    }
    for (row, dark) in [false, true].enumerated() {
        for (column, time) in times.enumerated() {
            guard let image = StopButtonSnapshot.image(dark: dark, at: time) else { throw CheckFailure.message("Stop snapshot failed") }
            context.draw(image, in: CGRect(x: column * width, y: (1 - row) * height, width: width, height: height))
        }
    }
    guard let image = context.makeImage(),
          let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw CheckFailure.message("Stop sheet image failed")
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else { throw CheckFailure.message("Stop sheet write failed") }
    return url.path + " (rows light, dark; times " + times.map { String($0) }.joined(separator: "/") + " s)"
}
