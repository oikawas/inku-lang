import CoreGraphics
import Foundation
import ImageIO

struct IconPreparationFailure: Error {
    let message: String
    init(_ message: String) { self.message = message }
}

func prepareIcon() throws {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let source = root.appendingPathComponent("docs/assets/incu-icon-512.png")
    let output = root.appendingPathComponent("apple/Resources/AppIcon.icns")
    guard let decoder = CGImageSourceCreateWithURL(source as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(decoder, 0, nil), image.width == 512, image.height == 512 else {
        throw IconPreparationFailure("The incu source icon must be a readable 512×512 PNG.")
    }
    let files = FileManager.default
    let temporary = files.temporaryDirectory.appendingPathComponent("inku-macos-icon-\(UUID().uuidString)", isDirectory: true)
    let iconset = temporary.appendingPathComponent("AppIcon.iconset", isDirectory: true)
    try files.createDirectory(at: iconset, withIntermediateDirectories: true)
    defer { try? files.removeItem(at: temporary) }
    let slots = [
        ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
    ]
    for (name, size) in slots {
        let destination = iconset.appendingPathComponent(name)
        if size == 512 {
            try files.copyItem(at: source, to: destination)
            continue
        }
        guard let context = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: size * 4,
                                      space: image.colorSpace ?? CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            throw IconPreparationFailure("Could not allocate the \(size)px icon slot.")
        }
        // Preserve the source's pixel boundaries, including the 2× 1024px slot.
        context.interpolationQuality = .none
        context.setShouldAntialias(false)
        context.setBlendMode(.copy)
        context.draw(image, in: CGRect(x: 0, y: 0, width: size, height: size))
        guard let resized = context.makeImage(),
              let encoder = CGImageDestinationCreateWithURL(destination as CFURL, "public.png" as CFString, 1, nil) else {
            throw IconPreparationFailure("Could not encode the \(size)px icon slot.")
        }
        CGImageDestinationAddImage(encoder, resized, nil)
        guard CGImageDestinationFinalize(encoder) else { throw IconPreparationFailure("Could not finish the \(size)px icon slot.") }
    }
    let generated = temporary.appendingPathComponent("AppIcon.icns")
    let conversion = Process()
    conversion.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
    conversion.arguments = ["--convert", "icns", "--output", generated.path, iconset.path]
    try conversion.run()
    conversion.waitUntilExit()
    guard conversion.terminationStatus == 0 else { throw IconPreparationFailure("iconutil failed (\(conversion.terminationStatus)).") }
    try files.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
    let data = try Data(contentsOf: generated)
    try data.write(to: output, options: .atomic)
    print("Prepared incu macOS icon: \(output.path) (10 slots, 16–1024px, nearest resizing, \(data.count) bytes)")
}

do {
    try prepareIcon()
} catch {
    let message = (error as? IconPreparationFailure)?.message ?? String(describing: error)
    FileHandle.standardError.write(Data("Icon preparation failed: \(message)\n".utf8))
    exit(1)
}
