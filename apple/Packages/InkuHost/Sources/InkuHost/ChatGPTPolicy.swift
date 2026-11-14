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
        if action.hasPrefix("sign_in_") { request["service"] = .string("chatgpt") }
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
        var value: [String: ExactJSON] = ["id": .string(profile.id), "issuer": .string(profile.issuer), "sub": .string(profile.subject),
            "client_id": .string(profile.clientID), "label": .string(profile.label),
            "generation": .number(String(profile.generation)), "state": .string(profile.state),
            "email": string(profile.email), "scopes": .array(profile.scopes.map(ExactJSON.string)),
            "access_token": string(profile.accessToken), "refresh_token": string(profile.refreshToken), "id_token": string(profile.idToken),
            "refresh_owner": .string("runtime"), "expires_at": number(profile.expiresAt.timeIntervalSince1970),
            "earliest_refresh_at": number(profile.earliestRefreshAt.timeIntervalSince1970),
            "published_models": .array((profile.publishedModels ?? []).map(ExactJSON.string)),
            "model_purposes": .object((profile.modelPurposes ?? [:]).mapValues { .array($0.map(ExactJSON.string)) }),
            "catalog": .object(["models": .array(models), "expires_at": number(profile.modelsExpireAt?.timeIntervalSince1970 ?? 0)])]
        // Members only core reads go back as core wrote them.
        for (key, member) in (profile.coreExtras.flatMap { try? ExactJSON(data: Data($0.utf8)) }?.object ?? [:]) where value[key] == nil || key == "refresh_owner" {
            value[key] = member
        }
        return .object(value)
    }

    private static let profileMembers: Set<String> = ["id", "issuer", "sub", "client_id", "label", "generation", "state", "email",
        "scopes", "access_token", "refresh_token", "id_token", "expires_at", "earliest_refresh_at", "published_models",
        "model_purposes", "catalog"]

    /// A registration as core wrote it (a sign-in flow's `write`), in the vault's form. Times are seconds in both.
    static func storedProfile(_ value: ExactJSON) throws -> ChatGPTStoredProfile {
        func time(_ member: ExactJSON) throws -> Date {
            guard let seconds = member.number.flatMap(Double.init), seconds.isFinite else { throw HostError("chatgpt_identity_invalid") }
            return Date(timeIntervalSince1970: seconds)
        }
        guard let generation = value["generation"].number.flatMap(Int64.init) else { throw HostError("chatgpt_identity_invalid") }
        let catalog = value["catalog"]
        let listed = try catalog["models"].array?.map { ChatGPTPlanModel(id: try $0.requiredString("id"), label: try $0.requiredString("label")) }
        let listExpiry = catalog["expires_at"].number.flatMap(Double.init) ?? 0
        let hasCatalog = catalog.object != nil && !(listExpiry == 0 && (listed ?? []).isEmpty)
        let extras = (value.object ?? [:]).filter { !profileMembers.contains($0.key) }
        return ChatGPTStoredProfile(id: try value.requiredString("id"), issuer: try value.requiredString("issuer"),
            subject: try value.requiredString("sub"), email: value["email"].string, clientID: try value.requiredString("client_id"),
            label: try value.requiredString("label"), state: try value.requiredString("state"), generation: generation,
            accessToken: value["access_token"].string, refreshToken: value["refresh_token"].string, idToken: value["id_token"].string,
            scopes: value["scopes"].array?.compactMap(\.string) ?? [], expiresAt: try time(value["expires_at"]),
            earliestRefreshAt: try time(value["earliest_refresh_at"]),
            models: hasCatalog ? listed : nil, modelsExpireAt: hasCatalog ? Date(timeIntervalSince1970: listExpiry) : nil,
            publishedModels: value["published_models"].array?.compactMap(\.string),
            modelPurposes: value["model_purposes"].object?.mapValues { $0.array?.compactMap(\.string) ?? [] },
            coreExtras: extras.isEmpty ? nil : ExactJSON.object(extras).text)
    }

    /// The vault in core's form (`profiles`, `registrations_pending`, `active`) for a sign-in flow's `read`.
    static func store(_ value: ChatGPTVaultState) -> ExactJSON {
        .object(["profiles": .object(value.profiles.mapValues(profile)),
                 "registrations_pending": .object(value.pendingRegistrations.mapValues { .object(["client_id": .string($0)]) }),
                 "active": string(value.activeProfileID)])
    }

    /// A sign-in flow's `write`: core's registrations replace the vault's; the host's own members stay.
    static func adopt(_ store: ExactJSON, into value: inout ChatGPTVaultState) throws {
        value.profiles = try (store["profiles"].object ?? [:]).mapValues(storedProfile)
        value.pendingRegistrations = try (store["registrations_pending"].object ?? [:]).mapValues { try $0.requiredString("client_id") }
        value.activeProfileID = store["active"].string
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
}
