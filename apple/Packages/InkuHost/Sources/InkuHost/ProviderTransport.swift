import Foundation

public protocol ProviderTransport: Sendable {
    /// Performs one attempt. Retries and schema validation belong to the shared core.
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings],
                 credentials: any CredentialStore, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data
}

public final class URLSessionProviderTransport: ObservedProviderTransport, Sendable {
    private let session: URLSession
    private let budget: ProviderRateBudget
    private let http: (any ProviderHTTPClient)?
    public let maximumResponseBytes: Int
    public convenience init(maximumResponseBytes: Int = 1_048_576, usageURL: URL? = nil) {
        self.init(maximumResponseBytes: maximumResponseBytes, usageURL: usageURL, http: nil)
    }
    init(maximumResponseBytes: Int = 1_048_576, usageURL: URL? = nil, http: (any ProviderHTTPClient)?) {
        self.maximumResponseBytes = max(1, maximumResponseBytes)
        self.budget = ProviderRateBudget(url: usageURL ?? Self.defaultUsageURL)
        self.http = http
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil; configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.httpCookieStorage = nil; configuration.httpShouldSetCookies = false
        self.session = URLSession(configuration: configuration, delegate: RejectRedirects(), delegateQueue: nil)
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
              let timeoutMS = UInt64(try effect.requiredString("timeout_ms")), timeoutMS > 0,
              timeoutMS <= UInt64.max / 1_000_000 else { throw HostError("pipeline_schema_violation") }
        let began = ContinuousClock.now
        let modelReference = tag == "complete_visible_ddl_holes" ? models.stage2Model : models.stage1Model
        let maxTokens = tag == "complete_visible_ddl_holes" ? models.holeMaxTokens : models.stage1MaxTokens
        var failure: String?
        var response: String?
        do {
            let (provider, model) = try resolve(modelReference, providers: providers)
            let key = try await credentials.key(for: provider.credentialID)
            var request = try ProviderWire.request(action: action, provider: provider, model: model, maxTokens: maxTokens, key: key)
            request.timeoutInterval = Double(timeoutMS) / 1000
            let boundedRequest = request
            if let recorder {
                recorder.prepare(body: boundedRequest.httpBody ?? Data(), providerID: provider.id, model: model, secrets: key.map { [$0] } ?? [])
                // This gate precedes inference and Gemini's optional token-count HTTP call.
                try await recorder.saveRequest(willSend)
            }
            let raw = try await withThrowingTaskGroup(of: Data.self) { group in
                group.addTask { [self] in
                    var inputTokens = (boundedRequest.httpBody?.count ?? 0) + 128
                    // Gemini token accounting asks the provider for the same exact request.
                    if provider.kind == .gemini, provider.rateLimits?.tokensPerMinute != nil {
                        inputTokens = try await self.countGeminiTokens(boundedRequest)
                    }
                    let reservation = try await self.budget.reserve(provider: provider, inputTokens: inputTokens)
                    do {
                        let bytes: Data
                        if let recorder {
                            bytes = try await self.readObserved(boundedRequest, maximum: self.maximumResponseBytes, onBytes: onBytes,
                                onResponse: { recorder.receive($0) })
                        } else { bytes = try await self.read(boundedRequest, maximum: self.maximumResponseBytes, onBytes: onBytes) }
                        let value = try ExactJSON(data: bytes)
                        recorder?.report(value)
                        let usage = provider.kind == .gemini ? value["usageMetadata"] : value["usage"]
                        let tokenKey = provider.kind == .gemini ? "promptTokenCount" : (provider.kind == .anthropic ? "input_tokens" : "prompt_tokens")
                        let used = usage[tokenKey].number.flatMap(Int.init)
                        try await self.budget.settle(providerID: provider.id, reservation: reservation, used: used)
                        return bytes
                    } catch {
                        if let status = error as? HTTPFailure, status.status == 429 {
                            try await self.budget.coolDown(providerID: provider.id, seconds: status.retryAfter)
                        }
                        // An uncertain attempt retains its reservation to avoid over-admission.
                        throw error
                    }
                }
                group.addTask {
                    try await Task.sleep(nanoseconds: timeoutMS * 1_000_000)
                    throw HostError("transport_timeout")
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
        catch let error as HTTPFailure {
            failure = error.status == 429 ? "rate_limited" : (error.status >= 500 ? "transport_unavailable" : "provider_rejected")
        } catch let error as URLError {
            if error.code == .cancelled && Task.isCancelled {
                try await recorder?.finish(failure: nil, cancelled: true, callback: didFinish)
                throw CancellationError()
            }
            failure = error.code == .timedOut ? "transport_timeout" : "transport_unavailable"
        } catch let error as HostError {
            switch error.code {
            case "transport_timeout", "rate_limited", "transport_unavailable": failure = error.code
            case "malformed_payload", "invalid_json", "duplicate_json_key": failure = "malformed_payload"
            default: failure = "provider_rejected"
            }
        } catch { failure = "transport_unavailable" }
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

    private func readObserved(_ request: URLRequest, maximum: Int, onBytes: @escaping @Sendable (Int) -> Void,
                              onResponse: @escaping ProviderHTTPReadHandler) async throws -> Data {
        if let http {
            onResponse(ProviderHTTPRead(status: nil, data: nil, sent: true, complete: false, truncated: false))
            let response = try await http.send(request, maximumBytes: maximum, onBytes: onBytes, onResponse: onResponse)
            guard (200...299).contains(response.status) else { throw HTTPFailure(status: response.status, retryAfter: response.retryAfter) }
            return response.data
        }
        var data = Data(), status: Int?, complete = false, truncated = false
        defer { onResponse(ProviderHTTPRead(status: status, data: data, sent: true, complete: complete, truncated: truncated)) }
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
                    retryAfter: response.value(forHTTPHeaderField: "Retry-After").flatMap(Double.init) ?? 60)
            }
            throw error
        }
        onBytes(data.count)
        complete = !truncated
        if !success {
            throw HTTPFailure(status: response.statusCode,
                retryAfter: response.value(forHTTPHeaderField: "Retry-After").flatMap(Double.init) ?? 60)
        }
        guard !truncated else { throw HostError("malformed_payload") }
        return data
    }

    private func resolve(_ reference: String, providers: [ProviderSettings]) throws -> (ProviderSettings, String) {
        if let colon = reference.firstIndex(of: ":") {
            let providerID = String(reference[..<colon]); let model = String(reference[reference.index(after: colon)...])
            if let provider = providers.first(where: { $0.id == providerID }), !model.isEmpty { return (provider, model) }
        } else if providers.count == 1, !reference.isEmpty { return (providers[0], reference) }
        throw HostError("provider_selection_required")
    }

    /// Auxiliary calls share the pipeline transport's reservations and HTTP boundary.
    public func performAuxiliary(prompt: AuxiliaryPrompt, modelReference: String, settings: HostSettings,
                                 credentials: any CredentialStore,
                                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        let (provider, model) = try resolve(modelReference, providers: settings.providers)
        let key = try await credentials.key(for: provider.credentialID)
        let request = try AuxiliaryWire.request(prompt: prompt, provider: provider, model: model, key: key)
        do {
            let raw = try await withThrowingTaskGroup(of: Data.self) { group in
                group.addTask { [self] in
                    var inputTokens = (request.httpBody?.count ?? 0) + 128
                    if provider.kind == .gemini, provider.rateLimits?.tokensPerMinute != nil {
                        inputTokens = try await self.countGeminiTokens(request)
                    }
                    let reservation = try await self.budget.reserve(provider: provider, inputTokens: inputTokens)
                    do {
                        let bytes = try await self.read(request, maximum: self.maximumResponseBytes, onBytes: onBytes)
                        let value = try ExactJSON(data: bytes)
                        let usage = provider.kind == .gemini ? value["usageMetadata"] : value["usage"]
                        let key = provider.kind == .gemini ? "promptTokenCount" : (provider.kind == .anthropic ? "input_tokens" : "prompt_tokens")
                        try await self.budget.settle(providerID: provider.id, reservation: reservation,
                                                   used: usage[key].number.flatMap(Int.init))
                        return bytes
                    } catch {
                        if let failure = error as? HTTPFailure, failure.status == 429 {
                            try await self.budget.coolDown(providerID: provider.id, seconds: failure.retryAfter)
                        }
                        throw error
                    }
                }
                group.addTask {
                    try await Task.sleep(for: .seconds(prompt.timeoutSeconds))
                    throw HostError("transport_timeout")
                }
                defer { group.cancelAll() }
                guard let bytes = try await group.next() else { throw HostError("transport_unavailable") }
                return bytes
            }
            try Task.checkCancellation()
            return try AuxiliaryWire.responseText(raw, kind: provider.kind)
        } catch is CancellationError { throw CancellationError() }
        catch let error as HTTPFailure {
            throw HostError(error.status == 429 ? "rate_limited" : error.status >= 500 ? "transport_unavailable" : "provider_rejected")
        } catch let error as URLError {
            if error.code == .cancelled && Task.isCancelled { throw CancellationError() }
            throw HostError(error.code == .timedOut ? "transport_timeout" : "transport_unavailable")
        }
    }

    private func countGeminiTokens(_ original: URLRequest) async throws -> Int {
        guard let originalURL = original.url,
              let originalBody = original.httpBody,
              let url = URL(string: originalURL.absoluteString.replacingOccurrences(of: ":generateContent", with: ":countTokens")) else { throw HostError("rate_limited") }
        let requestBody = try ExactJSON(data: originalBody)
        var inner = requestBody
        let modelPath = originalURL.path.components(separatedBy: "/models/").last?.replacingOccurrences(of: ":generateContent", with: "") ?? ""
        inner["model"] = .string("models/" + modelPath)
        var request = original; request.url = url
        request.httpBody = ExactJSON.object(["generateContentRequest": inner]).data
        let value = try ExactJSON(data: await read(request, maximum: min(16384, maximumResponseBytes), onBytes: { _ in }))
        guard let count = value["totalTokens"].number.flatMap(Int.init), count >= 0, count <= (Int.max - 9) / 11 else { throw HostError("rate_limited") }
        return (count * 11 + 9) / 10
    }

    private func read(_ request: URLRequest, maximum: Int, onBytes: @Sendable (Int) -> Void) async throws -> Data {
        let (bytes, response) = try await session.bytes(for: request)
        defer { bytes.task.cancel() }
        guard let response = response as? HTTPURLResponse else { throw HostError("transport_unavailable") }
        guard (200...299).contains(response.statusCode) else {
            let retry = response.value(forHTTPHeaderField: "Retry-After").flatMap(Double.init) ?? 60
            throw HTTPFailure(status: response.statusCode, retryAfter: max(0, retry))
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

private struct HTTPFailure: Error { let status: Int; let retryAfter: Double }
private final class RejectRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}

/// Reservations and cooldowns are durable before a paid request leaves the host.
private actor ProviderRateBudget {
    struct Reservation: Codable, Sendable { var id: String; var at: Date; var tokens: Int }
    struct State: Codable { var reservations: [String: [Reservation]] = [:]; var cooldowns: [String: Date] = [:] }
    let url: URL
    var loaded = false
    var state = State()
    init(url: URL) { self.url = url }
    func reserve(provider: ProviderSettings, inputTokens: Int) async throws -> String? {
        let limits = provider.rateLimits ?? ProviderRateLimits()
        try load()
        if let tpm = limits.tokensPerMinute, inputTokens > tpm { throw HostError("rate_limited") }
        while true {
            try Task.checkCancellation()
            let now = Date()
            var calendar = Calendar(identifier: .iso8601)
            calendar.timeZone = TimeZone(secondsFromGMT: 0)!
            let dayStart = calendar.startOfDay(for: now)
            let reservations = (state.reservations[provider.id] ?? []).filter { $0.at >= min(dayStart, now.addingTimeInterval(-60)) }
            state.reservations[provider.id] = reservations
            let recent = reservations.filter { now.timeIntervalSince($0.at) < 60 }
            if let daily = limits.requestsPerDay, reservations.filter({ $0.at >= dayStart }).count >= daily { throw HostError("rate_limited") }
            let minuteFull = limits.requestsPerMinute.map { recent.count >= $0 } ?? false
            let tokensFull = limits.tokensPerMinute.map { recent.reduce(0) { $0 + $1.tokens } + inputTokens > $0 } ?? false
            let cooldown = max(0, state.cooldowns[provider.id]?.timeIntervalSince(now) ?? 0)
            if !minuteFull && !tokensFull && cooldown <= 0 {
                let id = UUID().uuidString
                state.reservations[provider.id, default: []].append(.init(id: id, at: now, tokens: inputTokens))
                try persist(); return id
            }
            let minuteWait = (minuteFull || tokensFull) ? max(0.01, 60 - now.timeIntervalSince(recent.first?.at ?? now)) : 0
            try await Task.sleep(for: .seconds(max(cooldown, minuteWait)))
        }
    }
    func settle(providerID: String, reservation: String?, used: Int?) throws {
        guard let reservation, let used, used >= 0 else { return }
        if let index = state.reservations[providerID]?.firstIndex(where: { $0.id == reservation }) {
            state.reservations[providerID]![index].tokens = used; try persist()
        }
    }
    func coolDown(providerID: String, seconds: Double) throws {
        try load()
        state.cooldowns[providerID] = Date().addingTimeInterval(seconds.isFinite ? min(seconds, 86400) : 60)
        try persist()
    }
    func load() throws {
        guard !loaded else { return }
        if FileManager.default.fileExists(atPath: url.path) { state = try JSONDecoder().decode(State.self, from: Data(contentsOf: url)) }
        loaded = true
    }
    func persist() throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONEncoder().encode(state).write(to: url, options: .atomic)
    }
}
