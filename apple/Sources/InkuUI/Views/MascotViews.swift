import SwiftUI

/// A CSS `animation-timing-function`, applied from one keyframe to the next.
enum MascotTiming {
    case linear, stepEnd
    case bezier(Double, Double, Double, Double)
    static let ease = MascotTiming.bezier(0.25, 0.1, 0.25, 1)
    static let easeInOut = MascotTiming.bezier(0.42, 0, 0.58, 1)
    static let easeIn = MascotTiming.bezier(0.42, 0, 1, 1)

    func callAsFunction(_ x: Double) -> Double {
        switch self {
        case .linear: return x
        case .stepEnd: return x < 1 ? 0 : 1
        case .bezier(let x1, let y1, let x2, let y2):
            func curve(_ t: Double, _ a: Double, _ b: Double) -> Double {
                3 * (1 - t) * (1 - t) * t * a + 3 * (1 - t) * t * t * b + t * t * t
            }
            var low = 0.0, high = 1.0, t = x
            for _ in 0..<40 {
                let value = curve(t, x1, x2)
                if abs(value - x) < 1e-7 { break }
                if value < x { low = t } else { high = t }
                t = (low + high) / 2
            }
            return curve(t, y1, y2)
        }
    }
}

/// One CSS `@keyframes` with its duration: each stop's values run to the next stop under that stop's timing.
struct MascotTrack {
    let duration: Double
    let stops: [(at: Double, values: [Double], timing: MascotTiming)]

    /// `animation-delay` shifts the start; before it, and when motion is reduced, the element keeps its own style,
    /// which every mascot track starts from.
    func sample(_ time: Double, delay: Double = 0) -> [Double] {
        let local = time - delay
        guard local >= 0, duration > 0 else { return stops[0].values }
        let progress = local.truncatingRemainder(dividingBy: duration) / duration
        var index = 0
        for candidate in 0..<(stops.count - 1) where stops[candidate].at <= progress { index = candidate }
        let from = stops[index], to = stops[index + 1]
        let span = to.at - from.at
        let eased = from.timing(span > 0 ? min(1, max(0, (progress - from.at) / span)) : 1)
        return zip(from.values, to.values).map { $0 + ($1 - $0) * eased }
    }
}

/// The inku standard palette (`render_color_map`) the Web mascots paint with, the same in light and dark themes.
enum MascotPalette {
    static let white = [1.0, 1.0, 1.0]
    static let black = rgb(0x11, 0x11, 0x11)
    static let blue = rgb(0x2c, 0x3e, 0x91)
    static let red = rgb(0xa2, 0x34, 0x2a)
    static let green = rgb(0x2f, 0x6b, 0x3a)
    static let gray = rgb(0x88, 0x88, 0x88)
    static let inkShade = rgb(0x55, 0x55, 0x55)
    private static func rgb(_ r: Int, _ g: Int, _ b: Int) -> [Double] { [Double(r), Double(g), Double(b)].map { $0 / 255 } }
    static func color(_ value: [Double], opacity: Double = 1) -> Color {
        Color(.sRGB, red: value[0], green: value[1], blue: value[2], opacity: opacity)
    }
}

/// Web `IncuMascot.svelte`: a 5x5 pixel cube orbiting every 15 s while each pixel breathes around the cube's
/// centre, three incubator pixels blinking between palette colours.
public enum IncuMascotFrames {
    enum Tone { case top, left, right }
    struct Pixel { let x: Int; let y: Int; let tone: Tone; let delay: Double; let incubator: Bool }
    static let pixels: [Pixel] = [
        .init(x: 0, y: -2, tone: .top, delay: -0.4, incubator: false),
        .init(x: -1, y: -1, tone: .top, delay: -0.4, incubator: false),
        .init(x: 0, y: -1, tone: .top, delay: -0.6, incubator: true),
        .init(x: 1, y: -1, tone: .top, delay: -0.4, incubator: false),
        .init(x: -2, y: 0, tone: .left, delay: -0.4, incubator: false),
        .init(x: -1, y: 0, tone: .left, delay: -0.6, incubator: false),
        .init(x: 0, y: 0, tone: .top, delay: -0.8, incubator: false),
        .init(x: 1, y: 0, tone: .right, delay: -0.6, incubator: false),
        .init(x: 2, y: 0, tone: .right, delay: -0.4, incubator: false),
        .init(x: -1, y: 1, tone: .left, delay: -0.4, incubator: false),
        .init(x: 0, y: 1, tone: .left, delay: -0.6, incubator: true),
        .init(x: 1, y: 1, tone: .right, delay: -0.4, incubator: true),
        .init(x: 2, y: 1, tone: .right, delay: -0.2, incubator: false),
        .init(x: 0, y: 2, tone: .left, delay: -0.4, incubator: false),
        .init(x: 1, y: 2, tone: .right, delay: -0.2, incubator: false),
    ]
    static let spin = MascotTrack(duration: 15, stops: [(0, [0], .linear), (1, [360], .linear)])
    /// `vortex-breathe`: rotation (degrees), scale, corner radius as a fraction of the pixel.
    static let breathe = MascotTrack(duration: 4, stops: [
        (0, [0, 1, 0], .bezier(0.7, 0, 1, 0.5)), (0.1, [0, 1, 0], .bezier(0.7, 0, 1, 0.5)),
        (0.4, [180, 0.33, 0.5], .linear), (0.6, [180, 0.33, 0.5], .bezier(0, 0.5, 0.3, 1)),
        (0.9, [360, 1, 0], .linear), (1, [360, 1, 0], .linear)])
    static func incubation(_ tone: Tone) -> MascotTrack {
        let (base, other, period): ([Double], [Double], Double) = switch tone {
        case .left: (MascotPalette.black, MascotPalette.red, 5)
        case .right: (MascotPalette.blue, MascotPalette.green, 7)
        case .top: (MascotPalette.gray, MascotPalette.inkShade, 6)
        }
        return MascotTrack(duration: period, stops: [(0, base, .stepEnd), (0.5, other, .stepEnd), (1, base, .stepEnd)])
    }
    static func base(_ tone: Tone) -> [Double] {
        switch tone { case .top: MascotPalette.gray; case .left: MascotPalette.black; case .right: MascotPalette.blue }
    }

    /// The whole cube's rotation in degrees.
    public static func spinDegrees(at time: Double) -> Double { spin.sample(time)[0] }
    /// One pixel's breathing: rotation in degrees, scale and corner radius (fraction of the pixel).
    public static func breathing(at time: Double, delay: Double) -> (rotation: Double, scale: Double, radius: Double) {
        let value = breathe.sample(time, delay: delay)
        return (value[0], value[1], value[2])
    }
    /// The colour an incubator pixel of the given face ("top", "left" or "right") shows, as 0-1 sRGB.
    public static func incubatorColor(face: String, at time: Double) -> [Double] {
        incubation(face == "left" ? .left : face == "right" ? .right : .top).sample(time)
    }

    static func draw(_ context: GraphicsContext, at time: Double, still: Bool) {
        var cube = context
        cube.rotate(by: .degrees(still ? 0 : spinDegrees(at: time)))
        for pixel in pixels {
            let (rotation, scale, radius) = still ? (0, 1, 0) : breathing(at: time, delay: pixel.delay)
            let color = pixel.incubator && !still ? incubation(pixel.tone).sample(time) : base(pixel.tone)
            var cell = cube
            cell.rotate(by: .degrees(rotation))
            cell.scaleBy(x: scale, y: scale)
            cell.translateBy(x: Double(pixel.x) * 19, y: Double(pixel.y) * 19)
            cell.fill(Path(roundedRect: CGRect(x: -8, y: -8, width: 16, height: 16), cornerRadius: radius * 16),
                      with: .color(MascotPalette.color(color)))
        }
    }
}

/// Web `YuragiMascot.svelte`: a 5x5 pixel crab stepping sideways, greeting with each claw on its own period,
/// trembling, blinking and winking, and blowing a round of grey bubbles every 12 s.
public enum YuragiMascotFrames {
    static let step = MascotTrack(duration: 1.5, stops: [
        (0, [-4, -3], .easeInOut), (0.5, [4, 3], .easeInOut), (1, [-4, -3], .easeInOut)])
    private static let rest = [1.0, 0, 0, 0]
    /// scale, rotation (degrees), translateY, corner radius fraction.
    static let leftClaw = MascotTrack(duration: 11, stops: [
        (0, rest, .easeInOut), (0.85, rest, .easeInOut), (0.87, [1.3, -45, -4, 0.5], .easeInOut),
        (0.89, [1.3, 15, -4, 0.5], .easeInOut), (0.91, [1.3, -45, -4, 0.5], .easeInOut),
        (0.93, [1.3, 15, -4, 0.5], .easeInOut), (0.95, rest, .easeInOut), (1, rest, .easeInOut)])
    static let rightClaw = MascotTrack(duration: 8, stops: [
        (0, rest, .easeInOut), (0.8, rest, .easeInOut), (0.82, [1.3, 45, -4, 0.5], .easeInOut),
        (0.84, [1.3, -15, -4, 0.5], .easeInOut), (0.86, [1.3, 45, -4, 0.5], .easeInOut),
        (0.88, [1.3, -15, -4, 0.5], .easeInOut), (0.9, [1.3, 45, -4, 0.5], .easeInOut),
        (0.92, rest, .easeInOut), (1, rest, .easeInOut)])
    static let leg = MascotTrack(duration: 0.6, stops: [(0, [0], .easeInOut), (0.5, [-3], .easeInOut), (1, [0], .easeInOut)])
    static let incubator = MascotTrack(duration: 4, stops: [
        (0, MascotPalette.red, .stepEnd), (0.5, MascotPalette.inkShade, .stepEnd), (1, MascotPalette.red, .stepEnd)])
    static let leftEye = MascotTrack(duration: 7, stops: [
        (0, MascotPalette.white, .ease), (0.94, MascotPalette.white, .ease), (0.96, MascotPalette.black, .ease),
        (0.98, MascotPalette.black, .ease), (1, MascotPalette.white, .ease)])
    static let rightEye = MascotTrack(duration: 7, stops: [
        (0, MascotPalette.white, .ease), (0.64, MascotPalette.white, .ease), (0.66, MascotPalette.black, .ease),
        (0.68, MascotPalette.black, .ease), (0.7, MascotPalette.white, .ease), (0.94, MascotPalette.white, .ease),
        (0.96, MascotPalette.black, .ease), (0.98, MascotPalette.black, .ease), (1, MascotPalette.white, .ease)])
    /// (horizontal travel, scale, delay) of the eight bubbles.
    static let bubbleSpecs: [(tx: Double, scale: Double, delay: Double)] = [
        (-25, 1.2, 0), (15, 0.8, 0.2), (-10, 1.5, 0.4), (30, 1.0, 0.6),
        (-5, 1.8, 0.8), (20, 0.7, 1.0), (-35, 1.1, 1.2), (10, 1.4, 1.4)]
    /// x, y, scale, corner radius fraction, opacity.
    static func bubble(_ tx: Double, _ scale: Double) -> MascotTrack {
        let hidden = [0, 0, 0.2, 0, 0]
        return MascotTrack(duration: 12, stops: [
            (0, hidden, .easeIn), (0.85, hidden, .easeIn), (0.87, [tx * 0.2, -5, 0.4, 0.2, 0.9], .easeIn),
            (0.92, [tx * 0.7, -30, scale, 0.5, 0.6], .easeIn), (0.98, [tx, -90, scale * 1.5, 0.5, 0], .easeIn),
            (1, hidden, .easeIn)])
    }
    /// Lower-leg and side-leg pixels as (column, row, delay).
    static let legs: [(column: Int, row: Int, delay: Double)] = [(0, 2, 0), (4, 2, 0.3), (0, 3, 0.1), (2, 3, 0.2), (4, 3, 0.4)]
    /// Red pixels that do not move.
    static let body: [(column: Int, row: Int)] = [(0, 1), (2, 1), (4, 1), (1, 2), (3, 2)]

    /// The sideways step: horizontal offset and rotation in degrees.
    public static func stepping(at time: Double) -> (x: Double, rotation: Double) {
        let value = step.sample(time); return (value[0], value[1])
    }
    /// A claw's greeting: scale, rotation in degrees, vertical offset and corner radius fraction.
    public static func claw(left: Bool, at time: Double) -> (scale: Double, rotation: Double, y: Double, radius: Double) {
        let value = (left ? leftClaw : rightClaw).sample(time); return (value[0], value[1], value[2], value[3])
    }
    /// One of the eight bubbles: offset, scale, corner radius fraction and opacity.
    public static func bubble(index: Int, at time: Double) -> (x: Double, y: Double, scale: Double, radius: Double, opacity: Double) {
        let spec = bubbleSpecs[index]
        let value = bubble(spec.tx, spec.scale).sample(time, delay: spec.delay)
        return (value[0], value[1], value[2], value[3], value[4])
    }
    /// An eye's colour as 0-1 sRGB.
    public static func eyeColor(left: Bool, at time: Double) -> [Double] { (left ? leftEye : rightEye).sample(time) }

    private static func cell(_ column: Int, _ row: Int) -> CGPoint { CGPoint(x: Double(column - 2) * 19, y: Double(row - 2) * 19) }

    static func draw(_ context: GraphicsContext, at time: Double, still: Bool) {
        var crab = context
        let (x, rotation) = still ? (0, 0) : stepping(at: time)
        crab.translateBy(x: x, y: 0)
        crab.rotate(by: .degrees(rotation))
        func square(_ context: GraphicsContext, _ center: CGPoint, _ color: [Double], opacity: Double = 1) {
            context.fill(Path(CGRect(x: center.x - 8, y: center.y - 8, width: 16, height: 16)),
                         with: .color(MascotPalette.color(color, opacity: opacity)))
        }
        // Web paints untransformed pixels first, the positioned bubbles next, and the moving claws and legs last.
        for pixel in body { square(crab, cell(pixel.column, pixel.row), MascotPalette.red) }
        square(crab, cell(1, 1), still ? MascotPalette.white : eyeColor(left: true, at: time))
        square(crab, cell(3, 1), still ? MascotPalette.white : eyeColor(left: false, at: time))
        square(crab, cell(2, 2), still ? MascotPalette.red : incubator.sample(time))
        if !still {
            for index in bubbleSpecs.indices {
                let bubble = bubble(index: index, at: time)
                guard bubble.opacity > 0 else { continue }
                var drop = crab
                drop.translateBy(x: bubble.x, y: -4 + bubble.y)
                drop.scaleBy(x: bubble.scale, y: bubble.scale)
                drop.fill(Path(roundedRect: CGRect(x: -8, y: -8, width: 16, height: 16), cornerRadius: bubble.radius * 16),
                          with: .color(MascotPalette.color(MascotPalette.gray, opacity: bubble.opacity)))
            }
        }
        for leg in legs {
            let lift = still ? 0 : self.leg.sample(time, delay: leg.delay)[0]
            let center = cell(leg.column, leg.row)
            square(crab, CGPoint(x: center.x, y: center.y + lift), MascotPalette.red)
        }
        for left in [true, false] {
            let (scale, angle, lift, radius) = still ? (1, 0, 0, 0) : claw(left: left, at: time)
            let center = cell(left ? 0 : 4, 0)
            // transform-origin: bottom right (left claw) / bottom left (right claw).
            let origin = CGPoint(x: center.x + (left ? 8 : -8), y: center.y + 8)
            var claw = crab
            claw.translateBy(x: origin.x, y: origin.y)
            claw.scaleBy(x: scale, y: scale)
            claw.rotate(by: .degrees(angle))
            claw.translateBy(x: 0, y: lift)
            claw.fill(Path(roundedRect: CGRect(x: left ? -16 : 0, y: -16, width: 16, height: 16), cornerRadius: radius * 16),
                      with: .color(MascotPalette.color(MascotPalette.red)))
        }
    }
}

/// The drawing mascot (Web `IncuMascot.svelte` / `YuragiMascot.svelte`): a 32-point box holding the 92-point pixel
/// grid at 33%. Its motion starts when it appears, like a CSS animation on insertion; bubbles rise out of the box.
struct MascotView: View {
    let kind: String
    /// Web hides the mascot from assistive technology; the run status names it ("Incu is drawing").
    var accessibilityText: String?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var start = Date()

    var body: some View {
        Color.clear
            .frame(width: 32, height: 32)
            .overlay {
                Group {
                    if reduceMotion { canvas(at: 0, still: true) }
                    else { TimelineView(.animation) { timeline in canvas(at: timeline.date.timeIntervalSince(start), still: false) } }
                }
                .frame(width: 112, height: 112)
                .allowsHitTesting(false)
            }
            .accessibilityHidden(accessibilityText == nil)
            .accessibilityLabel(accessibilityText ?? "")
    }

    private func canvas(at time: Double, still: Bool) -> some View {
        Canvas { context, size in
            var grid = context
            grid.translateBy(x: size.width / 2, y: size.height / 2)
            grid.scaleBy(x: 0.33, y: 0.33)
            if kind == "yuragi" { YuragiMascotFrames.draw(grid, at: time, still: still) }
            else { IncuMascotFrames.draw(grid, at: time, still: still) }
        }
    }
}

/// Still frames of the mascots for checks: the Canvas the view draws, at a chosen time.
public enum MascotSnapshot {
    @MainActor public static func image(kind: String, at time: Double, side: Double = 112, scale: Double = 4) -> CGImage? {
        let renderer = ImageRenderer(content: Canvas { context, size in
            var grid = context
            grid.translateBy(x: size.width / 2, y: size.height / 2)
            grid.scaleBy(x: 0.33, y: 0.33)
            if kind == "yuragi" { YuragiMascotFrames.draw(grid, at: time, still: false) }
            else { IncuMascotFrames.draw(grid, at: time, still: false) }
        }.frame(width: side, height: side).background(Color.white))
        renderer.scale = scale
        return renderer.cgImage
    }
}
