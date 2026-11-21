import CryptoKit
import Foundation
import Security

public struct ChatGPTAuthorization: Sendable {
    public let id: String
    public let profileID: String
    public let authorizationURL: URL
}

public struct ChatGPTPlanDiagnostic: Sendable, Equatable {
    public let code: String
    public let action: String
    public let requestID: String?
    public let parameter: String?
    public let status: Int?
    public let reportedCode: String?
    public let eventCount: Int?
    public let lastEvent: String?
    public let toolShapes: [ProviderAttemptDiagnostic.ToolShape]?
    public let streamedCalls: Int?
    public let finalizedCalls: Int?
    /// Whether the pipeline may retry (`provider_rejected`, `transport_unavailable`, `transport_timeout`).
    public let pipelineFailure: String
    /// The failure table is the shared core's (`chatgpt_failure`). `temporary` is given only for a failure the
    /// core itself classified; without it only an incomplete response is temporary.
    public init(code: String, status: Int? = nil, requestID: String? = nil, parameter: String? = nil, temporary: Bool? = nil) {
        let classified = ChatGPTWire.classify(code: code, temporary: temporary)
        self.init(code: code, status: status, requestID: requestID, parameter: parameter,
                  failure: classified.failure, action: classified.action)
    }
    init(code: String, status: Int?, requestID: String?, parameter: String?, failure: String, action: String,
         reportedCode: String? = nil, eventCount: Int? = nil, lastEvent: String? = nil,
         toolShapes: [ProviderAttemptDiagnostic.ToolShape]? = nil, streamedCalls: Int? = nil, finalizedCalls: Int? = nil) {
        self.code = code; self.status = status; self.pipelineFailure = failure; self.action = action
        self.requestID = Self.safe(requestID); self.parameter = Self.safe(parameter)
        self.reportedCode = Self.safe(reportedCode); self.eventCount = eventCount; self.lastEvent = Self.safe(lastEvent)
        self.toolShapes = toolShapes?.map {
            .init(type: Self.safe($0.type), name: Self.safe($0.name), namespace: Self.safe($0.namespace))
        }
        self.streamedCalls = streamedCalls; self.finalizedCalls = finalizedCalls
    }
    static func safe(_ value: String?) -> String? {
        guard let value, value.range(of: "^[A-Za-z0-9_.:\\[\\]-]{1,160}$", options: .regularExpression) != nil else { return nil }
        return value
    }
}

struct ChatGPTPlanFailure: Error { let diagnostic: ChatGPTPlanDiagnostic }

/// One native local user owns this vault. Personal profiles never select a different artwork database.
public actor ChatGPTPlanRuntime {
    let store: ChatGPTPlanStore
    let http: any ChatGPTHTTPClient
    private var closed = false
    private var epoch: UInt64 = 0
    private var startingAuthorization = false
    private var attempts: [String: Attempt] = [:]
    /// A sign-in waiting at the core's `open`: its flow answer and what the flow holds (the callback socket).
    private struct Attempt: Sendable {
        let id: String
        let profileID: String
        let epoch: UInt64
        let answer: ExactJSON
        var context: ChatGPTFlowContext
    }
    public init(directory: URL, http: any ChatGPTHTTPClient = ChatGPTURLSessionClient()) {
        store = ChatGPTPlanStore(directory: directory); self.http = http
    }
    init(store: ChatGPTPlanStore, http: any ChatGPTHTTPClient) { self.store = store; self.http = http }

    public func state() throws -> ChatGPTPlanState { try store.load().publicValue }
    public func setEnabled(_ enabled: Bool) async throws {
        try checkOpen()
        if !enabled { epoch &+= 1 }
        try await mutate { $0.enabled = enabled }
        if !enabled {
            let active = Array(attempts.values); attempts.removeAll()
            for attempt in active { await attempt.context.listener?.cancel() }
        }
    }
    public func shutdown() async {
        closed = true; epoch &+= 1
        let active = Array(attempts.values); attempts.removeAll()
        for attempt in active { await attempt.context.listener?.cancel() }
    }
    public func pin() throws -> ChatGPTPlanSession {
        let value = try checkedState()
        guard let id = value.activeProfileID, let profile = value.profiles[id] else { throw HostError("chatgpt_not_connected") }
        let session = ChatGPTPlanSession(profileID: id, generation: profile.generation)
        _ = try checkedProfile(session); return session
    }
    public func validate(_ session: ChatGPTPlanSession) throws { _ = try checkedProfile(session) }
    /// The core saves the resumed registration (step 5, the table's 8).
    public func retryQuota(_ id: String) async throws { _ = try await profileFlow("resume", id) }
    /// One connection per host (the author, 2026-11-14): the core keeps the chosen registration and removes the
    /// others and unfinished ones, writing only when there is something to remove. Run once at start.
    public func tidy() async throws {
        try checkOpen()
        var context = ChatGPTFlowContext(check: { try await self.checkOpen() })
        _ = try await drive(Self.flowStart("tidy", input: [:]), &context)
    }
    /// Resume and sign out: the registration's procedure, answered by the core.
    private func profileFlow(_ flow: String, _ id: String) async throws -> ExactJSON {
        try checkOpen()
        var context = ChatGPTFlowContext(profileID: id, check: { try await self.checkOpen() })
        return try await drive(Self.flowStart(flow, input: ["profile_id": .string(id)]), &context)
    }

    /// The core's login flow runs until it asks to open the sign-in page; that URL is returned, and
    /// `finishAuthorization` goes on from there. The core signs in again with the host's one registration and its
    /// saved client id; `newRegistration` replaces it (another account). `language` is the callback page's.
    public func beginAuthorization(consent: Bool = false, newRegistration: Bool = false, language: String = "en") async throws -> ChatGPTAuthorization {
        _ = try checkedState()
        // The true number of sign-ins in progress (step 5, the table's 2); one local owner holds them all.
        let count = attempts.count + (startingAuthorization ? 1 : 0)
        startingAuthorization = true
        defer { startingAuthorization = false }
        var input: [String: ExactJSON] = ["consent": .bool(consent), "language": .string(language == "ja" ? "ja" : "en"),
                                          "pending_count": .integer(count), "owner_count": .integer(count)]
        if newRegistration { input["new_registration"] = .bool(true) }
        let id = UUID().uuidString, beginEpoch = epoch
        var context = ChatGPTFlowContext(check: { try await self.checkStarting(beginEpoch) })
        do {
            let opened = try await drive(Self.flowStart("login", input: input), &context, stop: "open")
            guard let url = URL(string: opened["todo"]["url"].string ?? ""), let selected = opened["todo"]["profile_id"].string
            else { throw HostError("chatgpt_auth_unavailable") }
            context.profileID = selected
            context.check = { try await self.checkAttempt(id) }
            attempts[id] = Attempt(id: id, profileID: selected, epoch: beginEpoch, answer: opened, context: context)
            return ChatGPTAuthorization(id: id, profileID: selected, authorizationURL: url)
        } catch { await context.listener?.cancel(); throw safeError(error) }
    }
    public func cancelAuthorization(_ id: String) async {
        guard let attempt = attempts.removeValue(forKey: id) else { return }
        await attempt.context.listener?.cancel()
    }
    public func finishAuthorization(_ id: String) async throws -> ChatGPTPlanProfile {
        guard var attempt = attempts[id] else { throw HostError("chatgpt_attempt_not_found") }
        return try await withTaskCancellationHandler {
            do {
                let next = try ChatGPTPolicy.call("sign_in_flow_next", ["state": attempt.answer["state"], "result": .object([:]),
                    "now": ChatGPTPolicy.number(Date().timeIntervalSince1970)])
                let done = try await drive(next, &attempt.context)
                attempts.removeValue(forKey: id); await attempt.context.listener?.cancel()
                guard let profile = try store.load().profiles[done["profile_id"].string ?? ""] else { throw HostError("chatgpt_identity_invalid") }
                return profile.publicValue
            } catch { attempts.removeValue(forKey: id); await attempt.context.listener?.cancel(); throw safeError(error) }
        } onCancel: { Task { await self.cancelAuthorization(id) } }
    }

    /// The core signs out first and then tries the revocation; it answers whether the provider confirmed it.
    public func signOut(_ id: String) async throws -> Bool {
        for attempt in Array(attempts.values) where attempt.profileID == id { await cancelAuthorization(attempt.id) }
        return try await profileFlow("sign_out", id)["revocation_confirmed"].bool == true
    }


    public func models(session: ChatGPTPlanSession? = nil, force: Bool = false) async throws -> [ChatGPTPlanModel] {
        let session = try session ?? pin()
        try validate(session)
        // The catalog flow takes the `wire` lock itself, and its deadline is the core's 15 seconds.
        return try await offeredModels(session: session, force: force, deadline: nil, operationEpoch: epoch)
    }
    /// Server chatgpt_models.saved_publication: opening model settings never starts a catalog or token refresh.
    public func publication() throws -> ChatGPTPlanPublication {
        let session = try pin()
        return try Self.publication(try checkedProfile(session))
    }
    /// Server POST /api/me/chatgpt/models/refresh.
    public func refreshPublication() async throws -> ChatGPTPlanPublication {
        let session = try pin()
        _ = try await models(session: session, force: true)
        let value = try checkedState()
        guard value.activeProfileID == session.profileID else { throw HostError("chatgpt_session_changed") }
        return try Self.publication(try checkedProfile(session, value: value))
    }
    /// Server chatgpt_models.save_publication: only the active profile, only models in its saved catalog. `purposes`
    /// replaces the named models' purposes and keeps the others; a published model needs at least one purpose.
    public func savePublication(profileID: String, generation: Int64, models selected: [String],
                                purposes: [String: [String]] = [:]) async throws -> ChatGPTPlanPublication {
        try checkOpen()
        _ = try ChatGPTPolicy.call("sign_in_auth_publication_input", ["profile_id": .string(profileID),
            "generation": .number(String(generation)), "selected": .array(selected.map(ExactJSON.string)),
            "model_purposes": .object(purposes.mapValues { .array($0.map(ExactJSON.string)) })])
        let session = ChatGPTPlanSession(profileID: profileID, generation: generation)
        return try await mutate { value in
            var profile = try self.checkedProfile(session, value: value)
            _ = try ChatGPTPolicy.call("sign_in_auth_publication_active", ["active": ChatGPTPolicy.string(value.activeProfileID), "profile_id": .string(profileID)])
            let result = try ChatGPTPolicy.call("sign_in_publication_update", ["profile": ChatGPTPolicy.profile(profile),
                "selected": .array(selected.map(ExactJSON.string)),
                "model_purposes": .object(purposes.mapValues { .array($0.map(ExactJSON.string)) }),
                "assessments": try ChatGPTPolicy.assessments()])["profile"]
            profile.publishedModels = result["published_models"].array?.compactMap(\.string)
            profile.modelPurposes = result["model_purposes"].object?.mapValues { $0.array?.compactMap(\.string) ?? [] }
            value.profiles[profileID] = profile
            return try Self.publication(profile)
        }
    }
    private static func publication(_ profile: ChatGPTStoredProfile) throws -> ChatGPTPlanPublication {
        let answer = try ChatGPTPolicy.call("sign_in_publication", ["profile": ChatGPTPolicy.profile(profile),
            "assessments": try ChatGPTPolicy.assessments()])["publication"]
        let rows = answer["models"].array ?? []
        var models: [ChatGPTPlanModel] = [], published = Set<String>(), purposes: [String: [String]] = [:]
        var assessed: [String: ProviderModelSettings] = [:]
        for row in rows {
            let id = try row.requiredString("id"), label = try row.requiredString("label")
            models.append(.init(id: id, label: label))
            if row["enabled"].bool == true { published.insert(id) }
            purposes[id] = row["purposes"].array?.compactMap(\.string) ?? []
            if let object = try JSONSerialization.jsonObject(with: row.data) as? [String: Any] { assessed[id] = try ProviderCoreSettings.model(object) }
        }
        return .init(profileID: profile.id, generation: profile.generation, models: models, published: published,
                     purposes: purposes, assessedModels: assessed, coreAnswer: answer.data)
    }
    /// The caller holds `wire` for the request.
    private func checkOffered(_ model: String, purpose: String, session: ChatGPTPlanSession, deadline: Date, operationEpoch: UInt64) async throws {
        _ = try await offeredModels(session: session, force: false, deadline: deadline, operationEpoch: operationEpoch, holdingWire: true)
        let publication = try Self.publication(try checkedProfile(session))
        try Self.requireOffered(model, purpose: purpose, publication: publication)
    }
    private static func requireOffered(_ model: String, purpose: String, publication: ChatGPTPlanPublication) throws {
        let rows = publication.models.map { ExactJSON.object(["id": .string($0.id), "enabled": .bool(publication.published.contains($0.id)),
            "purposes": .array(publication.purposes(of: $0.id).map(ExactJSON.string))]) }
        let result = try ChatGPTPolicy.call("sign_in_offered", ["models": .array(rows), "model": .string(model), "purpose": .string(purpose)])
        guard result["offered"].bool == true else { throw HostError("chatgpt_model_not_offered") }
    }
    public func checkVisionAccess(session: ChatGPTPlanSession, model: String) throws {
        try Self.requireOffered(model, purpose: "vision", publication: Self.publication(checkedProfile(session)))
    }
    public func perform(action: Data, session: ChatGPTPlanSession, model: String, argumentLimit: Int,
                        onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        try await perform(parsed: ParsedProviderAction(action), session: session, model: model, argumentLimit: argumentLimit, onBytes: onBytes)
    }
    func perform(parsed: ParsedProviderAction, session: ChatGPTPlanSession, model: String, argumentLimit: Int,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        try await performAttempt(parsed: parsed, session: session, model: model, argumentLimit: argumentLimit,
                                 recorder: nil, willSend: { _ in }, onBytes: onBytes)
    }
    func performObserved(parsed: ParsedProviderAction, session: ChatGPTPlanSession, model: String, providerID: String, argumentLimit: Int,
                         recorder: ProviderAttemptRecorder, willSend: @escaping ProviderObservationHandler,
                         onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        try await performAttempt(parsed: parsed, session: session, model: model, providerID: providerID,
                                 argumentLimit: argumentLimit, recorder: recorder, willSend: willSend, onBytes: onBytes)
    }
    private func performAttempt(parsed: ParsedProviderAction, session: ChatGPTPlanSession, model: String, providerID: String = "chatgpt",
                                argumentLimit: Int, recorder: ProviderAttemptRecorder?, willSend: @escaping ProviderObservationHandler,
                                onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        let effect = parsed.effect, tag = try effect.requiredString("tag")
        let imageEffects = try ChatGPTPolicy.call("sign_in_auth_constants")["image_effects"].array?.compactMap(\.string) ?? []
        let purpose = imageEffects.contains(tag) ? "vision" : "llm"
        _ = try ChatGPTPolicy.call("sign_in_auth_operation", ["purpose": .string(purpose), "tag": .string(tag)])
        guard let timeout = Double(try effect.requiredString("timeout_ms")), timeout.isFinite,
              argumentLimit > 0, argumentLimit <= (Int.max - 524_288) / 6 else { throw HostError("pipeline_schema_violation") }
        // Server raises TimeoutError for a non-positive attempt timeout before the ChatGPT request.
        guard timeout > 0 else { throw ChatGPTWire.transport(.timeout) }
        let deadline = Date().addingTimeInterval(timeout / 1000)
        let operationEpoch = epoch
        try validate(session)
        let lease = try await store.lease("wire-" + session.profileID, deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) })
        defer { _ = lease }
        do {
            // The body does not depend on authentication. Durably save it before any
            // model-discovery or token-refresh HTTP, as well as before the paid request.
            let body: ChatGPTWire.Request?
            let imageBody = purpose == "vision" ? try Self.request(parsed: parsed, model: model, argumentLimit: argumentLimit) : nil
            if let recorder {
                let profile = try checkedProfile(session)
                let prepared = try imageBody ?? Self.request(parsed: parsed, model: model, argumentLimit: argumentLimit)
                recorder.prepare(body: prepared.body, providerID: providerID, model: model,
                    secrets: [profile.accessToken, profile.refreshToken, profile.idToken].compactMap { $0 })
                try await recorder.saveRequest(willSend)
                body = prepared
            } else { body = imageBody }
            try await checkOffered(model, purpose: purpose, session: session, deadline: deadline, operationEpoch: operationEpoch)
            let token = try await accessToken(session, deadline: deadline, operationEpoch: operationEpoch)
            if let recorder {
                let profile = try checkedProfile(session)
                recorder.addSecrets([token, profile.refreshToken, profile.idToken].compactMap { $0 })
            }
            let sent = try body ?? Self.request(parsed: parsed, model: model, argumentLimit: argumentLimit)
            // The core answers where it goes, the headers and how the token is sent (step 4).
            let boundedRequest = sent.endpoint.request(token: token, body: sent.body, deadline: deadline)
            let result = try await guarded(deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) }) {
                if let recorder {
                    recorder.receive(ProviderHTTPRead(status: nil, data: nil, sent: true, complete: false, truncated: false))
                    if let observed = self.http as? any ObservedChatGPTHTTPClient {
                        return try await observed.sendObserved(boundedRequest, maximumBytes: sent.wireLimit,
                            errorBytes: sent.endpoint.errorLimit, onBytes: onBytes, onResponse: { recorder.receive($0) })
                    }
                    let response = try await self.http.send(boundedRequest, maximumBytes: sent.wireLimit,
                        errorBytes: sent.endpoint.errorLimit, onBytes: onBytes)
                    recorder.receive(ProviderHTTPRead(status: response.status, data: response.data, sent: true, complete: true, truncated: false))
                    return response
                }
                return try await self.http.send(boundedRequest, maximumBytes: sent.wireLimit, errorBytes: sent.endpoint.errorLimit, onBytes: onBytes)
            }
            if !(200...299).contains(result.status) { throw try ChatGPTWire.httpFailure(result) }
            // The core reads the whole stream: a failure following a completed frame invalidates that frame.
            let stream = try ChatGPTWire.read(text: false, answerLimit: argumentLimit, wire: result.data,
                                              status: result.status, requestID: result.requestID)
            if let terminal = stream.terminal { recorder?.report(terminal) }
            try Task.checkCancellation()
            let answer = try stream.result.get(); try validate(session, operationEpoch: operationEpoch); return answer
        } catch {
            let diagnostic = Self.diagnostic(error)
            if try Self.shouldPause(diagnostic.code) { try await pauseQuota(session, code: diagnostic.code) }
            throw error
        }
    }

    /// Vision advice and colophons on the plan: one text answer about images through the same Responses endpoint,
    /// without tools, temperature or an output limit (the drawing body sends neither). The model must be offered,
    /// published and chosen for Vision; otherwise nothing is sent.
    public func visionText(session: ChatGPTPlanSession, model: String, system: String, message: String, images: [String],
                           timeoutSeconds: Double, onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        _ = try ChatGPTPolicy.call("sign_in_auth_operation", ["purpose": .string("vision"), "tag": .string("vision")])
        guard timeoutSeconds.isFinite, timeoutSeconds > 0 else { throw ChatGPTWire.transport(.timeout) }
        let prepared = try ChatGPTWire.visionRequest(model: model, system: system, text: message, images: images, answerLimit: Self.visionTextLimit)
        let deadline = Date().addingTimeInterval(timeoutSeconds)
        let operationEpoch = epoch
        try validate(session)
        let lease = try await store.lease("wire-" + session.profileID, deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) })
        defer { _ = lease }
        do {
            try await checkOffered(model, purpose: "vision", session: session, deadline: deadline, operationEpoch: operationEpoch)
            let token = try await accessToken(session, deadline: deadline, operationEpoch: operationEpoch)
            let boundedRequest = prepared.endpoint.request(token: token, body: prepared.body, deadline: deadline)
            let result = try await guarded(deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) }) {
                try await self.http.send(boundedRequest, maximumBytes: prepared.wireLimit, errorBytes: prepared.endpoint.errorLimit, onBytes: onBytes)
            }
            if !(200...299).contains(result.status) { throw try ChatGPTWire.httpFailure(result) }
            let stream = try ChatGPTWire.read(text: true, answerLimit: Self.visionTextLimit, wire: result.data,
                                              status: result.status, requestID: result.requestID)
            try Task.checkCancellation()
            let answer = try stream.result.get(); try validate(session, operationEpoch: operationEpoch); return answer
        } catch {
            let code = Self.diagnostic(error).code
            if try Self.shouldPause(code) { try await pauseQuota(session, code: code) }
            throw error
        }
    }
    /// Server request_vision: the answer may be up to 512 KiB of UTF-8.
    static let visionTextLimit = 512 * 1024

    /// The bytes recorded and sent: the effect's prompt as written, so the schema keeps its member order.
    static func request(parsed: ParsedProviderAction, model: String, argumentLimit: Int) throws -> ChatGPTWire.Request {
        let images = parsed.effect["_transient_images"].array?.compactMap(\.string) ?? []
        return try ChatGPTWire.request(model: model, prompt: ExactJSON.rawMemberValidated("prompt", in: ExactJSON.rawMemberValidated("payload", in: parsed.bytes)), answerLimit: argumentLimit, images: images)
    }

    /// The core's catalog flow: the saved list while it is fresh, otherwise a new one fetched and kept under `edit`.
    private func offeredModels(session: ChatGPTPlanSession, force: Bool, deadline: Date?, operationEpoch: UInt64,
                               holdingWire: Bool = false) async throws -> [ChatGPTPlanModel] {
        try validate(session, operationEpoch: operationEpoch)
        var input: [String: ExactJSON] = ["profile_id": .string(session.profileID), "generation": .number(String(session.generation)),
                                          "force": .bool(force)]
        if let deadline { input["deadline"] = ChatGPTPolicy.number(deadline.timeIntervalSince1970) }
        var context = ChatGPTFlowContext(outside: holdingWire ? ["wire"] : [], profileID: session.profileID,
                                         check: { try await self.validate(session, operationEpoch: operationEpoch) })
        let done = try await drive(Self.flowStart("catalog", input: input), &context)
        return try (done["models"].array ?? []).map { ChatGPTPlanModel(id: try $0.requiredString("id"), label: try $0.requiredString("label")) }
    }
    /// The core's access flow: the saved token while it is good, otherwise a refresh saved under `edit`.
    private func accessToken(_ session: ChatGPTPlanSession, deadline: Date, operationEpoch: UInt64) async throws -> String {
        var context = ChatGPTFlowContext(profileID: session.profileID, check: { try await self.validate(session, operationEpoch: operationEpoch) })
        let done = try await drive(Self.flowStart("access", input: ["profile_id": .string(session.profileID),
            "generation": .number(String(session.generation)), "deadline": ChatGPTPolicy.number(deadline.timeIntervalSince1970)]), &context)
        guard let token = done["access_token"].string else { throw HostError("chatgpt_reauthentication_required") }
        return token
    }
    /// The core saves the paused registration (step 5, the table's 8).
    private func pauseQuota(_ session: ChatGPTPlanSession, code: String) async throws {
        var context = ChatGPTFlowContext(profileID: session.profileID, check: { try await self.checkOpen() })
        _ = try await drive(Self.flowStart("pause", input: ["profile_id": .string(session.profileID),
            "generation": .number(String(session.generation)), "code": .string(code)]), &context)
    }
    private func checkedState() throws -> ChatGPTVaultState {
        try checkOpen(); let value = try store.load()
        guard value.enabled else { throw HostError("chatgpt_disabled") }; return value
    }
    private func checkedProfile(_ session: ChatGPTPlanSession, value: ChatGPTVaultState? = nil) throws -> ChatGPTStoredProfile {
        // The core's `sign_in_auth_session` decides whether the session is still this registration's.
        let value = try value ?? checkedState()
        try checkOpen(); guard value.enabled else { throw HostError("chatgpt_disabled") }
        guard let profile = value.profiles[session.profileID] else { throw HostError("chatgpt_not_connected") }
        _ = try ChatGPTPolicy.call("sign_in_auth_session", ["profile": ChatGPTPolicy.profile(profile), "generation": .number(String(session.generation))])
        return profile
    }
    private func checkOpen() throws { try Task.checkCancellation(); guard !closed else { throw HostError("chatgpt_cancelled") } }
    private func validate(_ session: ChatGPTPlanSession, operationEpoch: UInt64) throws {
        guard epoch == operationEpoch else { throw HostError("chatgpt_cancelled") }; try validate(session)
    }
    /// A sign-in goes on while it is the current one; the core keeps its deadline and the registration's generation.
    private func checkAttempt(_ id: String) throws {
        _ = try checkedState()
        guard let attempt = attempts[id], epoch == attempt.epoch else { throw HostError("chatgpt_cancelled") }
    }
    private func checkStarting(_ beginEpoch: UInt64) throws {
        _ = try checkedState()
        guard epoch == beginEpoch else { throw HostError("chatgpt_cancelled") }
    }
    func mutate<T>(_ operation: (inout ChatGPTVaultState) throws -> T) async throws -> T {
        let lease = try await store.lease("edit", deadline: Date().addingTimeInterval(5)); defer { _ = lease }
        try checkOpen(); var value = try store.load(); let result = try operation(&value); try store.write(value); return result
    }
    func guarded<T: Sendable>(deadline: Date, check: @escaping @Sendable () async throws -> Void,
                                      operation: @escaping @Sendable () async throws -> T) async throws -> T {
        try await check()
        return try await withThrowingTaskGroup(of: T.self) { group in
            group.addTask { try await operation() }
            group.addTask {
                while true {
                    try Task.checkCancellation(); try await check()
                    guard Date() < deadline else { throw ChatGPTWire.transport(.timeout) }
                    try await Task.sleep(for: .milliseconds(100))
                }
            }
            defer { group.cancelAll() }
            guard let value = try await group.next() else { throw ChatGPTWire.transport(.unavailable) }
            try await check(); return value
        }
    }
    func random(_ count: Int) throws -> String {
        var bytes = [UInt8](repeating: 0, count: count)
        guard SecRandomCopyBytes(kSecRandomDefault, count, &bytes) == errSecSuccess else { throw HostError("chatgpt_auth_unavailable") }
        return Self.base64URL(Data(bytes))
    }
    private static func base64URL(_ data: Data) -> String { data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
    private static func shouldPause(_ code: String) throws -> Bool {
        try ChatGPTPolicy.call("sign_in_auth_quota_failure", ["code": .string(code)])["pause"].bool == true
    }
    public static func diagnostic(_ error: Error) -> ChatGPTPlanDiagnostic {
        if let failure = error as? ChatGPTPlanFailure { return failure.diagnostic }
        if let error = error as? HostError { return .init(code: error.code) }
        // A transport failure is classified by the core (`chatgpt_transport`, step 4).
        if let error = error as? URLError { return ChatGPTWire.transport(error.code == .timedOut ? .timeout : .unavailable).diagnostic }
        return ChatGPTWire.transport(.unavailable).diagnostic
    }
    private func safeError(_ error: Error) -> Error {
        if error is CancellationError { return CancellationError() }
        if error is ChatGPTPlanFailure { return error }
        return HostError(Self.diagnostic(error).code)
    }
}
