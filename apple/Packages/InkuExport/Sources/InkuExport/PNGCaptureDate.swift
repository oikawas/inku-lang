import Foundation

/// Web pngMetadata.ts: the PNG carries the work's generation time as an `eXIf` chunk (read as EXIF by Finder,
/// Preview, Lightroom and exiftool) and a `tEXt` "Creation Time" entry, both right after IHDR.
public enum PNGCaptureDate {
    private static let signature: [UInt8] = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]
    private static let crcTable: [UInt32] = (0..<256).map { n in
        (0..<8).reduce(UInt32(n)) { c, _ in c & 1 != 0 ? 0xedb88320 ^ (c >> 1) : c >> 1 }
    }

    /// A copy of `png` carrying `date` in local time; bytes that are not a PNG are returned unchanged.
    public static func stamp(_ png: Data, date: Date, timeZone: TimeZone = .current) -> Data {
        let source = [UInt8](png)
        guard source.count >= 8 + 25, Array(source.prefix(8)) == signature else { return png }
        let ihdrLength = Int(source[8]) << 24 | Int(source[9]) << 16 | Int(source[10]) << 8 | Int(source[11])
        let insertAt = 8 + 12 + ihdrLength
        guard insertAt <= source.count else { return png }
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = timeZone
        let parts = calendar.dateComponents([.year, .month, .day, .hour, .minute, .second, .weekday], from: date)
        let minutes = timeZone.secondsFromGMT(for: date) / 60
        let offset = (minutes < 0 ? "-" : "+") + pad(abs(minutes) / 60) + ":" + pad(abs(minutes) % 60)
        let exifDate = "\(parts.year!):\(pad(parts.month!)):\(pad(parts.day!)) \(pad(parts.hour!)):\(pad(parts.minute!)):\(pad(parts.second!))"
        let days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        let rfc1123 = "\(days[parts.weekday! - 1]), \(pad(parts.day!)) \(months[parts.month! - 1]) \(parts.year!) "
            + "\(pad(parts.hour!)):\(pad(parts.minute!)):\(pad(parts.second!)) " + offset.replacingOccurrences(of: ":", with: "")
        let exif = chunk("eXIf", exifBlock(date: exifDate, offset: offset))
        let text = chunk("tEXt", Array(("Creation Time\0" + rfc1123).utf8))
        return Data(source[..<insertAt] + exif + text + source[insertAt...])
    }

    private static func pad(_ value: Int) -> String { value < 10 ? "0\(value)" : String(value) }

    private static func chunk(_ type: String, _ data: [UInt8]) -> [UInt8] {
        let body = Array(type.utf8) + data
        let crc = ~body.reduce(UInt32.max) { c, byte in crcTable[Int((c ^ UInt32(byte)) & 0xff)] ^ (c >> 8) }
        return bigEndian(UInt32(data.count)) + body + bigEndian(crc)
    }
    private static func bigEndian(_ value: UInt32) -> [UInt8] { [24, 16, 8, 0].map { UInt8((value >> $0) & 0xff) } }

    /// Little-endian TIFF: IFD0 DateTime and the Exif IFD pointer; the Exif IFD holds ExifVersion 0231,
    /// DateTimeOriginal, DateTimeDigitized and the three OffsetTime tags.
    private static func exifBlock(date: String, offset: String) -> [UInt8] {
        let ifd0 = 8, exifIFD = ifd0 + 2 + 2 * 12 + 4, dateAt = exifIFD + 2 + 6 * 12 + 4, offsetAt = dateAt + 20
        var bytes = [UInt8](repeating: 0, count: offsetAt + 7)
        func put16(_ at: Int, _ value: Int) { bytes[at] = UInt8(value & 0xff); bytes[at + 1] = UInt8(value >> 8 & 0xff) }
        func put32(_ at: Int, _ value: Int) { for index in 0..<4 { bytes[at + index] = UInt8(value >> (8 * index) & 0xff) } }
        bytes[0] = 0x49; bytes[1] = 0x49; put16(2, 42); put32(4, ifd0)
        var cursor = ifd0
        func entry(_ tag: Int, _ type: Int, _ count: Int, _ value: (Int) -> Void) {
            put16(cursor, tag); put16(cursor + 2, type); put32(cursor + 4, count); value(cursor + 8); cursor += 12
        }
        put16(cursor, 2); cursor += 2
        entry(0x0132, 2, 20) { put32($0, dateAt) }
        entry(0x8769, 4, 1) { put32($0, exifIFD) }
        put32(cursor, 0); cursor += 4
        put16(cursor, 6); cursor += 2
        entry(0x9000, 7, 4) { at in bytes.replaceSubrange(at..<(at + 4), with: [0x30, 0x32, 0x33, 0x31]) }
        entry(0x9003, 2, 20) { put32($0, dateAt) }
        entry(0x9004, 2, 20) { put32($0, dateAt) }
        entry(0x9010, 2, 7) { put32($0, offsetAt) }
        entry(0x9011, 2, 7) { put32($0, offsetAt) }
        entry(0x9012, 2, 7) { put32($0, offsetAt) }
        put32(cursor, 0)
        for (index, byte) in date.utf8.prefix(19).enumerated() { bytes[dateAt + index] = byte }
        for (index, byte) in offset.utf8.prefix(6).enumerated() { bytes[offsetAt + index] = byte }
        return bytes
    }
}
