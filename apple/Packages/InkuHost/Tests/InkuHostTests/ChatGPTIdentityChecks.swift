import CryptoKit
import Foundation
import Security
import XCTest
@testable import InkuHost

/// The host's part of the core `verify` todo: the signature alone (the core chose the key and checks the claims).
final class ChatGPTIdentityChecks: XCTestCase, @unchecked Sendable {
    private func b64(_ bytes: Data) -> String {
        bytes.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
    private func input(_ algorithm: String, subject: String = "fixture-subject") -> String {
        b64(ExactJSON.object(["alg": .string(algorithm), "kid": .string("fixture-key")]).data) + "."
            + b64(ExactJSON.object(["sub": .string(subject)]).data)
    }

    // Failure: a genuine RS256 signature is accepted over an altered payload, or not accepted over its own.
    func testRS256SignatureCoversTheSigningInput() throws {
        let attributes: [String: Any] = [kSecAttrKeyType as String: kSecAttrKeyTypeRSA, kSecAttrKeySizeInBits as String: 2048,
            kSecPrivateKeyAttrs as String: [kSecAttrIsPermanent as String: false]]
        var error: Unmanaged<CFError>?
        let fixtureKey = try XCTUnwrap(SecKeyCreateRandomKey(attributes as CFDictionary, &error))
        let publicKey = try XCTUnwrap(SecKeyCopyPublicKey(fixtureKey))
        let representation = try XCTUnwrap(SecKeyCopyExternalRepresentation(publicKey, &error)) as Data
        // Read the platform-generated PKCS#1 public fixture, independent of the verifier's encoder.
        let numbers = try rsaNumbers(representation)
        let key: ExactJSON = .object(["kty": .string("RSA"), "n": .string(b64(numbers.0)), "e": .string(b64(numbers.1))])
        let signed = input("RS256")
        let signature = b64(try XCTUnwrap(SecKeyCreateSignature(fixtureKey, .rsaSignatureMessagePKCS1v15SHA256, Data(signed.utf8) as CFData, &error)) as Data)
        XCTAssertTrue(ChatGPTIdentityVerifier.signatureValid(algorithm: "RS256", key: key, signingInput: signed, signature: signature))
        XCTAssertFalse(ChatGPTIdentityVerifier.signatureValid(algorithm: "RS256", key: key, signingInput: input("RS256", subject: "forged"), signature: signature))
    }

    // Failure: JOSE's raw ES256 signature is treated as DER.
    func testES256UsesP256RawSignature() throws {
        let fixtureKey = try P256.Signing.PrivateKey(rawRepresentation: Data(repeating: 0, count: 31) + Data([1]))
        let publicBytes = fixtureKey.publicKey.x963Representation
        let key: ExactJSON = .object(["kty": .string("EC"), "crv": .string("P-256"),
            "x": .string(b64(publicBytes.subdata(in: 1..<33))), "y": .string(b64(publicBytes.subdata(in: 33..<65)))])
        let signed = input("ES256"), signature = try fixtureKey.signature(for: Data(signed.utf8))
        XCTAssertTrue(ChatGPTIdentityVerifier.signatureValid(algorithm: "ES256", key: key, signingInput: signed, signature: b64(signature.rawRepresentation)))
        XCTAssertFalse(ChatGPTIdentityVerifier.signatureValid(algorithm: "ES256", key: key, signingInput: signed, signature: b64(signature.derRepresentation)))
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
