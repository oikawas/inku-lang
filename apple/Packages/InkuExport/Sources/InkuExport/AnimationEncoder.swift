import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers
import InkuCore
import InkuHost

enum AnimationEncoder {
    static var fontURL: URL? { Bundle.module.url(forResource: "NotoSerifJP-Variable", withExtension: "ttf") }
    static func order(frameCount: Int, replay: String) -> [Int] {
        guard frameCount > 0 else { return [] }
        let forward = [frameCount - 1] + Array(0..<frameCount)
        return replay == "reverse" && forward.count > 2 ? forward + forward.dropFirst().dropLast().reversed() : forward
    }

    static func encode(sources: [ExportSource], options: ExportOptions) throws -> (data: Data, matches: Bool?, outcome: String?) {
        let single = sources.count == 1
        var states: [String] = []; var matches: Bool?; var outcome: String?; var fonts: PreparedRasterFonts?
        if single {
            guard var request = sources[0].lineAnimationRequest,
                  let font = fontURL else {
                throw ExportFailure("行ごとのアニメーションの保存条件または字体がありません。")
            }
            request["show_ddl"] = .bool(options.showDDL)
            request["font_family"] = .string("Noto Serif JP")
            request["font_files"] = .array([.string(font.path)])
            let result = try ExactJSON(data: InkuCore.lineAnimation(request.data))
            if let error = result["error"].string { throw ExportFailure(error) }
            guard let frames = result["frames"].array, !frames.isEmpty,
                  let match = result["matches_saved_svg"].bool, let resultOutcome = result["outcome"].string else {
                throw ExportFailure("行ごとのアニメーションの応答が不正です。")
            }
            states = try frames.map { try $0.requiredString("svg") }
            matches = match; outcome = resultOutcome
            fonts = try InkuCore.prepareRasterFonts([font.path])
        }
        let layerOrder = order(frameCount: states.count, replay: options.layerReplay)
        let prepared: [PreparedSVG]
        if let fonts { prepared = try states.map { try fonts.prepareSVG($0) } }
        else { prepared = [] }
        let (width, height): (Int, Int)
        if let last = prepared.last {
            (width, height) = try ExportRaster.dimensions(scene: last, height: options.pixelHeight, maximumPixels: ExportService.maximumAnimationPixels)
        } else { (width, height) = try ExportRaster.dimensions(svg: sources[0].work.svg, height: options.pixelHeight) }
        let steps = options.pixelHeight <= 1080 ? 6 : options.pixelHeight <= 2160 ? 4 : 2
        let transitions = options.transition == "cut" ? 0 : steps
        let count = single ? layerOrder.count : sources.count + (sources.count - 1) * transitions
        guard width * height <= ExportService.maximumAnimationPixels / count else {
            throw ExportFailure("この解像度とフレーム数はアニメーションの上限（6億画素）を超えます。")
        }
        let holdMS = max(100, Int((1000 * (single ? options.layerIntervalSeconds : options.holdSeconds)).rounded(.toNearestOrEven)))
        let data = NSMutableData()
        let gif = options.format == .gif
        guard let destination = CGImageDestinationCreateWithData(data, (gif ? UTType.gif.identifier : UTType.png.identifier) as CFString, count, nil) else { throw ExportFailure("アニメーションエンコーダーを準備できませんでした。") }
        let once = single && options.layerReplay == "once"
        if gif {
            if !once { CGImageDestinationSetProperties(destination, [kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: 0]] as CFDictionary) }
        } else {
            CGImageDestinationSetProperties(destination, [kCGImagePropertyPNGDictionary: [kCGImagePropertyAPNGLoopCount: once ? 1 : 0]] as CFDictionary)
        }
        func add(_ image: CGImage, durationMS: Int) throws {
            try Task.checkCancellation()
            let timing = gif ? [kCGImagePropertyGIFDelayTime: Double(durationMS) / 1000, kCGImagePropertyGIFUnclampedDelayTime: Double(durationMS) / 1000] : [kCGImagePropertyAPNGDelayTime: Double(durationMS) / 1000, kCGImagePropertyAPNGUnclampedDelayTime: Double(durationMS) / 1000]
            CGImageDestinationAddImage(destination, image, [(gif ? kCGImagePropertyGIFDictionary : kCGImagePropertyPNGDictionary): timing] as CFDictionary)
        }
        if single {
            guard fonts != nil else { throw ExportFailure("字体を準備できませんでした。") }
            for index in layerOrder {
                try autoreleasepool { try add(ExportRaster.image(scene: prepared[index], height: height, maximumPixels: ExportService.maximumAnimationPixels), durationMS: holdMS) }
            }
        } else {
            var current = try ExportRaster.fitted(svg: sources[0].work.svg, width: width, height: height)
            for index in sources.indices {
                try add(current, durationMS: holdMS)
                guard index + 1 < sources.count else { break }
                let following = try ExportRaster.fitted(svg: sources[index + 1].work.svg, width: width, height: height)
                for step in 1..<(transitions + 1) {
                    let progress = Double(step) / Double(steps + 1)
                    try autoreleasepool { try add(transition(current: current, following: following, pattern: options.transition, progress: progress), durationMS: max(40, min(120, holdMS / 4))) }
                }
                current = following
            }
        }
        try Task.checkCancellation()
        guard CGImageDestinationFinalize(destination) else { throw ExportFailure("アニメーションを書き出せませんでした。") }
        return (data as Data, matches, outcome)
    }

    private static func transition(current: CGImage, following: CGImage, pattern: String, progress: Double) throws -> CGImage {
        let context = try ExportRaster.bitmap(width: current.width, height: current.height)
        let rect = CGRect(x: 0, y: 0, width: current.width, height: current.height)
        context.setFillColor(CGColor(gray: 1, alpha: 1)); context.fill(rect)
        switch pattern {
        case "crossfade":
            context.draw(current, in: rect)
            context.setAlpha(progress); context.draw(following, in: rect)
        case "fade_white":
            context.setAlpha(progress < 0.5 ? 1 - progress * 2 : (progress - 0.5) * 2)
            context.draw(progress < 0.5 ? current : following, in: rect)
        default:
            let offset = (Double(current.width) * progress).rounded(.toNearestOrEven)
            context.draw(current, in: rect.offsetBy(dx: -offset, dy: 0))
            context.draw(following, in: rect.offsetBy(dx: Double(current.width) - offset, dy: 0))
        }
        guard let result = context.makeImage() else { throw ExportFailure("トランジション画像を作れませんでした。") }
        return result
    }
}
