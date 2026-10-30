import CryptoKit
import Foundation
import Security

public struct ChatGPTVerifiedIdentity: Sendable, Equatable {
    public let issuer: String
    public let subject: String
    public let email: String?
    public let label: String
}

/// Verifies only supplied discovery/JWKS data; fetching and profile activation belong to the runtime.
public enum ChatGPTIdentityVerifier {
    private static let issuer = ChatGPTEndpoints.issuer

    public static func verify(idToken: String, clientID: String, nonce: String?, expectedSubject: String? = nil,
                              discovery: ExactJSON, jwks: ExactJSON, now: Date = Date()) throws -> ChatGPTVerifiedIdentity {
        do {
            return try verified(idToken: idToken, clientID: clientID, nonce: nonce, expectedSubject: expectedSubject,
                                discovery: discovery, jwks: jwks, now: now)
        } catch is CancellationError { throw CancellationError() }
        catch let error as HostError where error.code == "chatgpt_identity_mismatch" { throw error }
        catch { throw HostError("chatgpt_identity_invalid") }
    }

    private static func verified(idToken: String, clientID: String, nonce: String?, expectedSubject: String?,
                                 discovery: ExactJSON, jwks: ExactJSON, now: Date) throws -> ChatGPTVerifiedIdentity {
        try Task.checkCancellation()
        guard !clientID.isEmpty, clientID != "dynamic_agent_client", clientID.utf8.count <= 1024,
              idToken.utf8.count <= 65_536 else { throw invalid() }
        let parts = idToken.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3 else { throw invalid() }
        let header = try ExactJSON(data: base64URL(String(parts[0])))
        let payloadBytes = try base64URL(String(parts[1]))
        let payload = try ExactJSON(data: payloadBytes)
        let signature = try base64URL(String(parts[2]))
        guard header.object != nil, payload.object != nil else { throw invalid() }
        _ = try ChatGPTPolicy.call("chatgpt_auth_discovery", ["discovery": discovery])
        let selected = try ChatGPTPolicy.call("chatgpt_auth_key", ["header": header, "discovery": discovery, "keys": jwks])
        let key = selected["key"]
        let algorithm = try selected.requiredString("alg")
        let message = Data((String(parts[0]) + "." + String(parts[1])).utf8)
        try verifySignature(signature, message: message, key: key, algorithm: algorithm)
        // Verify the signature first. The shared policy alone checks all claims, including iat, nbf and jti.
        _ = try ChatGPTPolicy.call("chatgpt_auth_claims", ["claims": payload, "client_id": .string(clientID),
            "nonce": ChatGPTPolicy.string(nonce), "now": ChatGPTPolicy.number(now.timeIntervalSince1970)])
        let subject = try payload.requiredString("sub")
        guard subject.utf8.count <= 1024 else { throw invalid() }
        if let expectedSubject {
            _ = try ChatGPTPolicy.call("chatgpt_auth_identity", ["previous": .object(["sub": .string(expectedSubject)]), "sub": .string(subject)])
        }
        try Task.checkCancellation()
        var displayInput: [String: ExactJSON] = ["claims": payload, "client_id": .string(clientID)]
        if let raw = try? ExactJSON.rawMember("email", in: payloadBytes) {
            displayInput["email_json"] = .string(ChatGPTPolicy.pythonJSONNumbers(String(decoding: raw, as: UTF8.self)))
        }
        let display = try ChatGPTPolicy.call("chatgpt_auth_display", displayInput)
        return ChatGPTVerifiedIdentity(issuer: issuer, subject: subject, email: try display.requiredString("email"), label: try display.requiredString("label"))
    }

    private static func verifySignature(_ signature: Data, message: Data, key: ExactJSON, algorithm: String) throws {
        if algorithm == "ES256" {
            guard key["kty"].string == "EC", key["crv"].string == "P-256",
                  let x = key["x"].string, let y = key["y"].string else { throw invalid() }
            let xBytes = try base64URL(x), yBytes = try base64URL(y)
            guard xBytes.count == 32, yBytes.count == 32, signature.count == 64 else { throw invalid() }
            let publicKey = try P256.Signing.PublicKey(x963Representation: Data([4]) + xBytes + yBytes)
            let value = try P256.Signing.ECDSASignature(rawRepresentation: signature)
            guard publicKey.isValidSignature(value, for: message) else { throw invalid() }
        } else {
            guard key["kty"].string == "RSA", let n = key["n"].string, let e = key["e"].string else { throw invalid() }
            let modulus = try base64URL(n), exponent = try base64URL(e)
            guard (256...1024).contains(modulus.count), (1...8).contains(exponent.count),
                  modulus.first != 0, exponent.first != 0, signature.count == modulus.count else { throw invalid() }
            let representation = der(tag: 0x30, bytes: derInteger(modulus) + derInteger(exponent))
            let attributes: [String: Any] = [kSecAttrKeyType as String: kSecAttrKeyTypeRSA,
                kSecAttrKeyClass as String: kSecAttrKeyClassPublic]
            var error: Unmanaged<CFError>?
            defer { if let error { _ = error.takeRetainedValue() } }
            guard let publicKey = SecKeyCreateWithData(representation as CFData, attributes as CFDictionary, &error),
                  SecKeyIsAlgorithmSupported(publicKey, .verify, .rsaSignatureMessagePKCS1v15SHA256),
                  SecKeyVerifySignature(publicKey, .rsaSignatureMessagePKCS1v15SHA256, message as CFData, signature as CFData, &error) else { throw invalid() }
        }
    }

    private static func numericDate(_ value: ExactJSON) -> Double? {
        guard let number = value.number, let date = Double(number), date.isFinite else { return nil }
        return date
    }
    private static func base64URL(_ value: String) throws -> Data {
        guard !value.isEmpty, value.utf8.allSatisfy({ (65...90).contains($0) || (97...122).contains($0) || (48...57).contains($0) || $0 == 45 || $0 == 95 }), value.utf8.count % 4 != 1 else { throw invalid() }
        let padded = value.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/") + String(repeating: "=", count: (4 - value.utf8.count % 4) % 4)
        guard let data = Data(base64Encoded: padded), data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") == value else { throw invalid() }
        return data
    }
    private static func constantTimeEqual(_ lhs: String, _ rhs: String) -> Bool {
        let first = Array(lhs.utf8), second = Array(rhs.utf8)
        guard first.count == second.count else { return false }
        var difference: UInt8 = 0
        for (a, b) in zip(first, second) { difference |= a ^ b }
        return difference == 0
    }
    private static func derInteger(_ value: Data) -> Data {
        der(tag: 0x02, bytes: (value.first! >= 0x80 ? Data([0]) : Data()) + value)
    }
    private static func der(tag: UInt8, bytes: Data) -> Data {
        var length = bytes.count, octets: [UInt8] = []
        while length > 0 { octets.insert(UInt8(length & 255), at: 0); length >>= 8 }
        let prefix = bytes.count < 128 ? Data([tag, UInt8(bytes.count)]) : Data([tag, 0x80 | UInt8(octets.count)] + octets)
        return prefix + bytes
    }
    private static func invalid() -> HostError { HostError("chatgpt_identity_invalid") }
}
