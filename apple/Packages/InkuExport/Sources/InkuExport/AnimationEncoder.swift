import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

enum AnimationEncoder {
    struct State {
        let svg: String
        let repeats: Int
    }

    static func progressiveStates(svg: String, frameCount: Int) throws -> [State] {
        let document = try SVGDocument(svg)
        let root = document.root
        let ignored = Set(["defs", "desc", "metadata", "style", "title"])
        func background(_ element: SVGElement) -> Bool { element.attributes["id"]?.localizedCaseInsensitiveContains("background") ?? false }
        func children(_ element: SVGElement, isRoot: Bool = false) -> [SVGElement] {
            let all = element.children.compactMap(\.element).filter { !ignored.contains($0.localName) }
            let hasBackground = all.contains(where: background)
            let visible = all.filter { !background($0) }
            if isRoot, !hasBackground, visible.count > 1, visible.first?.localName == "rect" { return Array(visible.dropFirst()) }
            return visible
        }
        func descendants(_ element: SVGElement) -> [SVGElement] {
            [element] + element.children.compactMap(\.element).flatMap(descendants)
        }
        struct Record { let parent: SVGElement; let index: Int; let element: SVGElement }
        func records(_ parent: SVGElement, visible: [SVGElement]) -> [Record] {
            parent.children.enumerated().compactMap { index, node in
                guard let element = node.element, visible.contains(where: { $0 === element }) else { return nil }
                return Record(parent: parent, index: index, element: element)
            }
        }
        let containers = descendants(root).filter {
            ($0.attributes["id"]?.lowercased().hasPrefix("layer_") ?? false) && !background($0)
        }
        var layers = containers.flatMap { records($0, visible: children($0)) }
        if layers.isEmpty {
            let visible = children(root, isRoot: true)
            if visible.count == 1, let wrapper = visible.first, wrapper.localName == "g" { layers = records(wrapper, visible: children(wrapper)) }
            if layers.isEmpty { layers = records(root, visible: visible) }
        }
        guard !layers.isEmpty else { throw ExportFailure("保存SVGにアニメーションで順に描く要素がありません。") }
        for layer in layers { layer.parent.remove(layer.element) }
        var plan: [(count: Int, repeats: Int)] = []
        let segments = frameCount - 1
        for step in 0..<frameCount {
            let count = (2 * layers.count * step + segments) / (2 * segments)
            if plan.last?.count == count { plan[plan.count - 1].repeats += 1 }
            else { plan.append((count, 1)) }
        }
        var revealed = 0
        return plan.map { entry in
            while revealed < entry.count {
                let record = layers[revealed]
                record.parent.insert(record.element, at: min(record.index, record.parent.childCount))
                revealed += 1
            }
            return State(svg: entry.count == layers.count ? svg : root.xmlString, repeats: entry.repeats)
        }
    }

    static func encode(sources: [ExportSource], options: ExportOptions) throws -> Data {
        let (width, height) = try ExportRaster.dimensions(svg: sources[0].work.svg, height: options.pixelHeight)
        let single = sources.count == 1
        let states = single ? try progressiveStates(svg: sources[0].work.svg, frameCount: options.layerFrameCount) : []
        var layerOrder = Array(states.indices)
        var layerRepeats = states.map(\.repeats)
        if single, options.layerReplay == "reverse" {
            layerRepeats[0] = layerRepeats[0] * 2 - 1
            layerRepeats[layerRepeats.count - 1] = layerRepeats[layerRepeats.count - 1] * 2 - 1
            if states.count > 2 {
                let reverse = Array((1..<(states.count - 1)).reversed())
                layerOrder += reverse
                layerRepeats += reverse.map { states[$0].repeats }
            }
        }
        let steps = options.pixelHeight <= 1080 ? 6 : options.pixelHeight <= 2160 ? 4 : 2
        let transitions = options.transition == "cut" ? 0 : steps
        let count = single ? layerOrder.count : sources.count + (sources.count - 1) * transitions
        guard width * height <= ExportService.maximumAnimationPixels / count else {
            throw ExportFailure("この解像度とフレーム数はアニメーションの上限（6億画素）を超えます。")
        }
        let holdMS = max(100, Int((1000 * (single ? options.layerIntervalSeconds : options.holdSeconds)).rounded(.toNearestOrEven)))
        if options.format == .gif, (single ? layerRepeats : [1]).contains(where: { holdMS * $0 > 655_350 }) {
            throw ExportFailure("GIFでこのフレーム数と間隔を保持できません。間隔を短くするかAPNGを選択してください。")
        }
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
            for (offset, index) in layerOrder.enumerated() {
                try autoreleasepool { try add(ExportRaster.fitted(svg: states[index].svg, width: width, height: height), durationMS: holdMS * layerRepeats[offset]) }
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
        return data as Data
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
