import CoreGraphics
import CoreText
import Foundation

enum ExportSheets {
    static func card(source: ExportSource, options: ExportOptions) throws -> CGImage {
        let layoutW = 1080.0, layoutH = options.cardLayout == "portrait" ? 1350.0 : 1080.0
        let height = options.pixelHeight
        let width = Int((layoutW * Double(height) / layoutH).rounded(.toNearestOrEven))
        let context = try ExportRaster.bitmap(width: width, height: height)
        let scale = Double(height) / layoutH
        context.scaleBy(x: scale, y: scale)
        fill(context, CGRect(x: 0, y: 0, width: layoutW, height: layoutH), "fbfaf7")
        var lines = wrapHeadnote(source.work.effectiveSourceText, maximumEM: 936.0 / 32)
        if lines.count > 6 {
            lines = Array(lines.prefix(6))
            lines[5] = lines[5].count > 1 ? String(lines[5].dropLast()) + "…" : "…"
        }
        let footer = layoutH - 72
        let headnoteTop = footer - 22 - 40 - Double(lines.count * 54)
        let frameTop = 72.0
        let frameBottom = headnoteTop - (lines.isEmpty ? 0 : 40)
        let frameHeight = max(1, frameBottom - frameTop)
        let svg = try SVGDocument(source.work.svg)
        let ratio = svg.width / svg.height
        let workW = min(936, frameHeight * ratio), workH = min(936, frameHeight * ratio) / ratio
        let artHeight = max(1, Int((workH * scale).rounded()))
        let image = try ExportRaster.image(svg: source.work.svg, height: artHeight)
        context.draw(image, in: CGRect(x: (layoutW - workW) / 2, y: layoutH - frameTop - (frameHeight - workH) / 2 - workH, width: workW, height: workH))
        let face = try cardFont(size: 32)
        for (index, line) in lines.enumerated() {
            drawText(line, context: context, x: 72, baseline: layoutH - (headnoteTop + Double(54 * (index + 1)) - 12), font: face, color: "1b1a17")
        }
        let footerFace = try cardFont(size: 22)
        let digits = source.work.renderSeed?.filter(\.isNumber) ?? ""
        if !digits.isEmpty {
            let tail = String(digits.suffix(4)); let padded = String(repeating: "0", count: max(0, 4 - tail.count)) + tail
            drawText("seed " + padded, context: context, x: 72, baseline: layoutH - footer, font: footerFace, color: "6b6558", tracking: 2)
        }
        if options.cardSeal { drawText("inku", context: context, x: layoutW - 72, baseline: layoutH - footer, font: footerFace, color: "6b6558", tracking: 4, rightAligned: true) }
        guard let result = context.makeImage() else { throw ExportFailure("共有カードを作れませんでした。") }
        return result
    }

    static func wrapHeadnote(_ text: String, maximumEM: Double) -> [String] {
        func advance(_ character: Character) -> Double {
            let n = character.unicodeScalars.first?.value ?? 0
            return (0x1100...0x115F).contains(n) || (0x2E80...0xA4CF).contains(n) || (0xAC00...0xD7A3).contains(n) || (0xF900...0xFAFF).contains(n) || (0xFE30...0xFE6F).contains(n) || (0xFF00...0xFF60).contains(n) || (0xFFE0...0xFFE6).contains(n) ? 1 : 0.5
        }
        var result: [String] = []
        for paragraph in text.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n").components(separatedBy: "\n") {
            guard !paragraph.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { continue }
            var line = "", token = "", lineWidth = 0.0, tokenWidth = 0.0
            func flush() {
                guard !token.isEmpty else { return }
                if lineWidth + tokenWidth > maximumEM, !line.isEmpty { result.append(line); line = ""; lineWidth = 0 }
                line += token; lineWidth += tokenWidth; token = ""; tokenWidth = 0
            }
            for character in paragraph {
                let width = advance(character)
                if width == 1 || character.isWhitespace {
                    flush()
                    if character.isWhitespace, line.isEmpty { continue }
                    if lineWidth + width > maximumEM, !line.isEmpty {
                        result.append(line); line = ""; lineWidth = 0
                        if character.isWhitespace { continue }
                    }
                    line.append(character); lineWidth += width
                } else { token.append(character); tokenWidth += width }
            }
            flush(); if !line.isEmpty { result.append(line) }
        }
        return result
    }

    static func build(sources: [ExportSource], options: ExportOptions) throws -> [ExportArtifact] {
        let ai = options.format == .aiSheet
        let capacity = ai ? 12 : 28
        var artifacts: [ExportArtifact] = []
        var sheetReferences: [(String, Int, Int)] = []
        let pages = (sources.count + capacity - 1) / capacity
        for page in 0..<pages {
            try Task.checkCancellation()
            let start = page * capacity, end = min(sources.count, start + capacity)
            let name = "inku-\(ai ? "ai" : "review")-sheet-\(page + 1).png"
            let image = try contact(sources: Array(sources[start..<end]), options: options, startIndex: start)
            artifacts.append(ExportArtifact(name: name, data: try ExportService.png(image)))
            sheetReferences.append((name, start + 1, end))
        }
        if ai { artifacts.append(ExportArtifact(name: "inku-contact-sheet-notes.md", data: Data(notes(sources: sources, options: options, sheets: sheetReferences).utf8))) }
        return artifacts
    }

    private static func contact(sources: [ExportSource], options: ExportOptions, startIndex: Int) throws -> CGImage {
        let ai = options.format == .aiSheet
        let cols = min(ai ? 3 : 7, sources.count), rows = (sources.count + cols - 1) / cols
        let cellW = 300.0, cellH = 220.0, captionH = ai ? 0.0 : 44.0
        let gap = ai ? 14.0 : 18.0, pad = ai ? 24.0 : 32.0, headerH = ai ? 40.0 : 58.0
        let sheetW = pad * 2 + Double(cols) * cellW + Double(cols - 1) * gap
        let sheetH = pad * 2 + headerH + Double(rows) * (cellH + captionH) + Double(rows - 1) * gap
        let scale = ai ? 1568.0 / max(sheetW, sheetH) : min(2, 6000.0 / max(sheetW, sheetH))
        let width = Int((sheetW * scale).rounded()), height = Int((sheetH * scale).rounded())
        let context = try ExportRaster.bitmap(width: width, height: height)
        context.scaleBy(x: scale, y: scale)
        fill(context, CGRect(x: 0, y: 0, width: sheetW, height: sheetH), "ffffff")
        let heading = CTFontCreateUIFontForLanguage(.emphasizedSystem, ai ? 17 : 20, nil)!
        let normal = CTFontCreateUIFontForLanguage(.system, ai ? 13 : 12, nil)!
        drawText(options.title, context: context, x: pad, baseline: sheetH - pad - 17, font: heading, color: "1a1a1a", maxWidth: sheetW - pad * 2)
        drawText(options.subtitle, context: context, x: pad, baseline: sheetH - pad - (ai ? 36 : 40), font: normal, color: "8a8a8a", maxWidth: sheetW - pad * 2)
        for (index, source) in sources.enumerated() {
            try Task.checkCancellation()
            let col = index % cols, row = index / cols
            let x = pad + Double(col) * (cellW + gap)
            let top = pad + headerH + Double(row) * (cellH + captionH + gap)
            let y = sheetH - top - cellH
            fill(context, CGRect(x: x, y: y, width: cellW, height: cellH), "fbfbfa")
            let svg = try SVGDocument(source.work.svg)
            let artW = min(cellW, cellH * svg.width / svg.height), artH = artW * svg.height / svg.width
            let image = try ExportRaster.image(svg: source.work.svg, height: max(1, Int((artH * scale).rounded())))
            context.draw(image, in: CGRect(x: x + (cellW - artW) / 2, y: y + (cellH - artH) / 2, width: artW, height: artH))
            context.setStrokeColor(color("e2e0dc")); context.setLineWidth(1)
            context.stroke(CGRect(x: x + 0.5, y: y + 0.5, width: cellW - 1, height: cellH - 1))
            if ai {
                context.setFillColor(CGColor(gray: 20.0 / 255, alpha: 0.82))
                context.fillEllipse(in: CGRect(x: x + 8, y: y + cellH - 42, width: 34, height: 34))
                let badge = String(startIndex + index + 1)
                let face = CTFontCreateUIFontForLanguage(.emphasizedSystem, 20, nil)!
                let line = textLine(badge, font: face, color: color("ffffff"))
                context.textPosition = CGPoint(x: x + 25 - CTLineGetTypographicBounds(line, nil, nil, nil) / 2, y: y + cellH - 32)
                CTLineDraw(line, context)
            } else {
                drawText("\(startIndex + index + 1). \(source.work.effectiveSourceText)", context: context, x: x, baseline: y - 17, font: normal, color: "3a3a3a", maxWidth: cellW)
                let sub = [source.work.renderColorCatalogName, source.work.renderCanvasAspectID, source.work.renderSeed.map { "seed " + $0 }].compactMap { $0 }.joined(separator: " · ")
                let face = CTFontCreateUIFontForLanguage(.system, 11, nil)!
                drawText(sub, context: context, x: x, baseline: y - 33, font: face, color: "9a9a9a", maxWidth: cellW)
            }
        }
        guard let result = context.makeImage() else { throw ExportFailure("コンタクトシートを作れませんでした。") }
        return result
    }

    private static func notes(sources: [ExportSource], options: ExportOptions, sheets: [(String, Int, Int)]) -> String {
        var lines = ["# \(options.title)", "", "generated: \(ISO8601DateFormatter().string(from: Date()))", "items: \(sources.count)"]
        lines += sheets.map { "sheet: \($0.0) (No.\($0.1)\($0.1 == $0.2 ? "" : "-\($0.2)"))" }
        lines += ["", "Each numbered section below corresponds to the badge drawn on the artwork."]
        func field(_ key: String, _ value: String?) {
            guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
            if value.contains("\n") { lines += [key + ":", "```", value, "```"] }
            else { lines.append(key + ": " + value) }
        }
        for (index, source) in sources.enumerated() {
            let work = source.work
            lines += ["", "## No.\(index + 1)"]
            field("description", work.effectiveSourceText)
            field("color catalog", work.renderColorCatalogName ?? work.renderColorCatalogID)
            field("canvas", work.renderCanvasAspectID)
            field("engine", [work.renderEngineID, work.renderEngineVersion].compactMap { $0 }.joined(separator: " "))
            field("models", [work.stage1Model, work.stage2Model].compactMap { $0 }.joined(separator: " / "))
            field("variation", work.variationAmplitude); field("render hash", work.renderHash)
            field("created", ISO8601DateFormatter().string(from: Date(timeIntervalSince1970: Double(work.at) / 1000)))
            if let ddl = work.ddl, !ddl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { lines += ["ddl:", "```", ddl, "```"] }
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private static func cardFont(size: Double) throws -> CTFont {
        guard let url = Bundle.module.url(forResource: "NotoSerifJP-Variable", withExtension: "ttf", subdirectory: "Resources"),
              let provider = CGDataProvider(url: url as CFURL), let graphics = CGFont(provider) else { throw ExportFailure("共有カードの同梱フォントを読み込めませんでした。") }
        let font = CTFontCreateWithGraphicsFont(graphics, size, nil, nil)
        let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontVariationAttribute: [NSNumber(value: 0x77676874): NSNumber(value: 400)]] as CFDictionary)
        return CTFontCreateCopyWithAttributes(font, size, nil, descriptor)
    }

    private static func color(_ hex: String) -> CGColor {
        let n = UInt32(hex, radix: 16)!
        return CGColor(srgbRed: Double((n >> 16) & 255) / 255, green: Double((n >> 8) & 255) / 255, blue: Double(n & 255) / 255, alpha: 1)
    }
    private static func fill(_ context: CGContext, _ rect: CGRect, _ hex: String) { context.setFillColor(color(hex)); context.fill(rect) }
    private static func textLine(_ text: String, font: CTFont, color: CGColor, tracking: Double = 0) -> CTLine {
        CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: [
            NSAttributedString.Key(kCTFontAttributeName as String): font,
            NSAttributedString.Key(kCTForegroundColorAttributeName as String): color,
            NSAttributedString.Key(kCTKernAttributeName as String): tracking,
        ]))
    }
    private static func drawText(_ text: String, context: CGContext, x: Double, baseline: Double, font: CTFont, color hex: String, tracking: Double = 0, rightAligned: Bool = false, maxWidth: Double? = nil) {
        let line = textLine(text.replacingOccurrences(of: "\n", with: " "), font: font, color: color(hex), tracking: tracking)
        let rendered: CTLine
        if let maxWidth, CTLineGetTypographicBounds(line, nil, nil, nil) > maxWidth {
            rendered = CTLineCreateTruncatedLine(line, maxWidth, .end, textLine("…", font: font, color: color(hex))) ?? line
        } else { rendered = line }
        context.textMatrix = .identity
        context.textPosition = CGPoint(x: rightAligned ? x - CTLineGetTypographicBounds(rendered, nil, nil, nil) : x, y: baseline)
        CTLineDraw(rendered, context)
    }
}
