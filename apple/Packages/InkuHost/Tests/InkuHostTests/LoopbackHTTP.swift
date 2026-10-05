import Foundation
import Network

/// A keep-alive HTTP/1.1 server on 127.0.0.1 that answers scripted statuses and counts TCP connections.
final class LoopbackHTTP: @unchecked Sendable {
    private let listener: NWListener
    private let queue = DispatchQueue(label: "inku.loopback.http")
    private let lock = NSLock()
    private var script: [(status: Int, body: String)]
    private var connectionCount = 0
    private var requestCount = 0
    var connections: Int { lock.withLock { connectionCount } }
    var requests: Int { lock.withLock { requestCount } }
    private(set) var port: UInt16 = 0

    init(_ script: [(Int, String)]) async throws {
        self.script = script.map { (status: $0.0, body: $0.1) }
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
        listener = try NWListener(using: parameters)
        listener.newConnectionHandler = { [unowned self] connection in
            self.lock.withLock { self.connectionCount += 1 }
            connection.start(queue: self.queue)
            self.receive(connection, buffer: Data())
        }
        port = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<UInt16, any Error>) in
            // State updates arrive on the serial queue, so the flag needs no lock.
            final class Once: @unchecked Sendable { var done = false }
            let once = Once()
            listener.stateUpdateHandler = { [listener] state in
                guard !once.done else { return }
                switch state {
                case .ready: once.done = true; continuation.resume(returning: listener.port!.rawValue)
                case .failed(let error): once.done = true; continuation.resume(throwing: error)
                default: break
                }
            }
            listener.start(queue: queue)
        }
    }
    deinit { listener.cancel() }

    private func receive(_ connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [self] data, _, complete, error in
            var buffer = buffer + (data ?? Data())
            while let end = buffer.range(of: Data("\r\n\r\n".utf8)) {
                let head = String(decoding: buffer[..<end.lowerBound], as: UTF8.self).lowercased()
                let length = head.split(separator: "\r\n").first { $0.hasPrefix("content-length:") }
                    .flatMap { Int($0.dropFirst(15).trimmingCharacters(in: .whitespaces)) } ?? 0
                guard buffer.distance(from: buffer.startIndex, to: end.upperBound) + length <= buffer.count else { break }
                buffer = Data(buffer[buffer.index(end.upperBound, offsetBy: length)...])
                let reply = lock.withLock { () -> (status: Int, body: String) in
                    requestCount += 1
                    return script.isEmpty ? (500, "{}") : script.removeFirst()
                }
                let body = Data(reply.body.utf8)
                let header = "HTTP/1.1 \(reply.status) Fixture\r\nContent-Type: application/json\r\nContent-Length: \(body.count)\r\nConnection: keep-alive\r\n\r\n"
                connection.send(content: Data(header.utf8) + body, completion: .contentProcessed { _ in })
            }
            if complete || error != nil { connection.cancel() } else { receive(connection, buffer: buffer) }
        }
    }
}
