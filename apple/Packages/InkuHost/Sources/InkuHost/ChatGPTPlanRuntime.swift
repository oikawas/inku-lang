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
    /// Whether the pipeline may retry (`provider_rejected`, `transport_unavailable`, `transport_timeout`).
    public let pipelineFailure: String
    /// The failure table is the shared core's (`chatgpt_failure`). `temporary` is given only for a failure the
    /// core itself classified; without it only an incomplete response is temporary.
    public init(code: String, status: Int? = nil, requestID: String? = nil, parameter: String? = nil, temporary: Bool? = nil) {
        let classified = ChatGPTWire.classify(code: code, temporary: temporary)
        self.init(code: code, status: status, requestID: requestID, parameter: parameter,
                  failure: classified.failure, action: classified.action)
    }
    init(code: String, status: Int?, requestID: String?, parameter: String?, failure: String, action: String) {
        self.code = code; self.status = status; self.pipelineFailure = failure; self.action = action
        self.requestID = Self.safe(requestID); self.parameter = Self.safe(parameter)
    }
    private static func safe(_ value: String?) -> String? {
        guard let value, value.range(of: "^[A-Za-z0-9_.:\\[\\]-]{1,160}$", options: .regularExpression) != nil else { return nil }
        return value
    }
}

struct ChatGPTPlanFailure: Error { let diagnostic: ChatGPTPlanDiagnostic }

/// One native local user owns this vault. Personal profiles never select a different artwork database.
public actor ChatGPTPlanRuntime {
    private let store: ChatGPTPlanStore
    private let http: any ChatGPTHTTPClient
    private var closed = false
    private var epoch: UInt64 = 0
    private var startingAuthorization = false
    private var attempts: [String: Attempt] = [:]
    private struct Attempt: Sendable {
        let id: String
        let profileID: String
        let previous: ChatGPTStoredProfile?
        let previousClientID: String?
        let state: String
        let nonce: String
        let verifier: String
        let deadline: Date
        let epoch: UInt64
        let listener: ChatGPTLoopbackListener
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
            for attempt in active { await attempt.listener.cancel() }
        }
    }
    public func shutdown() async {
        closed = true; epoch &+= 1
        let active = Array(attempts.values); attempts.removeAll()
        for attempt in active { await attempt.listener.cancel() }
    }
    public func pin() throws -> ChatGPTPlanSession {
        let value = try checkedState()
        guard let id = value.activeProfileID, let profile = value.profiles[id] else { throw HostError("chatgpt_not_connected") }
        let session = ChatGPTPlanSession(profileID: id, generation: profile.generation)
        _ = try checkedProfile(session); return session
    }
    public func validate(_ session: ChatGPTPlanSession) throws { _ = try checkedProfile(session) }
    public func selectProfile(_ id: String) async throws {
        try checkOpen()
        try await mutate { value in
            guard value.profiles[id] != nil else { throw HostError("chatgpt_not_connected") }
            value.activeProfileID = id
        }
    }
    public func retryQuota(_ id: String) async throws {
        try checkOpen()
        try await mutate { value in
            guard var profile = value.profiles[id], profile.state == "quota",
                  profile.accessToken != nil, profile.refreshToken != nil else { throw HostError("chatgpt_not_connected") }
            profile.state = "connected"; profile.models = nil; profile.modelsExpireAt = nil
            value.profiles[id] = profile
        }
    }

    public func beginAuthorization(profileID: String? = nil, consent: Bool = false) async throws -> ChatGPTAuthorization {
        let saved = try checkedState()
        guard attempts.isEmpty, !startingAuthorization else { throw HostError("chatgpt_attempt_busy") }
        startingAuthorization = true
        defer { startingAuthorization = false }
        let previous = profileID.flatMap { saved.profiles[$0] }
        let previousClientID = previous?.clientID ?? profileID.flatMap { saved.pendingRegistrations[$0] }
        if profileID != nil && previousClientID == nil { throw HostError("chatgpt_not_connected") }
        if previous == nil && saved.profiles.count >= 8 { throw HostError("chatgpt_profile_limit") }
        let id = UUID().uuidString, selectedID = profileID ?? UUID().uuidString
        let state = try random(32), nonce = try random(32), verifier = try random(64)
        let deadline = Date().addingTimeInterval(300), beginEpoch = epoch
        // Reserve before the listener suspends; another authorize action cannot create a second attempt.
        let hostID: String = try await mutate { value in
            if value.hostID == nil { value.hostID = "urn:uuid:" + UUID().uuidString.lowercased() }
            return value.hostID!
        }
        guard epoch == beginEpoch, attempts.isEmpty else { throw HostError("chatgpt_cancelled") }
        let listener = try await ChatGPTLoopbackListener.start(expectedState: state, deadline: deadline)
        do {
            guard epoch == beginEpoch, attempts.isEmpty else { throw HostError("chatgpt_cancelled") }
            _ = try checkedState()
            let attempt = Attempt(id: id, profileID: selectedID, previous: previous, previousClientID: previousClientID,
                state: state, nonce: nonce, verifier: verifier, deadline: deadline, epoch: beginEpoch, listener: listener)
            attempts[id] = attempt
            var parts = URLComponents(url: ChatGPTEndpoints.authorize, resolvingAgainstBaseURL: false)!
            var query = ["client_id": previousClientID ?? "dynamic_agent_client", "ext_agent_host_id": hostID,
                "response_type": "code", "redirect_uri": listener.redirectURI.absoluteString, "scope": ChatGPTEndpoints.scope,
                "resource": ChatGPTEndpoints.resource, "state": state, "nonce": nonce, "code_challenge_method": "S256",
                "code_challenge": Self.base64URL(Data(SHA256.hash(data: Data(verifier.utf8))))]
            if let email = previous?.email, !email.isEmpty { query["login_hint"] = email }
            if previousClientID == nil { query["agent_name_hint"] = "inku" }
            if consent { query["prompt"] = "consent" }
            parts.queryItems = query.sorted { $0.key < $1.key }.map { .init(name: $0.key, value: $0.value) }
            return ChatGPTAuthorization(id: id, profileID: selectedID, authorizationURL: parts.url!)
        } catch { await listener.cancel(); throw error }
    }
    public func cancelAuthorization(_ id: String) async {
        guard let attempt = attempts.removeValue(forKey: id) else { return }
        await attempt.listener.cancel()
    }
    public func finishAuthorization(_ id: String) async throws -> ChatGPTPlanProfile {
        guard let attempt = attempts[id] else { throw HostError("chatgpt_attempt_not_found") }
        return try await withTaskCancellationHandler {
            do {
                let callback = try await guarded(deadline: attempt.deadline, check: { try await self.checkAttempt(id) }) {
                    try await attempt.listener.waitForCallback()
                }
                try checkAttempt(id)
                guard Self.constantTime(callback.state, attempt.state) else { throw HostError("chatgpt_callback_invalid") }
                let issued = callback.clientID ?? attempt.previousClientID ?? ""
                guard !issued.isEmpty, issued != "dynamic_agent_client", issued.utf8.count <= 1024,
                      attempt.previousClientID == nil || attempt.previousClientID == issued else { throw HostError("chatgpt_registration_incomplete") }
                // Keep the issued registration even if exchange or verification fails.
                try await mutate { value in
                    try self.checkAttempt(id)
                    if value.pendingRegistrations[attempt.profileID] == nil && value.pendingRegistrations.count >= 8 { throw HostError("chatgpt_profile_limit") }
                    value.pendingRegistrations[attempt.profileID] = issued
                }
                let check: @Sendable () async throws -> Void = { try await self.checkAttempt(id) }
                let token = try await authJSON(url: ChatGPTEndpoints.token, fields: [
                    "grant_type": "authorization_code", "client_id": issued, "code": callback.code, "code_verifier": attempt.verifier,
                    "redirect_uri": attempt.listener.redirectURI.absoluteString, "resource": ChatGPTEndpoints.resource,
                ], deadline: attempt.deadline, check: check)
                let identity = try await verifyIdentity(token: token.requiredString("id_token"), clientID: issued, nonce: attempt.nonce,
                    expectedSubject: attempt.previous?.subject, deadline: attempt.deadline, check: check)
                let fields = try tokenFields(token, previous: nil)
                try checkAttempt(id)
                let profile = try await mutate { value in
                    try self.checkAttempt(id)
                    let current = value.profiles[attempt.profileID]
                    guard current?.generation == attempt.previous?.generation,
                          current == nil || (current?.issuer == identity.issuer && current?.subject == identity.subject && current?.clientID == issued),
                          current != nil || value.profiles.count < 8 else { throw HostError("chatgpt_identity_mismatch") }
                    let generation = try Self.nextGeneration(current?.generation ?? 0)
                    let profile = ChatGPTStoredProfile(id: attempt.profileID, issuer: identity.issuer, subject: identity.subject,
                        email: identity.email, clientID: issued, label: (identity.email ?? "ChatGPT") + " / " + issued.suffix(8),
                        state: "connected", generation: generation, accessToken: fields.access, refreshToken: fields.refresh,
                        idToken: fields.identity, scopes: fields.scopes, expiresAt: fields.expiry, earliestRefreshAt: fields.earliest,
                        // Server chatgpt_store.save_profile: reauthorization keeps the profile's model choices.
                        publishedModels: current?.publishedModels, modelPurposes: current?.modelPurposes)
                    value.profiles[profile.id] = profile; value.activeProfileID = profile.id
                    value.pendingRegistrations.removeValue(forKey: profile.id)
                    return profile.publicValue
                }
                attempts.removeValue(forKey: id); await attempt.listener.cancel(); return profile
            } catch { attempts.removeValue(forKey: id); await attempt.listener.cancel(); throw safeError(error) }
        } onCancel: { Task { await self.cancelAuthorization(id) } }
    }

    /// Local invalidation commits before a best-effort remote revocation, including during blocked refresh.
    public func signOut(_ id: String) async throws -> Bool {
        try checkOpen()
        let old = try await mutate { value in
            guard var profile = value.profiles[id] else { throw HostError("chatgpt_not_connected") }
            let old = profile
            profile.state = "signed_out"; profile.generation = try Self.nextGeneration(profile.generation); profile.removeTokens()
            value.profiles[id] = profile; return old
        }
        for attempt in Array(attempts.values) where attempt.profileID == id { await cancelAuthorization(attempt.id) }
        guard let refresh = old.refreshToken else { return false }
        do {
            let deadline = Date().addingTimeInterval(10)
            let check: @Sendable () async throws -> Void = { try await self.checkOpen() }
            let discovery = try await authJSON(url: ChatGPTEndpoints.discovery, deadline: deadline, check: check)
            guard let endpoint = URL(string: try discovery.requiredString("revocation_endpoint")) else { return false }
            try ChatGPTEndpoints.validate(endpoint, authenticationOnly: true)
            var request = URLRequest(url: endpoint); request.httpMethod = "POST"; request.timeoutInterval = 10
            request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
            request.httpBody = ChatGPTEndpoints.form(["token": refresh, "token_type_hint": "refresh_token", "client_id": old.clientID])
            let boundedRequest = request
            let result = try await guarded(deadline: deadline, check: check) {
                try await self.http.send(boundedRequest, maximumBytes: 65_536, onBytes: { _ in })
            }
            return result.status == 200
        } catch { return false }
    }

    public func models(session: ChatGPTPlanSession? = nil, force: Bool = false) async throws -> [ChatGPTPlanModel] {
        let session = try session ?? pin(), deadline = Date().addingTimeInterval(15)
        let operationEpoch = epoch
        try validate(session)
        let lease = try await store.lease("wire-" + session.profileID, deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) })
        defer { _ = lease }
        return try await offeredModels(session: session, force: force, deadline: deadline, operationEpoch: operationEpoch)
    }
    /// Server chatgpt_models.saved_publication: opening model settings never starts a catalog or token refresh.
    public func publication() throws -> ChatGPTPlanPublication {
        let session = try pin()
        return Self.publication(try checkedProfile(session))
    }
    /// Server POST /api/me/chatgpt/models/refresh.
    public func refreshPublication() async throws -> ChatGPTPlanPublication {
        let session = try pin()
        _ = try await models(session: session, force: true)
        let value = try checkedState()
        guard value.activeProfileID == session.profileID else { throw HostError("chatgpt_session_changed") }
        return Self.publication(try checkedProfile(session, value: value))
    }
    /// Server chatgpt_models.save_publication: only the active profile, only models in its saved catalog. `purposes`
    /// replaces the named models' purposes and keeps the others; a published model needs at least one purpose.
    public func savePublication(profileID: String, generation: Int64, models selected: [String],
                                purposes: [String: [String]] = [:]) async throws -> ChatGPTPlanPublication {
        try checkOpen()
        guard selected.count <= 1024, selected.allSatisfy({ (1...256).contains($0.count) }) else { throw HostError("chatgpt_model_not_offered") }
        guard purposes.values.allSatisfy({ $0.allSatisfy(["llm", "vision"].contains) }) else { throw HostError("chatgpt_model_not_offered") }
        let session = ChatGPTPlanSession(profileID: profileID, generation: generation)
        return try await mutate { value in
            var profile = try self.checkedProfile(session, value: value)
            guard value.activeProfileID == profileID else { throw HostError("chatgpt_session_changed") }
            let offered = Set((profile.models ?? []).map(\.id))
            guard selected.allSatisfy(offered.contains), purposes.keys.allSatisfy(offered.contains) else { throw HostError("chatgpt_model_not_offered") }
            var chosen = profile.modelPurposes ?? [:]
            for (id, value) in purposes { chosen[id] = ChatGPTPlanPublication.ordered(value) }
            guard selected.allSatisfy({ !(chosen[$0] ?? ChatGPTPlanPublication.defaultPurposes).isEmpty }) else {
                throw HostError("chatgpt_model_not_offered")
            }
            var seen = Set<String>()
            profile.publishedModels = selected.filter { seen.insert($0).inserted }
            profile.modelPurposes = chosen.isEmpty ? nil : chosen
            value.profiles[profileID] = profile
            return Self.publication(profile)
        }
    }
    private static func publication(_ profile: ChatGPTStoredProfile) -> ChatGPTPlanPublication {
        let models = profile.models ?? []
        let published = Set(profile.publishedModels ?? []).intersection(models.map(\.id))
        return ChatGPTPlanPublication(profileID: profile.id, generation: profile.generation, models: models, published: published,
                                      purposes: profile.modelPurposes ?? [:])
    }
    /// Server chatgpt_provider.request: offered, published by this profile, and chosen for this purpose.
    private func checkOffered(_ model: String, purpose: String, session: ChatGPTPlanSession, deadline: Date, operationEpoch: UInt64) async throws {
        let offered = try await offeredModels(session: session, force: false, deadline: deadline, operationEpoch: operationEpoch)
        let profile = try checkedProfile(session)
        guard offered.contains(where: { $0.id == model }), profile.publishedModels?.contains(model) == true,
              (profile.modelPurposes?[model] ?? ChatGPTPlanPublication.defaultPurposes).contains(purpose) else {
            throw HostError("chatgpt_model_not_offered")
        }
    }
    /// Server vision_client.check_vision_access: the pinned profile still publishes the model for Vision. It reads the
    /// saved profile only, so a cached colophon reading is checked without a request.
    public func checkVisionAccess(session: ChatGPTPlanSession, model: String) throws {
        let profile = try checkedProfile(session)
        guard (profile.models ?? []).contains(where: { $0.id == model }), profile.publishedModels?.contains(model) == true,
              (profile.modelPurposes?[model] ?? ChatGPTPlanPublication.defaultPurposes).contains("vision") else {
            throw HostError("chatgpt_model_not_offered")
        }
    }
    public func perform(action: Data, session: ChatGPTPlanSession, model: String, argumentLimit: Int,
                        onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        try await performAttempt(action: action, session: session, model: model, argumentLimit: argumentLimit,
                                 recorder: nil, willSend: { _ in }, onBytes: onBytes)
    }
    func performObserved(action: Data, session: ChatGPTPlanSession, model: String, providerID: String, argumentLimit: Int,
                         recorder: ProviderAttemptRecorder, willSend: @escaping ProviderObservationHandler,
                         onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        try await performAttempt(action: action, session: session, model: model, providerID: providerID,
                                 argumentLimit: argumentLimit, recorder: recorder, willSend: willSend, onBytes: onBytes)
    }
    private func performAttempt(action: Data, session: ChatGPTPlanSession, model: String, providerID: String = "chatgpt",
                                argumentLimit: Int, recorder: ProviderAttemptRecorder?, willSend: @escaping ProviderObservationHandler,
                                onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        let effect = try ExactJSON(data: action), tag = try effect.requiredString("tag")
        guard ["generate_sketch", "select_description_catalog", "generate_normalized_ddl", "read_composition",
               "choose_laws", "choose_colors", "complete_visible_ddl_holes"].contains(tag) else {
            throw HostError("chatgpt_operation_not_supported")
        }
        guard let timeout = Double(try effect.requiredString("timeout_ms")), timeout.isFinite,
              argumentLimit > 0, argumentLimit <= (Int.max - 524_288) / 6 else { throw HostError("pipeline_schema_violation") }
        // Server raises TimeoutError for a non-positive attempt timeout before the ChatGPT request.
        guard timeout > 0 else { throw HostError("chatgpt_transport_timeout") }
        let deadline = Date().addingTimeInterval(timeout / 1000)
        let operationEpoch = epoch
        try validate(session)
        let lease = try await store.lease("wire-" + session.profileID, deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) })
        defer { _ = lease }
        do {
            // The body does not depend on authentication. Durably save it before any
            // model-discovery or token-refresh HTTP, as well as before the paid request.
            let body: ChatGPTWire.Request?
            if let recorder {
                let profile = try checkedProfile(session)
                let prepared = try Self.request(action: action, model: model, argumentLimit: argumentLimit)
                recorder.prepare(body: prepared.body, providerID: providerID, model: model,
                    secrets: [profile.accessToken, profile.refreshToken, profile.idToken].compactMap { $0 })
                try await recorder.saveRequest(willSend)
                body = prepared
            } else { body = nil }
            try await checkOffered(model, purpose: "llm", session: session, deadline: deadline, operationEpoch: operationEpoch)
            let token = try await accessToken(session, deadline: deadline, operationEpoch: operationEpoch)
            if let recorder {
                let profile = try checkedProfile(session)
                recorder.addSecrets([token, profile.refreshToken, profile.idToken].compactMap { $0 })
            }
            let sent = try body ?? Self.request(action: action, model: model, argumentLimit: argumentLimit)
            var request = URLRequest(url: ChatGPTEndpoints.responses); request.httpMethod = "POST"; request.httpBody = sent.body
            request.timeoutInterval = max(0.001, deadline.timeIntervalSinceNow)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
            let boundedRequest = request
            let result = try await guarded(deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) }) {
                if let recorder {
                    recorder.receive(ProviderHTTPRead(status: nil, data: nil, sent: true, complete: false, truncated: false))
                    if let observed = self.http as? any ObservedChatGPTHTTPClient {
                        return try await observed.sendObserved(boundedRequest, maximumBytes: sent.wireLimit,
                            onBytes: onBytes, onResponse: { recorder.receive($0) })
                    }
                    let response = try await self.http.send(boundedRequest, maximumBytes: sent.wireLimit, onBytes: onBytes)
                    recorder.receive(ProviderHTTPRead(status: response.status, data: response.data, sent: true, complete: true, truncated: false))
                    return response
                }
                return try await self.http.send(boundedRequest, maximumBytes: sent.wireLimit, onBytes: onBytes)
            }
            if !(200...299).contains(result.status) { throw try ChatGPTWire.httpFailure(result) }
            // The core reads the whole stream: a failure following a completed frame invalidates that frame.
            let stream = try ChatGPTWire.read(text: false, answerLimit: argumentLimit, wire: result.data)
            if let terminal = stream.terminal { recorder?.report(terminal) }
            try Task.checkCancellation()
            let answer = try stream.result.get(); try validate(session, operationEpoch: operationEpoch); return answer
        } catch {
            let diagnostic = Self.diagnostic(error)
            if diagnostic.code == "subscription_sharing_usage_limit_exceeded" { try await pauseQuota(session) }
            throw error
        }
    }

    /// Vision advice and colophons on the plan: one text answer about images through the same Responses endpoint,
    /// without tools, temperature or an output limit (the drawing body sends neither). The model must be offered,
    /// published and chosen for Vision; otherwise nothing is sent.
    public func visionText(session: ChatGPTPlanSession, model: String, system: String, message: String, images: [String],
                           timeoutSeconds: Double, onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        guard timeoutSeconds.isFinite, timeoutSeconds > 0 else { throw HostError("chatgpt_transport_timeout") }
        let prepared = try ChatGPTWire.visionRequest(model: model, system: system, text: message, images: images, answerLimit: Self.visionTextLimit)
        let deadline = Date().addingTimeInterval(timeoutSeconds)
        let operationEpoch = epoch
        try validate(session)
        let lease = try await store.lease("wire-" + session.profileID, deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) })
        defer { _ = lease }
        do {
            try await checkOffered(model, purpose: "vision", session: session, deadline: deadline, operationEpoch: operationEpoch)
            let token = try await accessToken(session, deadline: deadline, operationEpoch: operationEpoch)
            var request = URLRequest(url: ChatGPTEndpoints.responses); request.httpMethod = "POST"; request.httpBody = prepared.body
            request.timeoutInterval = max(0.001, deadline.timeIntervalSinceNow)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
            let boundedRequest = request
            let result = try await guarded(deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) }) {
                try await self.http.send(boundedRequest, maximumBytes: prepared.wireLimit, onBytes: onBytes)
            }
            if !(200...299).contains(result.status) { throw try ChatGPTWire.httpFailure(result) }
            let stream = try ChatGPTWire.read(text: true, answerLimit: Self.visionTextLimit, wire: result.data)
            try Task.checkCancellation()
            let answer = try stream.result.get(); try validate(session, operationEpoch: operationEpoch); return answer
        } catch {
            if Self.diagnostic(error).code == "subscription_sharing_usage_limit_exceeded" { try await pauseQuota(session) }
            throw error
        }
    }
    /// Server request_vision: the answer may be up to 512 KiB of UTF-8.
    static let visionTextLimit = 512 * 1024

    /// The bytes recorded and sent: the effect's prompt as written, so the schema keeps its member order.
    static func request(action: Data, model: String, argumentLimit: Int) throws -> ChatGPTWire.Request {
        try ChatGPTWire.request(model: model, prompt: ExactJSON.rawMember("prompt", in: ExactJSON.rawMember("payload", in: action)), answerLimit: argumentLimit)
    }

    private func offeredModels(session: ChatGPTPlanSession, force: Bool, deadline: Date, operationEpoch: UInt64) async throws -> [ChatGPTPlanModel] {
        try validate(session, operationEpoch: operationEpoch)
        let profile = try checkedProfile(session)
        if !force, let models = profile.models, let expiry = profile.modelsExpireAt, expiry > Date() { return models }
        let token = try await accessToken(session, deadline: deadline, operationEpoch: operationEpoch)
        var request = URLRequest(url: ChatGPTEndpoints.models); request.timeoutInterval = max(0.001, deadline.timeIntervalSinceNow)
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        let boundedRequest = request
        let result = try await guarded(deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) }) {
            try await self.http.send(boundedRequest, maximumBytes: 1_048_576, onBytes: { _ in })
        }
        if !(200...299).contains(result.status) {
            let error = try ChatGPTWire.httpFailure(result)
            if error.diagnostic.code == "subscription_sharing_usage_limit_exceeded" { try await pauseQuota(session) }
            throw error
        }
        guard let value = try? ExactJSON(data: result.data) else { throw HostError("chatgpt_response_invalid") }
        let models = try ChatGPTWire.catalog(value)
        try await mutate { value in
            try self.validate(session, operationEpoch: operationEpoch)
            _ = try self.checkedProfile(session, value: value)
            value.profiles[session.profileID]?.models = models
            value.profiles[session.profileID]?.modelsExpireAt = Date().addingTimeInterval(300)
        }
        return models
    }
    private func accessToken(_ session: ChatGPTPlanSession, deadline: Date, operationEpoch: UInt64) async throws -> String {
        let lease = try await store.lease("refresh", deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) })
        defer { _ = lease }
        let profile = try checkedProfile(session)
        if profile.expiresAt > Date().addingTimeInterval(60), let token = profile.accessToken { return token }
        if profile.earliestRefreshAt > Date() {
            if profile.expiresAt > Date(), let token = profile.accessToken { return token }
            throw HostError("chatgpt_refresh_not_ready")
        }
        guard let refresh = profile.refreshToken else { throw HostError("chatgpt_reauthentication_required") }
        let check: @Sendable () async throws -> Void = { try await self.validate(session, operationEpoch: operationEpoch) }
        do {
            let value = try await authJSON(url: ChatGPTEndpoints.token, fields: ["grant_type": "refresh_token", "client_id": profile.clientID,
                "refresh_token": refresh, "resource": ChatGPTEndpoints.resource], deadline: deadline, check: check)
            if let token = value["id_token"].string, !token.isEmpty {
                _ = try await verifyIdentity(token: token, clientID: profile.clientID, nonce: nil,
                    expectedSubject: profile.subject, deadline: deadline, check: check)
            }
            let fields = try tokenFields(value, previous: profile)
            try validate(session, operationEpoch: operationEpoch)
            try await mutate { saved in
                try self.validate(session, operationEpoch: operationEpoch)
                var current = try self.checkedProfile(session, value: saved)
                guard current.refreshToken == refresh else { throw HostError("chatgpt_session_changed") }
                current.accessToken = fields.access; current.refreshToken = fields.refresh; current.idToken = fields.identity
                current.scopes = fields.scopes; current.expiresAt = fields.expiry; current.earliestRefreshAt = fields.earliest
                current.models = nil; current.modelsExpireAt = nil; saved.profiles[current.id] = current
            }
            return fields.access
        } catch let error as HostError where error.code == "chatgpt_reauthentication_required" {
            try await mutate { saved in
                var current = try self.checkedProfile(session, value: saved)
                current.state = "reauthentication_required"; current.generation = try Self.nextGeneration(current.generation); current.removeTokens()
                saved.profiles[current.id] = current
            }
            throw error
        }
    }
    private struct TokenFields { let access: String; let refresh: String; let identity: String?; let scopes: [String]; let expiry: Date; let earliest: Date }
    private func tokenFields(_ value: ExactJSON, previous: ChatGPTStoredProfile?) throws -> TokenFields {
        let access = try value.requiredString("access_token"), refresh = try value.requiredString("refresh_token")
        guard value["token_type"].string?.lowercased() == "bearer", !access.isEmpty, !refresh.isEmpty,
              access.utf8.count <= 65_536, refresh.utf8.count <= 65_536,
              let expires = (value["expires_in"].number ?? value["expires_in"].string).flatMap(Double.init), expires.isFinite, expires > 0, expires <= 86400,
              value["scope"] == .null || value["scope"].string != nil,
              value["id_token"] == .null || (value["id_token"].string?.utf8.count ?? Int.max) <= 65_536 else { throw HostError("chatgpt_identity_invalid") }
        let earliest: Date
        if value["earliest_refresh_at"] == .null { earliest = Date(timeIntervalSince1970: 0) }
        else if let timestamp = value["earliest_refresh_at"].number.flatMap(Double.init), timestamp.isFinite { earliest = Date(timeIntervalSince1970: timestamp) }
        else if let text = value["earliest_refresh_at"].string,
                let date = ISO8601DateFormatter().date(from: text) ?? Self.fractionalISODate(text) { earliest = date }
        else { throw HostError("chatgpt_identity_invalid") }
        return TokenFields(access: access, refresh: refresh, identity: value["id_token"].string ?? previous?.idToken,
            scopes: value["scope"].string.map { $0.split(whereSeparator: \.isWhitespace).map(String.init) } ?? previous?.scopes ?? [],
            expiry: Date().addingTimeInterval(expires), earliest: earliest)
    }
    private static func fractionalISODate(_ text: String) -> Date? {
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: text)
    }
    private func verifyIdentity(token: String, clientID: String, nonce: String?, expectedSubject: String?, deadline: Date,
                                check: @escaping @Sendable () async throws -> Void) async throws -> ChatGPTVerifiedIdentity {
        let metadata = try await authJSON(url: ChatGPTEndpoints.discovery, deadline: deadline, check: check)
        guard metadata["issuer"].string == ChatGPTEndpoints.issuer, let url = URL(string: try metadata.requiredString("jwks_uri")) else { throw HostError("chatgpt_identity_invalid") }
        try ChatGPTEndpoints.validate(url, authenticationOnly: true)
        let keys = try await authJSON(url: url, deadline: deadline, check: check)
        try await check()
        return try ChatGPTIdentityVerifier.verify(idToken: token, clientID: clientID, nonce: nonce, expectedSubject: expectedSubject, discovery: metadata, jwks: keys)
    }
    private func authJSON(url: URL, fields: [String: String]? = nil, deadline: Date,
                          check: @escaping @Sendable () async throws -> Void) async throws -> ExactJSON {
        try ChatGPTEndpoints.validate(url, authenticationOnly: true)
        var request = URLRequest(url: url); request.timeoutInterval = max(0.001, deadline.timeIntervalSinceNow)
        if let fields { request.httpMethod = "POST"; request.httpBody = ChatGPTEndpoints.form(fields); request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type") }
        let boundedRequest = request
        let result = try await guarded(deadline: deadline, check: check) { try await self.http.send(boundedRequest, maximumBytes: 1_048_576, onBytes: { _ in }) }
        let value: ExactJSON
        do { value = try ExactJSON(data: result.data) }
        catch { throw HostError("chatgpt_auth_unavailable") }
        if !(200...299).contains(result.status) {
            let code = value["error"].string ?? value["error"]["code"].string
            if ["invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused"].contains(code ?? "") { throw HostError("chatgpt_reauthentication_required") }
            throw HostError(result.status >= 500 ? "chatgpt_auth_unavailable" : "chatgpt_auth_rejected")
        }
        guard value.object != nil else { throw HostError("chatgpt_identity_invalid") }; try await check(); return value
    }
    private func pauseQuota(_ session: ChatGPTPlanSession) async throws {
        try await mutate { value in
            guard var profile = value.profiles[session.profileID], profile.generation == session.generation else { throw HostError("chatgpt_session_changed") }
            profile.state = "quota"; profile.models = nil; profile.modelsExpireAt = nil; value.profiles[profile.id] = profile
        }
    }
    private func checkedState() throws -> ChatGPTVaultState {
        try checkOpen(); let value = try store.load()
        guard value.enabled else { throw HostError("chatgpt_disabled") }; return value
    }
    private func checkedProfile(_ session: ChatGPTPlanSession, value: ChatGPTVaultState? = nil) throws -> ChatGPTStoredProfile {
        guard UUID(uuidString: session.profileID) != nil, session.generation > 0 else { throw HostError("chatgpt_session_changed") }
        let value = try value ?? checkedState()
        try checkOpen(); guard value.enabled else { throw HostError("chatgpt_disabled") }
        guard let profile = value.profiles[session.profileID] else { throw HostError("chatgpt_not_connected") }
        guard profile.generation == session.generation else { throw HostError("chatgpt_session_changed") }
        guard profile.state == "connected" else { throw HostError("chatgpt_" + profile.state) }
        guard profile.accessToken != nil, profile.refreshToken != nil else { throw HostError("chatgpt_not_connected") }
        guard profile.scopes.contains("chatgpt.tokens.use.direct") else { throw HostError("chatgpt_scope_required") }
        return profile
    }
    private func checkOpen() throws { try Task.checkCancellation(); guard !closed else { throw HostError("chatgpt_cancelled") } }
    private func validate(_ session: ChatGPTPlanSession, operationEpoch: UInt64) throws {
        guard epoch == operationEpoch else { throw HostError("chatgpt_cancelled") }; try validate(session)
    }
    private func checkAttempt(_ id: String) throws {
        _ = try checkedState()
        guard let attempt = attempts[id], epoch == attempt.epoch, Date() < attempt.deadline else { throw HostError("chatgpt_cancelled") }
        let current = try store.load().profiles[attempt.profileID]
        guard current?.generation == attempt.previous?.generation else { throw HostError("chatgpt_session_changed") }
    }
    private func mutate<T>(_ operation: (inout ChatGPTVaultState) throws -> T) async throws -> T {
        let lease = try await store.lease("edit", deadline: Date().addingTimeInterval(5)); defer { _ = lease }
        try checkOpen(); var value = try store.load(); let result = try operation(&value); try store.write(value); return result
    }
    private func guarded<T: Sendable>(deadline: Date, check: @escaping @Sendable () async throws -> Void,
                                      operation: @escaping @Sendable () async throws -> T) async throws -> T {
        try await check()
        return try await withThrowingTaskGroup(of: T.self) { group in
            group.addTask { try await operation() }
            group.addTask {
                while true {
                    try Task.checkCancellation(); try await check()
                    guard Date() < deadline else { throw HostError("chatgpt_transport_timeout") }
                    try await Task.sleep(for: .milliseconds(100))
                }
            }
            defer { group.cancelAll() }
            guard let value = try await group.next() else { throw HostError("chatgpt_transport_unavailable") }
            try await check(); return value
        }
    }
    private func random(_ count: Int) throws -> String {
        var bytes = [UInt8](repeating: 0, count: count)
        guard SecRandomCopyBytes(kSecRandomDefault, count, &bytes) == errSecSuccess else { throw HostError("chatgpt_auth_unavailable") }
        return Self.base64URL(Data(bytes))
    }
    private static func base64URL(_ data: Data) -> String { data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
    private static func constantTime(_ first: String, _ second: String) -> Bool {
        let a = Array(first.utf8), b = Array(second.utf8)
        guard a.count == b.count else { return false }; return zip(a, b).reduce(UInt8(0)) { $0 | ($1.0 ^ $1.1) } == 0
    }
    private static func nextGeneration(_ generation: Int64) throws -> Int64 {
        guard generation >= 0, generation < Int64.max else { throw HostError("chatgpt_session_changed") }; return generation + 1
    }
    public static func diagnostic(_ error: Error) -> ChatGPTPlanDiagnostic {
        if let failure = error as? ChatGPTPlanFailure { return failure.diagnostic }
        if let error = error as? HostError { return .init(code: error.code) }
        if let error = error as? URLError { return .init(code: error.code == .timedOut ? "chatgpt_transport_timeout" : "chatgpt_transport_unavailable") }
        return .init(code: "chatgpt_transport_unavailable")
    }
    private func safeError(_ error: Error) -> Error {
        if error is CancellationError { return CancellationError() }; return HostError(Self.diagnostic(error).code)
    }
}
