import SwiftUI

@MainActor struct AutomationView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    @State private var tab = "batch"
    @State private var replaceBatch = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Picker(model.display.localized("自動制作"), selection: $tab) { Text(model.display.localized("バッチ")).tag("batch"); Text(model.display.localized("デモ")).tag("demo") }
                .pickerStyle(.segmented).frame(width: 260).disabled(automation.running)
            if tab == "batch" { batch } else { demo }
            if automation.running {
                HStack {
                    ProgressView().controlSize(.small)
                    Text(model.display.message(automation.status))
                    Spacer()
                    Button(model.display.localized(automation.stopping ? "停止中" : "停止"), systemImage: "stop.fill") { Task { await automation.stop(app: model) } }
                        .disabled(automation.stopping)
                }
            } else { Text(model.display.message(automation.status)).font(.callout).foregroundStyle(.secondary) }
            if let error = automation.errorText { Text(error).foregroundStyle(.red).textSelection(.enabled) }
        }.padding(20)
        .confirmationDialog(model.display.localized("前回のバッチ記録を新しいバッチで置き換えます"), isPresented: $replaceBatch, titleVisibility: .visible) {
            Button(model.display.localized("新しいバッチを開始")) { Task { await automation.startBatch(app: model) } }
            Button(model.display.localized("キャンセル"), role: .cancel) {}
        } message: { Text(model.display.localized("保存済み作品は残ります。未処理の行を再開する場合は「前回のバッチを再開」を選んでください。")) }
    }
    private var batch: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.display.localized("1行に1つの記述またはDDLを入力")).font(.headline)
            Text(model.display.localized("制作画面の入力方式・配色・用紙・モデルで独立した作品を作ります。空行を除き、元の行番号を保持します。"))
                .font(.callout).foregroundStyle(.secondary)
            TextEditor(text: $automation.batchText).font(.system(.body, design: .monospaced))
                .frame(minHeight: 140, maxHeight: 220).border(.quaternary).disabled(automation.running)
            HStack {
                Button(model.display.localized("バッチを開始"), systemImage: "play.fill") {
                    if automation.canResume { replaceBatch = true } else { Task { await automation.startBatch(app: model) } }
                }.disabled(automation.running || model.isBusy || automation.batchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if automation.canResume {
                    Button(model.display.localized("前回のバッチを再開")) { Task { await automation.resumeBatch(app: model) } }
                        .disabled(automation.running || model.isBusy || automation.uncertainCount > 0)
                }
                Spacer()
                Text("\(automation.completedCount) / \(automation.rows.count)").monospacedDigit()
            }
            if !automation.rows.isEmpty {
                List(automation.rows) { row in
                    HStack(alignment: .top, spacing: 12) {
                        Text(model.display.localizedFormat("%ld行", row.line)).font(.caption.monospacedDigit()).frame(width: 45, alignment: .trailing)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(row.input).lineLimit(2)
                            if let error = row.error { Text(error).font(.caption).foregroundStyle(.secondary) }
                            if row.state == .uncertain {
                                HStack {
                                    Button(model.display.localized("履歴を確認")) { NotificationCenter.default.post(name: .inkuOpenSection, object: "library") }
                                    Button(model.display.localized("この行を再試行")) { Task { await automation.resolveUncertain(id: row.id, retry: true) } }
                                    Button(model.display.localized("この行を省略")) { Task { await automation.resolveUncertain(id: row.id, retry: false) } }
                                }.disabled(automation.running)
                            }
                        }
                        Spacer()
                        Text(model.display.localized(stateLabel(row.state))).font(.caption)
                        Text(model.display.localizedFormat("%ld回", row.attempts)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
    private var demo: some View {
        VStack(alignment: .leading, spacing: 14) {
            GroupBox(model.display.localized("デモの条件")) {
                VStack(alignment: .leading, spacing: 12) {
                    TextField(model.display.localized("次の記述を作るための種になる文章"), text: $automation.demoSeedPhrase, axis: .vertical).lineLimit(2...4)
                    TextField(model.display.localized("記述を作るモデル（空欄で制作モデル）"), text: $automation.demoModel)
                    Stepper(model.display.localizedFormat("生成後の間隔: %ld秒", automation.demoInterval), value: $automation.demoInterval, in: 1...3600)
                    Stepper(model.display.localizedFormat("実行時間: %ld秒", automation.demoDuration), value: $automation.demoDuration, in: 60...86400, step: 60)
                    Toggle(model.display.localized("生成作品をライブラリへ保存"), isOn: $automation.demoSaveWorks)
                    Text(model.display.localized("保存をオフにした作品はデモ表示用です。生成条件はデモ開始時に固定します。"))
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(6)
            }.disabled(automation.running || model.isBusy)
            Button(model.display.localized("デモを開始"), systemImage: "play.fill") { Task { await automation.startDemo(app: model) } }
                .disabled(automation.running || model.isBusy || !model.hasConfiguredProviders)
            if let work = automation.demoWork {
                ArtworkCanvas(svg: work.svg, renderer: model.renderer, caption: automation.demoPrompt)
                    .frame(minHeight: 320)
            } else {
                ContentUnavailableView(model.display.localized("デモの作品"), systemImage: "play.rectangle", description: Text(model.display.localized("種になる文章から記述を作り、共通コアで順に描画します。")))
            }
        }
    }
    private func stateLabel(_ state: BatchRow.State) -> String {
        switch state {
        case .waiting: "待機"; case .running: "生成中"; case .succeeded: "成功"
        case .failed: "失敗"; case .uncertain: "要確認"; case .skipped: "省略"
        }
    }
}
