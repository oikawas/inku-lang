import Foundation
import InkuCore

/// Shared ChatGPT decisions. Secrets remain in the host; callers supply only the fields needed by each decision.
public enum ChatGPTPolicy {
    public static func evaluate(_ request: ExactJSON) throws -> ExactJSON {
        try ExactJSON(data: InkuCore.modelCatalog(request.data))
    }
    static func result(_ action: String, _ fields: [String: ExactJSON] = [:]) throws -> ExactJSON {
        var request = fields
        request["action"] = .string(action)
        request["schema"] = .string("inku.model-catalog-request.v1")
        return try evaluate(.object(request))
    }
    static func call(_ action: String, _ fields: [String: ExactJSON] = [:]) throws -> ExactJSON {
        let result = try result(action, fields)
        if let code = result["error"].string { throw HostError(code) }
        return result
    }
    static func number(_ value: TimeInterval) -> ExactJSON { .number(String(value)) }
    static func string(_ value: String?) -> ExactJSON { value.map(ExactJSON.string) ?? .null }
    static func profile(_ profile: ChatGPTStoredProfile) -> ExactJSON {
        let models = (profile.models ?? []).map { ExactJSON.object(["id": .string($0.id), "label": .string($0.label)]) }
        return .object(["id": .string(profile.id), "issuer": .string(profile.issuer), "sub": .string(profile.subject),
            "client_id": .string(profile.clientID), "generation": .number(String(profile.generation)), "state": .string(profile.state),
            "email": string(profile.email), "scopes": .array(profile.scopes.map(ExactJSON.string)),
            "access_token": string(profile.accessToken), "refresh_token": string(profile.refreshToken), "id_token": string(profile.idToken),
            "refresh_owner": .string("runtime"), "expires_at": number(profile.expiresAt.timeIntervalSince1970),
            "earliest_refresh_at": number(profile.earliestRefreshAt.timeIntervalSince1970),
            "published_models": .array((profile.publishedModels ?? []).map(ExactJSON.string)),
            "model_purposes": .object((profile.modelPurposes ?? [:]).mapValues { .array($0.map(ExactJSON.string)) }),
            "catalog": .object(["models": .array(models), "expires_at": number(profile.modelsExpireAt?.timeIntervalSince1970 ?? 0)])])
    }
    static func assessments() throws -> ExactJSON {
        let root = try ExactJSON(data: SharedModelCatalog.catalogData)
        let rows = root["providers"]["chatgpt"]["models"].array ?? []
        var result: [String: ExactJSON] = [:]
        for row in rows {
            if let id = row["id"].string { result[id] = try call("internal", ["model": row])["model"] }
        }
        return .object(result)
    }
    /// Python's JSON encoder retains arbitrary integers and writes decoded floating-point numbers in shortest form.
    /// Scan raw JSON so object member order is not lost when the email claim is an object.
    static func pythonJSONNumbers(_ raw: String) -> String {
        let bytes = Array(raw.utf8); var out = "", i = 0, quoted = false, escaped = false
        while i < bytes.count {
            let c = bytes[i]
            if quoted {
                if c >= 128 {
                    let start = i
                    while i < bytes.count && bytes[i] >= 128 { i += 1 }
                    out += String(decoding: bytes[start..<i], as: UTF8.self); continue
                }
                out.append(Character(UnicodeScalar(c)))
                if escaped { escaped = false } else if c == 92 { escaped = true } else if c == 34 { quoted = false }
                i += 1; continue
            }
            if c == 34 { quoted = true; out.append("\""); i += 1; continue }
            if c == 45 || (48...57).contains(c) {
                let start = i
                while i < bytes.count && ((48...57).contains(bytes[i]) || [45, 43, 46, 69, 101].contains(bytes[i])) { i += 1 }
                let token = String(decoding: bytes[start..<i], as: UTF8.self)
                if token.contains(".") || token.contains("e") || token.contains("E"), let value = Double(token), value.isFinite {
                    out += String(value)
                } else { out += token }
                continue
            }
            let start = i
            while i < bytes.count && bytes[i] >= 128 { i += 1 }
            if i > start { out += String(decoding: bytes[start..<i], as: UTF8.self); continue }
            out.append(Character(UnicodeScalar(c))); i += 1
        }
        return out
    }
}
