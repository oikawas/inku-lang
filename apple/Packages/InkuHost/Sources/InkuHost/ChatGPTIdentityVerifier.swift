import CryptoKit
import Foundation
import Security

/// The signature over an id token (core `verify`). The core chooses the key and checks the claims; the host only
/// says whether the signature is the key's.
public enum ChatGPTIdentityVerifier {
    /// Core `verify` (Sign in with ChatGPT step 5): whether the signature over `signingInput` is the key's. The key's
    /// shape is still checked here; the core chose the key and checks the claims.
    static func signatureValid(algorithm: String, key: ExactJSON, signingInput: String, signature: String) -> Bool {
        guard let bytes = try? base64URL(signature) else { return false }
        return (try? verifySignature(bytes, message: Data(signingInput.utf8), key: key, algorithm: algorithm)) != nil
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

    private static func base64URL(_ value: String) throws -> Data {
        guard !value.isEmpty, value.utf8.allSatisfy({ (65...90).contains($0) || (97...122).contains($0) || (48...57).contains($0) || $0 == 45 || $0 == 95 }), value.utf8.count % 4 != 1 else { throw invalid() }
        let padded = value.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/") + String(repeating: "=", count: (4 - value.utf8.count % 4) % 4)
        guard let data = Data(base64Encoded: padded), data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") == value else { throw invalid() }
        return data
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
