import InkuHost
import SwiftUI

/// ChatGPTSettings.svelte: the tab connects the account only. Models are published in model settings.
public struct ChatGPTPlanSettingsView: View {
    @Bindable private var app: AppModel
    private let onOpenModelSettings: () -> Void
    @State private var controller = ChatGPTPlanSettingsModel()
    @State private var confirmingSignOut = false
    @Environment(\.openURL) private var openURL
    @State private var login = InkuLoginPresenter()
    public init(model: AppModel, onOpenModelSettings: @escaping () -> Void) { app = model; self.onOpenModelSettings = onOpenModelSettings }
    private var language: String { app.display.preferences.language }
    /// Core `sign_in_connection_view`: one connection, its state's one action, and signing out apart.
    private var view: SignInConnectionView? { controller.view(canReopen: InkuLoginPresenter.canReopen) }

    public var body: some View {
        Group {
            Section(app.display.signInLabel()) {
                Text(app.display.localized(InkuPlatform.chatGPTPlanIntro)).foregroundStyle(.secondary)
                Text(app.display.localized("記述の解釈・写生・自動配色選択・指示書の補完、Vision推敲と奥書で利用できます。デモ記述生成とモデル調査には対応していません。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                // The state every time from core's answer; nothing is carried over from an earlier action.
                if let view {
                    VStack(alignment: .leading, spacing: 3) {
                        if let label = view.label { Text(label).inkuFont(14, weight: .semibold) }
                        if let status = view.status { Text(ChatGPTStatusCopy.text(status, language: language)).textSelection(.enabled) }
                    }
                }
                if let primary = view?.primary {
                    Button(primaryTitle(primary.name)) { run(primary.name) }.disabled(!primary.enabled)
                }
                ForEach(view?.attemptActions ?? [], id: \.name) { action in
                    if action.name == "reopen_sign_in" {
                        Button(app.display.webCopy("chatgptReopenSignIn", "認証画面をもう一度開く")) { controller.reopen { openURL($0) } }
                    } else {
                        Button(app.display.localized("認証を停止")) { Task { await controller.cancel(app: app) } }.disabled(!action.enabled)
                    }
                }
                if let url = view?.manageUsage {
                    Link(app.display.webCopy("chatgptManageUsage", "利用枠を管理"), destination: url)
                }
            }
            // The page's start and end go on this section only, which is always shown. On the group they were handed
            // to every section and row: the state loaded once per section, and on iOS, whose form lets rows scrolled
            // out of sight disappear, any of them could stop a sign-in (ios-app step 7d, the author's request).
            .task { await controller.load(app: app) }
            .onDisappear { Task { await controller.cancel(app: app) } }
            if view?.guide == true {
                Section {
                    // The present state, not a past event (Web chatgptModelSettingsGuide, changed with it on 2026-11-14).
                    Text(app.display.localized("接続済みです。モデル設定で用途と公開するモデルを選んで保存すると、描画やVisionに使えます。"))
                        .foregroundStyle(.secondary)
                    Button(app.display.webCopy("chatgptOpenModelSettings", "モデル設定を開く"), action: onOpenModelSettings)
                }
            }
            // Signing out ends the connection; it stands apart from the state's action and asks first.
            if view?.signOut != nil || view?.notice != nil {
                Section {
                    if let signOut = view?.signOut {
                        if confirmingSignOut {
                            Text(app.display.localized("この接続を解除します。もう一度使うにはサインインが必要です。"))
                                .inkuFont(12).foregroundStyle(.secondary)
                            Button(app.display.webCopy("chatgptSignOut", "接続を解除"), role: .destructive) {
                                confirmingSignOut = false
                                Task { await controller.signOut(app: app) }
                            }.disabled(!signOut.enabled)
                            Button(app.display.webCopy("chatgptDeleteCancel", "やめる")) { confirmingSignOut = false }
                        } else {
                            Button(app.display.webCopy("chatgptSignOut", "接続を解除"), role: .destructive) { confirmingSignOut = true }
                                .disabled(!signOut.enabled)
                        }
                    }
                    if let notice = view?.notice {
                        Text(ChatGPTStatusCopy.text(notice, language: language)).inkuFont(12).foregroundStyle(.secondary)
                    }
                }
            }
            if controller.busy { ProgressView() }
        }
    }

    private func primaryTitle(_ name: String) -> String {
        switch name {
        case "grant_plan": app.display.webCopy("chatgptGrantPlan", "プラン利用を許可")
        case "retry": app.display.webCopy("chatgptRetry", "利用枠を確認して再試行")
        case "new_sign_in": app.display.localized("新しい登録でサインイン")
        default: app.display.webCopy("chatgptSignIn", "ChatGPTにサインイン")
        }
    }

    /// The state's one action: a sign-in (with consent, or replacing the registration for another account), or
    /// the retry after the usage limit.
    private func run(_ name: String) {
        switch name {
        case "retry": Task { await controller.retryQuota(app: app) }
        case "grant_plan": authorize(consent: true)
        case "new_sign_in": authorize(newRegistration: true)
        default: authorize()
        }
    }

    /// The Mac opens the sign-in in the browser; iOS in a login sheet over the app, closed when the callback arrives
    /// (closing it by hand stops the sign-in, as "認証を停止" does).
    private func authorize(consent: Bool = false, newRegistration: Bool = false) {
        let fallback = openURL
        Task {
            await controller.authorize(consent: consent, newRegistration: newRegistration, app: app,
                openURL: { url in login.open(url, fallback: fallback) { Task { await controller.cancel(app: app) } } },
                closeLogin: { login.close() })
        }
    }
}
