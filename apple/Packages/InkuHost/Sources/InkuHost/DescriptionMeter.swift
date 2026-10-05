import Foundation
import InkuCore

public struct DictionaryMeterCount: Codable, Sendable, Equatable {
    public let mora: Int?
    public let phrases: [Int]?
    public let unread: [String]?
    public let syllables: Int?
    public let lines: [Int]?
    public let unknown: [String]?
}

/// Each editor gets a guarded answer; the actor shares only successful dictionary reads.
public actor DescriptionMeter {
    public static let shared = DescriptionMeter()
    private var cache: [String: DictionaryMeterCount] = [:]
    private var order: [String] = []
    public init() {}

    public func count(text: String, language: String) async throws -> DictionaryMeterCount {
        try Task.checkCancellation()
        guard text.unicodeScalars.count <= 4000 else { throw HostError("meter_text_too_long") }
        guard language == "ja" || language == "en" else { throw HostError("meter_language_invalid") }
        let key = language + ":" + text
        if let value = cache[key] { return value }
        guard let directory = Bundle.module.url(forResource: "description-meter", withExtension: nil),
              FileManager.default.fileExists(atPath: directory.appendingPathComponent("manifest.json").path) else {
            throw HostError("meter_resources_not_prepared")
        }
        let data = await Task.detached(priority: .utility) {
            InkuCore.countDescriptionMeter(text: text, languageCode: language, dictionaryDirectory: directory.path)
        }.value
        try Task.checkCancellation()
        let value = try ExactJSON(data: data)
        if let code = value["error"].string { throw HostError(code) }
        let answer = try JSONDecoder().decode(DictionaryMeterCount.self, from: data)
        guard language == "ja" ? answer.mora != nil && answer.phrases != nil && answer.unread != nil
            : answer.syllables != nil && answer.lines != nil && answer.unknown != nil else { throw HostError("meter_dictionary_response_invalid") }
        cache[key] = answer; order.append(key)
        if order.count > 32 { cache.removeValue(forKey: order.removeFirst()) }
        return answer
    }
}
