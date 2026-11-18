import Foundation
import ImageIO

/// Only the named camera fields are read; GPS is never requested or copied.
public enum ImageProvenance {
    public static func text(url: URL, includeFileName: Bool, includeExif: Bool, language: String) -> String {
        text(fileName: url.lastPathComponent, source: includeExif ? CGImageSourceCreateWithURL(url as CFURL, nil) : nil,
             includeFileName: includeFileName, includeExif: includeExif, language: language)
    }

    /// The same text from bytes already read: a chosen file (`fileName`), or a photo, which has no file name.
    public static func text(data: Data, fileName: String?, includeFileName: Bool, includeExif: Bool, language: String) -> String {
        text(fileName: fileName, source: includeExif ? CGImageSourceCreateWithData(data as CFData, nil) : nil,
             includeFileName: includeFileName, includeExif: includeExif, language: language)
    }

    private static func text(fileName: String?, source: CGImageSource?, includeFileName: Bool, includeExif: Bool, language: String) -> String {
        let en = language == "en"
        var first: [String] = []
        var second: [String] = []
        if includeFileName, let name = fileName?.trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty {
            first.append("\(en ? "File name" : "ファイル名"): \(name)")
        }
        guard includeExif, let source,
              let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] else { return first.joined(separator: " · ") }
        let tiff = props[kCGImagePropertyTIFFDictionary] as? [CFString: Any] ?? [:]
        let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any] ?? [:]
        if let date = (exif[kCGImagePropertyExifDateTimeOriginal] ?? tiff[kCGImagePropertyTIFFDateTime]) as? String, !date.isEmpty { first.append(date) }
        let make = tiff[kCGImagePropertyTIFFMake] as? String ?? ""
        let camera = tiff[kCGImagePropertyTIFFModel] as? String ?? ""
        let body = camera.lowercased().hasPrefix(make.lowercased()) ? camera : [make, camera].filter { !$0.isEmpty }.joined(separator: " ")
        if !body.isEmpty { second.append(body) }
        func number(_ value: Double) -> String {
            let rounded = (value * 10).rounded() / 10
            return rounded.rounded() == rounded ? String(format: "%.0f", rounded) : String(format: "%.1f", rounded)
        }
        if let f = exif[kCGImagePropertyExifFNumber] as? Double, f > 0 { second.append("f/\(number(f))") }
        if let s = exif[kCGImagePropertyExifExposureTime] as? Double, s > 0 { second.append(s < 0.5 ? "1/\(Int((1 / s).rounded())) s" : "\(number(s)) s") }
        if let iso = (exif[kCGImagePropertyExifISOSpeedRatings] as? [Int])?.first, iso > 0 { second.append("ISO \(iso)") }
        if let focal = exif[kCGImagePropertyExifFocalLength] as? Double, focal > 0 { second.append("\(number(focal)) mm") }
        return [first, second].filter { !$0.isEmpty }.map { $0.joined(separator: " · ") }.joined(separator: "\n")
    }
}
