import Foundation
import XCTest
@testable import InkuHost

final class ChatGPTLoopbackChecks: XCTestCase, @unchecked Sendable {
    // Failure: a wrong route/state consumes authorization, or cancel leaves the single-flow lease occupied.
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
            let wrongState = try await request("/auth/callback?state=wrong_state&error=access_denied")
            XCTAssertEqual(wrongState, 400)
            let callbackTask = Task { try await listener.waitForCallback() }
            let accepted = try await request("/auth/callback?state=offline_state_fixture&code=offline_code%2B%3D")
            XCTAssertEqual(accepted, 200)
            let callback = try await callbackTask.value
            XCTAssertEqual(callback, ChatGPTLoopbackCallback(code: "offline_code+=", clientID: nil, state: "offline_state_fixture"))
            await listener.cancel()
        } catch {
            await listener.cancel()
            throw error
        }

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
