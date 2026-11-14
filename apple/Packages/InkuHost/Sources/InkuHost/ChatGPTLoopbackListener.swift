import Foundation
@preconcurrency import Network

/// The sign-in callback's socket (Sign in with ChatGPT step 5): it listens on 127.0.0.1, hands each request head to
/// the core flow (`await_callback`) and writes the core's answer (`respond`). Reading the head and deciding the
/// answer are the core's.
public final class ChatGPTLoopbackListener: Sendable {
    public let port: UInt16
    private let engine: LoopbackEngine

    private init(engine: LoopbackEngine, port: UInt16) { self.engine = engine; self.port = port }

    public static func start(deadline: Date) async throws -> ChatGPTLoopbackListener {
        let duration = deadline.timeIntervalSinceNow
        guard duration.isFinite, duration > 0, !Task.isCancelled else { throw HostError("chatgpt_cancelled") }
        let lease = try LoopbackLease.shared.acquire()
        let engine: LoopbackEngine
        do {
            let parameters = NWParameters.tcp
            // A listener on .any alone would expose the callback on other interfaces.
            parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)
            #if os(iOS)
            // iOS resets every connection, the login sheet's 127.0.0.1 callback included, on a listener that accepts
            // local peers only (ios-app step 5 screen check, 2026-11-09: POSIX 96 in the sheet, curl "reset by peer").
            // The loopback endpoint above already keeps other devices out.
            #else
            parameters.acceptLocalOnly = true
            #endif
            parameters.includePeerToPeer = false
            parameters.allowLocalEndpointReuse = false
            engine = LoopbackEngine(listener: try NWListener(using: parameters, on: .any), lease: lease, duration: duration)
        } catch {
            LoopbackLease.shared.release(lease)
            throw HostError("chatgpt_auth_unavailable")
        }
        do {
            let port = try await withTaskCancellationHandler {
                try await withCheckedThrowingContinuation { engine.start($0) }
            } onCancel: { engine.cancel() }
            guard !Task.isCancelled else { await engine.cancelAndWait(); throw HostError("chatgpt_cancelled") }
            return ChatGPTLoopbackListener(engine: engine, port: port)
        } catch {
            await engine.cancelAndWait()
            throw error
        }
    }

    /// The next request's head, without its closing blank line (core `await_callback`). Cancelling the wait cancels
    /// the listener.
    public func nextHead() async throws -> Data {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { engine.next($0) }
        } onCancel: { engine.cancel() }
    }

    /// Answers the request whose head was handed out last and closes it (core `respond`).
    public func respond(status: Int, headers: [(String, String)], body: String) async {
        await withCheckedContinuation { engine.respond(status: status, headers: headers, body: body, done: $0) }
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
        lock.lock(); defer { lock.unlock() }
        guard active == nil else { throw HostError("chatgpt_attempt_busy") }
        let lease = UUID()
        active = lease
        return lease
    }

    func release(_ lease: UUID) {
        lock.lock(); defer { lock.unlock() }
        if active == lease { active = nil }
    }
}

// All mutable engine and connection state is confined to this private serial queue.
private final class LoopbackEngine: @unchecked Sendable {
    /// One more than the core's head limit (`sign_in_auth_constants`), so a longer head reaches the core and is
    /// refused there.
    private static let headerLimit: Int = {
        guard let value = (try? ChatGPTPolicy.call("sign_in_auth_constants"))?["callback_header_bytes"].number.flatMap(Int.init) else {
            preconditionFailure("the core answers the callback head limit")
        }
        return value + 1
    }()
    private let queue = DispatchQueue(label: "inku.chatgpt.loopback")
    private let listener: NWListener
    private let lease: UUID
    private let deadline: DispatchTime
    private var ready: CheckedContinuation<UInt16, any Error>?
    private var waiter: CheckedContinuation<Data, any Error>?
    private var heads: [(ObjectIdentifier, Data)] = []
    private var current: ObjectIdentifier?
    private var closed = false
    private var deadlineTask: DispatchWorkItem?
    private var requests: [ObjectIdentifier: Request] = [:]

    private final class Request {
        let connection: NWConnection
        var bytes = Data()
        var timeout: DispatchWorkItem?
        init(_ connection: NWConnection) { self.connection = connection }
    }

    init(listener: NWListener, lease: UUID, duration: TimeInterval) {
        self.listener = listener
        self.lease = lease
        deadline = .now() + duration
    }

    func start(_ continuation: CheckedContinuation<UInt16, any Error>) {
        queue.async { [self] in
            guard !closed else { continuation.resume(throwing: HostError("chatgpt_cancelled")); return }
            ready = continuation
            listener.stateUpdateHandler = { [weak self] state in self?.listenerChanged(state) }
            listener.newConnectionHandler = { [weak self] connection in
                guard let self else { connection.cancel(); return }
                self.accept(connection)
            }
            let timeout = DispatchWorkItem { [weak self] in self?.close() }
            deadlineTask = timeout
            queue.asyncAfter(deadline: deadline, execute: timeout)
            listener.start(queue: queue)
        }
    }

    func next(_ continuation: CheckedContinuation<Data, any Error>) {
        queue.async { [self] in
            guard waiter == nil else { continuation.resume(throwing: HostError("chatgpt_callback_invalid")); return }
            if !heads.isEmpty { hand(continuation) }
            else if closed { continuation.resume(throwing: HostError("chatgpt_cancelled")) }
            else { waiter = continuation }
        }
    }

    func respond(status: Int, headers: [(String, String)], body: String, done: CheckedContinuation<Void, Never>) {
        queue.async { [self] in
            guard let id = current, let request = requests[id] else { done.resume(); return }
            current = nil
            let reason = status == 200 ? "OK" : "Bad Request"
            var text = "HTTP/1.1 \(status) \(reason)\r\n"
            for (name, value) in headers { text += "\(name): \(value)\r\n" }
            text += "Content-Length: \(body.utf8.count)\r\n\r\n" + body
            request.connection.send(content: Data(text.utf8), contentContext: .finalMessage, isComplete: true,
                                    completion: .contentProcessed { [weak self] _ in self?.removeRequest(id); done.resume() })
        }
    }

    func cancel() { queue.async { [self] in close() } }

    func cancelAndWait() async {
        await withCheckedContinuation { continuation in
            queue.async { [self] in close(); continuation.resume() }
        }
    }

    private func hand(_ continuation: CheckedContinuation<Data, any Error>) {
        let (id, head) = heads.removeFirst()
        current = id
        continuation.resume(returning: head)
    }

    private func listenerChanged(_ state: NWListener.State) {
        guard !closed else { return }
        switch state {
        case .ready:
            guard let port = listener.port?.rawValue, port != 0 else { fail(HostError("chatgpt_auth_unavailable")); return }
            let continuation = ready; ready = nil
            continuation?.resume(returning: port)
        case .waiting, .failed: fail(HostError("chatgpt_auth_unavailable"))
        case .cancelled: close()
        case .setup: break
        @unknown default: fail(HostError("chatgpt_auth_unavailable"))
        }
    }

    private func accept(_ connection: NWConnection) {
        guard !closed, ready == nil, requests.count < 4 else { connection.cancel(); return }
        let id = ObjectIdentifier(connection)
        let request = Request(connection)
        requests[id] = request
        // A connection that does not send its head within a second is dropped.
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
        guard let request = requests[id] else { return }
        let remaining = Self.headerLimit - request.bytes.count
        request.connection.receive(minimumIncompleteLength: 1, maximumLength: min(4096, remaining)) {
            [weak self] data, _, complete, error in
            guard let self, let request = self.requests[id] else { return }
            if let data { request.bytes.append(data) }
            let end = request.bytes.range(of: Data([13, 10, 13, 10]))
            if let end, end.upperBound == request.bytes.endIndex {
                self.queueHead(id, request.bytes.subdata(in: 0..<end.lowerBound))
            } else if end != nil || request.bytes.count >= Self.headerLimit {
                // Bytes after the blank line, or a head past its limit: the core refuses them as they came.
                self.queueHead(id, request.bytes)
            } else if error != nil || complete {
                self.removeRequest(id)
            } else {
                self.receive(id)
            }
        }
    }

    private func queueHead(_ id: ObjectIdentifier, _ head: Data) {
        guard !closed, let request = requests[id] else { return }
        request.timeout?.cancel(); request.timeout = nil
        request.bytes.removeAll(keepingCapacity: false)
        heads.append((id, head))
        if let continuation = waiter { waiter = nil; hand(continuation) }
    }

    private func removeRequest(_ id: ObjectIdentifier) {
        guard let request = requests.removeValue(forKey: id) else { return }
        request.timeout?.cancel()
        request.connection.stateUpdateHandler = nil
        request.connection.cancel()
        heads.removeAll { $0.0 == id }
        if current == id { current = nil }
    }

    private func fail(_ error: HostError) {
        if let continuation = ready { ready = nil; continuation.resume(throwing: error) }
        close()
    }

    private func close() {
        guard !closed else { return }
        closed = true
        deadlineTask?.cancel(); deadlineTask = nil
        listener.cancel()
        listener.newConnectionHandler = nil
        listener.stateUpdateHandler = nil
        for id in Array(requests.keys) { removeRequest(id) }
        LoopbackLease.shared.release(lease)
        if let continuation = ready { ready = nil; continuation.resume(throwing: HostError("chatgpt_cancelled")) }
        if let continuation = waiter { waiter = nil; continuation.resume(throwing: HostError("chatgpt_cancelled")) }
    }

    deinit {
        listener.cancel()
        LoopbackLease.shared.release(lease)
    }
}
