import Foundation
import InkuHost
import Observation

@MainActor @Observable
public final class ChatGPTPlanSettingsModel {
    public private(set) var state: ChatGPTPlanState?
    public private(set) var busy = false
    public private(set) var authorizing = false
    /// The last failure code (`chatgpt_*`, worded by `ChatGPTStatusCopy`), as the Web keeps `code`.
    public private(set) var code: String?
    /// The last sign-out or deletion and whether the provider confirmed the revocation.
    public private(set) var lastOperation: String?
    public private(set) var revocationConfirmed: Bool?
    @ObservationIgnored private var attemptID: String?
    @ObservationIgnored private var authorizationURL: URL?
    @ObservationIgnored private var operation: Task<Void, Never>?
    public init() {}

    /// Core `sign_in_connection_view`: the codes and actions the page shows (ChatGPTSettings.svelte).
    public func view(canReopen: Bool) -> SignInConnectionView? {
        SignInConnectionView.make(state: state, busy: busy, attempt: .init(active: authorizing, canReopen: canReopen && authorizationURL != nil),
                                  code: code, lastOperation: lastOperation, revocationConfirmed: revocationConfirmed)
    }

    /// The active profile is connected with the plan scope (core `guide`). Models are chosen in model settings,
    /// which the tab then opens.
    public var connected: Bool { view(canReopen: false)?.guide ?? false }

    /// Every connection change also refreshes the ChatGPT models the drawing pickers offer (Web `changed`).
    public func load(app: AppModel) async {
        do { state = try await app.personalPlanRuntime().state() }
        catch { report(error) }
        await app.synchronizePersonalPlanModels()
    }
    public func checkConnection(app: AppModel) async {
        await perform(app: app) {}
    }
    /// The page has no switch, as the Web has none (the author, step 2): a sign-in turns the connection on and
    /// lists the reserved `chatgpt` service for the pickers.
    private func enable(app: AppModel) async throws {
        let runtime = try app.personalPlanRuntime()
        if try await runtime.state().enabled == false { try await runtime.setEnabled(true) }
        var settings = await app.hostSettings()
        if !settings.providers.contains(where: { $0.kind == .chatGPTPlan }) {
            settings.providers = ProviderCoreSettings.orderedBySignIn(settings.providers + [.personalPlan])
            try await app.updateHostSettings(settings)
        }
    }
    public func authorize(profileID: String? = nil, consent: Bool = false, app: AppModel,
                          openURL: @escaping @MainActor (URL) -> Void,
                          closeLogin: @escaping @MainActor () -> Void = {}) async {
        guard !busy else { return }
        busy = true; authorizing = true; clear()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                try await self.enable(app: app)
                let runtime = try app.personalPlanRuntime()
                let attempt = try await runtime.beginAuthorization(profileID: profileID, consent: consent,
                                                                    language: app.display.preferences.language)
                self.attemptID = attempt.id
                try Task.checkCancellation()
                self.authorizationURL = attempt.authorizationURL
                openURL(attempt.authorizationURL)
                // iOS: the login sheet stays open over the app until the callback reaches the loopback listener.
                do { _ = try await runtime.finishAuthorization(attempt.id) } catch { closeLogin(); throw error }
                closeLogin()
                try Task.checkCancellation()
                // A connected profile has a fresh catalog before the pickers are synchronized.
                // Catalog failure does not undo the successful authorization.
                do { _ = try await runtime.refreshPublication() }
                catch { if !Task.isCancelled { self.report(error) } }
            } catch { if !Task.isCancelled { self.report(error) } }
            if let id = self.attemptID { try? await app.personalPlanRuntime().cancelAuthorization(id) }
            self.attemptID = nil; self.authorizationURL = nil
            await self.load(app: app)
        }
        operation = task; await task.value
        operation = nil; busy = false; authorizing = false
    }
    /// Core `reopen_sign_in`: the Mac opens the waiting sign-in page in the browser again.
    public func reopen(openURL: @MainActor (URL) -> Void) {
        if let authorizationURL { openURL(authorizationURL) }
    }
    public func cancel(app: AppModel) async {
        operation?.cancel()
        if let id = attemptID { try? await app.personalPlanRuntime().cancelAuthorization(id) }
        if let operation { await operation.value }
    }
    public func selectProfile(_ id: String, app: AppModel) async {
        await perform(app: app) { try await app.personalPlanRuntime().selectProfile(id) }
    }
    public func signOut(_ id: String, app: AppModel) async {
        await perform(app: app) {
            let confirmed = try await app.personalPlanRuntime().signOut(id)
            self.lastOperation = "sign_out"; self.revocationConfirmed = confirmed
        }
    }
    public func deleteProfile(_ id: String, app: AppModel) async {
        await perform(app: app) {
            let confirmed = try await app.personalPlanRuntime().deleteProfile(id)
            self.lastOperation = "delete"; self.revocationConfirmed = confirmed
        }
    }
    public func retryQuota(_ id: String, app: AppModel) async {
        await perform(app: app) { try await app.personalPlanRuntime().retryQuota(id) }
    }
    private func perform(app: AppModel, operation: @escaping @MainActor () async throws -> Void) async {
        guard !busy else { return }; busy = true; clear()
        do { try await operation() } catch { report(error) }
        await load(app: app); busy = false
    }
    private func clear() { code = nil; lastOperation = nil; revocationConfirmed = nil }
    /// Web ChatGPTSettings / model-administration keep the failure's code and word it with `chatgptStatus(code)`.
    private func report(_ error: Error) {
        code = ChatGPTPlanRuntime.diagnostic(error).code
    }
}
