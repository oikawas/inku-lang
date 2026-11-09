import InkuHost
import SwiftUI

/// ChatGPTSettings.svelte: the tab connects the account only. Models are published in model settings.
public struct ChatGPTPlanSettingsView: View {
    @Bindable private var app: AppModel
    private let onOpenModelSettings: () -> Void
    @State private var controller = ChatGPTPlanSettingsModel()
    @State private var confirmingDelete: String?
    @Environment(\.openURL) private var openURL
    @State private var login = InkuLoginPresenter()
    public init(model: AppModel, onOpenModelSettings: @escaping () -> Void) { app = model; self.onOpenModelSettings = onOpenModelSettings }
    public var body: some View {
        Group {
            Section(app.display.webCopy("chatgptPlanLabel", "ChatGPTプラン")) {
                Text(app.display.localized("本人のChatGPTプランで描画できます。APIキー接続とは別に、使うアカウントを接続します。描画に使うモデルはモデル設定で選びます。保存作品はこのMacの同じライブラリに残ります。"))
                    .foregroundStyle(.secondary)
                Toggle(app.display.localized("個人ChatGPTプラン接続を有効にする"), isOn: Binding(
                    get: { controller.state?.enabled ?? false },
                    set: { value in Task { await controller.setEnabled(value, app: app) } }))
                    .disabled(controller.busy)
                Text(app.display.localized("記述の解釈・写生・自動配色選択・指示書の補完、Vision推敲と奥書で利用できます。デモ記述生成とモデル調査には対応していません。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                if controller.state?.enabled == true {
                    Button(app.display.localized("新しい個人プロファイルを接続")) {
                        authorize(profileID: nil, consent: false)
                    }.disabled(controller.busy || (controller.state?.profiles.count ?? 0) >= 8)
                    if controller.authorizing {
                        Button(app.display.localized("認証を停止")) { Task { await controller.cancel(app: app) } }
                    }
                }
                Button(app.display.webCopy("chatgptCheckConnection", "接続状態を確認")) {
                    Task { await controller.checkConnection(app: app) }
                }.disabled(controller.busy)
            }
            // The page's start and end go on this section only, which is always shown. On the group they were handed
            // to every section and row: the state loaded once per section, and on iOS, whose form lets rows scrolled
            // out of sight disappear, any of them could stop a sign-in (ios-app step 7d, the author's request).
            .task { await controller.load(app: app) }
            .onDisappear { Task { await controller.cancel(app: app) } }
            if let state = controller.state {
                Section(app.display.localized("保存された接続")) {
                    ForEach(state.profiles) { profile in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(profile.label).inkuFont(14, weight: .semibold)
                                if state.activeProfileID == profile.id { Text(app.display.localized("次の描画で使用")).inkuFont(12).foregroundStyle(.secondary) }
                            }
                            Text(ChatGPTStatusCopy.text(profile.state == "connected" && !profile.scopes.contains("chatgpt.tokens.use.direct")
                                ? "chatgpt_scope_required" : "chatgpt_" + profile.state, language: app.display.preferences.language))
                                .inkuFont(12).textSelection(.enabled)
                            WrappingHStack(spacing: 6) {
                                Button(app.display.localized("選択")) { Task { await controller.selectProfile(profile.id, app: app) } }
                                Button(app.display.localized("再認証")) { authorize(profileID: profile.id, consent: false) }
                                if !profile.scopes.contains("chatgpt.tokens.use.direct") {
                                    Button(app.display.localized("同意を更新")) { authorize(profileID: profile.id, consent: true) }
                                }
                                Button(app.display.localized("接続解除")) { Task { await controller.signOut(profile.id, app: app) } }
                                if confirmingDelete != profile.id {
                                    Button(app.display.webCopy("chatgptDelete", "削除")) { confirmingDelete = profile.id }
                                }
                                if profile.state == "quota" {
                                    Button(app.display.localized("明示的に再試行")) { Task { await controller.retryQuota(profile.id, app: app) } }
                                }
                            }.disabled(controller.busy)
                            if confirmingDelete == profile.id {
                                Text(app.display.webCopy("chatgptDeleteConfirmText", "この登録と、公開モデルの設定を削除します。接続中なら先に接続を解除します。"))
                                    .inkuFont(12).foregroundStyle(.secondary)
                                HStack {
                                    Button(app.display.webCopy("chatgptDeleteConfirm", "削除する"), role: .destructive) {
                                        confirmingDelete = nil
                                        Task { await controller.deleteProfile(profile.id, app: app) }
                                    }.disabled(controller.busy)
                                    Button(app.display.webCopy("chatgptDeleteCancel", "やめる")) { confirmingDelete = nil }
                                }
                            }
                        }.padding(.vertical, 4)
                    }
                    ForEach(state.pendingRegistrations, id: \.self) { id in
                        Button(app.display.localized("未完了の登録を再開")) { Task { await controller.authorize(profileID: id, app: app) { openURL($0) } } }
                            .disabled(controller.busy)
                    }
                    Link(app.display.localized("ChatGPTの利用状況を確認"), destination: URL(string: "https://chatgpt.com/settings/usage")!)
                }
            }
            if controller.connected {
                Section {
                    Text(app.display.webCopy("chatgptModelSettingsGuide", "接続が完了しました。モデル設定で「ChatGPTプラン」のモデル一覧を取得し、公開するモデルを選んで保存してください。その後、描画モデルを選択できます。"))
                        .foregroundStyle(.secondary)
                    Button(app.display.webCopy("chatgptOpenModelSettings", "モデル設定を開く"), action: onOpenModelSettings)
                }
            }
            if controller.busy { ProgressView() }
            if !controller.status.isEmpty { Text(app.display.message(controller.status)).foregroundStyle(.secondary) }
            if let error = controller.errorText { Text(error).foregroundStyle(.red).textSelection(.enabled) }
        }
    }

    /// The Mac opens the sign-in in the browser; iOS in a login sheet over the app, closed when the callback arrives
    /// (closing it by hand stops the sign-in, as "認証を停止" does).
    private func authorize(profileID: String?, consent: Bool) {
        let fallback = openURL
        Task {
            await controller.authorize(profileID: profileID, consent: consent, app: app,
                openURL: { url in login.open(url, fallback: fallback) { Task { await controller.cancel(app: app) } } },
                closeLogin: { login.close() })
        }
    }
}
