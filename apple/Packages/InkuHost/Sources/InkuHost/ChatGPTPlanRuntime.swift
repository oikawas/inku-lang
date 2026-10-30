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
            _ = try ChatGPTPolicy.call("chatgpt_auth_select", ["profile_ids": .array(value.profiles.keys.map(ExactJSON.string)), "profile_id": .string(id)])
            value.activeProfileID = id
        }
    }
    public func retryQuota(_ id: String) async throws {
        try checkOpen()
        try await mutate { value in
            guard var profile = value.profiles[id] else { throw HostError("chatgpt_not_connected") }
            _ = try ChatGPTPolicy.call("chatgpt_auth_resume_quota", ["profile": ChatGPTPolicy.profile(profile)])
            profile.state = "connected"
            value.profiles[id] = profile
        }
    }

    public func beginAuthorization(profileID: String? = nil, consent: Bool = false) async throws -> ChatGPTAuthorization {
        let saved = try checkedState()
        let pendingCount = attempts.count + (startingAuthorization ? 1 : 0)
        let limits = try ChatGPTPolicy.call("chatgpt_auth_attempt", ["pending_count": .integer(pendingCount),
            "owner_count": .integer(pendingCount)])
        startingAuthorization = true
        defer { startingAuthorization = false }
        let previous = profileID.flatMap { saved.profiles[$0] }
        let pending = profileID.flatMap { saved.pendingRegistrations[$0] }
        let prior = try ChatGPTPolicy.call("chatgpt_auth_previous", ["profile_id": ChatGPTPolicy.string(profileID),
            "profile": previous.map { .object(["client_id": .string($0.clientID)]) } ?? .null,
            "pending": pending.map { .object(["client_id": .string($0)]) } ?? .null])["previous"]
        let previousClientID = prior["client_id"].string
        if previous == nil && saved.profiles.count >= 8 { throw HostError("chatgpt_profile_limit") }
        let id = UUID().uuidString, selectedID = profileID ?? UUID().uuidString
        let state = try random(32), nonce = try random(32), verifier = try random(64)
        let deadline = Date().addingTimeInterval(TimeInterval(limits["deadline_seconds"].number.flatMap(Double.init) ?? 300)), beginEpoch = epoch
        // Reserve before the listener suspends; another authorize action cannot create a second attempt.
        let hostID: String = try await mutate { value in
            if value.hostID == nil { value.hostID = "urn:uuid:" + UUID().uuidString.lowercased() }
            return value.hostID!
        }
        guard epoch == beginEpoch, attempts.isEmpty else { throw HostError("chatgpt_cancelled") }
        let listener = try await ChatGPTLoopbackListener.start(expectedState: state, deadline: deadline,
                                                               previousClientID: previousClientID)
        do {
            guard epoch == beginEpoch, attempts.isEmpty else { throw HostError("chatgpt_cancelled") }
            _ = try checkedState()
            let attempt = Attempt(id: id, profileID: selectedID, previous: previous, previousClientID: previousClientID,
                state: state, nonce: nonce, verifier: verifier, deadline: deadline, epoch: beginEpoch, listener: listener)
            attempts[id] = attempt
            var previous: [String: ExactJSON] = [:]
            if let previousClientID { previous["client_id"] = .string(previousClientID) }
            if let email = attempt.previous?.email { previous["email"] = .string(email) }
            let result = try ChatGPTPolicy.call("chatgpt_auth_url", ["previous": .object(previous), "host_id": .string(hostID),
                "redirect_uri": .string(listener.redirectURI.absoluteString), "state": .string(state), "nonce": .string(nonce),
                "verifier": .string(verifier), "consent": .bool(consent)])
            guard let url = URL(string: try result.requiredString("url")) else { throw HostError("chatgpt_auth_unavailable") }
            return ChatGPTAuthorization(id: id, profileID: selectedID, authorizationURL: url)
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
                _ = try ChatGPTPolicy.call("chatgpt_auth_callback", ["state": .string(callback.state), "expected_state": .string(attempt.state), "code": .string(callback.code)])
                let issued = callback.clientID ?? attempt.previousClientID ?? ""
                _ = try ChatGPTPolicy.call("chatgpt_auth_callback_client", ["issued": .string(issued), "previous": attempt.previousClientID.map { .object(["client_id": .string($0)]) } ?? .null])
                guard issued.utf8.count <= 1024 else { throw HostError("chatgpt_registration_incomplete") }
                // Keep the issued registration even if exchange or verification fails.
                try await mutate { value in
                    try self.checkAttempt(id)
                    _ = try ChatGPTPolicy.call("chatgpt_auth_pending_check", ["exists": .bool(value.pendingRegistrations[attempt.profileID] != nil), "count": .integer(value.pendingRegistrations.count)])
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
                    _ = try ChatGPTPolicy.call("chatgpt_auth_save_check", ["previous": current.map(ChatGPTPolicy.profile) ?? .null,
                        "expected_generation": attempt.previous.map { .number(String($0.generation)) } ?? .null, "count": .integer(value.profiles.count)])
                    let proposed: ExactJSON = .object(["issuer": .string(identity.issuer), "sub": .string(identity.subject), "client_id": .string(issued)])
                    _ = try ChatGPTPolicy.call("chatgpt_auth_preserve", ["previous": current.map(ChatGPTPolicy.profile) ?? .null, "profile": proposed])
                    let generation = try Self.nextGeneration(current?.generation ?? 0)
                    let profile = ChatGPTStoredProfile(id: attempt.profileID, issuer: identity.issuer, subject: identity.subject,
                        email: identity.email, clientID: issued, label: identity.label,
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
        try await signOutProfile(id).confirmed
    }

    /// Delete only a registration that is still signed out. The shared core decides the state transition.
    public func deleteProfile(_ id: String) async throws -> Bool {
        let result = try await signOutProfile(id)
        try await mutate { value in
            let states = ExactJSON.object(value.profiles.mapValues { .object(["state": .string($0.state)]) })
            let pending = ExactJSON.object(value.pendingRegistrations.mapValues { .object(["client_id": .string($0)]) })
            let answer = try ChatGPTPolicy.call("chatgpt_auth_delete", ["profile_id": .string(id), "value": .object([
                "profiles": states, "registrations_pending": pending, "active": ChatGPTPolicy.string(value.activeProfileID)])])["value"]
            let remaining = Set(answer["profiles"].object?.keys ?? Dictionary<String, ExactJSON>().keys)
            let remainingPending = Set(answer["registrations_pending"].object?.keys ?? Dictionary<String, ExactJSON>().keys)
            value.profiles = value.profiles.filter { remaining.contains($0.key) }
            value.pendingRegistrations = value.pendingRegistrations.filter { remainingPending.contains($0.key) }
            value.activeProfileID = answer["active"].string
        }
        return result.confirmed
    }

    private func signOutProfile(_ id: String) async throws -> (confirmed: Bool, generation: Int64) {
        try checkOpen()
        let (old, generation) = try await mutate { value in
            guard var profile = value.profiles[id] else { throw HostError("chatgpt_not_connected") }
            let old = profile
            try Self.transition(&profile, to: "signed_out")
            value.profiles[id] = profile; return (old, profile.generation)
        }
        for attempt in Array(attempts.values) where attempt.profileID == id { await cancelAuthorization(attempt.id) }
        let revocation = try ChatGPTPolicy.call("chatgpt_auth_revocation", ["profile": ChatGPTPolicy.profile(old)])
        guard revocation["send"].bool == true, let refresh = old.refreshToken else { return (false, generation) }
        do {
            let deadline = Date().addingTimeInterval(10)
            let check: @Sendable () async throws -> Void = { try await self.checkOpen() }
            let discovery = try await authJSON(url: ChatGPTEndpoints.discovery, deadline: deadline, check: check)
            guard let endpoint = URL(string: try discovery.requiredString("revocation_endpoint")) else { return (false, generation) }
            try ChatGPTEndpoints.validate(endpoint, authenticationOnly: true)
            var request = URLRequest(url: endpoint); request.httpMethod = "POST"; request.timeoutInterval = 10
            request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
            request.httpBody = ChatGPTEndpoints.form(["token": refresh, "token_type_hint": "refresh_token", "client_id": old.clientID])
            let boundedRequest = request
            let result = try await guarded(deadline: deadline, check: check) {
                try await self.http.send(boundedRequest, maximumBytes: 65_536, onBytes: { _ in })
            }
            let decision = try ChatGPTPolicy.call("chatgpt_auth_revocation", ["profile": ChatGPTPolicy.profile(old), "status": .integer(result.status)])
            return (decision["confirmed"].bool == true, generation)
        } catch { return (false, generation) }
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
        _ = try ChatGPTPolicy.call("chatgpt_auth_publication_input", ["profile_id": .string(profileID),
            "generation": .number(String(generation)), "selected": .array(selected.map(ExactJSON.string)),
            "model_purposes": .object(purposes.mapValues { .array($0.map(ExactJSON.string)) })])
        let session = ChatGPTPlanSession(profileID: profileID, generation: generation)
        return try await mutate { value in
            var profile = try self.checkedProfile(session, value: value)
            _ = try ChatGPTPolicy.call("chatgpt_auth_publication_active", ["active": ChatGPTPolicy.string(value.activeProfileID), "profile_id": .string(profileID)])
            let result = try ChatGPTPolicy.call("chatgpt_publication_update", ["profile": ChatGPTPolicy.profile(profile),
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
        let answer = try ChatGPTPolicy.call("chatgpt_publication", ["profile": ChatGPTPolicy.profile(profile),
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
                     purposes: purposes, assessedModels: assessed)
    }
    private func checkOffered(_ model: String, purpose: String, session: ChatGPTPlanSession, deadline: Date, operationEpoch: UInt64) async throws {
        _ = try await offeredModels(session: session, force: false, deadline: deadline, operationEpoch: operationEpoch)
        let publication = try Self.publication(try checkedProfile(session))
        try Self.requireOffered(model, purpose: purpose, publication: publication)
    }
    private static func requireOffered(_ model: String, purpose: String, publication: ChatGPTPlanPublication) throws {
        let rows = publication.models.map { ExactJSON.object(["id": .string($0.id), "enabled": .bool(publication.published.contains($0.id)),
            "purposes": .array(publication.purposes(of: $0.id).map(ExactJSON.string))]) }
        let result = try ChatGPTPolicy.call("chatgpt_offered", ["models": .array(rows), "model": .string(model), "purpose": .string(purpose)])
        guard result["offered"].bool == true else { throw HostError("chatgpt_model_not_offered") }
    }
    public func checkVisionAccess(session: ChatGPTPlanSession, model: String) throws {
        try Self.requireOffered(model, purpose: "vision", publication: Self.publication(checkedProfile(session)))
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
        let imageEffects = try ChatGPTPolicy.call("chatgpt_auth_constants")["image_effects"].array?.compactMap(\.string) ?? []
        let purpose = imageEffects.contains(tag) ? "vision" : "llm"
        _ = try ChatGPTPolicy.call("chatgpt_auth_operation", ["purpose": .string(purpose), "tag": .string(tag)])
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
            let imageBody = purpose == "vision" ? try Self.request(action: action, model: model, argumentLimit: argumentLimit) : nil
            if let recorder {
                let profile = try checkedProfile(session)
                let prepared = try imageBody ?? Self.request(action: action, model: model, argumentLimit: argumentLimit)
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
            if try Self.shouldPause(diagnostic.code) { try await pauseQuota(session) }
            throw error
        }
    }

    /// Vision advice and colophons on the plan: one text answer about images through the same Responses endpoint,
    /// without tools, temperature or an output limit (the drawing body sends neither). The model must be offered,
    /// published and chosen for Vision; otherwise nothing is sent.
    public func visionText(session: ChatGPTPlanSession, model: String, system: String, message: String, images: [String],
                           timeoutSeconds: Double, onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        _ = try ChatGPTPolicy.call("chatgpt_auth_operation", ["purpose": .string("vision"), "tag": .string("vision")])
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
            if try Self.shouldPause(Self.diagnostic(error).code) { try await pauseQuota(session) }
            throw error
        }
    }
    /// Server request_vision: the answer may be up to 512 KiB of UTF-8.
    static let visionTextLimit = 512 * 1024

    /// The bytes recorded and sent: the effect's prompt as written, so the schema keeps its member order.
    static func request(action: Data, model: String, argumentLimit: Int) throws -> ChatGPTWire.Request {
        let images = try ExactJSON(data: action)["_transient_images"].array?.compactMap(\.string) ?? []
        return try ChatGPTWire.request(model: model, prompt: ExactJSON.rawMember("prompt", in: ExactJSON.rawMember("payload", in: action)), answerLimit: argumentLimit, images: images)
    }

    private func offeredModels(session: ChatGPTPlanSession, force: Bool, deadline: Date, operationEpoch: UInt64) async throws -> [ChatGPTPlanModel] {
        try validate(session, operationEpoch: operationEpoch)
        let profile = try checkedProfile(session)
        let cache = try ChatGPTPolicy.call("chatgpt_cache", ["force": .bool(force), "cache": profile.models == nil ? .null : ChatGPTPolicy.profile(profile)["catalog"], "now": ChatGPTPolicy.number(Date().timeIntervalSince1970)])
        if cache["fresh"].bool == true, let models = profile.models { return models }
        let token = try await accessToken(session, deadline: deadline, operationEpoch: operationEpoch)
        var request = URLRequest(url: ChatGPTEndpoints.models); request.timeoutInterval = max(0.001, deadline.timeIntervalSinceNow)
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        let boundedRequest = request
        let result = try await guarded(deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) }) {
            try await self.http.send(boundedRequest, maximumBytes: 1_048_576, onBytes: { _ in })
        }
        if !(200...299).contains(result.status) {
            let error = try ChatGPTWire.httpFailure(result)
            if try Self.shouldPause(error.diagnostic.code) { try await pauseQuota(session) }
            throw error
        }
        guard let value = try? ExactJSON(data: result.data) else { throw HostError("chatgpt_response_invalid") }
        let models = try ChatGPTWire.catalog(value)
        try await mutate { value in
            try self.validate(session, operationEpoch: operationEpoch)
            _ = try self.checkedProfile(session, value: value)
            value.profiles[session.profileID]?.models = models
            let expires = cache["expires_at"].number.flatMap(Double.init) ?? Date().addingTimeInterval(300).timeIntervalSince1970
            value.profiles[session.profileID]?.modelsExpireAt = Date(timeIntervalSince1970: expires)
        }
        return models
    }
    private func accessToken(_ session: ChatGPTPlanSession, deadline: Date, operationEpoch: UInt64) async throws -> String {
        let lease = try await store.lease("refresh", deadline: deadline, check: { try await self.validate(session, operationEpoch: operationEpoch) })
        defer { _ = lease }
        let profile = try checkedProfile(session)
        let decision = try ChatGPTPolicy.call("chatgpt_auth_access", ["profile": ChatGPTPolicy.profile(profile), "now": ChatGPTPolicy.number(Date().timeIntervalSince1970)])
        if decision["decision"].string == "use", let token = profile.accessToken { return token }
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
                let tokens: ExactJSON = .object(["access_token": .string(fields.access), "refresh_token": .string(fields.refresh),
                    "id_token": ChatGPTPolicy.string(fields.identity), "scopes": .array(fields.scopes.map(ExactJSON.string)),
                    "expires_at": ChatGPTPolicy.number(fields.expiry.timeIntervalSince1970),
                    "earliest_refresh_at": ChatGPTPolicy.number(fields.earliest.timeIntervalSince1970)])
                let updated = try ChatGPTPolicy.call("chatgpt_auth_refresh_profile", ["profile": ChatGPTPolicy.profile(current), "tokens": tokens])["profile"]
                current.accessToken = updated["access_token"].string; current.refreshToken = updated["refresh_token"].string; current.idToken = updated["id_token"].string
                current.scopes = updated["scopes"].array?.compactMap(\.string) ?? []
                guard let expiry = updated["expires_at"].number.flatMap(Double.init), let earliest = updated["earliest_refresh_at"].number.flatMap(Double.init) else { throw HostError("chatgpt_identity_invalid") }
                current.expiresAt = Date(timeIntervalSince1970: expiry); current.earliestRefreshAt = Date(timeIntervalSince1970: earliest)
                current.models = nil; current.modelsExpireAt = nil; saved.profiles[current.id] = current
            }
            return fields.access
        } catch let error as HostError where error.code == "chatgpt_reauthentication_required" {
            try await mutate { saved in
                var current = try self.checkedProfile(session, value: saved)
                try Self.transition(&current, to: "reauthentication_required")
                saved.profiles[current.id] = current
            }
            throw error
        }
    }
    private struct TokenFields { let access: String; let refresh: String; let identity: String?; let scopes: [String]; let expiry: Date; let earliest: Date }
    private func tokenFields(_ value: ExactJSON, previous: ChatGPTStoredProfile?) throws -> TokenFields {
        let now = Date()
        let result = try ChatGPTPolicy.call("chatgpt_auth_tokens", ["value": value, "previous": previous.map(ChatGPTPolicy.profile) ?? .object([:]),
            "now": ChatGPTPolicy.number(now.timeIntervalSince1970), "local_offset_seconds": .integer(TimeZone.current.secondsFromGMT(for: now))])["tokens"]
        let access = try result.requiredString("access_token"), refresh = try result.requiredString("refresh_token")
        guard access.utf8.count <= 65_536, refresh.utf8.count <= 65_536,
              let expiry = result["expires_at"].number.flatMap(Double.init), let earliest = result["earliest_refresh_at"].number.flatMap(Double.init) else { throw HostError("chatgpt_identity_invalid") }
        let identity = result["id_token"].string
        guard identity == nil || identity!.utf8.count <= 65_536 else { throw HostError("chatgpt_identity_invalid") }
        return TokenFields(access: access, refresh: refresh, identity: identity, scopes: result["scopes"].array?.compactMap(\.string) ?? [],
            expiry: Date(timeIntervalSince1970: expiry), earliest: Date(timeIntervalSince1970: earliest))
    }

    private func verifyIdentity(token: String, clientID: String, nonce: String?, expectedSubject: String?, deadline: Date,
                                check: @escaping @Sendable () async throws -> Void) async throws -> ChatGPTVerifiedIdentity {
        let metadata = try await authJSON(url: ChatGPTEndpoints.discovery, deadline: deadline, check: check)
        _ = try ChatGPTPolicy.call("chatgpt_auth_discovery", ["discovery": metadata])
        guard let url = URL(string: try metadata.requiredString("jwks_uri")) else { throw HostError("chatgpt_identity_invalid") }
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
        let value = try? ExactJSON(data: result.data)
        _ = try ChatGPTPolicy.call("chatgpt_auth_http", ["status": .integer(result.status), "json_valid": .bool(value != nil), "value": value ?? .null])
        guard let value else { throw HostError("chatgpt_auth_unavailable") }
        try await check(); return value
    }

    private func pauseQuota(_ session: ChatGPTPlanSession) async throws {
        try await mutate { value in
            guard var profile = value.profiles[session.profileID] else { return }
            let result = try ChatGPTPolicy.call("chatgpt_auth_pause_quota", ["profile": ChatGPTPolicy.profile(profile), "generation": .number(String(session.generation))])
            if result["changed"].bool == true { profile.state = "quota"; profile.models = nil; profile.modelsExpireAt = nil; value.profiles[profile.id] = profile }
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
        _ = try ChatGPTPolicy.call("chatgpt_auth_session", ["profile": ChatGPTPolicy.profile(profile), "generation": .number(String(session.generation))])
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
    private static func shouldPause(_ code: String) throws -> Bool {
        try ChatGPTPolicy.call("chatgpt_auth_quota_failure", ["code": .string(code)])["pause"].bool == true
    }
    private static func transition(_ profile: inout ChatGPTStoredProfile, to state: String) throws {
        let result = try ChatGPTPolicy.call("chatgpt_auth_transition", ["profile": ChatGPTPolicy.profile(profile), "state": .string(state)])["profile"]
        guard let generation = result["generation"].number.flatMap(Int64.init), let state = result["state"].string else { throw HostError("chatgpt_identity_invalid") }
        profile.generation = generation; profile.state = state; profile.removeTokens()
    }
    private static func nextGeneration(_ generation: Int64) throws -> Int64 {
        let result = try ChatGPTPolicy.call("chatgpt_auth_generation", ["previous": .object(["generation": .number(String(generation))])])
        guard let next = result["generation"].number.flatMap(Int64.init) else { throw HostError("chatgpt_session_changed") }; return next
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
