import Foundation
@preconcurrency import Network

public struct ChatGPTLoopbackCallback: Sendable, Equatable {
    public let code: String
    public let clientID: String?
    public let state: String

    public init(code: String, clientID: String?, state: String) {
        self.code = code
        self.clientID = clientID
        self.state = state
    }
}

/// Receives one authorization callback without launching a browser or exchanging credentials.
public final class ChatGPTLoopbackListener: Sendable {
    public let redirectURI: URL
    private let engine: LoopbackEngine

    private init(engine: LoopbackEngine, port: UInt16) {
        self.engine = engine
        // This URI uses the actual bound port, and must be reused verbatim for code exchange.
        redirectURI = URL(string: "http://127.0.0.1:\(port)/auth/callback")!
    }

    public static func start(expectedState: String, deadline: Date = Date().addingTimeInterval(300)) async throws -> ChatGPTLoopbackListener {
        guard !expectedState.isEmpty, expectedState.utf8.count <= 256,
              !expectedState.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else {
            throw HostError("chatgpt_callback_invalid")
        }
        let duration = min(deadline.timeIntervalSinceNow, 300)
        guard duration.isFinite, duration > 0, !Task.isCancelled else { throw HostError("chatgpt_cancelled") }
        let lease = try LoopbackLease.shared.acquire()
        let engine: LoopbackEngine
        do {
            let parameters = NWParameters.tcp
            // A listener on .any alone would expose the callback on other interfaces.
            parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)
            parameters.acceptLocalOnly = true
            parameters.includePeerToPeer = false
            parameters.allowLocalEndpointReuse = false
            engine = LoopbackEngine(listener: try NWListener(using: parameters, on: .any),
                                    lease: lease, expectedState: expectedState, duration: duration)
        } catch {
            LoopbackLease.shared.release(lease)
            throw HostError("chatgpt_auth_unavailable")
        }
        do {
            let port = try await withTaskCancellationHandler {
                try await withCheckedThrowingContinuation { engine.start($0) }
            } onCancel: { engine.cancel() }
            guard !Task.isCancelled else {
                await engine.cancelAndWait()
                throw HostError("chatgpt_cancelled")
            }
            return ChatGPTLoopbackListener(engine: engine, port: port)
        } catch {
            await engine.cancelAndWait()
            throw error
        }
    }

    /// The callback is handed off once. Cancelling this wait cancels the complete listener.
    public func waitForCallback() async throws -> ChatGPTLoopbackCallback {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { engine.wait($0) }
        } onCancel: { engine.cancel() }
    }

    public func cancel() async { await engine.cancelAndWait() }

    deinit { engine.cancel() }
}

// The lease is constant-size and synchronous so cancel/timeout releases it before a new flow starts.
private final class LoopbackLease: @unchecked Sendable {
    static let shared = LoopbackLease()
    private let lock = NSLock()
    private var active: UUID?

    func acquire() throws -> UUID {
        lock.lock()
        defer { lock.unlock() }
        guard active == nil else { throw HostError("chatgpt_attempt_busy") }
        let lease = UUID()
        active = lease
        return lease
    }

    func release(_ lease: UUID) {
        lock.lock()
        defer { lock.unlock() }
        if active == lease { active = nil }
    }
}

// All mutable engine and connection state is confined to this private serial queue.
private final class LoopbackEngine: @unchecked Sendable {
    private static let headerLimit = 16 * 1024
    private let queue = DispatchQueue(label: "inku.chatgpt.loopback")
    private let listener: NWListener
    private let lease: UUID
    private let deadline: DispatchTime
    private var expectedState: String?
    private var port: UInt16?
    private var ready: CheckedContinuation<UInt16, any Error>?
    private var waiter: CheckedContinuation<ChatGPTLoopbackCallback, any Error>?
    private var terminal: Result<ChatGPTLoopbackCallback, HostError>?
    private var waitClaimed = false
    private var closed = false
    private var deadlineTask: DispatchWorkItem?
    private var requests: [ObjectIdentifier: Request] = [:]

    private final class Request {
        let connection: NWConnection
        var bytes = Data()
        var responding = false
        var timeout: DispatchWorkItem?
        init(_ connection: NWConnection) { self.connection = connection }
    }

    init(listener: NWListener, lease: UUID, expectedState: String, duration: TimeInterval) {
        self.listener = listener
        self.lease = lease
        self.expectedState = expectedState
        deadline = .now() + duration
    }

    func start(_ continuation: CheckedContinuation<UInt16, any Error>) {
        queue.async { [self] in
            guard !closed else {
                continuation.resume(throwing: HostError("chatgpt_cancelled"))
                return
            }
            ready = continuation
            listener.stateUpdateHandler = { [weak self] state in self?.listenerChanged(state) }
            listener.newConnectionHandler = { [weak self] connection in
                guard let self else { connection.cancel(); return }
                self.accept(connection)
            }
            let timeout = DispatchWorkItem { [weak self] in self?.finish(.failure(HostError("chatgpt_cancelled"))) }
            deadlineTask = timeout
            queue.asyncAfter(deadline: deadline, execute: timeout)
            listener.start(queue: queue)
        }
    }

    func wait(_ continuation: CheckedContinuation<ChatGPTLoopbackCallback, any Error>) {
        queue.async { [self] in
            guard !waitClaimed else {
                continuation.resume(throwing: HostError("chatgpt_callback_invalid"))
                return
            }
            waitClaimed = true
            if let result = terminal {
                terminal = nil
                continuation.resume(with: result.mapError { $0 as any Error })
            } else if closed {
                continuation.resume(throwing: HostError("chatgpt_cancelled"))
            } else {
                waiter = continuation
            }
        }
    }

    func cancel() { queue.async { [self] in cancelOnQueue() } }

    func cancelAndWait() async {
        await withCheckedContinuation { continuation in
            queue.async { [self] in
                cancelOnQueue()
                continuation.resume()
            }
        }
    }

    private func cancelOnQueue() {
        if closed {
            // Explicit cancellation also discards a callback that has not yet been handed off.
            if !waitClaimed { terminal = .failure(HostError("chatgpt_cancelled")) }
            for id in Array(requests.keys) { removeRequest(id) }
        } else {
            finish(.failure(HostError("chatgpt_cancelled")))
        }
    }

    private func listenerChanged(_ state: NWListener.State) {
        guard !closed else { return }
        switch state {
        case .ready:
            guard let boundPort = listener.port?.rawValue, boundPort != 0 else {
                finish(.failure(HostError("chatgpt_auth_unavailable")))
                return
            }
            port = boundPort
            let continuation = ready
            ready = nil
            continuation?.resume(returning: boundPort)
        case .waiting, .failed:
            finish(.failure(HostError("chatgpt_auth_unavailable")))
        case .cancelled:
            finish(.failure(HostError("chatgpt_cancelled")))
        case .setup: break
        @unknown default: finish(.failure(HostError("chatgpt_auth_unavailable")))
        }
    }

    private func accept(_ connection: NWConnection) {
        guard !closed, port != nil, requests.count < 4 else { connection.cancel(); return }
        let id = ObjectIdentifier(connection)
        let request = Request(connection)
        requests[id] = request
        let timeout = DispatchWorkItem { [weak self] in self?.removeRequest(id) }
        request.timeout = timeout
        queue.asyncAfter(deadline: .now() + 1, execute: timeout)
        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .failed, .cancelled: self?.removeRequest(id)
            default: break
            }
        }
        connection.start(queue: queue)
        receive(id)
    }

    private func receive(_ id: ObjectIdentifier) {
        guard let request = requests[id], !request.responding else { return }
        let remaining = Self.headerLimit - request.bytes.count
        guard remaining > 0 else { respond(id, status: 400); return }
        request.connection.receive(minimumIncompleteLength: 1, maximumLength: min(4096, remaining)) {
            [weak self] data, _, complete, error in
            guard let self, let request = self.requests[id], !request.responding else { return }
            if let data { request.bytes.append(data) }
            if let end = request.bytes.range(of: Data([13, 10, 13, 10])) {
                guard end.upperBound == request.bytes.endIndex else { self.respond(id, status: 400); return }
                self.handle(id, header: request.bytes.subdata(in: 0..<end.lowerBound))
            } else if error != nil || complete || request.bytes.count >= Self.headerLimit {
                self.respond(id, status: 400)
            } else {
                self.receive(id)
            }
        }
    }

    private func handle(_ id: ObjectIdentifier, header: Data) {
        guard !closed, let port, let expectedState else { respond(id, status: 400); return }
        guard DispatchTime.now() < deadline else {
            respond(id, status: 400)
            finish(.failure(HostError("chatgpt_cancelled")), keeping: id)
            return
        }
        guard let query = Self.query(header: header, port: port), let state = query["state"],
              state.utf8.count <= 256, Self.equal(state, expectedState) else {
            respond(id, status: 400)
            return
        }
        // State is checked before interpreting a consent error or consuming this attempt.
        let result: Result<ChatGPTLoopbackCallback, HostError>
        if query["error"] != nil || query["error_description"] != nil {
            result = .failure(HostError("chatgpt_consent_declined"))
        } else if let code = query["code"], !code.isEmpty {
            result = .success(ChatGPTLoopbackCallback(code: code, clientID: query["client_id"], state: state))
        } else {
            result = .failure(HostError("chatgpt_callback_invalid"))
        }
        respond(id, status: (try? result.get()) == nil ? 400 : 200)
        finish(result, keeping: id)
    }

    private func respond(_ id: ObjectIdentifier, status: Int) {
        guard let request = requests[id], !request.responding else { return }
        request.responding = true
        request.bytes.removeAll(keepingCapacity: false)
        let body = "Return to inku. The connection status is shown there."
        let reason = status == 200 ? "OK" : "Bad Request"
        let response = "HTTP/1.1 \(status) \(reason)\r\nContent-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: \(body.utf8.count)\r\n\r\n\(body)"
        request.connection.send(content: Data(response.utf8), contentContext: .finalMessage, isComplete: true,
                                completion: .contentProcessed { [weak self] _ in self?.removeRequest(id) })
    }

    private func removeRequest(_ id: ObjectIdentifier) {
        guard let request = requests.removeValue(forKey: id) else { return }
        request.timeout?.cancel()
        request.bytes.removeAll(keepingCapacity: false)
        request.connection.stateUpdateHandler = nil
        request.connection.cancel()
    }

    private func finish(_ result: Result<ChatGPTLoopbackCallback, HostError>, keeping id: ObjectIdentifier? = nil) {
        guard !closed else { return }
        closed = true
        expectedState = nil
        deadlineTask?.cancel()
        deadlineTask = nil
        listener.cancel()
        listener.newConnectionHandler = nil
        listener.stateUpdateHandler = nil
        for key in Array(requests.keys) where key != id { removeRequest(key) }
        LoopbackLease.shared.release(lease)
        if let continuation = ready {
            ready = nil
            continuation.resume(throwing: result.failure ?? HostError("chatgpt_callback_invalid"))
        }
        if let continuation = waiter {
            waiter = nil
            continuation.resume(with: result.mapError { $0 as any Error })
        } else {
            terminal = result
        }
    }

    private static func query(header: Data, port: UInt16) -> [String: String]? {
        guard header.allSatisfy({ $0 == 9 || $0 == 10 || $0 == 13 || (32...126).contains($0) }),
              let text = String(data: header, encoding: .utf8) else { return nil }
        let lines = text.components(separatedBy: "\r\n")
        guard lines.count <= 65, let first = lines.first else { return nil }
        let parts = first.split(separator: " ", omittingEmptySubsequences: false)
        guard parts.count == 3, parts[0] == "GET", parts[1].utf8.count <= 8192,
              parts[2] == "HTTP/1.1" || parts[2] == "HTTP/1.0" else { return nil }
        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            guard let colon = line.firstIndex(of: ":"), colon != line.startIndex else { return nil }
            let name = String(line[..<colon]).lowercased()
            guard name.utf8.allSatisfy({ (97...122).contains($0) || (48...57).contains($0) || $0 == 45 }),
                  headers[name] == nil else { return nil }
            headers[name] = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
        }
        guard headers["host"] == "127.0.0.1:\(port)", headers["transfer-encoding"] == nil,
              headers["content-length"] == nil || headers["content-length"] == "0" else { return nil }
        let target = String(parts[1])
        guard let delimiter = target.firstIndex(of: "?"), target[..<delimiter] == "/auth/callback",
              !target.contains("#") else { return nil }
        var query: [String: String] = [:]
        let pairs = target[target.index(after: delimiter)...].split(separator: "&", omittingEmptySubsequences: false)
        guard !pairs.isEmpty, pairs.count <= 32 else { return nil }
        for pair in pairs {
            let fields = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            guard fields.count == 2, let name = decode(fields[0]), let value = decode(fields[1]),
                  !name.isEmpty, name.utf8.count <= 128, value.utf8.count <= 4096,
                  query[name] == nil else { return nil }
            query[name] = value
        }
        return query
    }

    private static func decode(_ raw: Substring) -> String? {
        let bytes = Array(raw.utf8)
        var index = 0
        while index < bytes.count {
            if bytes[index] == 37 {
                guard index + 2 < bytes.count, hexadecimal(bytes[index + 1]), hexadecimal(bytes[index + 2]) else { return nil }
                index += 3
            } else { index += 1 }
        }
        guard let value = String(raw).replacingOccurrences(of: "+", with: " ").removingPercentEncoding,
              !value.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else { return nil }
        return value
    }

    private static func hexadecimal(_ byte: UInt8) -> Bool {
        (48...57).contains(byte) || (65...70).contains(byte) || (97...102).contains(byte)
    }

    private static func equal(_ lhs: String, _ rhs: String) -> Bool {
        let a = Array(lhs.utf8), b = Array(rhs.utf8)
        var difference = a.count ^ b.count
        for index in 0..<max(a.count, b.count) {
            difference |= Int((index < a.count ? a[index] : 0) ^ (index < b.count ? b[index] : 0))
        }
        return difference == 0
    }

    deinit {
        listener.cancel()
        LoopbackLease.shared.release(lease)
    }
}

private extension Result where Failure == HostError {
    var failure: HostError? {
        if case .failure(let error) = self { return error }
        return nil
    }
}
