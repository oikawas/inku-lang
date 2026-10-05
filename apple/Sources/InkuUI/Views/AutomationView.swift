import InkuHost
import SwiftUI

private enum DemoModelPicker: String, Identifiable {
    case prompt, stage1, stage2
    var id: String { rawValue }
    var title: String { self == .prompt ? "記述を作るモデル" : self == .stage1 ? "Stage 1" : "Stage 2" }
}

@MainActor struct AutomationView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    var demoOnly = false
    @State private var tab = "batch"
    @State private var modelPicker: DemoModelPicker?
    @State private var showCatalogs = false
    @State private var showPaper = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !demoOnly {
              Picker(model.display.localized("自動制作"), selection: $tab) { Text(model.display.localized("バッチ")).tag("batch"); Text(model.display.localized("デモ")).tag("demo") }
                .pickerStyle(.segmented).frame(width: 260).disabled(model.isBrowsingLocked)
            }
            if !demoOnly && tab == "batch" {
                BatchPanelView(model: model, automation: automation)
            } else {
                ScrollView { demo }
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
        .task(id: model.providerSettingsRevision) { await automation.refreshDemoModels(app: model) }
        .onChange(of: automation.isOccupied) { _, occupied in
            if !occupied { Task { await automation.refreshDemoModels(app: model) } }
        }
        .sheet(item: $modelPicker) { selection in
            BatchModelPickerView(model: model, initialReference: reference(selection), immediateSelection: true, title: selection.title) { value in
                switch selection {
                case .prompt: automation.demoModel = value
                case .stage1:
                    try await model.selectDemoDrawingModel(stage: 1, reference: value)
                    automation.demoStage1Model = value
                case .stage2:
                    try await model.selectDemoDrawingModel(stage: 2, reference: value)
                    automation.demoStage2Model = value
                }
            }
        }
        .sheet(isPresented: $showCatalogs) { ColorCatalogView(model: model, descriptionOnly: true) }
    }
    private var demo: some View {
        VStack(alignment: .leading, spacing: 14) {
            GroupBox(model.display.localized("デモの条件")) {
                VStack(alignment: .leading, spacing: 12) {
                    TextField(model.display.localized("次の記述を作るための種になる文章"), text: $automation.demoSeedPhrase, axis: .vertical).lineLimit(2...4)
                    modelButton(.prompt)
                    GroupBox(model.display.localized("次の生成条件")) {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack { modelButton(.stage1); modelButton(.stage2) }
                            Button { showCatalogs = true } label: {
                                Label(model.catalogMode == "auto" ? model.display.localized("記述から選択") : model.catalogs.first { $0.id == model.catalogID }?.name ?? model.catalogID, systemImage: "paintpalette")
                            }
                            HStack {
                                Picker(model.display.localized("写生"), selection: $automation.demoSketchMode) {
                                    Text(model.display.localized("なし")).tag("off")
                                    Text(model.display.localized("あり")).tag("on")
                                }.pickerStyle(.segmented).frame(maxWidth: 240)
                                    .help(model.display.preferences.showTooltips ? model.display.localized(automation.demoSketchMode == "on"
                                        ? "記述の横に、場所の広がりや季節・時刻の光を補って描く" : "写生を通さず、記述だけで描く") : "")
                                Button { showPaper = true } label: {
                                    Label(model.canvases.first { $0.id == model.canvasID }?.label ?? model.canvasID, systemImage: "rectangle.portrait")
                                }.popover(isPresented: $showPaper) {
                                    CreationPaperPicker(model: model) { showPaper = false }
                                }
                            }
                        }.padding(6)
                    }
                    Stepper(model.display.localizedFormat("描画間隔: %ld秒", automation.demoInterval), value: $automation.demoInterval, in: 1...999)
                    Stepper(model.display.localizedFormat("実行時間: %ld分", automation.demoDuration / 60), value: Binding(
                        get: { automation.demoDuration / 60 }, set: { automation.demoDuration = $0 * 60 }), in: 1...1440)
                    Toggle(model.display.localized("生成作品をライブラリへ保存"), isOn: $automation.demoSaveWorks)
                    Toggle(model.display.localized("生成作品をファイルへ保存"), isOn: $automation.demoSaveFiles)
                    if let directory = model.localDataDirectory() {
                        Text(directory.appendingPathComponent("demo-output").path).font(.caption).textSelection(.enabled)
                    }
                    Text(model.display.localized("保存をオフにした作品はデモ表示用です。生成条件はデモ開始時に固定します。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                .padding(6)
            }.disabled(automation.isOccupied || model.isBusy)
            Button(model.display.localized("デモを開始"), systemImage: "play.fill") { Task { await automation.startDemo(app: model) } }
                .disabled(!automation.canStartDemo(app: model))
            if automation.demoModel.isEmpty || automation.demoStage1Model.isEmpty || automation.demoStage2Model.isEmpty {
                Button(model.display.localized("使用中のLLMモデルを設定してください。"), systemImage: "gearshape") {
                    NotificationCenter.default.post(name: .inkuOpenSection, object: "settings", userInfo: ["settingsSection": "models"])
                }.font(.caption).disabled(model.isBrowsingLocked)
            }
            demoStatistics
            if let work = automation.demoWork {
                ArtworkCanvas(svg: work.svg, renderer: model.renderer, caption: work.effectiveSourceText)
                    .frame(minHeight: 320)
                HStack {
                    Text(model.display.localized(automation.demoCurrentSaved ? "保存済み" : "未保存")).font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button(model.display.localized(automation.savingDemo ? "保存中…" : "現在の作品を保存"), systemImage: "square.and.arrow.down") {
                        Task { await automation.saveDemoCurrent(app: model) }
                    }.disabled(!automation.canSaveDemoCurrent || model.isBusy || (automation.isOccupied && automation.mode == "batch"))
                }
                if !automation.demoSaveStatus.isEmpty { Text(model.display.message(automation.demoSaveStatus)).font(.caption) }
                GroupBox(model.display.localized("生成した記述")) {
                    Text(automation.demoPrompt).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox(model.display.localized("生成した指示書")) {
                    Text(work.ddl ?? model.display.localized("未記録")).font(.callout.monospaced()).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                ProviderObservationView(model: model, metrics: automation.demoCurrentMetrics,
                    workID: automation.demoCurrentSaved ? work.id : nil)
            } else {
                ContentUnavailableView(model.display.localized("デモの作品"), systemImage: "play.rectangle", description: Text(model.display.localized("種になる文章から記述を作り、共通コアで順に描画します。")))
            }
            if automation.running, !automation.demoGeneratingPrompt.isEmpty, automation.demoGeneratingPrompt != automation.demoPrompt {
                GroupBox(model.display.localized("描画中の記述")) {
                    Text(automation.demoGeneratingPrompt).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }

    private func reference(_ selection: DemoModelPicker) -> String {
        switch selection {
        case .prompt: automation.demoModel
        case .stage1: automation.demoStage1Model
        case .stage2: automation.demoStage2Model
        }
    }

    private func modelButton(_ selection: DemoModelPicker) -> some View {
        Button { modelPicker = selection } label: {
            VStack(alignment: .leading, spacing: 3) {
                Text(model.display.localized(selection.title)).font(.caption).foregroundStyle(.secondary)
                Text(reference(selection).isEmpty ? model.display.localized("選択してください") : reference(selection))
                    .font(.callout).lineLimit(2).truncationMode(.middle)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.buttonStyle(.bordered)
    }

    private var demoStatistics: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let end = automation.demoEndedAt ?? context.date
            let elapsed = max(0, Int(end.timeIntervalSince(automation.demoStartedAt ?? end)))
            let remaining = max(0, automation.demoDuration - elapsed)
            VStack(alignment: .leading, spacing: 5) {
                Text(model.display.localizedFormat("作品 %ld · 経過 %ld秒 · 残り %ld秒", automation.demoCount, elapsed, remaining)).monospacedDigit()
                if let wait = automation.demoWaitUntil {
                    Text(model.display.localizedFormat("次の生成まで %ld秒", max(0, Int(ceil(wait.timeIntervalSince(context.date)))))).monospacedDigit()
                }
                Text(model.display.localized("描画トークン（記録分）") + ": " + tokens(automation.demoCurrentMetrics)
                    + " · " + model.display.localized("合計") + ": " + tokens(automation.demoTotalMetrics))
                Text(model.display.localized("記述生成のトークン: 記録なし")).foregroundStyle(.secondary)
            }.font(.caption).textSelection(.enabled)
        }
    }

    private func tokens(_ metrics: [ProviderAttemptMetric]) -> String {
        let input = metrics.compactMap { $0.usage?.inputTokens }
        let output = metrics.compactMap { $0.usage?.outputTokens }
        func sum(_ values: [UInt64]) -> String {
            guard !values.isEmpty else { return model.display.localized("記録なし") }
            var total: UInt64 = 0
            for value in values {
                let next = total.addingReportingOverflow(value)
                guard !next.overflow else { return model.display.localized("記録なし") }
                total = next.partialValue
            }
            return String(total)
        }
        return sum(input) + " → " + sum(output)
    }
}
