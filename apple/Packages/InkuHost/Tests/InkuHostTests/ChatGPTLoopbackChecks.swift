import Darwin
import Foundation
import XCTest
@testable import InkuHost

/// The callback socket only (step 5): the core reads the head and decides the answer, tested in the shared rows.
final class ChatGPTLoopbackChecks: XCTestCase, @unchecked Sendable {
    /// Sends `request` raw and returns everything answered.
    private func raw(port: UInt16, _ request: String) throws -> String {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { throw HostError("fixture_socket_failed") }
        defer { close(fd) }
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = port.bigEndian
        _ = "127.0.0.1".withCString { inet_pton(AF_INET, $0, &address.sin_addr) }
        let connected = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        guard connected == 0 else { throw HostError("fixture_socket_failed") }
        let sent = request.withCString { send(fd, $0, request.utf8.count, 0) }
        guard sent == request.utf8.count else { throw HostError("fixture_socket_failed") }
        var answer = Data(), buffer = [UInt8](repeating: 0, count: 4096)
        while true {
            let count = recv(fd, &buffer, buffer.count, 0)
            guard count > 0 else { break }
            answer.append(contentsOf: buffer[..<count])
        }
        return String(decoding: answer, as: UTF8.self)
    }

    func testHeadsReachTheFlowAsSentAndAnswersAreWrittenAsGiven() async throws {
        let listener = try await ChatGPTLoopbackListener.start(deadline: Date().addingTimeInterval(30))
        do {
            XCTAssertNotEqual(listener.port, 0)
            do {
                _ = try await ChatGPTLoopbackListener.start(deadline: Date().addingTimeInterval(30))
                XCTFail("An active flow must reserve the listener lease")
            } catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_attempt_busy") }

            let head = "GET /auth/callback?state=s&code=c HTTP/1.1\r\nHost: 127.0.0.1:\(listener.port)\r\nUser-Agent: fixture"
            let port = listener.port
            let client = Task.detached { try self.raw(port: port, head + "\r\n\r\n") }
            let received = try await listener.nextHead()
            XCTAssertEqual(String(decoding: received, as: UTF8.self), head, "the head without its blank line")
            await listener.respond(status: 400, headers: [("Cache-Control", "no-store"), ("Content-Type", "text/html; charset=utf-8")],
                                   body: "<p>page</p>")
            let answer = try await client.value
            XCTAssertEqual(answer, "HTTP/1.1 400 Bad Request\r\nCache-Control: no-store\r\nContent-Type: text/html; charset=utf-8\r\n"
                + "Content-Length: 11\r\n\r\n<p>page</p>")
            await listener.cancel()
        } catch {
            await listener.cancel()
            throw error
        }

        let cancelled = try await ChatGPTLoopbackListener.start(deadline: Date().addingTimeInterval(30))
        let waiting = Task { try await cancelled.nextHead() }
        await cancelled.cancel()
        do {
            _ = try await waiting.value
            XCTFail("Cancel must drain a pending wait")
        } catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_cancelled") }
        let restarted = try await ChatGPTLoopbackListener.start(deadline: Date().addingTimeInterval(30))
        await restarted.cancel()
    }
}
