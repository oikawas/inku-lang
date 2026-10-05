import Foundation

public enum ProviderObservationPolicy {
    public static let maximumRawBytes = 16 * 1_024 * 1_024
    public static var developerModeEnabled: Bool {
        ["1", "true", "yes", "on"].contains((ProcessInfo.processInfo.environment["INKU_DEVELOPER_MODE"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }
}

public struct ProviderActionIdentity: Codable, Sendable, Equatable {
    public let actionID: String
    public let attempt: UInt32
    public let requestDigest: String
    public init(actionID: String, attempt: UInt32, requestDigest: String) {
        self.actionID = actionID; self.attempt = attempt; self.requestDigest = requestDigest
    }
    public init(action: Data) throws {
        let identity = try ExactJSON(data: action).requiredObject("identity")
        guard let attempt = identity["attempt"].number.flatMap(UInt32.init), attempt > 0 else {
            throw HostError("pipeline_schema_violation")
        }
        self.init(actionID: try identity.requiredString("action_id"), attempt: attempt,
                  requestDigest: try identity.requiredString("request_digest"))
    }
}

public enum ProviderObservationStage: String, Codable, Sendable {
    case stage1, composition, stage2
    public init?(action: String) {
        switch action {
        case "read_composition": self = .composition
        case "complete_visible_ddl_holes": self = .stage2
        case "generate_sketch", "select_description_catalog", "generate_normalized_ddl": self = .stage1
        default: return nil
        }
    }
}

public struct ProviderUsage: Codable, Sendable, Equatable {
    public let inputTokens: UInt64?
    public let outputTokens: UInt64?
    public let totalTokens: UInt64?
    public init(inputTokens: UInt64? = nil, outputTokens: UInt64? = nil, totalTokens: UInt64? = nil) {
        self.inputTokens = inputTokens; self.outputTokens = outputTokens; self.totalTokens = totalTokens
    }
    static func reported(in value: ExactJSON) -> ProviderUsage? {
        let usage = value["usageMetadata"].object != nil ? value["usageMetadata"] : value["usage"]
        func token(_ keys: [String]) -> UInt64? {
            keys.lazy.compactMap { usage[$0].number.flatMap(UInt64.init) }.first
        }
        let result = ProviderUsage(inputTokens: token(["input_tokens", "prompt_tokens", "promptTokenCount"]),
            outputTokens: token(["output_tokens", "completion_tokens", "candidatesTokenCount"]),
            totalTokens: token(["total_tokens", "totalTokenCount"]))
        return result.inputTokens == nil && result.outputTokens == nil && result.totalTokens == nil ? nil : result
    }
}

public enum ProviderAttemptOutcome: String, Codable, Sendable { case requestSaved, completed, failed, cancelled }

/// Ordinary generation information. This type cannot contain provider bodies or secrets.
public struct ProviderAttemptMetric: Codable, Sendable, Equatable {
    public let identity: ProviderActionIdentity
    public let action: String
    public let stage: ProviderObservationStage
    public let requestedModelReference: String
    public var providerID: String?
    public var model: String?
    public var responseModel: String?
    public let timeoutMS: UInt64
    public var elapsedMS: UInt64?
    public var usage: ProviderUsage?
    public var httpStatus: Int?
    public var outcome: ProviderAttemptOutcome
    public var failure: String?
    public var sent: Bool
    public var diagnostic: ProviderAttemptDiagnostic?
    public init(identity: ProviderActionIdentity, action: String, stage: ProviderObservationStage,
                requestedModelReference: String, providerID: String? = nil, model: String? = nil,
                responseModel: String? = nil, timeoutMS: UInt64, elapsedMS: UInt64? = nil,
                usage: ProviderUsage? = nil, httpStatus: Int? = nil, outcome: ProviderAttemptOutcome = .requestSaved,
                failure: String? = nil, sent: Bool = false, diagnostic: ProviderAttemptDiagnostic? = nil) {
        self.identity = identity; self.action = action; self.stage = stage; self.requestedModelReference = requestedModelReference
        self.providerID = providerID; self.model = model; self.responseModel = responseModel; self.timeoutMS = timeoutMS
        self.elapsedMS = elapsedMS; self.usage = usage; self.httpStatus = httpStatus; self.outcome = outcome
        self.failure = failure; self.sent = sent; self.diagnostic = diagnostic
    }
}

public struct ProviderRawObservation: Codable, Sendable, Equatable {
    public var requestBody: String?
    public var responseBody: String?
    public var requestTruncated: Bool
    public var responseTruncated: Bool
    public var responseIncomplete: Bool
    public var captureComplete: Bool
    public init(requestBody: String? = nil, responseBody: String? = nil, requestTruncated: Bool = false,
                responseTruncated: Bool = false, responseIncomplete: Bool = true, captureComplete: Bool = false) {
        self.requestBody = requestBody; self.responseBody = responseBody; self.requestTruncated = requestTruncated
        self.responseTruncated = responseTruncated; self.responseIncomplete = responseIncomplete; self.captureComplete = captureComplete
    }
}

/// Private execution storage only; callers of the ordinary metric API receive `metric`.
public struct ProviderAttemptObservation: Codable, Sendable, Equatable {
    public var metric: ProviderAttemptMetric
    public var raw: ProviderRawObservation?
    public init(metric: ProviderAttemptMetric, raw: ProviderRawObservation? = nil) { self.metric = metric; self.raw = raw }
}

public struct ProviderObservationOptions: Sendable {
    public let captureRaw: Bool
    public let maximumRawBytes: Int
    public init(captureRaw: Bool = false, maximumRawBytes: Int = ProviderObservationPolicy.maximumRawBytes) {
        self.captureRaw = captureRaw
        self.maximumRawBytes = max(1, min(maximumRawBytes, ProviderObservationPolicy.maximumRawBytes))
    }
}

/// A persistence failure must escape transport retry classification.
public enum ProviderObservationFailure: Error, Sendable, Equatable {
    case requestSaveFailed, outcomeSaveFailed, unsupportedTransport
}
public typealias ProviderObservationHandler = @Sendable (ProviderAttemptObservation) async throws -> Void

public protocol ObservedProviderTransport: ProviderTransport {
    func performObserved(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                         observation: ProviderObservationOptions, willSend: @escaping ProviderObservationHandler,
                         didFinish: @escaping ProviderObservationHandler, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data
}

public protocol ObservedChatGPTPlanEffectTransport: ChatGPTPlanEffectTransport {
    func performPersonalPlanObserved(action: Data, models: ModelSelection, providers: [ProviderSettings],
                                    session: ChatGPTPlanSession?, argumentLimit: Int, credentials: any CredentialStore,
                                    observation: ProviderObservationOptions, willSend: @escaping ProviderObservationHandler,
                                    didFinish: @escaping ProviderObservationHandler, onBytes: @escaping @Sendable (Int) -> Void,
                                    onDiagnostic: @escaping @Sendable (ChatGPTPlanDiagnostic) -> Void) async throws -> Data
}

/// Only response facts cross this boundary, never request URLs or headers.
struct ProviderHTTPRead: Sendable {
    let status: Int?
    let data: Data?
    let sent: Bool
    let complete: Bool
    let truncated: Bool
}
typealias ProviderHTTPReadHandler = @Sendable (ProviderHTTPRead) -> Void

struct ProviderHTTPResponse: Sendable {
    let status: Int
    let data: Data
    var retryAfter: Double = 60
}
protocol ProviderHTTPClient: Sendable {
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse
}

/// Synchronous byte callbacks can arrive from a task being cancelled by its deadline.
/// The final snapshot is read only after that task has drained.
final class ProviderAttemptRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private let began = ContinuousClock.now
    private let options: ProviderObservationOptions
    private var value: ProviderAttemptObservation
    private var secrets: [String] = []
    private var received: ProviderHTTPRead?
    private var endpoint: URL?
    private var operation: ProviderAttemptDiagnosticOperation?

    init(action: Data, reference: String, options: ProviderObservationOptions) throws {
        let effect = try ExactJSON(data: action), tag = try effect.requiredString("tag")
        guard let stage = ProviderObservationStage(action: tag),
              let timeout = UInt64(try effect.requiredString("timeout_ms")), timeout > 0 else {
            throw HostError("pipeline_schema_violation")
        }
        self.options = options
        value = ProviderAttemptObservation(metric: ProviderAttemptMetric(identity: try ProviderActionIdentity(action: action),
            action: tag, stage: stage, requestedModelReference: reference, timeoutMS: timeout),
            raw: options.captureRaw ? ProviderRawObservation() : nil)
    }
    func prepare(body: Data, providerID: String, model: String, secrets: [String]) {
        lock.withLock {
            self.secrets += secrets.filter { !$0.isEmpty }
            value.metric.providerID = ProviderSecretRedactor.redact(providerID, secrets: self.secrets)
            value.metric.model = ProviderSecretRedactor.redact(model, secrets: self.secrets)
            if options.captureRaw {
                let (text, truncated) = bounded(body)
                value.raw?.requestBody = text; value.raw?.requestTruncated = truncated
            }
        }
    }
    func addSecrets(_ secrets: [String]) { lock.withLock { self.secrets += secrets.filter { !$0.isEmpty } } }
    func setEndpoint(_ endpoint: URL) { lock.withLock { self.endpoint = endpoint } }
    func setOperation(_ operation: ProviderAttemptDiagnosticOperation?) { lock.withLock { self.operation = operation } }
    func recordFailure(_ error: any Error, httpStatus: Int? = nil, httpBody: Data? = nil) {
        lock.withLock {
            value.metric.diagnostic = ProviderDiagnosticSanitizer.diagnostic(error: error, endpoint: endpoint,
                secrets: secrets, httpStatus: httpStatus, httpBody: httpBody, operation: operation)
        }
    }
    func receive(_ response: ProviderHTTPRead) {
        lock.withLock {
            received = response
            if let data = response.data {
                for facts in ProviderResponseFacts.reported(in: data) { reportLocked(facts) }
            }
        }
    }
    func report(_ response: ExactJSON) {
        lock.withLock { reportLocked(response) }
    }
    private func reportLocked(_ response: ExactJSON) {
        if let usage = ProviderUsage.reported(in: response) { value.metric.usage = usage }
        if let model = response["model"].string, model.utf8.count <= 4_096 {
            value.metric.responseModel = ProviderSecretRedactor.redact(model, secrets: secrets)
        }
    }
    func saveRequest(_ callback: ProviderObservationHandler) async throws {
        let snapshot = lock.withLock { value }
        do { try await callback(snapshot) } catch { throw ProviderObservationFailure.requestSaveFailed }
    }
    func finish(failure: String?, cancelled: Bool = false, callback: ProviderObservationHandler) async throws {
        let snapshot = lock.withLock {
            let parts = began.duration(to: .now).components
            value.metric.elapsedMS = UInt64(max(0, parts.seconds * 1_000 + parts.attoseconds / 1_000_000_000_000_000))
            value.metric.failure = failure
            value.metric.outcome = cancelled ? .cancelled : (failure == nil ? .completed : .failed)
            if let received {
                value.metric.sent = received.sent; value.metric.httpStatus = received.status
                if options.captureRaw {
                    let captured = received.data.map { bounded($0, incomplete: !received.complete || received.truncated) }
                    let truncated = captured?.1 ?? false
                    value.raw?.responseBody = captured?.0
                    value.raw?.responseTruncated = truncated || received.truncated
                    value.raw?.responseIncomplete = !received.complete || cancelled
                    let requestTruncated = value.raw?.requestTruncated ?? true
                    value.raw?.captureComplete = failure == nil && !cancelled && received.complete && !received.truncated
                        && !truncated && !requestTruncated
                }
            }
            return value
        }
        do { try await callback(snapshot) } catch { throw ProviderObservationFailure.outcomeSaveFailed }
    }
    private func bounded(_ data: Data, incomplete: Bool = false) -> (String, Bool) {
        // Mask before slicing: a credential crossing the byte limit must not leak a prefix.
        let masked = Data(ProviderSecretRedactor.redact(String(decoding: data, as: UTF8.self), secrets: secrets, incomplete: incomplete).utf8)
        var end = min(masked.count, options.maximumRawBytes)
        if end < masked.count {
            while end > 0 && (masked[end] & 0xc0) == 0x80 { end -= 1 }
        }
        return (String(decoding: masked.prefix(end), as: UTF8.self), masked.count > options.maximumRawBytes)
    }
}

enum ProviderSecretRedactor {
    static func redact(_ text: String, secrets: [String], incomplete: Bool = false) -> String {
        let secrets = Array(Set(secrets.filter { !$0.isEmpty })).sorted { $0.count > $1.count }
        guard !secrets.isEmpty else { return text }
        func mask(_ value: String) -> String {
            secrets.reduce(value) { $0.replacingOccurrences(of: $1, with: "[redacted]") }
        }
        // Decode individual JSON strings to catch escaped quotes, backslashes and Unicode
        // escapes without re-encoding the surrounding JSON or SSE frames.
        let bytes = Array(text.utf8)
        var output = Data(), index = 0
        while index < bytes.count {
            guard bytes[index] == 34 else { output.append(bytes[index]); index += 1; continue }
            let start = index; index += 1
            var escaped = false
            while index < bytes.count {
                let byte = bytes[index]; index += 1
                if escaped { escaped = false }
                else if byte == 92 { escaped = true }
                else if byte == 34 { break }
            }
            let token = Data(bytes[start..<index])
            if let decoded = try? JSONDecoder().decode(String.self, from: token), mask(decoded) != decoded {
                output.append(ExactJSON.string(mask(decoded)).data)
            } else { output.append(token) }
        }
        var result = mask(String(decoding: output, as: UTF8.self))
        if incomplete {
            // A failed read can end inside a literal or JSON-escaped credential.
            for secret in secrets {
                let escaped = String(ExactJSON.string(secret).text.dropFirst().dropLast())
                let unicode = secret.utf16.map { String(format: "\\u%04x", $0) }.joined()
                for variant in Set([secret, escaped, escaped.replacingOccurrences(of: "/", with: "\\/"), unicode, unicode.uppercased().replacingOccurrences(of: "\\U", with: "\\u")]) {
                    result = maskPartialTail(result, pattern: Array(variant.utf8))
                }
            }
        }
        return result
    }
    private static func maskPartialTail(_ text: String, pattern: [UInt8]) -> String {
        guard pattern.count > 1 else { return text }
        // Linear prefix matching keeps the maximum-size OAuth token bounded too.
        var prefix = [Int](repeating: 0, count: pattern.count)
        for index in 1..<pattern.count {
            var matched = prefix[index - 1]
            while matched > 0 && pattern[index] != pattern[matched] { matched = prefix[matched - 1] }
            if pattern[index] == pattern[matched] { matched += 1 }
            prefix[index] = matched
        }
        let bytes = Array(text.utf8)
        var matched = 0
        for byte in bytes.suffix(pattern.count - 1) {
            while matched > 0 && byte != pattern[matched] { matched = prefix[matched - 1] }
            if byte == pattern[matched] { matched += 1 }
        }
        guard matched > 0 else { return text }
        return String(decoding: bytes.dropLast(matched), as: UTF8.self) + "[redacted]"
    }
}

private enum ProviderResponseFacts {
    static func reported(in data: Data) -> [ExactJSON] {
        if let value = try? ExactJSON(data: data), value.object != nil { return [value] }
        // Read metadata only from complete SSE frames, never from partial tool arguments.
        let text = String(decoding: data, as: UTF8.self).replacingOccurrences(of: "\r\n", with: "\n")
        let frames = text.components(separatedBy: "\n\n").dropLast()
        return frames.compactMap { frame in
            let payload = frame.components(separatedBy: "\n").filter { $0.hasPrefix("data:") }
                .map { String($0.dropFirst(5)).trimmingCharacters(in: .whitespaces) }.joined(separator: "\n")
            guard let event = try? ExactJSON(data: Data(payload.utf8)),
                  ["response.completed", "response.failed", "response.incomplete"].contains(event["type"].string ?? ""),
                  event["response"].object != nil else { return nil }
            return event["response"]
        }
    }
}
