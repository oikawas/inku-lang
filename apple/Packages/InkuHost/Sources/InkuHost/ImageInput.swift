import Foundation
import CryptoKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import InkuCore

/// The encoded image is transient and must not be placed in a persisted execution.
public struct PreparedImageInput: Sendable {
    public let jpeg: Data
    public let width: Int
    public let height: Int
    public let originalWidth: Int
    public let originalHeight: Int
    public let nearestFormatID: String
    public var sha256: String { SHA256.hash(data: jpeg).map { String(format: "%02x", $0) }.joined() }
    public var authoringJSON: Data {
        ExactJSON.object(["sent": .object(["media_type": .string("image/jpeg"), "width": .integer(width),
            "height": .integer(height), "sha256": .string(sha256), "byte_len": .integer(jpeg.count)]),
            "original_width": .integer(originalWidth), "original_height": .integer(originalHeight)]).data
    }
}

public enum ImageInput {
    public static func prepare(_ raw: Data) throws -> PreparedImageInput {
        guard !raw.isEmpty else { throw HostError("image_invalid") }
        guard raw.count <= 32 * 1024 * 1024 else { throw HostError("image_too_large") }
        guard let source = CGImageSourceCreateWithData(raw as CFData, nil),
              let type = CGImageSourceGetType(source) as String?,
              [UTType.jpeg.identifier, UTType.png.identifier, UTType.gif.identifier, UTType.tiff.identifier].contains(type),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let rawWidth = properties[kCGImagePropertyPixelWidth] as? Int,
              let rawHeight = properties[kCGImagePropertyPixelHeight] as? Int,
              rawWidth > 0, rawHeight > 0 else { throw HostError("image_invalid") }
        let orientation = properties[kCGImagePropertyOrientation] as? Int ?? 1
        let swapped = (5...8).contains(orientation)
        let width = swapped ? rawHeight : rawWidth
        let height = swapped ? rawWidth : rawHeight
        let request = try JSONSerialization.data(withJSONObject: ["original": [width, height]])
        guard let canvas = try JSONSerialization.jsonObject(with: InkuCore.imageCanvas(request)) as? [String: Any],
              let sent = canvas["sent"] as? [Int], sent.count == 2, sent[0] > 0, sent[1] > 0,
              let format = canvas["nearest_format_id"] as? String,
              let policyRoot = try JSONSerialization.jsonObject(with: Data(InkuCore.imageInputPolicy().utf8)) as? [String: Any],
              let policy = policyRoot["policy"] as? [String: Any],
              let quality = policy["jpeg_quality"] as? Int, let maxBytes = policy["max_bytes"] as? Int else {
            throw HostError("image_invalid")
        }
        let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: max(sent[0], sent[1]),
            kCGImageSourceShouldCacheImmediately: true]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary),
              let context = CGContext(data: nil, width: sent[0], height: sent[1], bitsPerComponent: 8,
                                      bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { throw HostError("image_invalid") }
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: sent[0], height: sent[1]))
        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: sent[0], height: sent[1]))
        guard let flattened = context.makeImage() else { throw HostError("image_invalid") }
        let encoded = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(encoded, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw HostError("image_invalid")
        }
        CGImageDestinationAddImage(destination, flattened, [kCGImageDestinationLossyCompressionQuality: Double(quality) / 100] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw HostError("image_invalid") }
        let jpeg = encoded as Data
        guard jpeg.count <= maxBytes else { throw HostError("image_too_large") }
        return PreparedImageInput(jpeg: jpeg, width: sent[0], height: sent[1], originalWidth: width,
                                  originalHeight: height, nearestFormatID: format)
    }
}
