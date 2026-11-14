import InkuHost
import SwiftUI

/// ChatGPTSettings.svelte: the tab connects the account only. Models are published in model settings.
public struct ChatGPTPlanSettingsView: View {
    @Bindable private var app: AppModel
    private let onOpenModelSettings: () -> Void
    @State private var controller = ChatGPTPlanSettingsModel()
    @State private var confirmingDelete: String?
    @State private var confirmingSignOut: String?
    @Environment(\.openURL) private var openURL
    @State private var login = InkuLoginPresenter()
    public init(model: AppModel, onOpenModelSettings: @escaping () -> Void) { app = model; self.onOpenModelSettings = onOpenModelSettings }
    private var language: String { app.display.preferences.language }
    /// Core `sign_in_connection_view` (ChatGPTSettings.svelte): which codes and actions the page shows.
    private var view: SignInConnectionView? { controller.view(canReopen: InkuLoginPresenter.canReopen) }

    public var body: some View {
        Group {
            Section(app.display.signInLabel()) {
                Text(app.display.localized("本人のChatGPTプランで描画できます。APIキー接続とは別に、使うアカウントを接続します。描画に使うモデルはモデル設定で選びます。保存作品はこのMacの同じライブラリに残ります。"))
                    .foregroundStyle(.secondary)
                Text(app.display.localized("記述の解釈・写生・自動配色選択・指示書の補完、Vision推敲と奥書で利用できます。デモ記述生成とモデル調査には対応していません。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                if let code = view?.status {
                    Text(ChatGPTStatusCopy.text(code, language: language)).textSelection(.enabled)
                }
                if let action = view?.action("sign_in") {
                    Button(app.display.localized("新しい個人プロファイルを接続")) { authorize(profileID: nil, consent: false) }
                        .disabled(!action.enabled)
                }
                if let action = view?.action("check_connection") {
                    Button(app.display.webCopy("chatgptCheckConnection", "接続状態を確認")) {
                        Task { await controller.checkConnection(app: app) }
                    }.disabled(!action.enabled)
                }
                if let url = view?.action("manage_usage")?.url {
                    Link(app.display.localized("ChatGPTの利用状況を確認"), destination: url)
                }
                if view?.action("reopen_sign_in") != nil {
                    Button(app.display.webCopy("chatgptReopenSignIn", "認証画面をもう一度開く")) { controller.reopen { openURL($0) } }
                }
                if let action = view?.action("cancel") {
                    Button(app.display.localized("認証を停止")) { Task { await controller.cancel(app: app) } }.disabled(!action.enabled)
                }
            }
            // The page's start and end go on this section only, which is always shown. On the group they were handed
            // to every section and row: the state loaded once per section, and on iOS, whose form lets rows scrolled
            // out of sight disappear, any of them could stop a sign-in (ios-app step 7d, the author's request).
            .task { await controller.load(app: app) }
            .onDisappear { Task { await controller.cancel(app: app) } }
            if let view, !view.pending.isEmpty || !view.profiles.isEmpty {
                Section(app.display.localized("保存された接続")) {
                    // The Web lists unfinished registrations before the registrations, with their client id.
                    ForEach(view.pending, id: \.id) { pending in
                        Button(app.display.localized("未完了の登録を再開") + (pending.clientID.map { "（\($0)）" } ?? "")) {
                            authorize(profileID: pending.id, consent: false)
                        }.disabled(pending.actions.first { $0.name == "reconnect" }?.enabled != true)
                    }
                    ForEach(view.profiles, id: \.id) { profile in profileRow(profile) }
                }
            }
            if view?.guide == true {
                Section {
                    Text(app.display.webCopy("chatgptModelSettingsGuide", "接続が完了しました。モデル一覧を取得します。モデル設定で用途と公開するモデルを選んで保存すると、描画やVisionに使えます。"))
                        .foregroundStyle(.secondary)
                    Button(app.display.webCopy("chatgptOpenModelSettings", "モデル設定を開く"), action: onOpenModelSettings)
                }
            }
            if controller.busy { ProgressView() }
        }
    }

    private func profileRow(_ profile: SignInConnectionView.Profile) -> some View {
        func enabled(_ name: String) -> Bool { profile.actions.first { $0.name == name }?.enabled == true }
        func offered(_ name: String) -> Bool { profile.actions.contains { $0.name == name } }
        return VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(profile.label).inkuFont(14, weight: .semibold)
                if profile.active { Text(app.display.localized("次の描画で使用")).inkuFont(12).foregroundStyle(.secondary) }
            }
            Text(ChatGPTStatusCopy.text(profile.status, language: language)).inkuFont(12).textSelection(.enabled)
            WrappingHStack(spacing: 6) {
                Button(app.display.localized("選択")) { Task { await controller.selectProfile(profile.id, app: app) } }
                    .disabled(!enabled("select"))
                Button(app.display.localized("再認証")) { authorize(profileID: profile.id, consent: false) }
                    .disabled(!enabled("reauthenticate"))
                if offered("grant_plan") {
                    Button(app.display.localized("同意を更新")) { authorize(profileID: profile.id, consent: true) }
                        .disabled(!enabled("grant_plan"))
                }
                if offered("retry") {
                    Button(app.display.localized("明示的に再試行")) { Task { await controller.retryQuota(profile.id, app: app) } }
                        .disabled(!enabled("retry"))
                }
                // core marks sign-out and deletion `confirm`: both ask first (the author, step 2).
                if confirmingSignOut != profile.id {
                    Button(app.display.localized("接続解除")) { confirmingDelete = nil; confirmingSignOut = profile.id }
                        .disabled(!enabled("sign_out"))
                }
                if confirmingDelete != profile.id {
                    Button(app.display.webCopy("chatgptDelete", "削除")) { confirmingSignOut = nil; confirmingDelete = profile.id }
                        .disabled(!enabled("delete"))
                }
            }
            if confirmingSignOut == profile.id {
                Text(app.display.localized("この登録の接続を解除します。もう一度使うには再認証が必要です。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                HStack {
                    Button(app.display.localized("接続を解除する"), role: .destructive) {
                        confirmingSignOut = nil
                        Task { await controller.signOut(profile.id, app: app) }
                    }.disabled(!enabled("sign_out"))
                    Button(app.display.webCopy("chatgptDeleteCancel", "やめる")) { confirmingSignOut = nil }
                }
            }
            if confirmingDelete == profile.id {
                Text(app.display.webCopy("chatgptDeleteConfirmText", "この登録と、公開モデルの設定を削除します。接続中なら先に接続を解除します。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                HStack {
                    Button(app.display.webCopy("chatgptDeleteConfirm", "削除する"), role: .destructive) {
                        confirmingDelete = nil
                        Task { await controller.deleteProfile(profile.id, app: app) }
                    }.disabled(!enabled("delete"))
                    Button(app.display.webCopy("chatgptDeleteCancel", "やめる")) { confirmingDelete = nil }
                }
            }
        }.padding(.vertical, 4)
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
