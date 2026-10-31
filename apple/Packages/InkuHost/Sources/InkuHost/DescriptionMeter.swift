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
    private var cache: [Data: DictionaryMeterCount] = [:]
    private var order: [Data] = []
    private struct Flight {
        let text: String
        let language: String
        let directory: URL
        var waiters: [UUID: CheckedContinuation<DictionaryMeterCount, any Error>] = [:]
        var started = false
    }
    private var flights: [Data: Flight] = [:]
    private var pending: [Data] = []
    private var active = 0
    private let maximumActive = 2
    private let calculate: @Sendable (String, String, URL) -> Data
    public init() {
        calculate = { text, language, directory in
            InkuCore.countDescriptionMeter(text: text, languageCode: language, dictionaryDirectory: directory.path)
        }
    }
    init(calculate: @escaping @Sendable (String, String, URL) -> Data) { self.calculate = calculate }
    func waitingCountForChecks(text: String, language: String) -> Int {
        flights[Data((language + ":" + text).utf8)]?.waiters.count ?? 0
    }

    public func count(text: String, language: String) async throws -> DictionaryMeterCount {
        try Task.checkCancellation()
        guard text.unicodeScalars.count <= 4000 else { throw HostError("meter_text_too_long") }
        guard language == "ja" || language == "en" else { throw HostError("meter_language_invalid") }
        // Preserve exact spelling: Swift String equality folds canonically
        // equivalent text, while the answer can contain original unread words.
        let key = Data((language + ":" + text).utf8)
        if let value = cache[key] { return value }
        guard let directory = Bundle.module.url(forResource: "description-meter", withExtension: nil),
              FileManager.default.fileExists(atPath: directory.appendingPathComponent("manifest.json").path) else {
            throw HostError("meter_resources_not_prepared")
        }
        let waiter = UUID()
        let answer: DictionaryMeterCount = try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<DictionaryMeterCount, any Error>) in
                if Task.isCancelled { continuation.resume(throwing: CancellationError()); return }
                if flights[key] == nil {
                    flights[key] = Flight(text: text, language: language, directory: directory)
                    pending.append(key)
                }
                flights[key]?.waiters[waiter] = continuation
                startPending()
            }
        } onCancel: {
            Task { await self.cancelWaiter(waiter, key: key) }
        }
        try Task.checkCancellation()
        return answer
    }

    private func cancelWaiter(_ waiter: UUID, key: Data) {
        guard var flight = flights[key], let continuation = flight.waiters.removeValue(forKey: waiter) else { return }
        continuation.resume(throwing: CancellationError())
        if flight.waiters.isEmpty && !flight.started {
            flights[key] = nil
            pending.removeAll { $0 == key }
        } else { flights[key] = flight }
    }

    private func startPending() {
        while active < maximumActive, !pending.isEmpty {
            let key = pending.removeFirst()
            guard var flight = flights[key], !flight.waiters.isEmpty else { flights[key] = nil; continue }
            flight.started = true
            flights[key] = flight
            active += 1
            let (text, language, directory, calculate) = (flight.text, flight.language, flight.directory, self.calculate)
            Task.detached(priority: .utility) {
                let data = calculate(text, language, directory)
                await self.finish(key: key, data: data)
            }
        }
    }

    private func finish(key: Data, data: Data) {
        guard let flight = flights.removeValue(forKey: key), flight.started else { return }
        active -= 1
        if !flight.waiters.isEmpty {
            let result: Result<DictionaryMeterCount, any Error> = Result {
                let value = try ExactJSON(data: data)
                if let code = value["error"].string { throw HostError(code) }
                let answer = try JSONDecoder().decode(DictionaryMeterCount.self, from: data)
                guard flight.language == "ja" ? answer.mora != nil && answer.phrases != nil && answer.unread != nil
                    : answer.syllables != nil && answer.lines != nil && answer.unknown != nil else { throw HostError("meter_dictionary_response_invalid") }
                return answer
            }
            if case .success(let answer) = result {
                cache[key] = answer; order.append(key)
                if order.count > 32 { cache.removeValue(forKey: order.removeFirst()) }
            }
            for continuation in flight.waiters.values { continuation.resume(with: result) }
        }
        startPending()
    }
}
