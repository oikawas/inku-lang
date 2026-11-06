import Foundation
import InkuCore

/// XMLParser is available on both macOS and iOS and never resolves resources.
struct SVGDocument {
    let width: Double
    let height: Double

    init(_ svg: String) throws {
        // Stored generation bodies can be 64 MiB; description/card wrappers have separate headroom.
        guard !svg.isEmpty, UInt64(svg.utf8.count) <= InkuCore.svgConsumerMaximumBytes,
              !svg.localizedCaseInsensitiveContains("<!DOCTYPE"), !svg.localizedCaseInsensitiveContains("<!ENTITY") else {
            throw ExportFailure("保存SVGが空・大きすぎる・外部定義を含むため書き出せません。")
        }
        let parser = XMLParser(data: Data(svg.utf8))
        parser.shouldResolveExternalEntities = false
        parser.shouldProcessNamespaces = false
        let delegate = SVGParserDelegate(); parser.delegate = delegate
        guard parser.parse(), delegate.depth == 0, delegate.rootName == "svg", let attributes = delegate.attributes else {
            throw ExportFailure("保存SVGが正しいSVG XMLではありません。")
        }
        let box = attributes["viewBox"]?.split(whereSeparator: { $0.isWhitespace || $0 == "," }).compactMap { Double($0) }
        if let box, box.count == 4, box.allSatisfy(\.isFinite), box[2] > 0, box[3] > 0 {
            width = box[2]; height = box[3]
        } else if let w = Self.dimension(attributes["width"]), let h = Self.dimension(attributes["height"]), w.isFinite, h.isFinite, w > 0, h > 0 {
            width = w; height = h
        } else { throw ExportFailure("保存SVGの用紙寸法が不正です。") }
    }

    private static func dimension(_ text: String?) -> Double? {
        guard let text else { return nil }
        return Double(text.hasSuffix("px") ? String(text.dropLast(2)) : text)
    }
}

private final class SVGParserDelegate: NSObject, XMLParserDelegate {
    var rootName: String?
    var attributes: [String: String]?
    var depth = 0
    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String]) {
        guard depth < 256 else { parser.abortParsing(); return }
        if depth == 0 {
            guard rootName == nil else { parser.abortParsing(); return }
            let name = qName ?? elementName
            rootName = String(name.split(separator: ":").last ?? Substring(name))
            attributes = attributeDict
        }
        depth += 1
    }
    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) { depth -= 1 }
}
