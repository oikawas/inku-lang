import CoreGraphics
import Foundation
import ImageIO
import InkuHost
import InkuPersistence
import XCTest
@testable import InkuExport

final class ExportBoundaryTests: XCTestCase, @unchecked Sendable {
    private let layered = #"<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><rect id="background" width="64" height="64" fill="white"/><g id="layer_1"><rect x="0" y="0" width="32" height="64" fill="red"/><rect x="32" y="0" width="32" height="64" fill="blue"/></g></svg>"#
    private func source(_ svg: String? = nil, id: String = "one") -> ExportSource {
        ExportSource(work: SavedWork(id: id, at: 1, input: "a drawing", score: "{}", svg: svg ?? layered))
    }

    // Failure: custom Y=12000 is silently capped/rejected by the display raster's 8192 limit.
    func testTallExportUsesRequestedHeightAndKeepsBothTileEdges() throws {
        let svg = #"<svg xmlns="http://www.w3.org/2000/svg" width="8" height="12000" viewBox="0 0 8 12000"><rect width="8" height="12000" fill="red"/><rect x="0" y="11999" width="8" height="1" fill="blue"/></svg>"#
        let image = try ExportRaster.image(svg: svg, height: 12000)
        XCTAssertEqual(image.width, 8); XCTAssertEqual(image.height, 12000)
        let bytes = try XCTUnwrap(image.dataProvider?.data) as Data
        XCTAssertEqual(Array(bytes.prefix(4)), [255, 0, 0, 255])
        XCTAssertEqual(Array(bytes.suffix(4)), [0, 0, 255, 255])
        XCTAssertThrowsError(try ExportRaster.dimensions(svg: layered, height: 12001))
    }

    // Failure: an odd custom height rounds its half-pixel width differently from the core and crops an animation canvas.
    func testCustomOddHeightUsesCoreAspectRounding() throws {
        let svg = #"<svg xmlns="http://www.w3.org/2000/svg" width="3" height="2" viewBox="0 0 3 2"><rect width="3" height="2" fill="red"/></svg>"#
        let dimensions = try ExportRaster.dimensions(svg: svg, height: 67)
        let image = try ExportRaster.image(svg: svg, height: 67)
        XCTAssertEqual(dimensions.0, 101); XCTAssertEqual(dimensions.0, image.width)
    }

    // Failure: splitting a filtered/clipped SVG at a tile edge introduces seams.
    func testTiledBlurAndClipMatchDirectPixelsAcrossSeam() throws {
        let svg = #"<svg xmlns="http://www.w3.org/2000/svg" width="768" height="384" viewBox="0 0 768 384"><defs><filter id="blur" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="18"/></filter><clipPath id="clip"><rect x="100" y="20" width="550" height="340"/></clipPath></defs><g clip-path="url(#clip)"><rect x="220" y="60" width="330" height="250" fill="red" filter="url(#blur)"/></g></svg>"#
        let direct = try ExportRaster.image(svg: svg, height: 384)
        let tiled = try ExportRaster.image(svg: svg, height: 384, forcedTileSide: 256)
        XCTAssertEqual(direct.dataProvider?.data as Data?, tiled.dataProvider?.data as Data?)
    }

    // Failure: an exported APNG contains only its first image or loses held/reverse frames.
    func testAPNGHasActualFramesAndServerLayerTiming() throws {
        var options = ExportOptions(); options.format = .apng; options.pixelHeight = 64
        options.layerFrameCount = 12; options.layerIntervalSeconds = 0.3; options.layerReplay = "reverse"
        let artifacts = try ExportService.render(sources: [source()], options: options)
        let data = try XCTUnwrap(artifacts.first?.data)
        let decoder = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
        XCTAssertEqual(CGImageSourceGetCount(decoder), 4)
        let expected = [1.5, 1.8, 1.5, 1.8]
        for index in 0..<4 {
            let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(decoder, index, nil) as? [String: Any])
            let png = try XCTUnwrap(properties[kCGImagePropertyPNGDictionary as String] as? [String: Any])
            let duration = try XCTUnwrap(png[kCGImagePropertyAPNGUnclampedDelayTime as String] as? Double)
            XCTAssertEqual(duration, expected[index], accuracy: 0.011)
        }
        let first = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoder, 0, nil))
        let completed = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoder, 2, nil))
        XCTAssertNotEqual(first.dataProvider?.data as Data?, completed.dataProvider?.data as Data?)
        XCTAssertEqual(source().work.svg, layered)
        options.layerReplay = "once"
        let once = try ExportService.render(sources: [source()], options: options)[0].data
        let onceDecoder = try XCTUnwrap(CGImageSourceCreateWithData(once as CFData, nil))
        let globals = try XCTUnwrap(CGImageSourceCopyProperties(onceDecoder, nil) as? [String: Any])
        let png = try XCTUnwrap(globals[kCGImagePropertyPNGDictionary as String] as? [String: Any])
        XCTAssertEqual(png[kCGImagePropertyAPNGLoopCount as String] as? Int, 1)
    }

    // Failure: multi-work GIF omits transitions or applies the next work's canvas to all frames.
    func testMultiWorkGIFCarriesTransitionFramesOnFirstCanvas() throws {
        var options = ExportOptions(); options.format = .gif; options.pixelHeight = 64; options.transition = "crossfade"
        let blue = #"<svg xmlns="http://www.w3.org/2000/svg" width="128" height="64" viewBox="0 0 128 64"><rect width="128" height="64" fill="blue"/></svg>"#
        let data = try ExportService.render(sources: [source(), source(blue, id: "two")], options: options)[0].data
        let decoder = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
        XCTAssertEqual(CGImageSourceGetCount(decoder), 8)
        let last = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoder, 7, nil))
        XCTAssertEqual(last.width, 64); XCTAssertEqual(last.height, 64)
        options.pixelHeight = 12000
        XCTAssertThrowsError(try ExportService.render(sources: [source(), source(blue, id: "two"), source(id: "three")], options: options))
    }

    // Failure: Display SVG omits the saved description even though canonical SVG must remain unchanged.
    func testDisplaySVGUsesSavedDescriptionAndKeepsCanonicalIdentity() throws {
        let canonical = #"<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><desc>original SVG note</desc><rect width="64" height="64" fill="red"/></svg>"#
        let description = "保存した & < > \" ' 説明\n二行目"
        let work = SavedWork(id: "saved-display", at: 42, input: "saved fallback\nsecond line", score: "{}", svg: canonical,
                             sourceText: description, renderEngineVersion: "saved-engine", renderHash: "saved-render-hash",
                             lineageNodeID: "saved-node")
        let saved = ExportSource(work: work)
        var options = ExportOptions(); options.format = .svg

        func display(_ source: ExportSource) throws -> (ExportArtifact, DisplaySVGDescriptionDecoder) {
            let artifact = try XCTUnwrap(ExportService.render(sources: [source], options: options).first)
            let decoded = DisplaySVGDescriptionDecoder()
            let parser = XMLParser(data: artifact.data)
            parser.shouldResolveExternalEntities = false
            parser.delegate = decoded
            XCTAssertTrue(parser.parse(), parser.parserError?.localizedDescription ?? "Display SVG did not parse")
            return (artifact, decoded)
        }

        let (artifact, decoded) = try display(saved)
        XCTAssertEqual(decoded.descriptions, [description, "original SVG note"])
        XCTAssertEqual(decoded.rootChildren, ["desc", "desc", "rect"])
        var displayedSVG = String(decoding: artifact.data, as: UTF8.self)
        XCTAssertTrue(displayedSVG.contains("保存した &amp; &lt; &gt; &quot; ' 説明\n二行目"))
        let descriptionStart = try XCTUnwrap(displayedSVG.range(of: "<desc>"))
        let descriptionEnd = try XCTUnwrap(displayedSVG.range(of: "</desc>", range: descriptionStart.upperBound..<displayedSVG.endIndex))
        displayedSVG.removeSubrange(descriptionStart.lowerBound..<descriptionEnd.upperBound)
        XCTAssertEqual(Data(displayedSVG.utf8), Data(canonical.utf8))
        XCTAssertEqual(artifact.name, "inku-saved-display.svg")
        XCTAssertEqual(saved.work, work)
        XCTAssertEqual(try saved.svg(profile: "canonical"), canonical)
        options.svgProfile = "canonical"
        XCTAssertEqual(try ExportService.render(sources: [saved], options: options)[0].data, Data(canonical.utf8))
        XCTAssertEqual(saved.work, work)

        options.svgProfile = "display"
        var fallback = work; fallback.sourceText = nil
        XCTAssertEqual(try display(ExportSource(work: fallback)).1.descriptions, [work.input, "original SVG note"])
        var empty = work; empty.sourceText = ""
        XCTAssertEqual(try display(ExportSource(work: empty)).1.descriptions, ["", "original SVG note"])
    }

    // Failure: the DDL envelope loses aliases, includes unused plugins, or rounds a u64 definition value.
    func testDDLExportRetainsOnlyNamedDefinitionsWithoutRounding() throws {
        let definition = try ExactJSON(data: Data(#"{"schema":"inku.macro-definition.v1","namespace":"Nature","heading":"leaves","aliases":["foliage"],"seed":18446744073709551615}"#.utf8))
        let unused = try ExactJSON(data: Data(#"{"namespace":"Nature","heading":"unused"}"#.utf8))
        var work = source().work; work.ddl = "Nature.foliage"; work.instructionLangResolved = "en"
        let originalSVG = work.svg
        let exported = try ExactJSON(data: ExportService.ddl(ExportSource(work: work, pluginDefinitions: [definition, unused, definition], pluginSummaries: ["saved definition"])))
        XCTAssertEqual(exported["schema"].string, "inku.ddl-export.v1")
        XCTAssertEqual(exported["ddl"].string, work.ddl)
        let plugins = try XCTUnwrap(exported["plugins"].array)
        XCTAssertEqual(plugins.count, 1)
        XCTAssertEqual(plugins[0]["definition"]["seed"].number, "18446744073709551615")
        XCTAssertEqual(plugins[0]["summary"].string, "saved definition")
        var options = ExportOptions(); options.format = .svg; options.svgProfile = "canonical"
        XCTAssertEqual(try ExportService.render(sources: [ExportSource(work: work)], options: options)[0].data, Data(originalSVG.utf8))
        options.svgProfile = "compat"
        XCTAssertThrowsError(try ExportService.render(sources: [ExportSource(work: work)], options: options))
    }

    // Failure: AI sheets drop trailing selections or omit the full description-to-badge mapping.
    func testAISheetPaginationNotesAndBundledCardFont() throws {
        let sources = (1...13).map { number in
            var work = source(id: String(number)).work
            work.sourceText = "作品\(number)の説明\n省略しない二行目"
            return ExportSource(work: work)
        }
        var options = ExportOptions(); options.format = .aiSheet
        let artifacts = try ExportService.render(sources: sources, options: options)
        XCTAssertEqual(artifacts.count, 3)
        let first = try XCTUnwrap(CGImageSourceCreateWithData(artifacts[0].data as CFData, nil))
        let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(first, 0, nil))
        XCTAssertEqual(max(image.width, image.height), 1568)
        let notes = String(decoding: artifacts[2].data, as: UTF8.self)
        XCTAssertTrue(notes.contains("sheet: inku-ai-sheet-2.png (No.13)"))
        XCTAssertTrue(notes.contains("## No.13\ndescription:\n```\n作品13の説明\n省略しない二行目\n```"))
        options.format = .shareCard; options.cardLayout = "portrait"; options.pixelHeight = 300
        let card = try ExportService.render(sources: [sources[0]], options: options)
        let decoder = try XCTUnwrap(CGImageSourceCreateWithData(card[0].data as CFData, nil))
        let cardImage = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoder, 0, nil))
        XCTAssertEqual(cardImage.width, 240); XCTAssertEqual(cardImage.height, 300)
    }
}

private final class DisplaySVGDescriptionDecoder: NSObject, XMLParserDelegate {
    var descriptions: [String] = []
    var rootChildren: [String] = []
    private var depth = 0
    private var descriptionIndex: Int?

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String]) {
        if depth == 1 {
            rootChildren.append(elementName)
            if elementName == "desc" {
                descriptionIndex = descriptions.count
                descriptions.append("")
            }
        }
        depth += 1
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        if let descriptionIndex { descriptions[descriptionIndex] += string }
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        if depth == 2, elementName == "desc" { descriptionIndex = nil }
        depth -= 1
    }
}
