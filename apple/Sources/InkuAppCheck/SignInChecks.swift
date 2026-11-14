import Foundation
import InkuCore
import InkuHost
import InkuUI

/// Sign in with ChatGPT step 1. Failure: the Swift host asked core in another shape than the shared rows, kept
/// appending the ChatGPT connection after the other services, or named it with its own words.
func runSignInChecks(casesURL: URL) throws {
    let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: casesURL)) as? [String: Any]
    guard let cases = fixture?["cases"] as? [[String: Any]], cases.count == 49 else {
        throw CheckFailure.message("Shared sign-in cases unavailable")
    }
    // Each row goes through the binding the app uses, and the whole answer is compared.
    for row in cases {
        guard let name = row["name"] as? String, let request = row["request"] as? [String: Any],
              let answer = row["answer"] as? NSDictionary else { throw CheckFailure.message("Shared sign-in case malformed") }
        let output = InkuCore.modelCatalog(try JSONSerialization.data(withJSONObject: request))
        guard let actual = try JSONSerialization.jsonObject(with: output) as? NSDictionary, actual == answer else {
            throw CheckFailure.message("Sign-in case \(name): \(String(decoding: output, as: UTF8.self))")
        }
    }

    // The host's own request: the sign-in connection goes before every service, the others keep their order.
    var plan = ProviderSettings.personalPlan
    plan.models = [.init(id: "gpt-6.1-sol", label: "GPT-6.1-Sol")]
    let ollama = ProviderSettings(id: "ollama", kind: .openAICompatible, baseURL: URL(string: "http://127.0.0.1:11434/v1")!,
                                  requiresAPIKey: false, label: "Ollama")
    let anthropic = ProviderSettings(id: "anthropic", kind: .anthropic, baseURL: URL(string: "https://api.anthropic.com")!,
                                     label: "Claude API")
    guard ProviderCoreSettings.orderedBySignIn([ollama, anthropic, plan]).map(\.id) == ["chatgpt", "ollama", "anthropic"],
          ProviderCoreSettings.orderedBySignIn([anthropic, plan, ollama]).map(\.id) == ["chatgpt", "anthropic", "ollama"],
          ProviderCoreSettings.orderedBySignIn([anthropic, ollama]).map(\.id) == ["anthropic", "ollama"] else {
        throw CheckFailure.message("The Sign in with ChatGPT connection is not first, or another service moved")
    }
    guard ProviderCoreSettings.signInService("chatgpt", language: "ja")?["label"] as? String == "ChatGPT でサインイン",
          ProviderCoreSettings.signInService("chatgpt", language: "en")?["label"] as? String == "Sign in with ChatGPT",
          ProviderCoreSettings.signInService("chatgpt", language: "fr")?["label"] as? String == "Sign in with ChatGPT",
          ProviderCoreSettings.signInService("chatgpt", language: "ja")?["abbreviation"] as? String == "SIWC" else {
        throw CheckFailure.message("The Sign in with ChatGPT names differ from core's descriptor")
    }
    try runSignInStep2HostChecks(cases: cases)
    print("Sign in with ChatGPT passed: \(cases.count) shared rows through the Swift binding; connection first in 3 orders; ja/en names and SIWC; the connection view and publication draft from the host's own requests. No provider calls.")
}

/// Step 2. Failure: the Swift host built its connection or draft request in another shape than core reads, so the page
/// lost the reopen and pending rows, the sign-out confirmation, or the Web's draft rules and save body.
func runSignInStep2HostChecks(cases: [[String: Any]]) throws {
    let profile = ChatGPTPlanProfile(id: "profile-a", label: "me@example.com / aaaa1111", email: nil, clientID: "client-a",
                                     state: "connected", generation: 1, scopes: [], expiresAt: Date())
    let state = ChatGPTPlanState(enabled: true, activeProfileID: "profile-a", profiles: [profile],
                                 pendingRegistrations: ["pending-b"], pendingClientIDs: ["pending-b": "client-b"])
    guard let waiting = SignInConnectionView.make(state: state, busy: true, attempt: .init(active: true, canReopen: true),
                                                  code: nil, lastOperation: nil, revocationConfirmed: nil),
          waiting.actions.map(\.name) == ["sign_in", "check_connection", "manage_usage", "reopen_sign_in", "cancel"],
          waiting.action("sign_in")?.enabled == false, waiting.action("cancel")?.enabled == true,
          waiting.action("manage_usage")?.url?.absoluteString == "https://chatgpt.com/settings/usage",
          waiting.pending.map(\.clientID) == ["client-b"],
          waiting.profiles.first?.status == "chatgpt_scope_required", waiting.profiles.first?.active == true,
          waiting.profiles.first?.actions.first(where: { $0.name == "sign_out" })?.confirm == true,
          waiting.status == nil, !waiting.guide else {
        throw CheckFailure.message("Connection view from the host's request differs from core's Web rules")
    }
    guard let signedOut = SignInConnectionView.make(state: state, busy: false, attempt: .init(), code: nil,
                                                    lastOperation: "sign_out", revocationConfirmed: false),
          signedOut.status == "chatgpt_revocation_unconfirmed", signedOut.action("reopen_sign_in") == nil,
          SignInConnectionView.make(state: state, busy: false, attempt: .init(active: true, canReopen: false), code: "chatgpt_quota",
                                    lastOperation: nil, revocationConfirmed: nil)?.action("reopen_sign_in") == nil,
          SignInConnectionView.make(state: nil, busy: false, attempt: .init(), code: nil, lastOperation: nil,
                                    revocationConfirmed: nil)?.profiles.isEmpty == true else {
        throw CheckFailure.message("Connection view lost the revocation code or reopened without a page")
    }

    guard let opened = cases.first(where: { $0["name"] as? String == "draft: opened as published" }),
          let source = (opened["request"] as? [String: Any])?["publication"] else {
        throw CheckFailure.message("Shared draft row unavailable")
    }
    let publication = ChatGPTPlanPublication(profileID: "profile-aaaa1111", generation: 3, models: [], published: [],
                                             coreAnswer: try JSONSerialization.data(withJSONObject: source))
    guard var draft = SignInPublicationDraft(publication: publication), !draft.dirty, draft.canSave,
          draft.savedModels == ["gpt-6.1-sol", "gpt-6-luna"] else {
        throw CheckFailure.message("Draft opened differently from the publication")
    }
    draft.togglePurpose("gpt-6-luna", purpose: "llm")
    guard draft.row("gpt-6-luna")?.selected == false, draft.dirty, !draft.canRefresh, draft.savedModels == ["gpt-6.1-sol"] else {
        throw CheckFailure.message("Removing the last purpose did not unpublish the model")
    }
    draft.togglePurpose("gpt-6-luna", purpose: "vision")
    guard draft.row("gpt-6-luna")?.purposes == [] else { throw CheckFailure.message("A purpose not answered was pressed") }
    draft.select(["gpt-6.1-sol", "gpt-6-luna", "gpt-5-old", "gpt-6.1-terra"], selected: true)
    guard draft.savedModels == ["gpt-6.1-sol", "gpt-6.1-terra"],
          draft.savedPurposes == ["gpt-6.1-sol": ["llm", "vision"], "gpt-6-luna": [], "gpt-5-old": ["llm", "vision"],
                                  "gpt-6.1-terra": ["llm", "vision"]] else {
        throw CheckFailure.message("Select all or the save body differs from the Web")
    }
}
