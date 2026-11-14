import Foundation
import InkuHost

/// Core `sign_in_connection_view`: what the connection settings show, as the Web shows them. One connection per
/// host (the author, 2026-11-14): its state, the one action that state needs, and signing out apart from it. The
/// host keeps the wording (`ChatGPTStatusCopy`, Localizable) and the windows; core answers the codes and actions.
public struct SignInConnectionView: Equatable, Sendable {
    public struct Action: Equatable, Sendable {
        public let name: String
        public let enabled: Bool
        /// The host asks before running it (sign out).
        public let confirm: Bool
    }
    /// The state's code (`chatgpt_connected`, `chatgpt_signed_out`, `chatgpt_account_changed`, a failure, ...),
    /// shown every time from this answer, never carried over from an earlier action.
    public let status: String?
    /// The account's label (`<email> / <client id end>`), or nil before a registration.
    public let label: String?
    /// The one action the state needs: `sign_in`, `grant_plan`, `retry` or `new_sign_in`.
    public let primary: Action?
    /// While signing in: `cancel`, and `reopen_sign_in` where the page can be opened again.
    public let attemptActions: [Action]
    /// Signing out, shown apart from the state's action.
    public let signOut: Action?
    /// The guidance shown with signing out (`chatgpt_disconnect_in_settings`).
    public let notice: String?
    public let manageUsage: URL?
    /// Connected with plan use allowed: the guide to model settings is shown.
    public let guide: Bool

    public struct Attempt: Sendable {
        public var active = false
        public var canReopen = false
        public init(active: Bool = false, canReopen: Bool = false) { self.active = active; self.canReopen = canReopen }
    }

    /// `lastOperation` is `sign_out` after one finished, with whether the provider confirmed the revocation.
    public static func make(state: ChatGPTPlanState?, busy: Bool, attempt: Attempt, code: String?,
                            lastOperation: String?, revocationConfirmed: Bool?) -> SignInConnectionView? {
        var connection: [String: Any] = ["profiles": [Any](), "pending_registrations": [Any]()]
        if let state {
            connection["active_profile_id"] = state.activeProfileID ?? NSNull()
            connection["profiles"] = state.profiles.map { ["id": $0.id, "label": $0.label, "state": $0.state, "scopes": $0.scopes] }
            connection["pending_registrations"] = state.pendingRegistrations.map { id -> [String: Any] in
                var row: [String: Any] = ["id": id]
                if let client = state.pendingClientIDs[id] { row["client_id"] = client }
                return row
            }
        }
        var request: [String: Any] = ["service": ProviderSettings.personalPlan.id, "connection": connection, "busy": busy,
            "attempt": ["active": attempt.active, "can_reopen": attempt.active && attempt.canReopen, "helper": false]]
        if let code { request["code"] = code }
        if let lastOperation { request["last_operation"] = lastOperation }
        if let revocationConfirmed { request["revocation_confirmed"] = revocationConfirmed }
        guard let answer = try? ProviderCoreSettings.call("sign_in_connection_view", request),
              answer["outcome"] as? String == "ok" else { return nil }
        return SignInConnectionView(answer)
    }

    init(_ answer: [String: Any]) {
        func action(_ value: Any?) -> Action? {
            guard let row = value as? [String: Any], let name = row["action"] as? String else { return nil }
            return Action(name: name, enabled: row["enabled"] as? Bool ?? false, confirm: row["confirm"] as? Bool ?? false)
        }
        status = answer["status"] as? String
        label = answer["label"] as? String
        primary = action(answer["primary"])
        attemptActions = (answer["attempt_actions"] as? [Any] ?? []).compactMap(action)
        signOut = action(answer["sign_out"])
        notice = answer["notice"] as? String
        manageUsage = ((answer["manage_usage"] as? [String: Any])?["url"] as? String).flatMap(URL.init(string:))
        guide = answer["guide"] as? Bool ?? false
    }
}

/// Core `sign_in_publication_draft`: the editing of the models a sign-in connection publishes, as the Web edits them.
/// The publication rows (with their assessments) come from core `chatgpt_publication` only.
public struct SignInPublicationDraft {
    public struct Row: Equatable {
        public let id: String
        public let selected: Bool
        public let canToggle: Bool
        public let purposes: [String]
        public let lockedPurposes: [String]
    }
    private let publication: [String: Any]
    private var draft: [String: Any]?
    public private(set) var rows: [Row] = []
    public private(set) var dirty = false
    public private(set) var canRefresh = true
    public private(set) var canSave = true
    /// The `published_models` (catalog order) and every model's `model_purposes` to save.
    public private(set) var savedModels: [String] = []
    public private(set) var savedPurposes: [String: [String]] = [:]

    public init?(publication: ChatGPTPlanPublication) {
        guard let answer = try? JSONSerialization.jsonObject(with: publication.coreAnswer) as? [String: Any] else { return nil }
        self.publication = answer
        guard apply(nil) else { return nil }
    }

    public func row(_ id: String) -> Row? { rows.first { $0.id == id } }

    public mutating func toggleModel(_ id: String, selected: Bool) {
        apply(["kind": "toggle_model", "id": id, "selected": selected])
    }
    public mutating func togglePurpose(_ id: String, purpose: String) {
        apply(["kind": "toggle_purpose", "id": id, "purpose": purpose])
    }
    /// Select or clear the given models; selecting skips those core cannot publish.
    public mutating func select(_ ids: [String], selected: Bool) {
        apply(["kind": "select_all", "ids": ids, "selected": selected])
    }

    @discardableResult private mutating func apply(_ edit: [String: Any]?) -> Bool {
        var request: [String: Any] = ["service": ProviderSettings.personalPlan.id, "publication": publication, "administrator": false]
        if let draft { request["draft"] = draft }
        if let edit { request["edit"] = edit }
        guard let answer = try? ProviderCoreSettings.call("sign_in_publication_draft", request),
              answer["outcome"] as? String == "ok" else { return false }
        draft = answer["draft"] as? [String: Any]
        rows = (answer["rows"] as? [[String: Any]] ?? []).compactMap { row in
            guard let id = row["id"] as? String else { return nil }
            return Row(id: id, selected: row["selected"] as? Bool ?? false, canToggle: row["can_toggle"] as? Bool ?? false,
                       purposes: row["purposes"] as? [String] ?? [], lockedPurposes: row["locked_purposes"] as? [String] ?? [])
        }
        dirty = answer["dirty"] as? Bool ?? false
        canRefresh = answer["can_refresh"] as? Bool ?? !dirty
        canSave = answer["can_save"] as? Bool ?? true
        let save = answer["save"] as? [String: Any] ?? [:]
        savedModels = save["published_models"] as? [String] ?? []
        savedPurposes = save["model_purposes"] as? [String: [String]] ?? [:]
        return true
    }
}
