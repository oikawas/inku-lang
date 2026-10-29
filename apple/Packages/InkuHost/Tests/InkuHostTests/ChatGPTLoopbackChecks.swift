import Darwin
import Foundation
import XCTest
@testable import InkuHost

final class ChatGPTLoopbackChecks: XCTestCase, @unchecked Sendable {
    private func rawStatus(port: Int, target: String) throws -> Int {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { throw HostError("fixture_socket_failed") }
        defer { close(fd) }
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = UInt16(port).bigEndian
        _ = "127.0.0.1".withCString { inet_pton(AF_INET, $0, &address.sin_addr) }
        let connected = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        guard connected == 0 else { throw HostError("fixture_socket_failed") }
        let request = "GET \(target) HTTP/1.1\r\nHost: 127.0.0.1:\(port)\r\nContent-Length: 0\r\n\r\n"
        let sent = request.withCString { send(fd, $0, request.utf8.count, 0) }
        guard sent == request.utf8.count else { throw HostError("fixture_socket_failed") }
        var buffer = [UInt8](repeating: 0, count: 512)
        let count = recv(fd, &buffer, buffer.count, 0)
        guard count > 0, let line = String(bytes: buffer[..<count], encoding: .utf8)?.components(separatedBy: "\r\n").first,
              let status = Int(line.split(separator: " ")[1]) else { throw HostError("fixture_socket_failed") }
        return status
    }

    // Malformed targets and wrong states leave the listener available for the correct callback.
    func testTemporaryIPv4CallbackValidatesHandoffAndCancellationReleasesLease() async throws {
        let listener = try await ChatGPTLoopbackListener.start(expectedState: "offline_state_fixture")
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 2
        configuration.timeoutIntervalForResource = 3
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        do {
            XCTAssertEqual(listener.redirectURI.scheme, "http")
            XCTAssertEqual(listener.redirectURI.host, "127.0.0.1")
            XCTAssertEqual(listener.redirectURI.path, "/auth/callback")
            XCTAssertNotEqual(listener.redirectURI.port, 0)
            do {
                _ = try await ChatGPTLoopbackListener.start(expectedState: "second_offline_fixture")
                XCTFail("An active flow must reserve the listener lease")
            } catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_attempt_busy") }

            func request(_ pathAndQuery: String) async throws -> Int? {
                let address = "http://127.0.0.1:\(listener.redirectURI.port!)" + pathAndQuery
                let (body, response) = try await session.data(from: URL(string: address)!)
                XCTAssertEqual(String(data: body, encoding: .utf8), "Return to inku. The connection status is shown there.")
                return (response as? HTTPURLResponse)?.statusCode
            }
            let wrongRoute = try await request("/wrong?state=offline_state_fixture&code=offline_code")
            XCTAssertEqual(wrongRoute, 400)
            let callbackTask = Task { try await listener.waitForCallback() }
            let wrongState = try await request("/auth/callback?state=wrong_state&error=access_denied")
            XCTAssertEqual(wrongState, 400)
            let noEquals = try await request("/auth/callback?alone")
            XCTAssertEqual(noEquals, 400)
            let duplicate = try await request("/auth/callback?state=offline_state_fixture&state=again&code=offline_code")
            XCTAssertEqual(duplicate, 400)
            XCTAssertEqual(try rawStatus(port: listener.redirectURI.port!,
                target: "/auth/callback?state=offline_state_fixture&client_id=fixture-client&code=offline_code%2B%3D&error_description=ignored#fragment"), 200)
            let callback = try await callbackTask.value
            XCTAssertEqual(callback,
                ChatGPTLoopbackCallback(code: "offline_code+=", clientID: "fixture-client", state: "offline_state_fixture"))
            await listener.cancel()
        } catch {
            await listener.cancel()
            throw error
        }

        let emptyCode = try await ChatGPTLoopbackListener.start(expectedState: "empty_fixture")
        let emptyWait = Task { try await emptyCode.waitForCallback() }
        XCTAssertEqual(try rawStatus(port: emptyCode.redirectURI.port!, target: "/auth/callback?state=empty_fixture&client_id=fixture-client&code="), 400)
        do { _ = try await emptyWait.value; XCTFail("An empty code was accepted") }
        catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_auth_unavailable") }
        await emptyCode.cancel()

        let cancelled = try await ChatGPTLoopbackListener.start(expectedState: "cancel_fixture")
        let waiting = Task { try await cancelled.waitForCallback() }
        await cancelled.cancel()
        do {
            _ = try await waiting.value
            XCTFail("Cancel must drain a pending wait")
        } catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_cancelled") }
        let restarted = try await ChatGPTLoopbackListener.start(expectedState: "restart_fixture")
        await restarted.cancel()
    }
}
