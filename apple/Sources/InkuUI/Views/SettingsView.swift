import SwiftUI

@MainActor
struct SettingsView: View {
    @Bindable var model: AppModel
    @State private var confirmRestore = false

    var body: some View {
        Form {
            Section("生成モデル") {
                Picker("接続方式", selection: $model.providerKind) {
                    Text("OpenAI互換").tag("openai_compatible")
                    Text("MLX (mlx-vlm)").tag("mlx")
                    Text("Anthropic").tag("anthropic")
                    Text("Gemini").tag("gemini")
                }
                TextField("接続先URL", text: $model.providerURL)
                    .autocorrectionDisabled()
                TextField("モデル", text: $model.providerModel)
                    .autocorrectionDisabled()
                SecureField("APIキー", text: $model.providerKey)
                Button("接続設定を保存") { Task { await model.saveProvider() } }
                    .disabled(model.isBusy)
                Text("記述から作品を生成するときに、このモデルへ直接接続します。DDLからの生成にはモデル接続は不要です。")
                    .font(.callout).foregroundStyle(.secondary)
            }
            #if os(macOS)
            Section("保存データ") {
                Button("バックアップを保存…") {
                    guard let url = NativeFilePanels.backup() else { return }
                    Task { await model.backup(to: url) }
                }
                Button("バックアップから復元…") { confirmRestore = true }
                Text("バックアップには保存作品と作業状態を含みます。復元すると現在の保存データを置き換えます。")
                    .font(.callout).foregroundStyle(.secondary)
            }
            .disabled(model.isBusy)
            #endif
            Section("inku") {
                Text(model.versionSummary).textSelection(.enabled)
                Text("単一利用者のローカルアプリです。作品と設定をこの端末に保存します。")
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .confirmationDialog("現在の保存データを置き換えます", isPresented: $confirmRestore, titleVisibility: .visible) {
            #if os(macOS)
            Button("復元するバックアップを選択…", role: .destructive) {
                guard let url = NativeFilePanels.restore() else { return }
                Task { await model.restore(from: url) }
            }
            #endif
            Button("キャンセル", role: .cancel) {}
        } message: {
            Text("現在のデータを残す場合は、先にバックアップを保存してください。")
        }
    }
}
