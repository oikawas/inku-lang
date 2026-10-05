import CryptoKit
import Foundation
import Security
import XCTest
@testable import InkuHost

final class ChatGPTIdentityChecks: XCTestCase, @unchecked Sendable {
    private let now = Date(timeIntervalSince1970: 100)
    private var claims: ExactJSON {
        .object(["iss": .string("https://auth.openai.com"), "aud": .string("oaiapp_fixture"), "sub": .string("fixture-subject"),
                 "exp": .integer(150), "iat": .integer(90), "nonce": .string("fixture-nonce"), "email": .string("fixture@example.invalid")])
    }
    private func discovery(_ algorithm: String) -> ExactJSON {
        .object(["issuer": .string("https://auth.openai.com"), "jwks_uri": .string("https://auth.openai.com/.well-known/jwks.json"),
                 "id_token_signing_alg_values_supported": .array([.string(algorithm)])])
    }
    private func b64(_ bytes: Data) -> String {
        bytes.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
    private func message(_ algorithm: String) -> String {
        b64(ExactJSON.object(["alg": .string(algorithm), "kid": .string("fixture-key")]).data) + "." + b64(claims.data)
    }
    private func reject(_ expected: String = "chatgpt_identity_invalid", _ body: () throws -> Void) {
        XCTAssertThrowsError(try body()) { XCTAssertEqual(($0 as? HostError)?.code, expected) }
    }

    // Failure: a genuine RS256 signature authorizes a wrong nonce/audience, stale token, ambiguous kid, or altered payload.
    func testRS256IdentityRequiresSignedCurrentUnambiguousClaims() throws {
        let attributes: [String: Any] = [kSecAttrKeyType as String: kSecAttrKeyTypeRSA, kSecAttrKeySizeInBits as String: 2048,
            kSecPrivateKeyAttrs as String: [kSecAttrIsPermanent as String: false]]
        var error: Unmanaged<CFError>?
        let fixtureKey = try XCTUnwrap(SecKeyCreateRandomKey(attributes as CFDictionary, &error))
        let publicKey = try XCTUnwrap(SecKeyCopyPublicKey(fixtureKey))
        let representation = try XCTUnwrap(SecKeyCopyExternalRepresentation(publicKey, &error)) as Data
        // Read the platform-generated PKCS#1 public fixture, independent of the verifier's encoder.
        let numbers = try rsaNumbers(representation)
        let key: ExactJSON = .object(["kty": .string("RSA"), "kid": .string("fixture-key"), "use": .string("sig"),
            "n": .string(b64(numbers.0)), "e": .string(b64(numbers.1))])
        let jwks: ExactJSON = .object(["keys": .array([key])])
        let input = message("RS256")
        let signature = try XCTUnwrap(SecKeyCreateSignature(fixtureKey, .rsaSignatureMessagePKCS1v15SHA256, Data(input.utf8) as CFData, &error)) as Data
        let token = input + "." + b64(signature)
        let identity = try ChatGPTIdentityVerifier.verify(idToken: token, clientID: "oaiapp_fixture", nonce: "fixture-nonce", discovery: discovery("RS256"), jwks: jwks, now: now)
        XCTAssertEqual(identity.subject, "fixture-subject"); XCTAssertEqual(identity.email, "fixture@example.invalid")
        reject { _ = try ChatGPTIdentityVerifier.verify(idToken: token, clientID: "oaiapp_fixture", nonce: "different", discovery: discovery("RS256"), jwks: jwks, now: now) }
        reject { _ = try ChatGPTIdentityVerifier.verify(idToken: token, clientID: "oaiapp_other", nonce: "fixture-nonce", discovery: discovery("RS256"), jwks: jwks, now: now) }
        reject { _ = try ChatGPTIdentityVerifier.verify(idToken: token, clientID: "oaiapp_fixture", nonce: "fixture-nonce", discovery: discovery("RS256"), jwks: jwks, now: Date(timeIntervalSince1970: 150)) }
        reject { _ = try ChatGPTIdentityVerifier.verify(idToken: token, clientID: "oaiapp_fixture", nonce: "fixture-nonce", discovery: discovery("RS256"), jwks: .object(["keys": .array([key, key])]), now: now) }
        var forged = claims; forged["sub"] = .string("forged")
        let header = token.split(separator: ".")[0]
        reject { _ = try ChatGPTIdentityVerifier.verify(idToken: String(header) + "." + b64(forged.data) + "." + b64(signature), clientID: "oaiapp_fixture", nonce: "fixture-nonce", discovery: discovery("RS256"), jwks: jwks, now: now) }
    }

    // Failure: JOSE's raw ES256 signature is treated as DER or a returning account is replaced by a different signed subject.
    func testES256UsesP256RawSignatureAndKeepsReturningSubject() throws {
        let fixtureKey = try P256.Signing.PrivateKey(rawRepresentation: Data(repeating: 0, count: 31) + Data([1]))
        let publicBytes = fixtureKey.publicKey.x963Representation
        let key: ExactJSON = .object(["kty": .string("EC"), "crv": .string("P-256"), "kid": .string("fixture-key"),
            "x": .string(b64(publicBytes.subdata(in: 1..<33))), "y": .string(b64(publicBytes.subdata(in: 33..<65)))])
        let jwks: ExactJSON = .object(["keys": .array([key])])
        let input = message("ES256"), signature = try fixtureKey.signature(for: Data(input.utf8))
        let token = input + "." + b64(signature.rawRepresentation)
        XCTAssertEqual(try ChatGPTIdentityVerifier.verify(idToken: token, clientID: "oaiapp_fixture", nonce: nil, expectedSubject: "fixture-subject", discovery: discovery("ES256"), jwks: jwks, now: now).subject, "fixture-subject")
        reject("chatgpt_identity_mismatch") { _ = try ChatGPTIdentityVerifier.verify(idToken: token, clientID: "oaiapp_fixture", nonce: nil, expectedSubject: "different-subject", discovery: discovery("ES256"), jwks: jwks, now: now) }
        reject { _ = try ChatGPTIdentityVerifier.verify(idToken: input + "." + b64(signature.derRepresentation), clientID: "oaiapp_fixture", nonce: nil, discovery: discovery("ES256"), jwks: jwks, now: now) }
    }

    private func rsaNumbers(_ data: Data) throws -> (Data, Data) {
        let bytes = Array(data); var index = 0
        func length() throws -> Int {
            guard index < bytes.count else { throw HostError("fixture_invalid") }
            let first = bytes[index]; index += 1
            if first < 128 { return Int(first) }
            let count = Int(first & 127); guard (1...4).contains(count), index + count <= bytes.count else { throw HostError("fixture_invalid") }
            var value = 0; for _ in 0..<count { value = value * 256 + Int(bytes[index]); index += 1 }; return value
        }
        guard bytes.first == 0x30 else { throw HostError("fixture_invalid") }; index += 1; _ = try length()
        func integer() throws -> Data {
            guard index < bytes.count, bytes[index] == 2 else { throw HostError("fixture_invalid") }; index += 1
            let count = try length(); guard index + count <= bytes.count else { throw HostError("fixture_invalid") }
            let start = index; index += count
            var result = Data(bytes[start..<index]); if result.first == 0 { result.removeFirst() }; return result
        }
        return (try integer(), try integer())
    }
}
