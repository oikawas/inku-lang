import Foundation
import InkuPersistence

public protocol ProviderTransport: Sendable {
    /// Performs one attempt. Retries and schema validation belong to the shared core.
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings],
                 credentials: any CredentialStore, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data
}

public final class URLSessionProviderTransport: ObservedProviderTransport, Sendable {
    private let budget: ProviderRateBudget
    private let http: (any ProviderHTTPClient)?
    private let legacyUsageURL: URL
    public let maximumResponseBytes: Int
    public convenience init(maximumResponseBytes: Int = 1_048_576, usageURL: URL? = nil) {
        self.init(maximumResponseBytes: maximumResponseBytes, usageURL: usageURL, http: nil, database: nil)
    }
    public convenience init(database: InkuDatabase, maximumResponseBytes: Int = 1_048_576, usageURL: URL? = nil) {
        self.init(maximumResponseBytes: maximumResponseBytes, usageURL: usageURL, http: nil, database: database)
    }
    init(maximumResponseBytes: Int = 1_048_576, usageURL: URL? = nil, http: (any ProviderHTTPClient)?,
         database: InkuDatabase? = nil, environment: ProviderRateEnvironment = .live) {
        self.maximumResponseBytes = max(1, maximumResponseBytes)
        self.legacyUsageURL = usageURL ?? Self.defaultUsageURL
        self.budget = ProviderRateBudget(database: database, legacyURL: legacyUsageURL, environment: environment)
        self.http = http
    }
    private static func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil; configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.httpCookieStorage = nil; configuration.httpShouldSetCookies = false
        return URLSession(configuration: configuration, delegate: RejectRedirects(), delegateQueue: nil)
    }
    public func withRateDatabase(_ database: InkuDatabase) -> URLSessionProviderTransport {
        URLSessionProviderTransport(maximumResponseBytes: maximumResponseBytes, usageURL: legacyUsageURL,
                                    http: http, database: database, environment: budget.environment)
    }
    private static var defaultUsageURL: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("app.inku", isDirectory: true).appendingPathComponent("provider-usage.json")
    }

    public func perform(action: Data, models: ModelSelection, providers: [ProviderSettings],
                        credentials: any CredentialStore, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        try await performAttempt(action: action, models: models, providers: providers, credentials: credentials,
                                 recorder: nil, willSend: { _ in }, didFinish: { _ in }, onBytes: onBytes)
    }
    public func performObserved(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                                observation: ProviderObservationOptions, willSend: @escaping ProviderObservationHandler,
                                didFinish: @escaping ProviderObservationHandler, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let effect = try ExactJSON(data: action)
        let reference = effect["tag"].string == "complete_visible_ddl_holes" ? models.stage2Model : models.stage1Model
        let recorder = try ProviderAttemptRecorder(action: action, reference: reference, options: observation)
        return try await performAttempt(action: action, models: models, providers: providers, credentials: credentials,
                                        recorder: recorder, willSend: willSend, didFinish: didFinish, onBytes: onBytes)
    }
    private func performAttempt(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                                recorder: ProviderAttemptRecorder?, willSend: @escaping ProviderObservationHandler,
                                didFinish: @escaping ProviderObservationHandler, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let effect = try ExactJSON(data: action)
        let identity = try effect.requiredObject("identity")
        let tag = try effect.requiredString("tag")
        let results = ["generate_sketch": "sketch_generated", "select_description_catalog": "description_catalog_selected",
                       "generate_normalized_ddl": "normalized_ddl_generated", "read_composition": "composition_read",
                       "complete_visible_ddl_holes": "visible_ddl_hole_patch_generated"]
        guard let resultTag = results[tag],
              let timeoutMS = UInt64(try effect.requiredString("timeout_ms")),
              timeoutMS <= UInt64.max / 1_000_000 else { throw HostError("pipeline_schema_violation") }
        let began = ContinuousClock.now
        let deadline = budget.now().addingTimeInterval(Double(timeoutMS) / 1000)
        let modelReference = tag == "complete_visible_ddl_holes" ? models.stage2Model : models.stage1Model
        let maxTokens = tag == "complete_visible_ddl_holes" ? models.holeMaxTokens : models.stage1MaxTokens
        var failure: String?
        var response: String?
        let rateWait = ProviderRateWait()
        recorder?.setOperation(.preparation)
        do {
            // Server raises TimeoutError for a non-positive attempt timeout.
            guard timeoutMS > 0 else { throw HostError("transport_timeout") }
            let (provider, model) = try resolve(modelReference, providers: providers)
            recorder?.setEndpoint(provider.baseURL)
            let key = try await credentials.key(for: provider.credentialID)
            recorder?.addSecrets(key.map { [$0] } ?? [])
            var request = try ProviderWire.request(action: action, provider: provider, model: model, maxTokens: maxTokens, key: key)
            request.timeoutInterval = Double(timeoutMS) / 1000
            let boundedRequest = request
            if let recorder {
                recorder.prepare(body: boundedRequest.httpBody ?? Data(), providerID: provider.id, model: model, secrets: key.map { [$0] } ?? [])
                // This gate precedes inference and Gemini's optional token-count HTTP call.
                try await recorder.saveRequest(willSend)
            }
            let remaining = deadline.timeIntervalSince(budget.now())
            guard remaining > 0 else { throw HostError("transport_timeout") }
            // One HTTP client per core-owned attempt, shared only by token count and generation.
            // Structured concurrency drains the cancelled task group before this session closes.
            let attemptSession = http == nil ? Self.makeSession() : nil
            defer { attemptSession?.invalidateAndCancel() }
            let raw = try await withThrowingTaskGroup(of: Data.self) { group in
                // The provider slot is held for the whole attempt, inside its deadline (provider_limits.py).
                group.addTask { [self] in try await ProviderConcurrencySlots.shared.holding(provider.id) {
                    let limits = provider.effectiveRateLimits
                    var inputTokens = limits.tokensPerMinute > 0 ? (boundedRequest.httpBody?.count ?? 0) + 128 : 0
                    // Gemini token accounting asks the provider for the same exact request.
                    if provider.kind == .gemini, limits.tokensPerMinute > 0 {
                        recorder?.setOperation(.admission)
                        try await self.budget.prepare(provider: provider)
                        recorder?.setOperation(.tokenCount)
                        do { inputTokens = try await self.countGeminiTokens(boundedRequest, session: attemptSession) }
                        catch {
                            if let status = error as? HTTPFailure, status.status == 429 {
                                recorder?.setOperation(.admission)
                                try await self.budget.coolDown(providerID: provider.id, seconds: status.retryAfter)
                                recorder?.setOperation(.tokenCount)
                            }
                            throw error
                        }
                    }
                    recorder?.setOperation(.admission)
                    rateWait.set(true)
                    let reservation = try await self.budget.reserve(provider: provider, inputTokens: inputTokens, deadline: deadline)
                    rateWait.set(false)
                    var bytes: Data?, used: Int?, attemptError: (any Error)?
                    recorder?.setOperation(.generation)
                    do {
                        try Task.checkCancellation()
                        guard self.budget.now() < deadline else { throw HostError("rate_limited") }
                        bytes = try await self.readObserved(boundedRequest, session: attemptSession,
                            maximum: self.maximumResponseBytes, onBytes: onBytes,
                            onResponse: { recorder?.receive($0) })
                        let value = try ExactJSON(data: bytes!)
                        recorder?.report(value)
                        let usage = provider.kind == .gemini ? value["usageMetadata"] : value["usage"]
                        let tokenKey = provider.kind == .gemini ? "promptTokenCount" : (provider.kind == .anthropic ? "input_tokens" : "prompt_tokens")
                        used = usage[tokenKey].number.flatMap(Int.init).flatMap { $0 >= 0 ? $0 : nil }
                    } catch { attemptError = error }
                    recorder?.setOperation(.admission)
                    if let status = attemptError as? HTTPFailure, status.status == 429 {
                        try await self.budget.coolDown(providerID: provider.id, seconds: status.retryAfter)
                    }
                    // Unknown TPM retains its reservation and closes admission for 62 seconds.
                    try await self.budget.settle(providerID: provider.id, reservation: reservation,
                                                used: used ?? (limits.tokensPerMinute == 0 ? 0 : nil))
                    recorder?.setOperation(.generation)
                    if let attemptError { throw attemptError }
                    return bytes!
                } }
                group.addTask {
                    try await Task.sleep(for: .seconds(remaining))
                    throw ProviderAttemptDeadline()
                }
                defer { group.cancelAll() }
                guard let result = try await group.next() else { throw HostError("transport_unavailable") }
                return result
            }
            response = try ProviderWire.responseText(raw, kind: provider.kind)
        } catch let error as ProviderObservationFailure { throw error }
        catch is CancellationError {
            try await recorder?.finish(failure: nil, cancelled: true, callback: didFinish)
            throw CancellationError()
        }
        catch is ProviderAttemptDeadline {
            // The whole-attempt deadline can expire while a child is draining.
            // Do not attribute it to whichever HTTP operation finished cancellation last.
            // A deadline reached while waiting for admission is Server's rate_limit_wait.
            let waiting = rateWait.value
            recorder?.setOperation(waiting ? .admission : nil)
            failure = waiting ? "rate_limited" : "transport_timeout"
            recorder?.recordFailure(HostError(failure!))
        }
        catch let error as HTTPFailure {
            recorder?.recordFailure(error, httpStatus: error.status, httpBody: error.body)
            failure = error.status == 429 ? "rate_limited" : (error.status >= 500 ? "transport_unavailable" : "provider_rejected")
        } catch let error as URLError {
            if error.code == .cancelled && Task.isCancelled {
                try await recorder?.finish(failure: nil, cancelled: true, callback: didFinish)
                throw CancellationError()
            }
            recorder?.recordFailure(error)
            failure = error.code == .timedOut ? "transport_timeout" : "transport_unavailable"
        } catch let error as HostError {
            recorder?.recordFailure(error)
            switch error.code {
            case "transport_timeout", "rate_limited", "transport_unavailable": failure = error.code
            case "malformed_payload", "invalid_json", "duplicate_json_key": failure = "malformed_payload"
            default: failure = "provider_rejected"
            }
        } catch {
            // What remains are rate-ledger failures (database, legacy import), which Server reports as
            // RateAccountingUnavailable -> transport_unavailable.
            recorder?.recordFailure(error)
            failure = "transport_unavailable"
        }
        let elapsed = began.duration(to: .now)
        let parts = elapsed.components
        let milliseconds = max(0, parts.seconds * 1000 + parts.attoseconds / 1_000_000_000_000_000)
        try await recorder?.finish(failure: failure, callback: didFinish)
        var result: ExactJSON = .object(["tag": .string(failure == nil ? resultTag : "provider_failed"), "identity": identity,
                                        "elapsed_ms": .string(String(milliseconds))])
        if let failure { result["failure"] = .string(failure) }
        else { result["response"] = .string(response!) }
        return result.data
    }

    private func readObserved(_ request: URLRequest, session: URLSession?, maximum: Int, onBytes: @escaping @Sendable (Int) -> Void,
                              onResponse: @escaping ProviderHTTPReadHandler) async throws -> Data {
        if let http {
            // Calling a client does not prove it connected or sent a request.
            onResponse(ProviderHTTPRead(status: nil, data: nil, sent: false, complete: false, truncated: false))
            let response = try await http.send(request, maximumBytes: maximum, onBytes: onBytes, onResponse: onResponse)
            guard (200...299).contains(response.status) else {
                throw HTTPFailure(status: response.status,
                    retryAfter: ProviderRateBudget.retryAfter(String(response.retryAfter), raw: response.data, now: budget.now()), body: response.data)
            }
            return response.data
        }
        guard let session else { throw HostError("transport_unavailable") }
        var data = Data(), status: Int?, complete = false, truncated = false
        // An HTTP response proves a send; a connection error before response headers does not.
        defer { onResponse(ProviderHTTPRead(status: status, data: data, sent: status != nil, complete: complete, truncated: truncated)) }
        let (bytes, response) = try await session.bytes(for: request)
        defer { bytes.task.cancel() }
        guard let response = response as? HTTPURLResponse else { throw HostError("transport_unavailable") }
        status = response.statusCode
        let success = (200...299).contains(response.statusCode)
        let limit = success ? maximum : min(maximum, 65_536)
        // Keep the received prefix and status even when the server advertises an oversized body.
        do {
            for try await byte in bytes {
                try Task.checkCancellation()
                guard data.count < limit else { truncated = true; break }
                data.append(byte)
                if data.count % 4096 == 0 { onBytes(data.count) }
            }
        } catch {
            if !success && !Task.isCancelled {
                throw HTTPFailure(status: response.statusCode,
                    retryAfter: ProviderRateBudget.retryAfter(response.value(forHTTPHeaderField: "Retry-After"), raw: data, now: budget.now()), body: data)
            }
            throw error
        }
        onBytes(data.count)
        complete = !truncated
        if !success {
            throw HTTPFailure(status: response.statusCode,
                retryAfter: ProviderRateBudget.retryAfter(response.value(forHTTPHeaderField: "Retry-After"), raw: data, now: budget.now()), body: data)
        }
        // Server raises ValueError for an oversized answer: provider_rejected, which the core does not retry.
        guard !truncated else { throw HostError("provider_response_too_large") }
        return data
    }

    private func resolve(_ reference: String, providers: [ProviderSettings]) throws -> (ProviderSettings, String) {
        let (providerID, model) = ProviderModelReference.resolve(reference, providers: providers)
        guard !model.isEmpty, let provider = providers.first(where: { $0.id == providerID }) else { throw HostError("provider_selection_required") }
        return (provider, model)
    }

    /// Vision and other auxiliary routes share HTTP policy, not pipeline accounting.
    public func performAuxiliary(prompt: AuxiliaryPrompt, modelReference: String, settings: HostSettings,
                                 credentials: any CredentialStore,
                                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        let (provider, model) = try resolve(modelReference, providers: settings.providers)
        let key = try await credentials.key(for: provider.credentialID)
        let request = try AuxiliaryWire.request(prompt: prompt, provider: provider, model: model, key: key)
        // Server's demo calls the Anthropic and OpenAI SDKs (two retries by default) and Gemini through urllib
        // (none); Vision uses one httpx request.
        let retries = prompt.purpose == .demo && provider.kind != .gemini ? 2 : 0
        do {
            var attempt = 0
            while true {
                do {
                    let raw = try await auxiliaryAttempt(request, timeout: prompt.timeoutSeconds, onBytes: onBytes)
                    try Task.checkCancellation()
                    return try AuxiliaryWire.responseText(raw, kind: provider.kind, purpose: prompt.purpose)
                } catch {
                    guard attempt < retries, let delay = Self.sdkRetryDelay(error, retry: attempt, kind: provider.kind) else { throw error }
                    attempt += 1
                    try await Task.sleep(for: .seconds(delay))
                }
            }
        } catch is CancellationError { throw CancellationError() }
        catch let error as HTTPFailure {
            throw HostError(error.status == 429 ? "rate_limited" : error.status >= 500 ? "transport_unavailable" : "provider_rejected")
        } catch let error as URLError {
            if error.code == .cancelled && Task.isCancelled { throw CancellationError() }
            throw HostError(error.code == .timedOut ? "transport_timeout" : "transport_unavailable")
        }
    }

    private func countGeminiTokens(_ original: URLRequest, session: URLSession?) async throws -> Int {
        guard let originalURL = original.url,
              let originalBody = original.httpBody,
              let url = URL(string: originalURL.absoluteString.replacingOccurrences(of: ":generateContent", with: ":countTokens")) else { throw HostError("rate_limited") }
        let requestBody = try ExactJSON(data: originalBody)
        var inner = requestBody
        let modelPath = originalURL.path.components(separatedBy: "/models/").last?.replacingOccurrences(of: ":generateContent", with: "") ?? ""
        inner["model"] = .string("models/" + modelPath)
        var request = original; request.url = url
        request.httpBody = Data(ExactJSON.object(["generateContentRequest": inner]).orderedText.utf8)
        let value = try ExactJSON(data: await readObserved(request, session: session, maximum: min(16384, maximumResponseBytes),
            onBytes: { _ in }, onResponse: { _ in }))
        guard value.object != nil else { throw HostError("malformed_payload") }
        guard let count = value["totalTokens"].number.flatMap(Int.init), count >= 0, count <= (Int.max - 9) / 11 else { throw HostError("rate_limited") }
        return (count * 11 + 9) / 10
    }

    private func auxiliaryAttempt(_ request: URLRequest, timeout: Double, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        try await withThrowingTaskGroup(of: Data.self) { group in
            group.addTask { [self] in
                try await self.read(request, maximum: self.maximumResponseBytes, onBytes: onBytes)
            }
            group.addTask {
                try await Task.sleep(for: .seconds(timeout))
                throw HostError("transport_timeout")
            }
            defer { group.cancelAll() }
            guard let bytes = try await group.next() else { throw HostError("transport_unavailable") }
            return bytes
        }
    }

    /// The Anthropic (0.120) and OpenAI (2.52) Python SDK policy: 408, 409, 429, 5xx and connection or timeout
    /// failures, `x-should-retry` first, a short server-directed delay, else 0.5 s doubling to 8 s with jitter.
    static func sdkRetryDelay(_ error: any Error, retry: Int, kind: ProviderKind, random: Double = .random(in: 0..<1)) -> Double? {
        if let failure = error as? HTTPFailure {
            // OpenAI gives up on a Retry-After beyond two minutes; Anthropic falls back to its own backoff.
            let ceiling: Double = kind == .anthropic ? 60 : 120
            if kind != .anthropic, let after = failure.serverDelay, after.isFinite, after > ceiling { return nil }
            if let header = failure.shouldRetry { guard header else { return nil } }
            else { guard [408, 409, 429].contains(failure.status) || failure.status >= 500 else { return nil } }
            if let after = failure.serverDelay, after.isFinite, after > 0, after <= ceiling { return after }
        } else if let error = error as? URLError {
            guard error.code != .cancelled else { return nil }
        } else if (error as? HostError)?.code != "transport_timeout" { return nil }
        return min(0.5 * pow(2, Double(retry)), 8) * (1 - 0.25 * random)
    }

    /// `retry-after-ms`, then `retry-after` as seconds or an HTTP date, as both SDKs read them.
    static func sdkRetryAfter(_ response: HTTPURLResponse, now: Date = Date()) -> Double? {
        if let value = response.value(forHTTPHeaderField: "retry-after-ms").flatMap(Double.init) { return value / 1000 }
        guard let header = response.value(forHTTPHeaderField: "retry-after") else { return nil }
        if let seconds = Double(header) { return seconds }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
        return formatter.date(from: header).map { $0.timeIntervalSince(now) }
    }

    private func read(_ request: URLRequest, maximum: Int, onBytes: @Sendable (Int) -> Void) async throws -> Data {
        // One HTTP client per request, as Server opens one for each auxiliary call.
        let session = Self.makeSession()
        defer { session.invalidateAndCancel() }
        let (bytes, response) = try await session.bytes(for: request)
        defer { bytes.task.cancel() }
        guard let response = response as? HTTPURLResponse else { throw HostError("transport_unavailable") }
        guard (200...299).contains(response.statusCode) else {
            let retry = response.value(forHTTPHeaderField: "Retry-After").flatMap(Double.init) ?? 60
            throw HTTPFailure(status: response.statusCode, retryAfter: max(0, retry),
                              shouldRetry: response.value(forHTTPHeaderField: "x-should-retry").flatMap { ["true": true, "false": false][$0] },
                              serverDelay: Self.sdkRetryAfter(response))
        }
        if response.expectedContentLength > Int64(maximum) { throw HostError("malformed_payload") }
        var raw = Data(); raw.reserveCapacity(min(maximum, 65536))
        for try await byte in bytes {
            try Task.checkCancellation()
            guard raw.count < maximum else { throw HostError("malformed_payload") }
            raw.append(byte)
            if raw.count % 4096 == 0 { onBytes(raw.count) }
        }
        onBytes(raw.count)
        return raw
    }
}

private struct ProviderAttemptDeadline: Error {}

/// Server provider_limits.py: Ollama Cloud refuses above two simultaneous requests, so its pipeline
/// requests wait for one of two slots. The limit belongs to the builtin provider ID, not to a setting.
actor ProviderConcurrencySlots {
    static let shared = ProviderConcurrencySlots()
    static func limit(providerID: String) -> Int { providerID == "ollama-cloud" ? 2 : 0 }
    private var active: [String: Int] = [:]
    private var waiters: [String: [(id: UUID, continuation: CheckedContinuation<Void, any Error>)]] = [:]

    nonisolated func holding<T: Sendable>(_ providerID: String, _ operation: @Sendable () async throws -> T) async throws -> T {
        let limit = Self.limit(providerID: providerID)
        guard limit > 0 else { return try await operation() }
        try await acquire(providerID, limit: limit)
        do {
            let value = try await operation()
            await release(providerID)
            return value
        } catch {
            await release(providerID)
            throw error
        }
    }
    private func acquire(_ providerID: String, limit: Int) async throws {
        try Task.checkCancellation()
        if active[providerID, default: 0] < limit { active[providerID, default: 0] += 1; return }
        let id = UUID()
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                waiters[providerID, default: []].append((id, continuation))
            }
        } onCancel: { Task { await self.abandon(providerID, id) } }
    }
    private func abandon(_ providerID: String, _ id: UUID) {
        guard let index = waiters[providerID]?.firstIndex(where: { $0.id == id }) else { return }
        waiters[providerID]!.remove(at: index).continuation.resume(throwing: CancellationError())
    }
    private func release(_ providerID: String) {
        // A waiting request takes the released slot directly.
        if let next = waiters[providerID]?.first {
            waiters[providerID]!.removeFirst(); next.continuation.resume()
        } else { active[providerID, default: 1] -= 1 }
    }
}
/// Set while an attempt waits for rate admission, read after its task group has drained.
private final class ProviderRateWait: @unchecked Sendable {
    private let lock = NSLock()
    private var waiting = false
    var value: Bool { lock.withLock { waiting } }
    func set(_ value: Bool) { lock.withLock { waiting = value } }
}
struct HTTPFailure: Error {
    let status: Int; let retryAfter: Double; var body: Data? = nil
    var shouldRetry: Bool? = nil; var serverDelay: Double? = nil
}
private final class RejectRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}
