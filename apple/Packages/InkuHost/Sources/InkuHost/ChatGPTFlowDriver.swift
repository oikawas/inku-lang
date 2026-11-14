import Foundation

/// Sign in with ChatGPT step 5: the core answers each procedure (`chatgpt_flow_start`, `chatgpt_flow_next`) as one
/// thing to do next. The runtime does it — a lock, the vault, random bytes, the callback socket, an HTTP request, a
/// signature, a local offset — and hands the result back, until the core says `done` or `failed`.
struct ChatGPTFlowContext: Sendable {
    /// The locks this run holds, by the core's name (`edit`, `refresh`, `wire`).
    var held: [String: ChatGPTFileLease] = [:]
    /// Locks the caller already holds (a request holds `wire` while its model list is checked).
    var outside: Set<String> = []
    /// The registration whose `wire` lock is meant (`wire-<profile id>`).
    var profileID: String?
    var listener: ChatGPTLoopbackListener?
    /// Run between steps: cancellation, a changed session or a closed attempt stops the procedure.
    var check: @Sendable () async throws -> Void = {}
}

extension ChatGPTPlanRuntime {
    static func flowStart(_ flow: String, input: [String: ExactJSON]) throws -> ExactJSON {
        try ChatGPTPolicy.call("chatgpt_flow_start", ["flow": .string(flow), "input": .object(input), "now": ChatGPTPolicy.number(Date().timeIntervalSince1970)])
    }

    /// Answers each todo until `done` (returned) or `failed` (thrown), or until a todo named `stop` (its answer is
    /// returned unanswered). Every lock is let go when the run ends or throws.
    func drive(_ start: ExactJSON, _ context: inout ChatGPTFlowContext, stop: String? = nil) async throws -> ExactJSON {
        var answer = start
        do {
            while true {
                let todo = answer["todo"], kind = todo["todo"].string ?? ""
                switch kind {
                case "done": context.held.removeAll(); return todo
                case "failed": context.held.removeAll(); throw Self.flowFailure(todo)
                default: if kind == stop { return answer }
                }
                try await context.check()
                let result = try await perform(todo, &context)
                answer = try ChatGPTPolicy.call("chatgpt_flow_next", ["state": answer["state"], "result": result,
                    "now": ChatGPTPolicy.number(Date().timeIntervalSince1970)])
            }
        } catch {
            context.held.removeAll()
            throw error
        }
    }

    /// One todo of the table in PLAN-STEP5 §9-2, and its result.
    private func perform(_ todo: ExactJSON, _ context: inout ChatGPTFlowContext) async throws -> ExactJSON {
        func date(_ member: ExactJSON) -> Date { Date(timeIntervalSince1970: member.number.flatMap(Double.init) ?? 0) }
        switch todo["todo"].string ?? "" {
        case "acquire":
            let name = try todo.requiredString("lock")
            if context.outside.contains(name) { return .object(["acquired": .bool(true)]) }
            let file = name == "wire" ? "wire-" + (context.profileID ?? "") : name
            do {
                context.held[name] = try await store.lease(file, deadline: date(todo["deadline"]), check: context.check)
                return .object(["acquired": .bool(true)])
            } catch let failure as ChatGPTPlanFailure where failure.diagnostic.code == "chatgpt_transport_timeout" {
                return .object(["acquired": .bool(false)])
            }
        case "release":
            context.held.removeValue(forKey: try todo.requiredString("lock"))
            return .object([:])
        case "read":
            return .object(["value": ChatGPTPolicy.store(try store.load())])
        case "write":
            var value = try store.load()
            try ChatGPTPolicy.adopt(todo["value"], into: &value)
            try store.write(value)
            return .object([:])
        case "random":
            var values: [String: ExactJSON] = [:]
            for (name, count) in todo["bytes"].object ?? [:] {
                guard let bytes = count.number.flatMap(Int.init), (1...256).contains(bytes) else { throw HostError("chatgpt_auth_unavailable") }
                values[name] = .string(try random(bytes))
            }
            return .object(["values": .object(values)])
        case "host_id":
            let id: String = try await mutate { value in
                if value.hostID == nil { value.hostID = "urn:uuid:" + UUID().uuidString.lowercased() }
                return value.hostID!
            }
            return .object(["host_id": .string(id)])
        case "listen":
            let listener = try await ChatGPTLoopbackListener.start(deadline: date(todo["deadline"]))
            context.listener = listener
            return .object(["port": .integer(Int(listener.port))])
        case "await_callback":
            guard let listener = context.listener else { throw HostError("chatgpt_cancelled") }
            return .object(["head_base64": .string(try await listener.nextHead().base64EncodedString())])
        case "respond":
            guard let listener = context.listener, let status = todo["status"].number.flatMap(Int.init) else { throw HostError("chatgpt_cancelled") }
            let headers = (todo["headers"].object ?? [:]).compactMap { name, value in value.string.map { (name, $0) } }.sorted { $0.0 < $1.0 }
            await listener.respond(status: status, headers: headers, body: todo["body"].string ?? "")
            return .object([:])
        case "http":
            return try await send(todo, check: context.check)
        case "verify":
            return .object(["valid": .bool(ChatGPTIdentityVerifier.signatureValid(algorithm: todo["alg"].string ?? "", key: todo["key"],
                signingInput: todo["signing_input"].string ?? "", signature: todo["signature"].string ?? ""))])
        case "offset":
            return .object(["seconds": .integer(Self.localOffset(todo["local"].string ?? ""))])
        default:
            throw HostError("chatgpt_flow_invalid")
        }
    }

    /// A request the core shaped (`http`): no redirects (the ephemeral client refuses them), within its deadline and
    /// limits. A transport failure is one of the core's three kinds.
    private func send(_ todo: ExactJSON, check: @escaping @Sendable () async throws -> Void) async throws -> ExactJSON {
        guard let url = URL(string: try todo.requiredString("url")) else { throw HostError("chatgpt_endpoint_invalid") }
        try ChatGPTEndpoints.validate(url, authenticationOnly: todo["purpose"].string != "models")
        let deadline = Date(timeIntervalSince1970: todo["deadline"].number.flatMap(Double.init) ?? 0)
        var request = URLRequest(url: url); request.httpMethod = todo["method"].string ?? "GET"
        request.timeoutInterval = max(0.001, deadline.timeIntervalSinceNow)
        for (name, value) in todo["headers"].object ?? [:] { request.setValue(value.string, forHTTPHeaderField: name) }
        if let body = todo["body"].string { request.httpBody = Data(body.utf8) }
        let limit = todo["answer_limit"].number.flatMap(Double.init).map { Int($0) } ?? 1_048_576
        let bounded = request
        do {
            let response = try await guarded(deadline: deadline, check: check) {
                try await self.http.send(bounded, maximumBytes: limit, onBytes: { _ in })
            }
            var result: [String: ExactJSON] = ["status": .integer(response.status), "body": .string(String(decoding: response.data, as: UTF8.self))]
            if let id = response.requestID { result["request_id"] = .string(id) }
            return .object(result)
        } catch is CancellationError { throw CancellationError() }
        catch let failure as ChatGPTPlanFailure {
            switch failure.diagnostic.code {
            case "chatgpt_transport_timeout": return .object(["transport": .string("timeout")])
            case "chatgpt_response_too_large": return .object(["transport": .string("too_large")])
            case "chatgpt_transport_unavailable": return .object(["transport": .string("unavailable")])
            default: throw failure
            }
        } catch let error as URLError {
            return .object(["transport": .string(error.code == .timedOut ? "timeout" : "unavailable")])
        }
    }

    /// The local offset of a date or date and time the token answer gave without one (core `offset`).
    static func localOffset(_ local: String) -> Int {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = .current
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd"] {
            formatter.dateFormat = format
            if let date = formatter.date(from: local) { return TimeZone.current.secondsFromGMT(for: date) }
        }
        return TimeZone.current.secondsFromGMT(for: Date())
    }

    /// The core's `failed`: its code, failure and next action (and an HTTP failure's status, request id and param).
    static func flowFailure(_ todo: ExactJSON) -> ChatGPTPlanFailure {
        let code = todo["code"].string ?? "chatgpt_auth_unavailable"
        let classified = todo["failure"].string.flatMap { failure in todo["action"].string.map { (failure, $0) } }
            ?? ChatGPTWire.classify(code: code, temporary: nil)
        return ChatGPTPlanFailure(diagnostic: ChatGPTPlanDiagnostic(code: code, status: todo["status"].number.flatMap { Int($0) },
            requestID: todo["request_id"].string, parameter: todo["param"].string, failure: classified.0, action: classified.1))
    }
}
