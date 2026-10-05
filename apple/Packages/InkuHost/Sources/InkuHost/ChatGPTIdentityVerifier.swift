import CryptoKit
import Foundation
import Security

public struct ChatGPTVerifiedIdentity: Sendable, Equatable {
    public let issuer: String
    public let subject: String
    public let email: String?
}

/// Verifies only supplied discovery/JWKS data; fetching and profile activation belong to the runtime.
public enum ChatGPTIdentityVerifier {
    private static let issuer = "https://auth.openai.com"

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
              idToken.utf8.count <= 65_536, discovery["issuer"].string == issuer,
              let uri = discovery["jwks_uri"].string, let url = URLComponents(string: uri),
              url.scheme == "https", url.host == "auth.openai.com", url.user == nil, url.password == nil,
              url.port == nil, url.fragment == nil else { throw invalid() }
        let parts = idToken.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3 else { throw invalid() }
        let header = try ExactJSON(data: base64URL(String(parts[0])))
        let payload = try ExactJSON(data: base64URL(String(parts[1])))
        let signature = try base64URL(String(parts[2]))
        guard header.object != nil, payload.object != nil,
              let algorithm = header["alg"].string, ["RS256", "ES256"].contains(algorithm),
              let keyID = header["kid"].string, !keyID.isEmpty, keyID.utf8.count <= 256,
              header["crit"] == .null || header["crit"].array == [], header["b64"] == .null || header["b64"].bool == true else { throw invalid() }
        let supported: [ExactJSON]
        if discovery.object?["id_token_signing_alg_values_supported"] == nil { supported = [.string("RS256")] }
        else if let algorithms = discovery["id_token_signing_alg_values_supported"].array { supported = algorithms }
        else { throw invalid() }
        guard supported.allSatisfy({ $0.string != nil }), supported.contains(.string(algorithm)),
              let keys = jwks["keys"].array, keys.count <= 128 else { throw invalid() }
        let matching = keys.filter { $0["kid"].string == keyID && ($0["use"] == .null || $0["use"].string == "sig") }
        guard matching.count == 1 else { throw invalid() }
        let key = matching[0]
        guard key["alg"] == .null || key["alg"].string == algorithm else { throw invalid() }
        if key["key_ops"] != .null {
            guard let operations = key["key_ops"].array, operations.contains(.string("verify")),
                  operations.allSatisfy({ $0.string != nil }) else { throw invalid() }
        }
        let message = Data((String(parts[0]) + "." + String(parts[1])).utf8)
        try verifySignature(signature, message: message, key: key, algorithm: algorithm)
        // Claims become identity only after verification against the discovery-bound key.
        guard payload["iss"].string == issuer, let subject = payload["sub"].string, !subject.isEmpty,
              subject.utf8.count <= 1024, let expiry = numericDate(payload["exp"]),
              now.timeIntervalSince1970.isFinite, expiry > now.timeIntervalSince1970 else { throw invalid() }
        if payload["nbf"] != .null {
            guard let validFrom = numericDate(payload["nbf"]), validFrom <= now.timeIntervalSince1970 else { throw invalid() }
        }
        if payload["iat"] != .null {
            guard let issued = numericDate(payload["iat"]), issued <= now.timeIntervalSince1970 else { throw invalid() }
        }
        let audiences: [String]
        if let audience = payload["aud"].string { audiences = [audience] }
        else if let array = payload["aud"].array, !array.isEmpty, array.allSatisfy({ $0.string != nil }) { audiences = array.compactMap(\.string) }
        else { throw invalid() }
        guard audiences.contains(clientID), audiences.allSatisfy({ !$0.isEmpty }),
              audiences.count == 1 || payload["azp"].string == clientID else { throw invalid() }
        if let nonce {
            guard !nonce.isEmpty, let received = payload["nonce"].string, constantTimeEqual(received, nonce) else { throw invalid() }
        }
        if let expectedSubject, !constantTimeEqual(subject, expectedSubject) { throw HostError("chatgpt_identity_mismatch") }
        try Task.checkCancellation()
        return ChatGPTVerifiedIdentity(issuer: issuer, subject: subject, email: payload["email"].string)
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
