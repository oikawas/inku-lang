import Foundation
import InkuHost
import Observation

@MainActor @Observable
public final class ChatGPTPlanSettingsModel {
    public private(set) var state: ChatGPTPlanState?
    public private(set) var models: [ChatGPTPlanModel] = []
    public private(set) var busy = false
    public private(set) var authorizing = false
    public var errorText: String?
    public var status = ""
    @ObservationIgnored private var attemptID: String?
    @ObservationIgnored private var operation: Task<Void, Never>?
    public init() {}

    public func load(app: AppModel) async {
        do { state = try await app.personalPlanRuntime().state() }
        catch { report(error, language: app.display.preferences.language) }
    }
    public func setEnabled(_ enabled: Bool, app: AppModel) async {
        await perform(app: app) {
            let runtime = try app.personalPlanRuntime()
            try await runtime.setEnabled(enabled)
            if enabled {
                var settings = await app.hostSettings()
                if !settings.providers.contains(where: { $0.kind == .chatGPTPlan }) {
                    settings.providers.append(.personalPlan); try await app.updateHostSettings(settings)
                }
            }
            self.models = []
            self.status = enabled ? "ChatGPTプラン接続を有効にしました。接続は認証ボタンから開始します。" : "ChatGPTプラン接続を無効にしました。"
        }
    }
    public func authorize(profileID: String? = nil, consent: Bool = false, app: AppModel,
                          openURL: @escaping @MainActor (URL) -> Void) async {
        guard !busy else { return }
        busy = true; authorizing = true; errorText = nil; status = "ブラウザで本人確認を完了してください。"
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let runtime = try app.personalPlanRuntime()
                let attempt = try await runtime.beginAuthorization(profileID: profileID, consent: consent)
                self.attemptID = attempt.id
                try Task.checkCancellation()
                openURL(attempt.authorizationURL)
                _ = try await runtime.finishAuthorization(attempt.id)
                try Task.checkCancellation()
                self.models = []
                self.status = "本人確認済みのChatGPTプランを接続しました。提供モデルを取得して描画モデルを選択してください。"
            } catch { if !Task.isCancelled { self.report(error, language: app.display.preferences.language) } }
            if let id = self.attemptID { try? await app.personalPlanRuntime().cancelAuthorization(id) }
            self.attemptID = nil
            await self.load(app: app)
        }
        operation = task; await task.value
        operation = nil; busy = false; authorizing = false
    }
    public func cancel(app: AppModel) async {
        operation?.cancel()
        if let id = attemptID { try? await app.personalPlanRuntime().cancelAuthorization(id) }
        if let operation { await operation.value }
    }
    public func selectProfile(_ id: String, app: AppModel) async {
        await perform(app: app) {
            try await app.personalPlanRuntime().selectProfile(id); self.models = []
            self.status = "次の描画で使う個人プロファイルを変更しました。実行中・待機中の要求は元の接続に固定されています。"
        }
    }
    public func signOut(_ id: String, app: AppModel) async {
        await perform(app: app) {
            let confirmed = try await app.personalPlanRuntime().signOut(id)
            self.models = []
            self.status = confirmed ? "ローカル接続を解除し、提供元での失効を確認しました。"
                : "ローカル接続を解除しました。提供元での失効は確認できていません。"
        }
    }
    public func retryQuota(_ id: String, app: AppModel) async {
        await perform(app: app) { try await app.personalPlanRuntime().retryQuota(id); self.status = "利用状況を確認した後の明示的な再試行を許可しました。" }
    }
    public func refreshModels(app: AppModel) async {
        await perform(app: app) {
            self.models = try await app.personalPlanRuntime().models(force: true)
            self.status = "この個人プロファイルに提供されたモデルを取得しました。"
        }
    }
    public func selectModel(_ id: String, app: AppModel) async {
        await perform(app: app) {
            let runtime = try app.personalPlanRuntime()
            let offered = try await runtime.models()
            guard offered.contains(where: { $0.id == id }) else { throw HostError("chatgpt_model_not_offered") }
            var settings = await app.hostSettings()
            if !settings.providers.contains(where: { $0.kind == .chatGPTPlan }) { settings.providers.append(.personalPlan) }
            settings.models.stage1Model = "chatgpt:" + id
            settings.models.stage2Model = "chatgpt:" + id
            try await app.updateHostSettings(settings)
            self.status = "描画モデルを選択しました。"
        }
    }
    private func perform(app: AppModel, operation: @escaping @MainActor () async throws -> Void) async {
        guard !busy else { return }; busy = true; errorText = nil
        do { try await operation() } catch { report(error, language: app.display.preferences.language) }
        await load(app: app); busy = false
    }
    /// Web ChatGPTSettings / model-administration word a failure with `chatgptStatus(code)`.
    private func report(_ error: Error, language: String) {
        errorText = ChatGPTStatusCopy.text(ChatGPTPlanRuntime.diagnostic(error).code, language: language)
    }
}
