import SwiftUI

@MainActor struct AutomationView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    @State private var tab = "batch"

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker(model.display.localized("自動制作"), selection: $tab) { Text(model.display.localized("バッチ")).tag("batch"); Text(model.display.localized("デモ")).tag("demo") }
                .pickerStyle(.segmented).frame(width: 260).disabled(automation.isOccupied || model.isBusy)
            if tab == "batch" {
                BatchPanelView(model: model, automation: automation)
            } else {
                demo
                if automation.isOccupied {
                    HStack {
                        ProgressView().controlSize(.small)
                        Text(model.display.message(automation.preparing ? "生成の準備中" : automation.status))
                        Spacer()
                        if automation.running {
                            Button(model.display.localized(automation.stopping ? "停止中" : "停止"), systemImage: "stop.fill") { Task { await automation.stop(app: model) } }
                                .disabled(automation.stopping)
                        }
                    }
                } else { Text(model.display.message(automation.status)).font(.callout).foregroundStyle(.secondary) }
                if let error = automation.errorText { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
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
                }
                .padding(6)
            }.disabled(automation.isOccupied || model.isBusy)
            Button(model.display.localized("デモを開始"), systemImage: "play.fill") { Task { await automation.startDemo(app: model) } }
                .disabled(automation.isOccupied || model.isBusy || !model.hasConfiguredProviders)
            if let work = automation.demoWork {
                ArtworkCanvas(svg: work.svg, renderer: model.renderer, caption: automation.demoPrompt)
                    .frame(minHeight: 320)
            } else {
                ContentUnavailableView(model.display.localized("デモの作品"), systemImage: "play.rectangle", description: Text(model.display.localized("種になる文章から記述を作り、共通コアで順に描画します。")))
            }
        }
    }
}
