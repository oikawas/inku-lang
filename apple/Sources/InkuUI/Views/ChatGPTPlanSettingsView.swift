import InkuHost
import SwiftUI

public struct ChatGPTPlanSettingsView: View {
    @Bindable private var app: AppModel
    @State private var controller = ChatGPTPlanSettingsModel()
    @Environment(\.openURL) private var openURL
    public init(model: AppModel) { app = model }
    public var body: some View {
        Group {
            Section(app.display.localized("個人ChatGPTプラン")) {
                Text(app.display.localized("本人のChatGPTプランで描画できます。APIキー接続とは別に、使うアカウントと提供モデルを選びます。保存作品はこのMacの同じライブラリに残ります。"))
                    .foregroundStyle(.secondary)
                Toggle(app.display.localized("個人ChatGPTプラン接続を有効にする"), isOn: Binding(
                    get: { controller.state?.enabled ?? false },
                    set: { value in Task { await controller.setEnabled(value, app: app) } }))
                    .disabled(controller.busy)
                Text(app.display.localized("記述の解釈・写生・自動配色選択・指示書の補完で利用できます。Vision推敲、奥書、デモ記述生成、モデル調査には対応していません。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                if controller.state?.enabled == true {
                    Button(app.display.localized("新しい個人プロファイルを接続")) {
                        Task { await controller.authorize(app: app) { openURL($0) } }
                    }.disabled(controller.busy || (controller.state?.profiles.count ?? 0) >= 8)
                    if controller.authorizing {
                        Button(app.display.localized("認証を停止")) { Task { await controller.cancel(app: app) } }
                    }
                }
            }
            if let state = controller.state {
                Section(app.display.localized("保存された接続")) {
                    ForEach(state.profiles) { profile in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(profile.label).inkuFont(14, weight: .semibold)
                                if state.activeProfileID == profile.id { Text(app.display.localized("次の描画で使用")).inkuFont(12).foregroundStyle(.secondary) }
                            }
                            Text(app.display.localizedFormat("%@ · 接続世代 %ld", profile.state, profile.generation)).inkuFont(12).textSelection(.enabled)
                            HStack {
                                Button(app.display.localized("選択")) { Task { await controller.selectProfile(profile.id, app: app) } }
                                Button(app.display.localized("再認証")) { Task { await controller.authorize(profileID: profile.id, app: app) { openURL($0) } } }
                                Button(app.display.localized("同意を更新")) { Task { await controller.authorize(profileID: profile.id, consent: true, app: app) { openURL($0) } } }
                                Button(app.display.localized("接続解除")) { Task { await controller.signOut(profile.id, app: app) } }
                                if profile.state == "quota" {
                                    Button(app.display.localized("明示的に再試行")) { Task { await controller.retryQuota(profile.id, app: app) } }
                                }
                            }.disabled(controller.busy)
                        }.padding(.vertical, 4)
                    }
                    ForEach(state.pendingRegistrations, id: \.self) { id in
                        Button(app.display.localized("未完了の登録を再開")) { Task { await controller.authorize(profileID: id, app: app) { openURL($0) } } }
                            .disabled(controller.busy)
                    }
                    Link(app.display.localized("ChatGPTの利用状況を確認"), destination: URL(string: "https://chatgpt.com/settings/usage")!)
                }
            }
            if controller.state?.enabled == true {
                Section(app.display.localized("本人に提供された描画モデル")) {
                    Button(app.display.localized("モデル一覧を更新")) { Task { await controller.refreshModels(app: app) } }.disabled(controller.busy)
                    ForEach(controller.models) { model in
                        HStack {
                            VStack(alignment: .leading) { Text(model.label); Text(model.id).inkuFont(12).foregroundStyle(.secondary) }
                            Spacer()
                            Button(app.display.localized("描画に使用")) { Task { await controller.selectModel(model.id, app: app) } }
                        }.disabled(controller.busy)
                    }
                }
            }
            if controller.busy { ProgressView() }
            if !controller.status.isEmpty { Text(app.display.message(controller.status)).foregroundStyle(.secondary) }
            if let error = controller.errorText { Text(error).foregroundStyle(.red).textSelection(.enabled) }
        }
        .task { await controller.load(app: app) }
        .onDisappear { Task { await controller.cancel(app: app) } }
    }
}
