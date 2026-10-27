import Foundation
import ImageIO

/// Only the named camera fields are read; GPS is never requested or copied.
public enum ImageProvenance {
    public static func text(url: URL, includeFileName: Bool, includeExif: Bool, language: String) -> String {
        let en = language == "en"
        var lines: [String] = []
        if includeFileName { lines.append("\(en ? "File name" : "ファイル名"): \(url.lastPathComponent)") }
        guard includeExif, let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] else { return lines.joined(separator: "\n") }
        let tiff = props[kCGImagePropertyTIFFDictionary] as? [CFString: Any] ?? [:]
        let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any] ?? [:]
        if let date = exif[kCGImagePropertyExifDateTimeOriginal] as? String { lines.append("\(en ? "Taken at" : "撮影日時"): \(date)") }
        let make = tiff[kCGImagePropertyTIFFMake] as? String ?? ""
        let camera = tiff[kCGImagePropertyTIFFModel] as? String ?? ""
        let body = camera.lowercased().hasPrefix(make.lowercased()) ? camera : [make, camera].filter { !$0.isEmpty }.joined(separator: " ")
        if !body.isEmpty { lines.append("\(en ? "Camera" : "カメラ"): \(body)") }
        if let lens = exif[kCGImagePropertyExifLensModel] as? String, !lens.isEmpty { lines.append("\(en ? "Lens" : "レンズ"): \(lens)") }
        var exposure: [String] = []
        if let f = exif[kCGImagePropertyExifFNumber] as? Double, f > 0 { exposure.append("f/\(f)") }
        if let s = exif[kCGImagePropertyExifExposureTime] as? Double, s > 0 { exposure.append(s < 0.5 ? "1/\(Int((1 / s).rounded())) s" : "\(s) s") }
        if let iso = (exif[kCGImagePropertyExifISOSpeedRatings] as? [Int])?.first, iso > 0 { exposure.append("ISO \(iso)") }
        if let focal = exif[kCGImagePropertyExifFocalLength] as? Double, focal > 0 { exposure.append("\(focal) mm") }
        if !exposure.isEmpty { lines.append("\(en ? "Exposure" : "露出"): " + exposure.joined(separator: " · ")) }
        return lines.joined(separator: "\n")
    }
}
