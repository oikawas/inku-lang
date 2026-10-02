import Foundation

/// XMLParser is available on both macOS and iOS and never resolves resources.
struct SVGDocument {
    let root: SVGElement
    let width: Double
    let height: Double

    init(_ svg: String) throws {
        guard !svg.isEmpty, svg.utf8.count <= 8 * 1024 * 1024,
              !svg.localizedCaseInsensitiveContains("<!DOCTYPE"), !svg.localizedCaseInsensitiveContains("<!ENTITY") else {
            throw ExportFailure("保存SVGが空・大きすぎる・外部定義を含むため書き出せません。")
        }
        let parser = XMLParser(data: Data(svg.utf8))
        parser.shouldResolveExternalEntities = false
        parser.shouldProcessNamespaces = false
        let delegate = SVGParserDelegate(); parser.delegate = delegate
        guard parser.parse(), delegate.stack.isEmpty, let root = delegate.root, root.localName == "svg" else {
            throw ExportFailure("保存SVGが正しいSVG XMLではありません。")
        }
        self.root = root
        let box = root.attributes["viewBox"]?.split(whereSeparator: { $0.isWhitespace || $0 == "," }).compactMap { Double($0) }
        if let box, box.count == 4, box.allSatisfy(\.isFinite), box[2] > 0, box[3] > 0 {
            width = box[2]; height = box[3]
        } else if let w = Self.dimension(root.attributes["width"]), let h = Self.dimension(root.attributes["height"]), w.isFinite, h.isFinite, w > 0, h > 0 {
            width = w; height = h
        } else { throw ExportFailure("保存SVGの用紙寸法が不正です。") }
    }

    private static func dimension(_ text: String?) -> Double? {
        guard let text else { return nil }
        return Double(text.hasSuffix("px") ? String(text.dropLast(2)) : text)
    }
}

enum SVGChild {
    case element(SVGElement)
    case text(String)
    var element: SVGElement? { if case .element(let element) = self { element } else { nil } }
    var xml: String { switch self { case .element(let value): value.xmlString; case .text(let value): SVGElement.escape(value) } }
}

final class SVGElement {
    let name: String
    let attributes: [String: String]
    var children: [SVGChild] = []
    var localName: String { String(name.split(separator: ":").last ?? Substring(name)) }
    var childCount: Int { children.count }
    init(name: String, attributes: [String: String]) { self.name = name; self.attributes = attributes }
    var xmlString: String {
        let attrs = attributes.keys.sorted().map { " " + $0 + "=\"" + Self.escape(attributes[$0]!).replacingOccurrences(of: "\"", with: "&quot;") + "\"" }.joined()
        return "<" + name + attrs + ">" + children.map(\.xml).joined() + "</" + name + ">"
    }
    static func escape(_ text: String) -> String {
        text.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
    }
    func remove(_ element: SVGElement) { children.removeAll { $0.element === element } }
    func insert(_ element: SVGElement, at index: Int) { children.insert(.element(element), at: index) }
}

private final class SVGParserDelegate: NSObject, XMLParserDelegate {
    var root: SVGElement?
    var stack: [SVGElement] = []
    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String]) {
        guard stack.count < 256 else { parser.abortParsing(); return }
        let element = SVGElement(name: qName ?? elementName, attributes: attributeDict)
        if let parent = stack.last { parent.children.append(.element(element)) }
        else if root == nil { root = element }
        else { parser.abortParsing(); return }
        stack.append(element)
    }
    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) { _ = stack.popLast() }
    func parser(_ parser: XMLParser, foundCharacters string: String) { stack.last?.children.append(.text(string)) }
    func parser(_ parser: XMLParser, foundCDATA CDATABlock: Data) { stack.last?.children.append(.text(String(decoding: CDATABlock, as: UTF8.self))) }
}
