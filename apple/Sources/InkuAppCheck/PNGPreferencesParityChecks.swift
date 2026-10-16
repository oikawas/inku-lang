import CoreGraphics
import Foundation
import ImageIO
import InkuExport
import InkuPersistence
import InkuUI

/// Failure: old PNG choices invert or invert twice, a missing old field takes the new-install default,
/// or the single-work switch changes clipboard/bulk/card/animation options.
@MainActor
func runPNGPreferencesParityChecks() throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-png-preferences-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let noFile = DisplaySettings()
    noFile.connect(directory: folder)
    guard !noFile.preferences.singleWorkPNGTransparent else { throw CheckFailure.message("New PNG preferences must start white") }

    let svg = #"<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="1" height="1" fill="red"/></svg>"#
    let work = SavedWork(id: "png-migration", at: 1, input: "透明", score: "{}", svg: svg)
    for (json, transparent) in [
        (#"{"exportConfiguration":{"options":{"pngAlphaWhite":true}}}"#, false),
        (#"{"exportConfiguration":{"options":{"pngAlphaWhite":false}}}"#, true),
        (#"{"exportConfiguration":{"options":{}}}"#, true),
        (#"{}"#, true),
        (#"{"pngPreferencesVersion":1,"singleWorkPNGTransparent":false,"exportConfiguration":{"options":{"pngAlphaWhite":false}}}"#, false),
        (#"{"pngPreferencesVersion":1,"singleWorkPNGTransparent":true,"exportConfiguration":{"options":{"pngAlphaWhite":true}}}"#, true)
    ] {
        try Data(json.utf8).write(to: folder.appendingPathComponent("interface.json"), options: .atomic)
        let settings = DisplaySettings()
        settings.connect(directory: folder)
        var preferences = settings.preferences
        guard preferences.pngPreferencesVersion == 1, preferences.singleWorkPNGTransparent == transparent else {
            throw CheckFailure.message("PNG migration lost the effective old background: \(json)")
        }
        let originalLegacyOptions = preferences.exportConfiguration?.options
        let originalClipboard = preferences.clipboardExportOptions(height: 64)
        var options = preferences.singleWorkPNGOptions(height: 64)
        let artifacts = try ExportService.render(sources: [ExportSource(work: work)], options: options)
        guard let bytes = artifacts.first?.data,
              let source = CGImageSourceCreateWithData(bytes as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
              let context = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8,
                                      bytesPerRow: image.width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else {
            throw CheckFailure.message("PNG migration fixture could not be decoded")
        }
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        guard let pixels = context.data else { throw CheckFailure.message("PNG migration fixture has no pixels") }
        let corner = pixels.assumingMemoryBound(to: UInt8.self).advanced(by: (image.width * image.height - 1) * 4)
        guard corner[3] == (transparent ? 0 : 255), transparent || (corner[0] == 255 && corner[1] == 255 && corner[2] == 255) else {
            throw CheckFailure.message("PNG transparency adapter produced the opposite pixels")
        }
        for _ in 0..<2 {
            settings.preferences = preferences
            let reopened = DisplaySettings()
            reopened.connect(directory: folder)
            preferences = reopened.preferences
            guard settings.saveError == nil, reopened.saveError == nil, preferences.singleWorkPNGTransparent == transparent,
                  preferences.exportConfiguration?.options == originalLegacyOptions else {
                throw CheckFailure.message("PNG migration repeated or rewrote legacy export options")
            }
        }
        preferences.singleWorkPNGTransparent.toggle()
        guard preferences.clipboardExportOptions(height: 64) == originalClipboard,
              originalClipboard.pngAlphaWhite,
              preferences.exportConfiguration?.options == originalLegacyOptions else {
            throw CheckFailure.message("Single-work PNG choice leaked into another output path")
        }
        options = preferences.clipboardExportOptions(height: 64)
        preferences.clipboardFormat = "card"
        guard options.format == .png, preferences.clipboardExportOptions(height: 64).format == .shareCard else {
            throw CheckFailure.message("Clipboard card selection was lost")
        }
    }
    let configured = ExportTemplate(id: "custom", name: "保存済み", description: "小さいPNG", pixelHeight: 67)
    var preferences = DisplayPreferences()
    preferences.exportTemplates = [configured]
    guard preferences.savedPNGTemplates == [configured], preferences.animationDefaults.options.format == .apng,
          preferences.animationDefaults.resolution == 1080 else { throw CheckFailure.message("PNG templates or animation defaults were not resolved") }
    guard work.svg == svg else { throw CheckFailure.message("PNG output mutated the saved work") }
    print("PNG preferences passed: old true/false/missing, no-file default, versioned choices, two reloads, actual alpha/white pixels, clipboard isolation, saved template, animation defaults. Temporary interface fixtures only.")
}
